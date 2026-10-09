"""URL and image-candidate discovery (separate from page crawling).

Adapters:
  sitemap       sitemap.xml / sitemap index (+ image:image entries), optionally .gz
  rss           RSS 2.0 / Atom (+ enclosure / media:content images)
  html          links on the source's entry pages (depth 1, same host, nofollow honoured)
  json_catalog  a JSON catalog/API response mapped with `catalog_mapping`

Discovery records page URLs in `discovered_urls` and image URLs as assets.
It never downloads images and never follows links recursively.
"""
from __future__ import annotations

import gzip
import json
import logging
import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .assets import AssetRepo, CandidateMeta, coerce_year
from .extract import extract
from .http import Fetcher, FetchError
from .registry import Source
from .timeutil import utcnow
from .urls import redact_url, same_site, try_normalize

log = logging.getLogger("magref.discovery")

SKIP_EXTENSIONS = re.compile(
    r"\.(jpe?g|png|gif|webp|svg|ico|css|js|json|xml|pdf|zip|gz|mp4|mp3|mov|woff2?|ttf)$", re.I)
MAX_SITEMAPS = 50
MAX_DECOMPRESSED = 50_000_000


class DiscoveryError(Exception):
    pass


@dataclass
class DiscoveryResult:
    source_id: str
    pages_found: int = 0
    pages_new: int = 0
    pages_duplicate: int = 0
    pages_filtered: int = 0
    images_found: int = 0
    images_new: int = 0
    errors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


# --------------------------------------------------------------------------- parsing helpers

