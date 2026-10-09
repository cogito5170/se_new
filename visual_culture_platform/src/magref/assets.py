"""Image references ("assets"): one row per normalized image URL.

Several assets may share one stored file (`image_files`, keyed by SHA-256):
the same bytes found at different URLs or from different sources keep their
own source, page, licence and policy records.

Dates: `publication_date`, `creation_date` and `upload_date` are separate and
never derived from each other. `year_start`/`year_end` describe the WORK and are
only set from explicit data (a declared year or a publication/creation date);
discovery time, crawl time and upload dates never produce a year.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

from .features import IMAGE_TYPES, classify_image_type
from .timeutil import normalize_date, utcnow
from .urls import reference_id

DOWNLOAD_STATUSES = ("pending", "downloaded", "failed_transient", "failed_permanent",
                     "blocked", "missing_file")
# Allowed transitions of image_refs.download_status. Anything else is a bug.
TRANSITIONS = {
    "pending": {"downloaded", "failed_transient", "failed_permanent", "blocked"},
    "failed_transient": {"downloaded", "failed_transient", "failed_permanent", "blocked", "pending"},
    "failed_permanent": {"pending"},                 # only by an explicit reset
    "blocked": {"pending", "blocked"},                # re-eligible only after a policy change
    "downloaded": {"missing_file", "downloaded"},
    "missing_file": {"downloaded", "failed_transient", "failed_permanent", "blocked", "pending"},
}
MEDIA_TYPES = ("photograph", "illustration", "painting", "graphic_design", "typography",
               "print_scan", "mixed", "unknown")
YEAR_RE = re.compile(r"^\s*(\d{4})\s*$")


class InvalidTransition(ValueError):
    pass


def image_id(normalized_url: str) -> str:
    return "mi_" + reference_id(normalized_url)[3:]


def _year_of(date: str | None) -> int | None:
    if date and re.match(r"^\d{4}", date):
        return int(date[:4])
    return None


@dataclass
class CandidateMeta:
    """Everything a discovery adapter may know about one image. All optional."""
    source_page_url: str | None = None
    reference_id: str | None = None
    publisher: str | None = None
    title: str | None = None
    alt: str | None = None
    caption: str | None = None
    description: str | None = None
    creator: str | None = None
    publication_date: str | None = None
    creation_date: str | None = None
    upload_date: str | None = None
    year_start: int | None = None
    year_end: int | None = None
    country: str | None = None
    region: str | None = None
    media_type: str | None = None
    declared_width: int | None = None
    declared_height: int | None = None
    declared_license: str | None = None
    declared_type: str | None = None
    page_type: str | None = None
    genres: list[str] | None = None


def resolve_years(meta: CandidateMeta) -> tuple[int | None, int | None, str | None, list[str]]:
    """Return (year_start, year_end, basis, warnings) from explicit data only."""
    warnings: list[str] = []
    if meta.year_start is not None or meta.year_end is not None:
        ys = meta.year_start if meta.year_start is not None else meta.year_end
        ye = meta.year_end if meta.year_end is not None else meta.year_start
        if ys is not None and ye is not None and ys > ye:
            warnings.append(f"year_start {ys} > year_end {ye}; years dropped")
            return None, None, None, warnings
        return ys, ye, "source_declared", warnings
    year = _year_of(meta.publication_date)
    if year is not None:
        return year, year, "publication", warnings
    year = _year_of(meta.creation_date)
    if year is not None:
        return year, year, "creation", warnings
    return None, None, None, warnings


class AssetRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- candidates --------------------------------------------------------------
    def upsert_candidate(self, source_id: str, url: str, method: str,
                         meta: CandidateMeta) -> tuple[str, bool]:
        """Insert a new candidate or fill in missing fields of an existing one.

        Existing non-null values are never overwritten (first evidence wins;
        conflicting later values are ignored, not merged).
        """
        aid = image_id(url)
        now = utcnow()
        for name in ("publication_date", "creation_date", "upload_date"):
            raw = getattr(meta, name)
            if raw is not None:
                setattr(meta, name, normalize_date(str(raw)))
        ys, ye, basis, _ = resolve_years(meta)
        media = meta.media_type if meta.media_type in MEDIA_TYPES else "unknown"
        itype, tstatus, tmethod, tbasis = classify_image_type(
            declared=meta.declared_type, alt=meta.alt, caption=meta.caption, title=meta.title,
            url=url, page_type=meta.page_type)
        row = self.conn.execute("SELECT * FROM image_refs WHERE id=?", (aid,)).fetchone()
        fields = {
            "source_page_url": meta.source_page_url, "reference_id": meta.reference_id,
            "publisher": meta.publisher, "title": meta.title, "alt": meta.alt,
            "caption": meta.caption, "description": meta.description, "creator": meta.creator,
            "publication_date": meta.publication_date, "creation_date": meta.creation_date,
            "upload_date": meta.upload_date, "year_start": ys, "year_end": ye,
            "year_basis": basis, "country": meta.country, "region": meta.region,
            "declared_width": meta.declared_width, "declared_height": meta.declared_height,
            "declared_license": meta.declared_license,
        }
        with self.conn:
            if row is None:
                cols = ["id", "url", "source_id", "discovery_method", "media_type", "image_type",
                        "type_status", "type_method", "type_basis", "discovered_at", "updated_at"]
                vals = [aid, url, source_id, method, media, itype, tstatus, tmethod, tbasis, now, now]
                for k, v in fields.items():
                    cols.append(k)
                    vals.append(v)
                self.conn.execute(
                    f"INSERT INTO image_refs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    vals)
                created = True
            else:
                updates = {k: v for k, v in fields.items() if v is not None and row[k] is None}
                if row["year_start"] is not None:          # keep the year triple consistent
                    for k in ("year_start", "year_end", "year_basis"):
                        updates.pop(k, None)
                if row["media_type"] == "unknown" and media != "unknown":
                    updates["media_type"] = media
                rank = {"unverified": 0, "inferred": 1, "observed": 2}
                if rank[tstatus] > rank[row["type_status"]]:
                    updates.update(image_type=itype, type_status=tstatus, type_method=tmethod,
                                   type_basis=tbasis)
                if updates:
                    updates["updated_at"] = now
                    sets = ", ".join(f"{k}=?" for k in updates)
                    self.conn.execute(f"UPDATE image_refs SET {sets} WHERE id=?",
                                      list(updates.values()) + [aid])
                created = False
        if meta.genres:
            from .research import GenreRepo   # local import: research depends on assets
            genres = GenreRepo(self.conn)
            for g in meta.genres:
                genres.link_asset(aid, genres.ensure(g), assigned_by="source_declared")
        return aid, created

    # -- reads -----------------------------------------------------------------------
    def get(self, asset_id: str) -> dict | None:
        row = self.conn.execute(
            """SELECT r.*, f.rel_path, f.abs_path, f.mime_type, f.size_bytes, f.width, f.height,
                      f.file_status, f.verified_at, f.ext
               FROM image_refs r LEFT JOIN image_files f ON f.sha256 = r.file_sha256
               WHERE r.id=?""", (asset_id,)).fetchone()
        return dict(row) if row else None

    def same_file(self, asset_id: str) -> list[str]:
        row = self.conn.execute("SELECT file_sha256 FROM image_refs WHERE id=?", (asset_id,)).fetchone()
        if not row or not row[0]:
            return []
        return [r[0] for r in self.conn.execute(
            "SELECT id FROM image_refs WHERE file_sha256=? AND id<>? ORDER BY id", (row[0], asset_id))]

    def query(self, *, source: str | None = None, status: str | None = None,
              image_type: str | None = None, year_from: int | None = None,
              year_to: int | None = None, country: str | None = None, region: str | None = None,
              genre_ids: list[int] | None = None, media_type: str | None = None,
              downloaded_only: bool = False, include_undated: bool = False,
              limit: int | None = None) -> list[dict]:
        sql = ["""SELECT r.*, f.rel_path, f.abs_path, f.mime_type, f.size_bytes, f.width, f.height,
                         f.file_status
                  FROM image_refs r LEFT JOIN image_files f ON f.sha256 = r.file_sha256 WHERE 1=1"""]
        args: list = []
        if source:
            sql.append("AND r.source_id=?")
            args.append(source)
        if status:
            sql.append("AND r.download_status=?")
            args.append(status)
        if image_type:
            sql.append("AND r.image_type=?")
            args.append(image_type)
        if media_type:
            sql.append("AND r.media_type=?")
            args.append(media_type)
        if country:
            sql.append("AND lower(r.country)=lower(?)")
            args.append(country)
        if region:
            sql.append("AND lower(r.region)=lower(?)")
            args.append(region)
        if year_from is not None or year_to is not None:
            # Overlap of [year_start, year_end] with the requested range. Undated assets are
            # excluded unless include_undated -- they are never placed in a period by guess.
            cond = "(r.year_start IS NOT NULL"
            if year_to is not None:
                cond += " AND r.year_start <= ?"
                args.append(year_to)
            if year_from is not None:
                cond += " AND r.year_end >= ?"
                args.append(year_from)
            cond += ")"
            if include_undated:
                cond = f"({cond} OR r.year_start IS NULL)"
            sql.append("AND " + cond)
        if genre_ids:
            sql.append(f"AND r.id IN (SELECT asset_id FROM asset_genres WHERE genre_id IN "
                       f"({', '.join('?' * len(genre_ids))}))")
            args.extend(genre_ids)
        if downloaded_only:
            sql.append("AND r.download_status='downloaded'")
        sql.append("ORDER BY r.year_start IS NULL, r.year_start, r.id")
        if limit:
            sql.append("LIMIT ?")
            args.append(limit)
        return [dict(r) for r in self.conn.execute(" ".join(sql), args)]

    # -- status -----------------------------------------------------------------------
    def set_status(self, asset_id: str, new: str, *, error: str | None = None,
                   error_class: str | None = None, attempted: bool = False,
                   final_url: str | None = None, sha256: str | None = None) -> None:
        row = self.conn.execute("SELECT download_status FROM image_refs WHERE id=?",
                                (asset_id,)).fetchone()
        if row is None:
            raise KeyError(asset_id)
        old = row[0]
        if new not in TRANSITIONS.get(old, set()):
            raise InvalidTransition(f"{asset_id}: {old} -> {new} is not allowed")
        sets = ["download_status=?", "updated_at=?", "last_error=?", "last_error_class=?"]
        args: list = [new, utcnow(), error, error_class]
        if attempted:
            sets += ["attempt_count=attempt_count+1", "last_attempt_at=?"]
            args.append(utcnow())
        if final_url is not None:
            sets.append("final_url=?")
            args.append(final_url)
        if sha256 is not None:
            sets.append("file_sha256=?")
            args.append(sha256)
        self.conn.execute(f"UPDATE image_refs SET {', '.join(sets)} WHERE id=?", args + [asset_id])

    def update_metadata(self, asset_id: str, **fields) -> dict:
        """Human edits (CLI/UI). Only listed fields; validates years and enums."""
        allowed = {"title", "description", "creator", "publication_date", "creation_date",
                   "upload_date", "year_start", "year_end", "year_basis", "country", "region",
                   "media_type", "image_type", "review_status"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"cannot edit fields {sorted(bad)}")
        current = self.get(asset_id)
        if current is None:
            raise KeyError(asset_id)
        updates = dict(fields)
        for d in ("publication_date", "creation_date", "upload_date"):
            if updates.get(d):
                norm = normalize_date(updates[d])
                if norm is None:
                    raise ValueError(f"{d}: not a date: {updates[d]!r}")
                updates[d] = norm
        ys = updates.get("year_start", current["year_start"])
        ye = updates.get("year_end", current["year_end"])
        if ys is not None and ye is not None and int(ys) > int(ye):
            raise ValueError("year_start must be <= year_end")
        if ("year_start" in updates or "year_end" in updates) and "year_basis" not in updates:
            updates["year_basis"] = "source_declared" if ys is not None else None
        if "media_type" in updates and updates["media_type"] not in MEDIA_TYPES:
            raise ValueError(f"media_type must be one of {MEDIA_TYPES}")
        if "image_type" in updates:
            if updates["image_type"] not in IMAGE_TYPES:
                raise ValueError(f"image_type must be one of {IMAGE_TYPES}")
            updates.update(type_status="observed", type_method="human_review",
                           type_basis="set by a reviewer")
        updates["updated_at"] = utcnow()
        with self.conn:
            sets = ", ".join(f"{k}=?" for k in updates)
            self.conn.execute(f"UPDATE image_refs SET {sets} WHERE id=?",
                              list(updates.values()) + [asset_id])
        return self.get(asset_id)

    def record_error(self, *, source_id: str | None, target_kind: str, target_id: str | None,
                     url: str | None, stage: str, code: str, message: str,
                     severity: str = "error", error_class: str | None = None) -> None:
        self.conn.execute(
            """INSERT INTO processing_errors (source_id, target_kind, target_id, url, stage, code,
               message, severity, error_class, occurred_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (source_id, target_kind, target_id, url, stage, code, message[:2000], severity,
             error_class, utcnow()))

    def attempts(self, asset_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM download_attempts WHERE image_ref_id=? ORDER BY id", (asset_id,))]

    def genres(self, asset_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            """SELECT g.id, g.name, g.parent_id, ag.assigned_by FROM asset_genres ag
               JOIN genres g ON g.id = ag.genre_id WHERE ag.asset_id=? ORDER BY g.name""",
            (asset_id,))]


def coerce_year(value) -> int | None:
    """Accept 1994 or "1994"; anything else (e.g. "c. 1990s", "") -> None (no guessing)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if 1000 <= value <= 2999 else None
    m = YEAR_RE.match(str(value))
    return int(m.group(1)) if m else None


def dumps(v) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)
