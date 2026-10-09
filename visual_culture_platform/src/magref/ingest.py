"""Local HTML files as input -- the same pipeline as `crawl`, without fetching.

`magref ingest-html PATH... --source ID [--url URL] [--links] [--probe-images]`

For each file (or every *.html / *.htm in a directory):

1. Find the page's ORIGIN URL, in this order: `--url` (single file only), `<link rel=canonical>`,
   `og:url`, the browser's "saved from url=(N)https://..." comment, a SingleFile `url:` header.
   The origin must belong to the source's site -- the source carries the access policy.
2. With an origin: extract metadata exactly as a crawl would, build the 10 design features,
   store the page reference (dedup by canonical URL) and its images as candidates.
   Provenance says "local HTML file" and `fetched_url`/`http_status` stay null: nothing was fetched.
3. Without an origin (e.g. a report or list document): no page reference is created -- there is
   no URL to back it. Absolute images on the source's hosts still become candidates; with
   `--links`, same-site links become discovered URLs for a later `crawl`. Links and images on other
   hosts are counted per host so you can register (and review) those sources.

Nothing is fetched unless `--probe-images` is given. Files are parsed, never executed. Local image
copies saved next to a page (e.g. `page_files/x.jpg`) are not imported: their original URL is lost.
Only the file NAME (never the directory) is recorded, so local paths do not end up in exports.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .assets import AssetRepo, CandidateMeta
from .config import Settings
from .extract import extract
from .http import Fetcher, Response
from .pages import Crawler, PageRepo, _Fetched
from .registry import Source
from .timeutil import utcnow
from .urls import host_of, same_site, try_normalize

PLACEHOLDER = "https://local-file.invalid/"          # reserved TLD: never resolvable
SAVED_FROM = re.compile(r"<!--\s*saved from url=\(\d+\)(https?://[^\s>]+?)\s*-->", re.I)
SINGLEFILE = re.compile(r"<!--.{0,400}?\burl:\s*(https?://\S+)", re.I | re.S)
META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-]+)""", re.I)
SKIP_LINK = re.compile(r"\.(jpe?g|png|gif|webp|svg|ico|css|js|json|xml|pdf|zip|gz|mp4|mp3|mov|woff2?|ttf)$", re.I)


class IngestError(ValueError):
    pass


