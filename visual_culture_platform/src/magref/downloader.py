"""Policy-gated, streaming, verified image downloads.

Per asset:
  1. policy gate: source enabled, source not restricted, effective policy 'allowed',
     URL host = source site or one of its allowed_asset_hosts (checked again on
     every redirect hop, together with SSRF checks and robots.txt)
  2. stream to <data>/tmp/*.part with size cap, SHA-256 computed while writing
  3. validate: non-empty, Content-Length matches, magic bytes are a supported
     image, declared image MIME agrees with the bytes, Pillow can parse it (if installed)
  4. same SHA-256 already stored -> link this asset to the existing file
     (bytes stored once, every URL/source keeps its own record)
  5. otherwise write a journal entry, atomically move into place, commit the DB
     row, delete the journal. A crash between move and commit is recovered by
     `magref repair` from the journal.
Temp files are removed on every failure path.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import images as imglib
from .assets import AssetRepo
from .config import Settings
from .http import Fetcher, FetchError, PolicyBlocked, TransportError
from .registry import Registry, Source
from .storage import Layout, StorageError, slugify
from .timeutil import utcnow
from .urls import redact_url

log = logging.getLogger("magref.download")


class DownloadFailure(Exception):
    def __init__(self, code: str, message: str, error_class: str = "permanent",
                 http_status: int | None = None, outcome: str = "failed",
                 final_url: str | None = None, received: int = 0, already_retried: bool = False):
        super().__init__(message)
        self.already_retried = already_retried   # the Fetcher already spent its retries
        self.code = code
        self.error_class = error_class
        self.http_status = http_status
        self.outcome = outcome
        self.final_url = final_url
        self.received = received


class BudgetExceeded(Exception):
    pass


@dataclass
class Transfer:
    temp: Path
    sha256: str
    size: int
    mime: str
    ext: str
    width: int | None
    height: int | None
    final_url: str
    http_status: int


@dataclass
class JobResult:
    job_id: int
    kind: str
    selected: int = 0
    downloaded: int = 0
    duplicates: int = 0
    failed_transient: int = 0
    failed_permanent: int = 0
    blocked: int = 0
    skipped_not_allowed: int = 0
    bytes_received: int = 0
    stopped_by_budget: bool = False
    status: str = "running"
    items: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


class Downloader:
    def __init__(self, conn: sqlite3.Connection, fetcher: Fetcher, settings: Settings,
                 layout: Layout, sleep=time.sleep):
        self.conn = conn
        self.fetcher = fetcher
        self.settings = settings
        self.layout = layout
        self.sleep = sleep
        self.assets = AssetRepo(conn)
        self.registry = Registry(conn)
        self.before_db_commit = None       # test hook: called after the file is in place

    # -- selection -------------------------------------------------------------
    def eligible(self, statuses: tuple[str, ...], source: str | None = None,
                 ids: list[str] | None = None) -> tuple[list[dict], int]:
        """Assets in `statuses` whose effective policy is 'allowed'. Returns (rows, not_allowed)."""
        sql = f"SELECT * FROM image_refs WHERE download_status IN ({', '.join('?' * len(statuses))})"
        args: list = list(statuses)
        if source:
            sql += " AND source_id=?"
            args.append(source)
        if ids:
            sql += f" AND id IN ({', '.join('?' * len(ids))})"
            args.extend(ids)
        sql += " ORDER BY discovered_at, id"
        rows, not_allowed = [], 0
        sources: dict[str, Source] = {}
        for row in self.conn.execute(sql, args).fetchall():
            src = sources.get(row["source_id"]) or self.registry.get(row["source_id"])
            sources[src.id] = src
            policy = self.registry.effective_image_policy(row["id"], src)
            if src.enabled and policy["status"] == "allowed":
                rows.append(dict(row))
            else:
                not_allowed += 1
        return rows, not_allowed

    # -- job -------------------------------------------------------------------
    def run(self, kind: str, *, limit: int | None = None, max_total_bytes: int | None = None,
            source: str | None = None, ids: list[str] | None = None,
            include_missing: bool = False) -> JobResult:
        limit = limit or self.settings.max_downloads_per_run
        budget = max_total_bytes or self.settings.max_total_bytes_per_run
        if kind == "download":
            # 'blocked' items return to 'pending' only through a policy/config change
            # (Registry._unblock) or `magref reset`; they are not re-tried every run.
            statuses = ("pending",)
        else:
            statuses = ("failed_transient", "missing_file") if include_missing else ("failed_transient",)
        rows, not_allowed = self.eligible(statuses, source, ids)
        params = {"limit": limit, "max_total_bytes": budget, "source": source, "ids": ids,
                  "include_missing": include_missing}
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO download_jobs (kind, started_at, params) VALUES (?,?,?)",
                (kind, utcnow(), json.dumps(params)))
        res = JobResult(job_id=cur.lastrowid, kind=kind, skipped_not_allowed=not_allowed)
        for row in rows[:limit]:
            res.selected += 1
            remaining = budget - res.bytes_received
            try:
                outcome = self.download_one(row, res.job_id, remaining)
            except BudgetExceeded:
                res.stopped_by_budget = True
                res.items.append({"id": row["id"], "outcome": "not_started_budget"})
                break
            res.items.append(outcome)
            res.bytes_received += outcome.get("bytes", 0)
            key = {"downloaded": "downloaded", "duplicate": "duplicates", "blocked": "blocked"}.get(
                outcome["outcome"])
            if key:
                setattr(res, key, getattr(res, key) + 1)
            elif outcome.get("error_class") == "transient":
                res.failed_transient += 1
            else:
                res.failed_permanent += 1
        if res.stopped_by_budget:
            res.status = "stopped_budget"
        elif res.failed_transient or res.failed_permanent or res.blocked:
            res.status = "completed_with_errors"
        else:
            res.status = "completed"
        stats = {k: v for k, v in res.as_dict().items() if k != "items"}
        with self.conn:
            self.conn.execute("UPDATE download_jobs SET finished_at=?, status=?, stats=? WHERE id=?",
                              (utcnow(), res.status, json.dumps(stats), res.job_id))
        return res

    # -- one asset ---------------------------------------------------------------
    def download_one(self, row: dict, job_id: int | None, budget: int) -> dict:
        src = self.registry.get(row["source_id"])
        url = row["url"]
        policy = self.registry.effective_image_policy(row["id"], src)
        gate = None
        if not src.enabled:
            gate = ("source_disabled", f"source '{src.id}' is disabled")
        elif policy["status"] != "allowed":
            gate = (f"policy_{policy['status']}",
                    f"effective policy is '{policy['status']}' ({policy['scope']}); only 'allowed' downloads")
        elif not src.asset_host_allowed(url):
            gate = ("host_not_allowed", "image host is neither the source site nor an allowed asset host")
        if gate:
            fail = DownloadFailure(gate[0], gate[1], outcome="blocked")
            return self._record_failure(row, src, job_id, fail, utcnow())

        def hop_check(hop_url: str) -> None:
            if not src.asset_host_allowed(hop_url):
                raise PolicyBlocked("redirect_host_not_allowed",
                                    f"redirect to a host not allowed for this source: {redact_url(hop_url)}",
                                    url=hop_url)

        attempt = 0
        while True:
            attempt += 1
            started = utcnow()
            try:
                transfer = self._transfer(url, hop_check, budget)
            except DownloadFailure as fail:
                if (fail.error_class == "transient" and not fail.already_retried
                        and attempt <= self.settings.max_retries):
                    self._record_attempt(row, job_id, started, fail)
                    self.assets.set_status(row["id"], "failed_transient", error=f"{fail.code}: {fail}",
                                           error_class="transient", attempted=True)
                    self.conn.commit()
                    row["download_status"] = "failed_transient"
                    self.sleep(self.settings.backoff_base * (2 ** (attempt - 1)))
                    continue
                return self._record_failure(row, src, job_id, fail, started)
            return self._store(row, src, job_id, transfer, started)

    def _transfer(self, url: str, hop_check, budget: int) -> Transfer:
        try:
            stream = self.fetcher.open(url, hop_check=hop_check)
        except PolicyBlocked as exc:
            raise DownloadFailure(exc.code, str(exc), outcome="blocked", http_status=exc.http_status) from exc
        except FetchError as exc:
            outcome = "blocked" if exc.http_status in (401, 403) else "failed"
            raise DownloadFailure(exc.code, str(exc), exc.error_class, exc.http_status,
                                  outcome=outcome, already_retried=True) from exc
        raw = stream.raw
        final_url = raw.url
        ctype = imglib.normalize_mime(raw.headers.get("content-type"))
        temp = None
        try:
            if ctype and not ctype.startswith("image/") and ctype not in (
                    "application/octet-stream", "binary/octet-stream"):
                raise DownloadFailure("not_image_content_type", f"Content-Type {ctype} is not an image",
                                      http_status=raw.status, final_url=final_url)
            if ctype and ctype.startswith("image/") and ctype not in imglib.SUPPORTED_MIME:
                raise DownloadFailure("unsupported_format", f"unsupported image type {ctype}",
                                      http_status=raw.status, final_url=final_url)
            declared = raw.headers.get("content-length")
            declared_len = int(declared) if declared and declared.isdigit() else None
            if declared_len is not None and declared_len > self.settings.max_file_bytes:
                raise DownloadFailure("too_large", f"Content-Length {declared_len} exceeds "
                                      f"{self.settings.max_file_bytes}", http_status=raw.status,
                                      final_url=final_url)
            if declared_len is not None and declared_len > budget:
                raise BudgetExceeded()
            temp = self.layout.new_temp()
            hasher = hashlib.sha256()
            head = bytearray()
            tail = b""
            total = 0
            try:
                with open(temp, "wb") as fh:
                    for chunk in raw.iter_chunks(65536):
                        total += len(chunk)
                        if total > self.settings.max_file_bytes:
                            raise DownloadFailure("too_large", f"body exceeds {self.settings.max_file_bytes} bytes",
                                                  http_status=raw.status, final_url=final_url,
                                                  received=total)
                        if total > budget:
                            raise BudgetExceeded()
                        hasher.update(chunk)
                        fh.write(chunk)
                        if len(head) < 65536:
                            head.extend(chunk[: 65536 - len(head)])
                        tail = (tail + chunk)[-32:]
                    fh.flush()
                    os.fsync(fh.fileno())
            except TransportError as exc:
                raise DownloadFailure("stream_interrupted", str(exc), "transient", raw.status,
                                      final_url=final_url, received=total) from exc
            if total == 0:
                raise DownloadFailure("empty_response", "response body is empty",
                                      http_status=raw.status, final_url=final_url)
            if declared_len is not None and total != declared_len:
                raise DownloadFailure("length_mismatch", f"received {total} bytes, Content-Length "
                                      f"was {declared_len}", "transient", raw.status,
                                      final_url=final_url, received=total)
            fmt = imglib.sniff_format(bytes(head))
            if fmt in ("html", "json"):
                raise DownloadFailure("html_instead_of_image" if fmt == "html" else "not_an_image",
                                      f"body is {fmt.upper()}, not an image", http_status=raw.status,
                                      final_url=final_url, received=total)
            if fmt not in imglib.FORMATS:
                raise DownloadFailure("unsupported_format", "body is not a supported image format",
                                      http_status=raw.status, final_url=final_url, received=total)
            mime, ext = imglib.FORMATS[fmt]
            if ctype and ctype.startswith("image/") and ctype != mime:
                raise DownloadFailure("mime_mismatch", f"Content-Type {ctype} but bytes are {mime}",
                                      http_status=raw.status, final_url=final_url, received=total)
            if not imglib.looks_complete(fmt, bytes(head), tail, total):
                raise DownloadFailure("truncated_image", f"{fmt} data ends before its end marker",
                                      http_status=raw.status, final_url=final_url, received=total)
            problem = imglib.verify_with_pillow(temp)
            if problem:
                raise DownloadFailure("corrupt_image", f"image does not decode: {problem}",
                                      http_status=raw.status, final_url=final_url, received=total)
            dims = imglib.dimensions(bytes(head))
            transfer = Transfer(temp, hasher.hexdigest(), total, mime, ext,
                                dims.width if dims else None, dims.height if dims else None,
                                final_url, raw.status)
            temp = None    # ownership passes to _store
            return transfer
        finally:
            raw.close()
            if temp is not None:
                temp.unlink(missing_ok=True)

    def _store(self, row: dict, src: Source, job_id: int | None, t: Transfer, started: str) -> dict:
        existing = self.conn.execute("SELECT * FROM image_files WHERE sha256=?", (t.sha256,)).fetchone()
        try:
            if existing is not None:
                outcome = "duplicate"
                target = self.layout.resolve(existing["rel_path"])
                if not target.exists():           # restore a missing file from identical bytes
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(t.temp, target)
                    self.conn.execute("UPDATE image_files SET file_status='ok', abs_path=?, data_root=?, "
                                      "updated_at=? WHERE sha256=?",
                                      (str(target), str(self.layout.root), utcnow(), t.sha256))
                else:
                    t.temp.unlink(missing_ok=True)
                journal = None
            else:
                outcome = "downloaded"
                year = utcnow()[:4]
                rel = self.layout.relative_image_path(slugify(row.get("publisher") or src.id), year,
                                                      t.sha256, t.ext)
                journal = self.layout.write_journal({
                    "sha256": t.sha256, "rel_path": rel, "asset_id": row["id"], "mime": t.mime,
                    "ext": t.ext, "size": t.size, "width": t.width, "height": t.height,
                    "final_url": t.final_url, "job_id": job_id, "started": started})
                final, _ = self.layout.place(t.temp, rel, t.sha256)
                if self.before_db_commit:
                    self.before_db_commit(final)
                now = utcnow()
                self.conn.execute(
                    """INSERT INTO image_files (sha256, rel_path, abs_path, data_root, mime_type, ext,
                       size_bytes, width, height, file_status, created_at, verified_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,'ok',?,?,?)""",
                    (t.sha256, rel, str(final), str(self.layout.root), t.mime, t.ext, t.size,
                     t.width, t.height, now, now, now))
        except StorageError as exc:
            t.temp.unlink(missing_ok=True)
            self.conn.rollback()
            fail = DownloadFailure("storage_error", str(exc), final_url=t.final_url, received=t.size)
            return self._record_failure(row, src, job_id, fail, started)
        self.assets.set_status(row["id"], "downloaded", attempted=True, final_url=t.final_url,
                               sha256=t.sha256)
        self.conn.execute(
            """INSERT INTO download_attempts (job_id, image_ref_id, started_at, finished_at, outcome,
               http_status, requested_url, final_url, bytes_received, sha256)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (job_id, row["id"], started, utcnow(), outcome, t.http_status, row["url"], t.final_url,
             t.size, t.sha256))
        self.conn.commit()
        if journal is not None:
            journal.unlink(missing_ok=True)
        log.debug("%s %s -> %s", outcome, row["id"], t.sha256[:12])
        return {"id": row["id"], "outcome": outcome, "sha256": t.sha256, "bytes": t.size,
                "final_url": t.final_url}

    def _record_attempt(self, row: dict, job_id: int | None, started: str, fail: DownloadFailure) -> None:
        self.conn.execute(
            """INSERT INTO download_attempts (job_id, image_ref_id, started_at, finished_at, outcome,
               error_class, error_code, message, http_status, requested_url, final_url, bytes_received)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job_id, row["id"], started, utcnow(), fail.outcome, fail.error_class, fail.code,
             str(fail)[:2000], fail.http_status, row["url"], fail.final_url, fail.received))

    def _record_failure(self, row: dict, src: Source, job_id: int | None, fail: DownloadFailure,
                        started: str) -> dict:
        self._record_attempt(row, job_id, started, fail)
        if fail.outcome == "blocked":
            new_status = "blocked"
        else:
            new_status = "failed_transient" if fail.error_class == "transient" else "failed_permanent"
        self.assets.set_status(row["id"], new_status, error=f"{fail.code}: {fail}",
                               error_class=fail.error_class, attempted=fail.outcome != "blocked"
                               or fail.http_status is not None)
        self.assets.record_error(source_id=src.id, target_kind="image", target_id=row["id"],
                                 url=row["url"], stage="policy" if fail.outcome == "blocked" else "fetch",
                                 code=fail.code, message=str(fail), error_class=fail.error_class)
        self.conn.commit()
        log.warning("%s %s: %s", new_status, row["id"], fail.code)
        return {"id": row["id"], "outcome": fail.outcome, "code": fail.code,
                "error_class": fail.error_class, "message": str(fail), "bytes": fail.received}
