"""Consistency between the database and the files on disk.

verify       every image_files row: file present? size and SHA-256 still match?
             missing -> file_status 'missing', assets -> 'missing_file'
             corrupt -> file moved to quarantine/corrupt, assets -> 'missing_file'
             present only under the CURRENT data root (data dir moved) -> 'relocated'
             (`--relocate` rewrites abs_path after re-hashing)
orphans      files under images/ with no image_files row (reported, never deleted)
repair       replays write-ahead journal entries left by an interrupted download
deduplicate  reports shared files and duplicate copies; `apply` moves duplicate
             copies to quarantine/duplicates (never deletes)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .storage import Layout, StorageError, sha256_file
from .timeutil import utcnow


def _set_assets_missing(conn: sqlite3.Connection, sha: str) -> int:
    cur = conn.execute(
        """UPDATE image_refs SET download_status='missing_file', updated_at=?,
           last_error='file missing or corrupt on disk', last_error_class='transient'
           WHERE file_sha256=? AND download_status='downloaded'""", (utcnow(), sha))
    return cur.rowcount


def verify(conn: sqlite3.Connection, layout: Layout, *, relocate: bool = False,
           only: list[str] | None = None) -> dict:
    report = {"checked": 0, "ok": 0, "missing": [], "corrupt": [], "relocated": [], "assets_marked": 0}
    rows = conn.execute("SELECT * FROM image_files ORDER BY sha256").fetchall()
    for row in rows:
        if only and row["sha256"] not in only:
            continue
        report["checked"] += 1
        sha = row["sha256"]
        recorded = Path(row["abs_path"])
        try:
            current = layout.resolve(row["rel_path"])
        except StorageError:
            current = None
        path = recorded if recorded.is_file() else None
        moved = False
        if path is None and current is not None and current.is_file():
            path, moved = current, True
        now = utcnow()
        if path is None:
            conn.execute("UPDATE image_files SET file_status='missing', verified_at=?, updated_at=? "
                         "WHERE sha256=?", (now, now, sha))
            report["assets_marked"] += _set_assets_missing(conn, sha)
            report["missing"].append({"sha256": sha, "path": str(recorded)})
            continue
        actual_size = path.stat().st_size
        actual_sha = sha256_file(path)
        if actual_size != row["size_bytes"] or actual_sha != sha:
            dest = layout.root / "quarantine" / "corrupt"
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / f"{sha}-{path.name}"
            path.replace(target)
            conn.execute("UPDATE image_files SET file_status='corrupt', verified_at=?, updated_at=? "
                         "WHERE sha256=?", (now, now, sha))
            report["assets_marked"] += _set_assets_missing(conn, sha)
            report["corrupt"].append({"sha256": sha, "actual_sha256": actual_sha,
                                      "quarantined_to": str(target)})
            continue
        if moved:
            report["relocated"].append({"sha256": sha, "old": str(recorded), "new": str(path)})
            if relocate:
                conn.execute("UPDATE image_files SET abs_path=?, data_root=?, file_status='ok', "
                             "verified_at=?, updated_at=? WHERE sha256=?",
                             (str(path), str(layout.root), now, now, sha))
                report["ok"] += 1
            else:
                conn.execute("UPDATE image_files SET file_status='relocated', verified_at=?, "
                             "updated_at=? WHERE sha256=?", (now, now, sha))
            continue
        conn.execute("UPDATE image_files SET file_status='ok', verified_at=?, updated_at=? "
                     "WHERE sha256=?", (now, now, sha))
        # A file that was missing and is back (restored by the user) heals its assets.
        conn.execute("""UPDATE image_refs SET download_status='downloaded', updated_at=?
                        WHERE file_sha256=? AND download_status='missing_file'""", (now, sha))
        report["ok"] += 1
    conn.commit()
    return report


def orphans(conn: sqlite3.Connection, layout: Layout) -> dict:
    known = {r[0] for r in conn.execute("SELECT rel_path FROM image_files")}
    out = {"orphan_files": [], "stale_temp_files": []}
    for path in layout.iter_image_files():
        rel = path.relative_to(layout.root).as_posix()
        if rel not in known:
            out["orphan_files"].append(str(path))
    if layout.tmp.is_dir():
        out["stale_temp_files"] = [str(p) for p in sorted(layout.tmp.glob("*.part"))]
    return out


def clean_temp(layout: Layout) -> int:
    """Delete leftover *.part files (only files this program creates)."""
    n = 0
    if layout.tmp.is_dir():
        for p in layout.tmp.glob("dl-*.part"):
            p.unlink(missing_ok=True)
            n += 1
    return n


def repair(conn: sqlite3.Connection, layout: Layout) -> dict:
    """Finish downloads interrupted between 'file moved into place' and 'DB committed'."""
    out = {"recovered": [], "already_recorded": [], "dropped": []}
    for jpath, entry in layout.journal_entries():
        sha = entry.get("sha256")
        if not sha or not entry.get("rel_path"):
            out["dropped"].append({"journal": jpath.name, "reason": "unreadable journal"})
            jpath.unlink(missing_ok=True)
            continue
        if conn.execute("SELECT 1 FROM image_files WHERE sha256=?", (sha,)).fetchone():
            out["already_recorded"].append(sha)
            jpath.unlink(missing_ok=True)
            continue
        try:
            path = layout.resolve(entry["rel_path"])
        except StorageError as exc:
            out["dropped"].append({"journal": jpath.name, "reason": str(exc)})
            jpath.unlink(missing_ok=True)
            continue
        if not path.is_file() or sha256_file(path) != sha:
            out["dropped"].append({"journal": jpath.name, "reason": "file absent or hash differs"})
            jpath.unlink(missing_ok=True)
            continue
        now = utcnow()
        with conn:
            conn.execute(
                """INSERT INTO image_files (sha256, rel_path, abs_path, data_root, mime_type, ext,
                   size_bytes, width, height, file_status, created_at, verified_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,'ok',?,?,?)""",
                (sha, entry["rel_path"], str(path), str(layout.root), entry["mime"], entry["ext"],
                 path.stat().st_size, entry.get("width"), entry.get("height"), now, now, now))
            asset = conn.execute("SELECT download_status FROM image_refs WHERE id=?",
                                 (entry.get("asset_id"),)).fetchone()
            if asset is not None and asset[0] != "downloaded":
                conn.execute(
                    """UPDATE image_refs SET download_status='downloaded', file_sha256=?, final_url=?,
                       last_error=NULL, last_error_class=NULL, updated_at=? WHERE id=?""",
                    (sha, entry.get("final_url"), now, entry["asset_id"]))
                conn.execute(
                    """INSERT INTO download_attempts (job_id, image_ref_id, started_at, finished_at,
                       outcome, requested_url, final_url, bytes_received, sha256, message)
                       SELECT ?, id, ?, ?, 'downloaded', url, ?, ?, ?, 'recovered by repair'
                       FROM image_refs WHERE id=?""",
                    (entry.get("job_id"), entry.get("started") or now, now, entry.get("final_url"),
                     path.stat().st_size, sha, entry["asset_id"]))
        jpath.unlink(missing_ok=True)
        out["recovered"].append(sha)
    return out


def deduplicate(conn: sqlite3.Connection, layout: Layout, *, apply: bool = False) -> dict:
    shared = []
    for row in conn.execute(
            """SELECT file_sha256, COUNT(*) AS n FROM image_refs WHERE file_sha256 IS NOT NULL
               GROUP BY file_sha256 HAVING n > 1 ORDER BY file_sha256"""):
        refs = [dict(r) for r in conn.execute(
            """SELECT r.id, r.url, r.source_id, r.declared_license,
                      (SELECT status FROM policy_reviews p WHERE p.target_kind='image'
                       AND p.target_id=r.id ORDER BY p.id DESC LIMIT 1) AS image_policy
               FROM image_refs r WHERE r.file_sha256=? ORDER BY r.id""", (row[0],))]
        shared.append({"sha256": row[0], "references": refs,
                       "distinct_sources": len({r["source_id"] for r in refs}),
                       "distinct_licenses": len({r["declared_license"] for r in refs})})
    known = {r["rel_path"]: r["sha256"] for r in conn.execute("SELECT rel_path, sha256 FROM image_files")}
    known_shas = set(known.values())
    copies, unknown = [], []
    for path in layout.iter_image_files():
        rel = path.relative_to(layout.root).as_posix()
        if rel in known:
            continue
        digest = sha256_file(path)
        if digest in known_shas:
            entry = {"path": str(path), "sha256": digest}
            if apply:
                entry["moved_to"] = str(layout.quarantine_file(path))
            copies.append(entry)
        else:
            unknown.append(str(path))
    return {"mode": "apply" if apply else "dry-run",
            "same_file_different_urls": shared,
            "duplicate_copies_on_disk": copies,
            "unrecorded_files": unknown,
            "note": "Files are stored once per SHA-256; every URL/source keeps its own record. "
                    "SHA-256 shows byte identity only, not licence or ownership."}
