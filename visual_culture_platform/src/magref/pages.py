"""Page references: crawl discovered URLs, extract metadata, persist, deduplicate.

Identity of a page reference = its canonical URL when the page declares a
valid one, otherwise the final fetched URL (both normalized). The stable ID is
derived from that identity, so the same article reached through tracking
parameters, alternate paths or redirects collapses into one record. Pages
without a canonical link but with identical visible text (>= 200 chars) are
recorded as aliases of the first record instead of creating a duplicate.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import images as imglib
from .assets import AssetRepo, CandidateMeta
from .config import Settings
from .extract import PageExtract, extract
from .features import build_features
from .http import Fetcher, FetchError, Response
from .models import EXTRACTOR_VERSION
from .registry import Registry, Source
from .timeutil import utcnow
from .urls import redact_url, reference_id

log = logging.getLogger("magref.pages")
HTML_TYPES = ("text/html", "application/xhtml+xml")
MIN_TEXT_FOR_HASH_DEDUP = 200


@dataclass
class CrawlResult:
    source_id: str
    attempted: int = 0
    fetched: int = 0
    new_references: int = 0
    updated_references: int = 0
    duplicates: int = 0
    skipped: int = 0
    blocked: int = 0
    failed: int = 0
    images_found: int = 0
    errors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class _Fetched:
    url: str
    response: Response | None = None
    error: FetchError | None = None
    extract: PageExtract | None = None
    measured: dict = field(default_factory=dict)
    probe_errors: list[dict] = field(default_factory=list)


class PageRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, ref_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM refs WHERE id=?", (ref_id,)).fetchone()
        if row is None:
            row = self.conn.execute(
                "SELECT r.* FROM ref_urls u JOIN refs r ON r.id = u.reference_id WHERE u.url=?",
                (ref_id,)).fetchone()
        return _decode(row) if row else None

    def aliases(self, ref_id: str) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT url FROM ref_urls WHERE reference_id=? ORDER BY url", (ref_id,))]

    def all(self, **filters) -> list[dict]:
        sql, args = ["SELECT * FROM refs WHERE 1=1"], []
        for key in ("source_id", "publisher", "category", "page_type", "language", "crawl_status"):
            if filters.get(key):
                sql.append(f"AND lower({key}) = lower(?)")
                args.append(filters[key])
        sql.append("ORDER BY id")
        return [_decode(r) for r in self.conn.execute(" ".join(sql), args)]

    def _add_url(self, url: str | None, ref_id: str, kind: str) -> None:
        if url:
            self.conn.execute("INSERT OR IGNORE INTO ref_urls (url, reference_id, kind, added_at) "
                              "VALUES (?,?,?,?)", (url, ref_id, kind, utcnow()))

    def save(self, src: Source, discovered: dict, fetched: _Fetched, robots: str) -> tuple[str, str]:
        """Persist one extracted page. Returns (reference_id, 'new'|'updated'|'duplicate')."""
        ex = fetched.extract
        resp = fetched.response
        identity = ex.canonical_url or resp.url
        rid = reference_id(identity)
        content_hash = None
        if len(ex.text) >= MIN_TEXT_FOR_HASH_DEDUP:
            content_hash = hashlib.sha256(ex.text.encode("utf-8")).hexdigest()
        existing = self.conn.execute("SELECT id, first_seen_at FROM refs WHERE id=?", (rid,)).fetchone()
        if existing is not None and resp.url != identity:
            # An alternate URL (AMP, tracking variant, ...) of a page we already hold:
            # record the alias, never overwrite the canonical page's data with it.
            self._add_url(resp.url, rid, "alias")
            self._add_url(discovered["url"], rid, "alias")
            return rid, "duplicate"
        if existing is None and content_hash and not ex.canonical_url:
            twin = self.conn.execute("SELECT id FROM refs WHERE content_hash=? LIMIT 1",
                                     (content_hash,)).fetchone()
            if twin is not None:
                self._add_url(resp.url, twin[0], "alias")
                self._add_url(discovered["url"], twin[0], "alias")
                return twin[0], "duplicate"
        vf, analysis, analysis_status = build_features(ex, fetched.measured)
        now = utcnow()
        errors = [dict(e, at=now) for e in ex.errors + fetched.probe_errors]
        assets = [_asset_dict(i, fetched.measured.get(i.url)) for i in ex.images]
        search_text = " ".join(filter(None, [
            ex.title, ex.description, ex.category, ex.publisher, " ".join(ex.keywords),
            " ".join(i.alt or "" for i in ex.images), " ".join(i.caption or "" for i in ex.images),
            " ".join(c["claim"] for c in analysis["inferred"]),
        ]))
        record = {
            "source_id": src.id, "url": identity, "canonical_url": ex.canonical_url,
            "fetched_url": resp.url, "discovery_method": discovered["discovery_method"],
            "discovered_from": discovered.get("discovered_from"), "robots_status": robots,
            "title": ex.title, "description": ex.description, "publisher": ex.publisher,
            "category": ex.category, "published_at": ex.published_at, "modified_at": ex.modified_at,
            "language": ex.language, "page_type": ex.page_type, "access": ex.access,
            "authors": json.dumps(ex.authors), "keywords": json.dumps(ex.keywords),
            "assets": json.dumps(assets), "visual_features": json.dumps(vf),
            "analysis": json.dumps(analysis), "field_sources": json.dumps(ex.field_sources),
            "errors": json.dumps(errors), "search_text": search_text,
            "crawl_status": "fetched", "analysis_status": analysis_status,
            "http_status": resp.status, "content_hash": content_hash,
            "extractor_version": EXTRACTOR_VERSION, "last_crawled_at": now, "fetched_at": now,
            "updated_at": now,
        }
        if existing is None:
            record.update(id=rid, first_seen_at=now)
            cols = ", ".join(record)
            self.conn.execute(f"INSERT INTO refs ({cols}) VALUES ({', '.join('?' * len(record))})",
                              list(record.values()))
            state = "new"
        else:
            sets = ", ".join(f"{k}=?" for k in record)
            self.conn.execute(f"UPDATE refs SET {sets} WHERE id=?", list(record.values()) + [rid])
            state = "updated"
        self._add_url(identity, rid, "identity")
        self._add_url(resp.url, rid, "fetched")
        self._add_url(ex.canonical_url, rid, "canonical")
        self._add_url(discovered["url"], rid, "alias")
        for e in errors:
            AssetRepo(self.conn).record_error(source_id=src.id, target_kind="page", target_id=rid,
                                              url=resp.url, stage=e["stage"], code=e["code"],
                                              message=e["message"], severity=e["severity"])
        return rid, state


def _asset_dict(img, measured: dict | None) -> dict:
    width, height, source, downloaded = img.width, img.height, None, "none"
    if img.width and img.height:
        source = "metadata" if img.role in ("og_image", "jsonld_image", "twitter_image") else "html_attribute"
    if measured and measured.get("width"):
        width, height = measured["width"], measured["height"]
        source = measured["source"]
        downloaded = "full" if source == "image_decoded" else "partial"
    if not (width and height):
        width = height = source = None
    return {"url": img.url, "role": img.role, "alt": img.alt, "width": width, "height": height,
            "dimension_source": source, "downloaded": downloaded}


def _decode(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("authors", "keywords", "assets", "visual_features", "analysis", "field_sources",
                "errors"):
        d[key] = json.loads(d[key]) if d.get(key) else ([] if key in ("authors", "keywords",
                                                                     "assets", "errors") else {})
    return d


class Crawler:
    def __init__(self, conn: sqlite3.Connection, fetcher: Fetcher, settings: Settings):
        self.conn = conn
        self.fetcher = fetcher
        self.settings = settings
        self.pages = PageRepo(conn)
        self.assets = AssetRepo(conn)
        self.registry = Registry(conn)

    def _probe_images(self, src: Source, item: _Fetched) -> None:
        """Measure dimensions of up to N images from partial bytes (nothing written to disk)."""
        mode = self.settings.image_mode
        if mode == "off" or not item.extract.images or src.policy_status == "restricted":
            return
        colors_allowed = mode == "colors" and src.policy_status == "allowed"
        for img in item.extract.images[: self.settings.images_per_page]:
            limit = self.settings.image_max_bytes if colors_allowed else self.settings.image_header_bytes
            try:
                stream = self.fetcher.open(img.url, headers={"Range": f"bytes=0-{limit - 1}"})
                raw = stream.raw
                data = bytearray()
                try:
                    for chunk in raw.iter_chunks(16384):
                        data.extend(chunk)
                        if len(data) >= limit:
                            break
                finally:
                    raw.close()
            except Exception as exc:  # noqa: BLE001 -- a failed probe never fails the page
                item.probe_errors.append({"stage": "image", "code": getattr(exc, "code", "probe_failed"),
                                          "message": f"{redact_url(img.url)}: {exc}",
                                          "severity": "warning"})
                continue
            dims = imglib.dimensions(bytes(data[:65536]))
            if dims is None:
                item.probe_errors.append({"stage": "image", "code": "dimensions_unreadable",
                                          "message": f"{redact_url(img.url)}: no readable image header",
                                          "severity": "warning"})
                continue
            entry = {"width": dims.width, "height": dims.height, "source": "image_header"}
            if colors_allowed and img.role == "primary":
                try:
                    colors = imglib.dominant_colors(bytes(data))
                except Exception:  # noqa: BLE001 -- truncated/odd files: colours stay unverified
                    colors = None
                if colors:
                    entry.update(colors=colors, source="image_decoded")
            item.measured[img.url] = entry

    def _fetch_one(self, src: Source, url: str) -> _Fetched:
        item = _Fetched(url=url)
        try:
            item.response = self.fetcher.fetch(url)
        except FetchError as exc:
            item.error = exc
            return item
        if item.response.content_type in HTML_TYPES:
            item.extract = extract(item.response.text(), item.response.url)
            if not ({"noindex", "none"} & item.extract.robots_meta):
                self._probe_images(src, item)
        return item

    def run(self, src: Source, limit: int, retry_failed: bool = False) -> CrawlResult:
        res = CrawlResult(source_id=src.id)
        statuses = ("pending", "failed") if retry_failed else ("pending",)
        rows = self.conn.execute(
            f"""SELECT * FROM discovered_urls WHERE source_id=? AND crawl_status IN
                ({', '.join('?' * len(statuses))}) ORDER BY discovered_at, url LIMIT ?""",
            (src.id, *statuses, limit)).fetchall()
        discovered = [dict(r) for r in rows]
        workers = max(1, min(self.settings.max_concurrency, len(discovered) or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda d: self._fetch_one(src, d["url"]), discovered))
        for disc, item in zip(discovered, results):     # all DB writes on this thread
            res.attempted += 1
            self._persist(src, disc, item, res)
        self.conn.commit()
        return res

    def _set_discovered(self, url: str, status: str, error: str | None = None,
                        ref_id: str | None = None) -> None:
        self.conn.execute(
            """UPDATE discovered_urls SET crawl_status=?, attempts=attempts+1, last_error=?,
               reference_id=COALESCE(?, reference_id), updated_at=? WHERE url=?""",
            (status, error, ref_id, utcnow(), url))

    def _persist(self, src: Source, disc: dict, item: _Fetched, res: CrawlResult) -> None:
        url = disc["url"]
        if item.error is not None:
            exc = item.error
            status = "blocked" if exc.stage in ("robots", "policy") or exc.code in (
                "robots_disallowed",) else "failed"
            if exc.http_status in (401, 403):
                status = "blocked"
            self._set_discovered(url, status, f"{exc.code}: {exc}")
            self.assets.record_error(source_id=src.id, target_kind="page", target_id=None, url=url,
                                     stage=exc.stage, code=exc.code, message=str(exc),
                                     error_class=exc.error_class)
            res.errors.append({"url": redact_url(url), "code": exc.code, "message": str(exc)})
            if status == "blocked":
                res.blocked += 1
            else:
                res.failed += 1
            return
        resp = item.response
        res.fetched += 1
        if resp.content_type not in HTML_TYPES:
            self._set_discovered(url, "skipped", f"not_html: {resp.content_type}")
            res.skipped += 1
            return
        if {"noindex", "none"} & item.extract.robots_meta:
            self._set_discovered(url, "skipped", "noindex: page asks not to be indexed")
            res.skipped += 1
            return
        rid, state = self.pages.save(src, disc, item, resp.robots)
        self._set_discovered(url, "fetched", None, rid)
        if state == "new":
            res.new_references += 1
        elif state == "updated":
            res.updated_references += 1
        else:
            res.duplicates += 1
            return
        ex = item.extract
        for img in ex.images:
            res.images_found += 1
            self.assets.upsert_candidate(src.id, img.url, disc["discovery_method"], CandidateMeta(
                source_page_url=resp.url, reference_id=rid, publisher=ex.publisher,
                title=ex.title if img.role == "primary" else None, alt=img.alt,
                caption=img.caption, upload_date=ex.published_at,
                declared_width=img.width, declared_height=img.height, page_type=ex.page_type))
