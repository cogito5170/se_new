"""Source registry and access-policy reviews.

A source's `policy_status` and an image's effective policy come only from
recorded reviews (`policy_reviews`). Setting `allowed` requires evidence -- a
licence identifier or an evidence URL (terms page, licence page, API policy).
robots.txt results are recorded separately and never change policy_status.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .models import DISCOVERY_METHODS, POLICY_STATUSES, SOURCE_ID_RE
from .timeutil import utcnow
from .urls import InvalidURL, host_of, normalize_url, same_site

HOST_RE = re.compile(r"^[a-z0-9.-]+$")
CATALOG_KEYS = ("items", "image_url", "page_url", "title", "alt", "caption", "description",
                "license", "type", "publisher", "width", "height", "creator",
                "publication_date", "creation_date", "upload_date", "year", "year_start",
                "year_end", "country", "region", "genres", "media_type", "rights_url")


class RegistryError(ValueError):
    pass


class NotFound(LookupError):
    pass


@dataclass
class Source:
    id: str
    name: str
    base_url: str
    discovery_method: str
    entry_urls: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    allowed_asset_hosts: list[str] = field(default_factory=list)
    catalog_mapping: dict | None = None
    max_pages: int | None = None
    policy_status: str = "unknown"
    license: str | None = None
    evidence_url: str | None = None
    terms_url: str | None = None
    policy_note: str | None = None
    policy_reviewed_at: str | None = None
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    last_run_at: str | None = None
    last_run_kind: str | None = None
    last_run_status: str | None = None
    last_error: str | None = None

    def asset_host_allowed(self, url: str) -> bool:
        host = host_of(url)
        return same_site(url, self.base_url) or host in self.allowed_asset_hosts

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _row_to_source(row: sqlite3.Row) -> Source:
    d = dict(row)
    for key in ("entry_urls", "include_patterns", "exclude_patterns", "allowed_asset_hosts"):
        d[key] = json.loads(d[key])
    d["catalog_mapping"] = json.loads(d["catalog_mapping"]) if d["catalog_mapping"] else None
    d["enabled"] = bool(d["enabled"])
    return Source(**d)


def validate_source(src: Source) -> Source:
    if not SOURCE_ID_RE.match(src.id or ""):
        raise RegistryError(f"invalid source id {src.id!r}: use lowercase letters, digits, '-' or '_'")
    if not src.name or not src.name.strip():
        raise RegistryError("source name is required")
    if src.discovery_method not in DISCOVERY_METHODS:
        raise RegistryError(f"discovery_method must be one of {DISCOVERY_METHODS}")
    if src.policy_status not in POLICY_STATUSES:
        raise RegistryError(f"policy_status must be one of {POLICY_STATUSES}")
    try:
        src.base_url = normalize_url(src.base_url)
        src.entry_urls = [normalize_url(u, src.base_url) for u in src.entry_urls]
    except InvalidURL as exc:
        raise RegistryError(f"invalid URL: {exc}") from exc
    for pattern in src.include_patterns + src.exclude_patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise RegistryError(f"invalid regex {pattern!r}: {exc}") from exc
    hosts = []
    for h in src.allowed_asset_hosts:
        h = h.strip().lower()
        if not HOST_RE.match(h):
            raise RegistryError(f"invalid asset host {h!r} (host names only, no scheme/path)")
        hosts.append(h)
    src.allowed_asset_hosts = hosts
    if src.discovery_method == "json_catalog":
        mapping = src.catalog_mapping or {}
        if "image_url" not in mapping:
            raise RegistryError("json_catalog sources need catalog_mapping.image_url")
        unknown = set(mapping) - set(CATALOG_KEYS)
        if unknown:
            raise RegistryError(f"unknown catalog_mapping keys: {sorted(unknown)}")
        if not src.entry_urls:
            raise RegistryError("json_catalog sources need at least one entry URL (the catalog)")
    if src.max_pages is not None and src.max_pages < 1:
        raise RegistryError("max_pages must be >= 1")
    if src.policy_status == "allowed" and not (src.license or src.evidence_url):
        raise RegistryError("policy 'allowed' requires --license or --evidence-url")
    return src


class Registry:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _unblock(self, *, source_id: str | None = None, image_id: str | None = None) -> None:
        """A policy/config change is the only thing that makes 'blocked' images eligible again."""
        col, val = ("source_id", source_id) if source_id else ("id", image_id)
        with self.conn:
            self.conn.execute(f"UPDATE image_refs SET download_status='pending', updated_at=? "
                              f"WHERE {col}=? AND download_status='blocked'", (utcnow(), val))

    # -- sources ---------------------------------------------------------------
    def add(self, src: Source, *, replace: bool = False) -> Source:
        src = validate_source(src)
        now = utcnow()
        exists = self.conn.execute("SELECT 1 FROM sources WHERE id = ?", (src.id,)).fetchone()
        if exists and not replace:
            raise RegistryError(f"source '{src.id}' already exists")
        values = (
            src.name, src.base_url, src.discovery_method, json.dumps(src.entry_urls),
            json.dumps(src.include_patterns), json.dumps(src.exclude_patterns),
            json.dumps(src.allowed_asset_hosts),
            json.dumps(src.catalog_mapping) if src.catalog_mapping else None,
            src.max_pages, int(src.enabled),
        )
        with self.conn:
            if exists:
                self.conn.execute(
                    """UPDATE sources SET name=?, base_url=?, discovery_method=?, entry_urls=?,
                       include_patterns=?, exclude_patterns=?, allowed_asset_hosts=?,
                       catalog_mapping=?, max_pages=?, enabled=?, updated_at=? WHERE id=?""",
                    values + (now, src.id))
            else:
                self.conn.execute(
                    """INSERT INTO sources (name, base_url, discovery_method, entry_urls,
                       include_patterns, exclude_patterns, allowed_asset_hosts, catalog_mapping,
                       max_pages, enabled, id, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    values + (src.id, now, now))
        if exists:
            self._unblock(source_id=src.id)          # asset hosts / filters may have changed
        if src.policy_status != "unknown" and (not exists or src.policy_status != self.get(src.id).policy_status):
            self.review_source(src.id, src.policy_status, license=src.license,
                               evidence_url=src.evidence_url, terms_url=src.terms_url,
                               note=src.policy_note or "set at registration")
        return self.get(src.id)

    def get(self, source_id: str) -> Source:
        row = self.conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise NotFound(f"source '{source_id}' not found")
        return _row_to_source(row)

    def list(self) -> list[Source]:
        rows = self.conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
        return [_row_to_source(r) for r in rows]

    def set_enabled(self, source_id: str, enabled: bool) -> Source:
        self.get(source_id)
        with self.conn:
            self.conn.execute("UPDATE sources SET enabled=?, updated_at=? WHERE id=?",
                              (int(enabled), utcnow(), source_id))
        if enabled:
            self._unblock(source_id=source_id)
        return self.get(source_id)

    def record_run(self, source_id: str, kind: str, status: str, error: str | None = None) -> None:
        now = utcnow()
        with self.conn:
            self.conn.execute(
                """UPDATE sources SET last_run_at=?, last_run_kind=?, last_run_status=?,
                   last_error=?, updated_at=? WHERE id=?""",
                (now, kind, status, error, now, source_id))

    def import_file(self, path: Path, *, replace: bool = False) -> list[Source]:
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"cannot read sources file {path}: {exc}") from exc
        items = doc.get("sources") if isinstance(doc, dict) else doc
        if not isinstance(items, list):
            raise RegistryError("sources file must be a list or {\"sources\": [...]}")
        allowed = set(Source.__dataclass_fields__) - {
            "created_at", "updated_at", "last_run_at", "last_run_kind", "last_run_status",
            "last_error", "policy_reviewed_at"}
        out = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise RegistryError(f"sources[{i}] must be an object")
            extra = set(item) - allowed - {"comment"}
            if extra:
                raise RegistryError(f"sources[{i}] has unknown fields {sorted(extra)}")
            item = {k: v for k, v in item.items() if k != "comment"}
            out.append(self.add(Source(**item), replace=replace))
        return out

    # -- policy ----------------------------------------------------------------
    def _check_review(self, status: str, license: str | None, evidence_url: str | None) -> None:
        if status not in POLICY_STATUSES:
            raise RegistryError(f"policy status must be one of {POLICY_STATUSES}")
        if status == "allowed" and not (license or evidence_url):
            raise RegistryError("'allowed' requires evidence: --license and/or --evidence-url")
        if evidence_url:
            try:
                normalize_url(evidence_url)
            except InvalidURL as exc:
                raise RegistryError(f"invalid evidence URL: {exc}") from exc

    def review_source(self, source_id: str, status: str, *, license: str | None = None,
                      evidence_url: str | None = None, terms_url: str | None = None,
                      robots_note: str | None = None, note: str | None = None,
                      reviewer: str | None = None) -> Source:
        self.get(source_id)
        self._check_review(status, license, evidence_url)
        now = utcnow()
        with self.conn:
            self.conn.execute(
                """INSERT INTO policy_reviews (target_kind, target_id, status, license, evidence_url,
                   robots_note, terms_note, note, reviewer, reviewed_at)
                   VALUES ('source',?,?,?,?,?,?,?,?,?)""",
                (source_id, status, license, evidence_url, robots_note, terms_url, note, reviewer, now))
            self.conn.execute(
                """UPDATE sources SET policy_status=?, license=?, evidence_url=?, terms_url=?,
                   policy_note=?, policy_reviewed_at=?, updated_at=? WHERE id=?""",
                (status, license, evidence_url, terms_url, note, now, now, source_id))
        self._unblock(source_id=source_id)
        return self.get(source_id)

    def review_image(self, image_id: str, status: str, *, license: str | None = None,
                     evidence_url: str | None = None, note: str | None = None,
                     reviewer: str | None = None) -> None:
        if self.conn.execute("SELECT 1 FROM image_refs WHERE id=?", (image_id,)).fetchone() is None:
            raise NotFound(f"image '{image_id}' not found")
        self._check_review(status, license, evidence_url)
        with self.conn:
            self.conn.execute(
                """INSERT INTO policy_reviews (target_kind, target_id, status, license, evidence_url,
                   note, reviewer, reviewed_at) VALUES ('image',?,?,?,?,?,?,?)""",
                (image_id, status, license, evidence_url, note, reviewer, utcnow()))
        self._unblock(image_id=image_id)

    def latest_review(self, kind: str, target_id: str) -> dict | None:
        row = self.conn.execute(
            """SELECT * FROM policy_reviews WHERE target_kind=? AND target_id=?
               ORDER BY id DESC LIMIT 1""", (kind, target_id)).fetchone()
        return dict(row) if row else None

    def effective_image_policy(self, image_id: str, source: Source) -> dict:
        """Image-level review wins; otherwise the source policy is inherited.

        A 'restricted' source can never be overridden to 'allowed' per image:
        the source-level restriction (e.g. terms forbidding download) applies to all.
        """
        review = self.latest_review("image", image_id)
        if source.policy_status == "restricted":
            return {"status": "restricted", "scope": "source", "license": source.license,
                    "evidence_url": source.evidence_url, "reviewed_at": source.policy_reviewed_at,
                    "note": source.policy_note}
        if review is not None:
            return {"status": review["status"], "scope": "image", "license": review["license"],
                    "evidence_url": review["evidence_url"], "reviewed_at": review["reviewed_at"],
                    "note": review["note"]}
        return {"status": source.policy_status, "scope": "source", "license": source.license,
                "evidence_url": source.evidence_url, "reviewed_at": source.policy_reviewed_at,
                "note": source.policy_note}

    def review_history(self, kind: str | None = None, target_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM policy_reviews WHERE 1=1", []
        if kind:
            sql += " AND target_kind=?"
            args.append(kind)
        if target_id:
            sql += " AND target_id=?"
            args.append(target_id)
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY id", args)]