def _safe_xml(body: bytes) -> ET.Element:
    if body[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=__import__("io").BytesIO(body)) as gz:
                body = gz.read(MAX_DECOMPRESSED + 1)
        except OSError as exc:
            raise DiscoveryError(f"invalid gzip: {exc}") from exc
        if len(body) > MAX_DECOMPRESSED:
            raise DiscoveryError("decompressed sitemap too large")
    head = body[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in head:
        raise DiscoveryError("XML with DOCTYPE/ENTITY declarations is refused")
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise DiscoveryError(f"malformed XML: {exc}") from exc


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _children(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if _local(c.tag) == name]


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def parse_sitemap(body: bytes) -> tuple[list[str], list[tuple[str, list[dict]]]]:
    """Return (child_sitemaps, [(page_url, [image dicts])])."""
    root = _safe_xml(body)
    kind = _local(root.tag)
    if kind == "sitemapindex":
        return [t for sm in _children(root, "sitemap") if (t := _text(next(iter(_children(sm, "loc")), None)))], []
    if kind != "urlset":
        raise DiscoveryError(f"not a sitemap (root element <{kind}>)")
    pages = []
    for u in _children(root, "url"):
        loc = _text(next(iter(_children(u, "loc")), None))
        if not loc:
            continue
        images = []
        for im in _children(u, "image"):
            iloc = _text(next(iter(_children(im, "loc")), None))
            if iloc:
                images.append({"url": iloc,
                               "title": _text(next(iter(_children(im, "title")), None)),
                               "caption": _text(next(iter(_children(im, "caption")), None)),
                               "license": _text(next(iter(_children(im, "license")), None))})
        pages.append((loc, images))
    return [], pages


def parse_feed(body: bytes) -> list[dict]:
    """RSS 2.0 or Atom -> [{link, title, published, images: [...]}]."""
    root = _safe_xml(body)
    items = []
    if _local(root.tag) == "rss":
        channel = next(iter(_children(root, "channel")), root)
        for item in _children(channel, "item"):
            images = []
            for el in item:
                name = _local(el.tag)
                if name == "enclosure" and el.get("type", "").startswith("image/") and el.get("url"):
                    images.append({"url": el.get("url")})
                elif name in ("content", "thumbnail") and el.get("url") and (
                        el.get("medium") == "image" or el.get("type", "").startswith("image/")
                        or name == "thumbnail"):
                    images.append({"url": el.get("url"), "width": el.get("width"),
                                   "height": el.get("height")})
            items.append({"link": _text(next(iter(_children(item, "link")), None)),
                          "title": _text(next(iter(_children(item, "title")), None)),
                          "published": _text(next(iter(_children(item, "pubdate")), None)),
                          "images": images})
    elif _local(root.tag) == "feed":
        for entry in _children(root, "entry"):
            link = None
            for l in _children(entry, "link"):
                if l.get("rel", "alternate") == "alternate" and l.get("href"):
                    link = l.get("href")
                    break
            items.append({"link": link,
                          "title": _text(next(iter(_children(entry, "title")), None)),
                          "published": _text(next(iter(_children(entry, "published")), None))
                          or _text(next(iter(_children(entry, "updated")), None)),
                          "images": []})
    else:
        raise DiscoveryError(f"not an RSS/Atom feed (root element <{_local(root.tag)}>)")
    return items


def dig(obj, path: str | None):
    """Follow a dotted path ('a.b.0.c') through dicts/lists; None if absent."""
    if not path:
        return None
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
        if cur is None:
            return None
    return cur


def _str(v) -> str | None:
    if v is None or isinstance(v, (dict, list)):
        return None
    s = str(v).strip()
    return s or None


def _int(v) -> int | None:
    try:
        n = int(str(v).strip())
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- discoverer

class Discoverer:
    def __init__(self, conn: sqlite3.Connection, fetcher: Fetcher, max_pages: int):
        self.conn = conn
        self.fetcher = fetcher
        self.assets = AssetRepo(conn)
        self.max_pages = max_pages

    def _passes_filters(self, src: Source, url: str) -> bool:
        if src.include_patterns and not any(re.search(p, url) for p in src.include_patterns):
            return False
        return not any(re.search(p, url) for p in src.exclude_patterns)

    def _error(self, res: DiscoveryResult, src: Source, url: str | None, exc: Exception,
               stage: str = "fetch") -> None:
        code = getattr(exc, "code", type(exc).__name__)
        cls = getattr(exc, "error_class", None)
        entry = {"url": redact_url(url) if url else None, "code": code, "message": str(exc)}
        res.errors.append(entry)
        self.assets.record_error(source_id=src.id, target_kind="discovery", target_id=None, url=url,
                                 stage=getattr(exc, "stage", stage), code=code, message=str(exc),
                                 error_class=cls)
        log.warning("discovery %s: %s %s", src.id, code, redact_url(url or ""))

    def _add_page(self, res: DiscoveryResult, src: Source, url: str, method: str,
                  discovered_from: str | None, hints: dict | None = None) -> None:
        norm = try_normalize(url, base=discovered_from)
        if norm is None or not same_site(norm, src.base_url):
            res.pages_filtered += 1
            return
        if not self._passes_filters(src, norm):
            res.pages_filtered += 1
            return
        if res.pages_found >= self.max_pages:
            return
        res.pages_found += 1
        now = utcnow()
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO discovered_urls (url, source_id, discovery_method, discovered_from,
               hints, discovered_at, updated_at) VALUES (?,?,?,?,?,?,?)""",
            (norm, src.id, method, discovered_from, json.dumps(hints or {}), now, now))
        if cur.rowcount:
            res.pages_new += 1
        else:
            res.pages_duplicate += 1

    def _add_image(self, res: DiscoveryResult, src: Source, url: str, method: str,
                   meta: CandidateMeta, base: str | None) -> None:
        norm = try_normalize(url, base=base)
        if norm is None:
            return
        res.images_found += 1
        _, created = self.assets.upsert_candidate(src.id, norm, method, meta)
        if created:
            res.images_new += 1

    def run(self, src: Source) -> DiscoveryResult:
        res = DiscoveryResult(source_id=src.id)
        handler = {"sitemap": self._sitemap, "rss": self._rss, "html": self._html,
                   "json_catalog": self._catalog}[src.discovery_method]
        handler(src, res)
        self.conn.commit()
        return res

    def _sitemap(self, src: Source, res: DiscoveryResult) -> None:
        queue = list(src.entry_urls) or self.fetcher.sitemaps_from_robots(src.base_url) \
            or [src.base_url.rstrip("/") + "/sitemap.xml"]
        seen: set[str] = set()
        while queue and len(seen) < MAX_SITEMAPS and res.pages_found < self.max_pages:
            sm_url = queue.pop(0)
            if sm_url in seen:
                continue
            seen.add(sm_url)
            try:
                resp = self.fetcher.fetch(sm_url)
                children, pages = parse_sitemap(resp.body)
            except (FetchError, DiscoveryError) as exc:
                self._error(res, src, sm_url, exc, stage="parse")
                continue
            for child in children:
                norm = try_normalize(child, base=sm_url)
                if norm and same_site(norm, src.base_url):
                    queue.append(norm)
            for loc, images in pages:
                self._add_page(res, src, loc, "sitemap", sm_url)
                for im in images:
                    self._add_image(res, src, im["url"], "sitemap",
                                    CandidateMeta(source_page_url=try_normalize(loc, base=sm_url),
                                                  title=im.get("title"), caption=im.get("caption"),
                                                  declared_license=im.get("license")), loc)

    def _rss(self, src: Source, res: DiscoveryResult) -> None:
        for feed_url in src.entry_urls or [src.base_url]:
            try:
                resp = self.fetcher.fetch(feed_url)
                items = parse_feed(resp.body)
            except (FetchError, DiscoveryError) as exc:
                self._error(res, src, feed_url, exc, stage="parse")
                continue
            for item in items:
                if not item.get("link"):
                    continue
                self._add_page(res, src, item["link"], "rss", feed_url,
                               {"title": item.get("title"), "published": item.get("published")})
                page = try_normalize(item["link"], base=feed_url)
                for im in item["images"]:
                    self._add_image(res, src, im["url"], "rss",
                                    CandidateMeta(source_page_url=page, title=item.get("title"),
                                                  declared_width=_int(im.get("width")),
                                                  declared_height=_int(im.get("height"))), feed_url)

    def _html(self, src: Source, res: DiscoveryResult) -> None:
        for entry in src.entry_urls or [src.base_url]:
            try:
                resp = self.fetcher.fetch(entry)
            except FetchError as exc:
                self._error(res, src, entry, exc)
                continue
            if resp.content_type not in ("text/html", "application/xhtml+xml"):
                self._error(res, src, entry, DiscoveryError(f"not HTML: {resp.content_type}"), "parse")
                continue
            page = extract(resp.text(), resp.url)
            if "nofollow" in page.robots_meta or "none" in page.robots_meta:
                res.errors.append({"url": entry, "code": "meta_nofollow",
                                   "message": "page asks not to follow links"})
                continue
            for link, rel in page.links:
                if "nofollow" in rel.split() or SKIP_EXTENSIONS.search(link.split("?")[0]):
                    res.pages_filtered += 1
                    continue
                if link.rstrip("/") == resp.url.rstrip("/"):
                    continue
                self._add_page(res, src, link, "html", resp.url)

    def _catalog(self, src: Source, res: DiscoveryResult) -> None:
        mapping = src.catalog_mapping or {}
        for cat_url in src.entry_urls:
            try:
                resp = self.fetcher.fetch(cat_url)
                doc = json.loads(resp.body.decode("utf-8"))
            except FetchError as exc:
                self._error(res, src, cat_url, exc)
                continue
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._error(res, src, cat_url, DiscoveryError(f"invalid catalog JSON: {exc}"), "parse")
                continue
            items = dig(doc, mapping.get("items")) if mapping.get("items") else doc
            if not isinstance(items, list):
                self._error(res, src, cat_url, DiscoveryError("catalog items path is not a list"), "parse")
                continue
            for i, item in enumerate(items[: self.max_pages]):
                image_url = _str(dig(item, mapping["image_url"]))
                if not image_url:
                    self.assets.record_error(source_id=src.id, target_kind="discovery",
                                             target_id=None, url=cat_url, stage="parse",
                                             code="catalog_item_without_image",
                                             message=f"item {i} has no image URL", severity="warning")
                    continue
                g = lambda key: dig(item, mapping.get(key)) if mapping.get(key) else None  # noqa: E731
                genres = g("genres")
                if isinstance(genres, str):
                    genres = [x.strip() for x in genres.split(",") if x.strip()]
                elif not isinstance(genres, list):
                    genres = None
                page = _str(g("page_url"))
                year = coerce_year(g("year"))
                meta = CandidateMeta(
                    source_page_url=try_normalize(page, base=cat_url) if page else None,
                    publisher=_str(g("publisher")), title=_str(g("title")), alt=_str(g("alt")),
                    caption=_str(g("caption")), description=_str(g("description")),
                    creator=_str(g("creator")), publication_date=_str(g("publication_date")),
                    creation_date=_str(g("creation_date")), upload_date=_str(g("upload_date")),
                    year_start=coerce_year(g("year_start")) or year,
                    year_end=coerce_year(g("year_end")) or year,
                    country=_str(g("country")), region=_str(g("region")),
                    media_type=_str(g("media_type")), declared_width=_int(g("width")),
                    declared_height=_int(g("height")), declared_license=_str(g("license")),
                    declared_type=_str(g("type")),
                    genres=[str(x) for x in genres if _str(x)] if genres else None)
                self._add_image(res, src, image_url, "json_catalog", meta, cat_url)