@dataclass
class IngestResult:
    source_id: str
    files: int = 0
    pages_new: int = 0
    pages_updated: int = 0
    pages_duplicate: int = 0
    without_origin: int = 0
    images_found: int = 0
    images_new: int = 0
    links_added: int = 0
    other_hosts: dict = field(default_factory=dict)      # host -> count of links/images skipped
    skipped_local_images: int = 0
    failed: int = 0
    items: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def collect_paths(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            out += sorted(x for x in p.rglob("*") if x.suffix.lower() in (".html", ".htm") and x.is_file())
        else:
            out.append(p)
    return out


def read_html(path: Path, max_bytes: int) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise IngestError(f"cannot read file: {exc.strerror}") from exc
    if size > max_bytes:
        raise IngestError(f"file is {size} bytes, above MAGREF_MAX_PAGE_BYTES={max_bytes}")
    data = path.read_bytes()
    if b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise IngestError("not a text/HTML file")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    m = META_CHARSET.search(data[:4096])
    for enc in ([m.group(1).decode("ascii", "ignore")] if m else []) + ["utf-8"]:
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("cp949" if re.search(rb"[\xb0-\xc8][\xa1-\xfe]", data) else "latin-1", errors="replace")


def find_origin(html: str, explicit: str | None) -> tuple[str | None, str | None]:
    """Return (normalized origin URL, how it was found) without trusting relative URLs."""
    if explicit:
        url = try_normalize(explicit)
        if url is None:
            raise IngestError(f"--url is not an http(s) URL: {explicit!r}")
        return url, "--url"
    probe = extract(html, PLACEHOLDER)
    for value, how in ((probe.canonical_url, probe.field_sources.get("canonical_url")),):
        if value and host_of(value) != host_of(PLACEHOLDER):
            return value, how
    for rx, how in ((SAVED_FROM, "saved-from comment"), (SINGLEFILE, "SingleFile header")):
        m = rx.search(html[:20000])
        if m and (url := try_normalize(m.group(1))):
            return url, how
    return None, None


class Ingester:
    def __init__(self, conn: sqlite3.Connection, settings: Settings, fetcher: Fetcher | None = None):
        self.conn = conn
        self.settings = settings
        self.fetcher = fetcher
        self.pages = PageRepo(conn)
        self.assets = AssetRepo(conn)

    def run(self, src: Source, paths: list[str], *, url: str | None = None, links: bool = False,
            probe: bool = False) -> IngestResult:
        files = collect_paths(paths)
        if url and len(files) != 1:
            raise IngestError("--url can only be used with exactly one file")
        if not files:
            raise IngestError("no HTML files found")
        res = IngestResult(source_id=src.id)
        other: Counter = Counter()
        for path in files:
            res.files += 1
            try:
                item = self._one(src, path, url, links, probe, res, other)
            except IngestError as exc:
                res.failed += 1
                item = {"file": path.name, "status": "failed", "reason": str(exc)}
                self.assets.record_error(source_id=src.id, target_kind="page", target_id=None, url=None,
                                         stage="parse", code="ingest_failed",
                                         message=f"{path.name}: {exc}")
            res.items.append(item)
        res.other_hosts = dict(other.most_common())
        self.conn.commit()
        return res

    def _one(self, src, path, url, links, probe, res, other) -> dict:
        html = read_html(path, self.settings.max_page_bytes)
        origin, how = find_origin(html, url)
        if origin is not None and not same_site(origin, src.base_url):
            raise IngestError(f"page origin {origin} ({how}) is not on source '{src.id}' "
                              f"({src.base_url}); register/choose the matching source")
        ex = extract(html, origin or PLACEHOLDER)
        label = f"local HTML file {path.name}"
        item = {"file": path.name, "origin": origin, "origin_from": how}
        # Which image URLs were written as absolute URLs in the file? Relative ones in a SAVED
        # copy (saved-from / SingleFile, or a "<name>_files/" folder) point at local copies whose
        # original URL is lost -- resolving them against the origin would invent URLs.
        absolute = {i.url for i in extract(html, PLACEHOLDER).images if host_of(i.url) != host_of(PLACEHOLDER)}
        saved_copy = how in ("saved-from comment", "SingleFile header")

        def local_copy(url: str) -> bool:
            if host_of(url) == host_of(PLACEHOLDER):
                return True
            if url in absolute:
                return False
            return saved_copy or "_files/" in url.lower()
        kept = [i for i in ex.images if not local_copy(i.url)]
        res.skipped_local_images += len(ex.images) - len(kept)
        ex.images = kept
        rid = None
        if origin is not None:
            fetched = _Fetched(url=origin, extract=ex,
                               response=Response(200, {"content-type": "text/html"}, b"", origin, origin))
            if probe and self.fetcher is not None:
                Crawler(self.conn, self.fetcher, self.settings)._probe_images(src, fetched)
            discovered = {"url": origin, "discovery_method": "import", "discovered_from": label}
            rid, state = self.pages.save(src, discovered, fetched, "not_checked")
            # Nothing was fetched over HTTP: say so instead of pretending.
            fs = self.conn.execute("SELECT field_sources FROM refs WHERE id=?", (rid,)).fetchone()[0]
            sources = json.loads(fs)
            sources["_input"] = f"{label} (origin from {how}; not fetched, robots not checked)"
            self.conn.execute("UPDATE refs SET fetched_url=NULL, http_status=NULL, field_sources=? "
                              "WHERE id=? AND discovery_method='import'", (json.dumps(sources), rid))
            key = {"new": "pages_new", "updated": "pages_updated", "duplicate": "pages_duplicate"}[state]
            setattr(res, key, getattr(res, key) + 1)
            item.update(status=state, reference_id=rid)
        else:
            res.without_origin += 1
            item.update(status="no_origin",
                        reason="no canonical/og:url/saved-from URL: no page reference created")
        for img in ex.images:
            if origin is None and not src.asset_host_allowed(img.url):
                other[host_of(img.url)] += 1
                continue
            res.images_found += 1
            _, created = self.assets.upsert_candidate(src.id, img.url, "import", CandidateMeta(
                source_page_url=origin, reference_id=rid, publisher=ex.publisher,
                title=ex.title if img.role == "primary" and origin else None, alt=img.alt,
                caption=img.caption, upload_date=ex.published_at if origin else None,
                declared_width=img.width, declared_height=img.height, page_type=ex.page_type))
            res.images_new += created
        if links:
            now = utcnow()
            for link, rel in ex.links:
                if host_of(link) == host_of(PLACEHOLDER) or "nofollow" in rel.split() \
                        or SKIP_LINK.search(link.split("?")[0]) or link == origin:
                    continue
                if not same_site(link, src.base_url):
                    other[host_of(link)] += 1
                    continue
                if src.include_patterns and not any(re.search(p, link) for p in src.include_patterns):
                    continue
                if any(re.search(p, link) for p in src.exclude_patterns):
                    continue
                cur = self.conn.execute(
                    """INSERT OR IGNORE INTO discovered_urls (url, source_id, discovery_method,
                       discovered_from, hints, discovered_at, updated_at) VALUES (?,?,?,?,?,?,?)""",
                    (link, src.id, "html", origin or label, "{}", now, now))
                res.links_added += cur.rowcount
        return item
