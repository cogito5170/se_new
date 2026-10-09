#!/usr/bin/env python3
"""Catalogue magazine pages you collected by hand (ProQuest PDFs, own scans, saved Pinterest images).

Nothing is downloaded. You put files in ``inbox/``, describe them in ``inbox/metadata.csv``,
and this script validates, de-duplicates, copies and records them in ``magazine_archive/``.
Files in ``inbox/`` are never moved, changed or deleted.

    python3 ingest_local.py init       # add a CSV row for every new file in inbox/
    python3 ingest_local.py ingest     # validate + copy + record every completed row
    python3 ingest_local.py validate   # re-check manifest, files and hashes
    python3 ingest_local.py gallery    # write magazine_archive/reports/gallery.html

Python 3.9+. Pillow is needed for image decoding (PDFs get a structural check only).
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
from pathlib import Path

from collector import (
    IMAGE_FORMAT_EXT, PROJECT_DIR, FetchError, Image, append_manifest, inspect_image,
    place_without_overwrite, read_manifest, sha256_file, signature_check, utc_now,
)

INBOX_DIR = PROJECT_DIR / "inbox"
ARCHIVE_DIR = PROJECT_DIR / "magazine_archive"
CSV_NAME = "metadata.csv"
CSV_FIELDS = ("filename", "magazine", "edition", "issue_date", "page", "page_type",
              "source_url", "rights_status", "notes")
REQUIRED = ("filename", "magazine", "rights_status")
ACCEPTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".webp", ".pdf"}

PAGE_TYPES = ("cover", "editorial", "advertisement", "contents", "other")
RIGHTS = {
    "licensed_access_personal_reference":
        "Downloaded one document at a time through a licensed database (e.g. ProQuest via a library). "
        "Copyright remains with the publisher and contributors. Personal research reference; do not redistribute.",
    "own_scan_personal_reference":
        "Scanned from a physical copy the collector owns. Copyright remains with the publisher and "
        "contributors. Personal research reference; do not redistribute.",
    "third_party_unverified":
        "Saved from a third-party site (e.g. Pinterest). Original source and rights holder not verified. "
        "Personal research reference only; do not redistribute.",
}
ISSUE_DATE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")
PLATFORMS = (("proquest.com", "proquest"), ("pinterest.", "pinterest"), ("pin.it", "pinterest"))


class RowError(Exception):
    pass


# --------------------------------------------------------------------------- helpers

def manifest_path(archive: Path) -> Path:
    return archive / "manifests" / "magazine_manifest.jsonl"


def inbox_files(inbox: Path) -> "list[Path]":
    if not inbox.is_dir():
        return []
    return sorted(p for p in inbox.iterdir()
                  if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in ACCEPTED_SUFFIXES)


def read_rows(csv_path: Path) -> "list[dict]":
    # utf-8-sig: Excel and Numbers may prepend a BOM.
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(fh)]


def pdf_check(path: Path) -> dict:
    """Structural check only: %PDF- header and %%EOF near the end. NOT a full parse or render."""
    size = path.stat().st_size
    with open(path, "rb") as fh:
        head = fh.read(8)
        fh.seek(max(0, size - 2048))
        tail = fh.read()
    if not head.startswith(b"%PDF-"):
        raise RowError(f"not a PDF (first bytes {head!r})")
    if b"%%EOF" not in tail:
        raise RowError("PDF has no %%EOF marker near the end (truncated?)")
    return {"file_type": "pdf", "validation_status": "pdf_header_and_eof_ok",
            "validation_note": "structural check only; the PDF was not parsed or rendered"}


def file_check(path: Path) -> "tuple[dict, str]":
    """Return (validation info, extension for the archived copy). Content decides, not the name."""
    if path.stat().st_size == 0:
        raise RowError("empty file")
    with open(path, "rb") as fh:
        head = fh.read(8)
    if head.startswith(b"%PDF-"):
        return pdf_check(path), ".pdf"
    sig = signature_check(path)
    if sig["signature_format"] is None:
        raise RowError(f"neither PDF nor a known image format (first bytes {head!r})")
    if sig["end_marker_ok"] is False:
        raise RowError(f"{sig['signature_format']} end marker missing (truncated?)")
    if Image is None:
        raise RowError("Pillow is not installed; images cannot be decoded, so they are not ingested")
    try:
        info = inspect_image(path)
    except FetchError as e:
        raise RowError(f"image does not decode: {e.detail}")
    if info["format"] != sig["signature_format"]:
        raise RowError(f"signature {sig['signature_format']} but decoded as {info['format']}")
    return ({"file_type": "image", "validation_status": "valid", "image_format": info["format"],
             "image_width": info["width"], "image_height": info["height"]},
            IMAGE_FORMAT_EXT[info["format"]])


def check_row(row: dict) -> dict:
    """Validate the user-entered fields; return them normalised (empty -> None)."""
    missing = [f for f in REQUIRED if not row.get(f)]
    if missing:
        raise RowError("incomplete: " + ", ".join(missing))
    out = {f: (row.get(f) or None) for f in CSV_FIELDS}
    if out["rights_status"] not in RIGHTS:
        raise RowError(f"rights_status must be one of {sorted(RIGHTS)}")
    if out["page_type"] is not None:
        out["page_type"] = out["page_type"].lower()
        if out["page_type"] not in PAGE_TYPES:
            raise RowError(f"page_type must be one of {PAGE_TYPES} or empty")
    if out["issue_date"] is not None and not ISSUE_DATE.match(out["issue_date"]):
        raise RowError("issue_date must be YYYY, YYYY-MM or YYYY-MM-DD")
    if out["source_url"] is not None:
        u = urllib.parse.urlparse(out["source_url"])
        if u.scheme not in ("http", "https") or not u.hostname:
            raise RowError("source_url must be an http(s) URL")
    if "/" in out["filename"] or "\\" in out["filename"] or out["filename"].startswith("."):
        raise RowError("filename must be a plain file name inside inbox/")
    return out


def source_platform(url: "str | None") -> "str | None":
    if not url:
        return None
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    for needle, name in PLATFORMS:
        if needle in host:
            return name
    return "other"


def build_record(fields: dict, info: dict, sha: str, size: int, rel_path: str) -> dict:
    rec = {
        "record_id": f"mag:{sha[:16]}",
        "magazine": fields["magazine"],
        "edition": fields["edition"],
        "issue_date": fields["issue_date"],
        "page": fields["page"],
        "page_type": fields["page_type"],
        "source_url": fields["source_url"],
        "source_platform": source_platform(fields["source_url"]),
        "rights_status": fields["rights_status"],
        "rights_note": RIGHTS[fields["rights_status"]],
        "notes": fields["notes"],
        "original_filename": fields["filename"],
        "local_file_path": rel_path,
        "sha256": sha,
        "file_size_bytes": size,
        "ingested_at": utc_now(),
    }
    rec.update(info)
    rec["field_provenance"] = {
        **{f: "user_csv" for f in ("magazine", "edition", "issue_date", "page", "page_type",
                                   "source_url", "rights_status", "notes")},
        "source_platform": "pipeline (from source_url host)",
        "rights_note": "pipeline (fixed text for rights_status)",
        "sha256": "pipeline", "file_size_bytes": "pipeline", "validation_status": "pipeline",
        "local_file_path": "pipeline", "ingested_at": "pipeline",
    }
    return rec


# --------------------------------------------------------------------------- commands

def cmd_init(inbox: Path, archive: Path) -> dict:
    """Append a row for every inbox file that is neither in the CSV nor already ingested.
    Existing rows (your edits) are never rewritten."""
    inbox.mkdir(parents=True, exist_ok=True)
    csv_path = inbox / CSV_NAME
    listed = {r.get("filename") for r in read_rows(csv_path)} if csv_path.exists() else set()
    ingested = {r.get("sha256") for r in read_manifest(manifest_path(archive))}
    new = [p.name for p in inbox_files(inbox)
           if p.name not in listed and sha256_file(p) not in ingested]
    write_header = not csv_path.exists()
    if write_header or new:
        if not write_header:
            with open(csv_path, "rb") as fh:
                data = fh.read()
            needs_newline = bool(data) and not data.endswith(b"\n")
        with open(csv_path, "a", newline="", encoding="utf-8") as fh:
            if not write_header and needs_newline:
                fh.write("\n")
            w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            if write_header:
                w.writeheader()
            for name in new:
                w.writerow({"filename": name})
    return {"csv": str(csv_path), "new_rows": new}


def cmd_ingest(inbox: Path, archive: Path) -> dict:
    csv_path = inbox / CSV_NAME
    if not csv_path.exists():
        raise SystemExit(f"{csv_path} not found; run `init` first")
    files_dir = archive / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_path(archive)
    known = {r["sha256"]: (r["record_id"], r.get("original_filename")) for r in read_manifest(manifest)
             if r.get("sha256")}
    result = {"ingested": [], "duplicate": [], "incomplete": [], "rejected": []}
    for n, row in enumerate(read_rows(csv_path), 2):  # line 1 is the header
        name = row.get("filename") or f"(line {n})"
        try:
            fields = check_row(row)
        except RowError as e:
            key = "incomplete" if str(e).startswith("incomplete") else "rejected"
            result[key].append({"line": n, "filename": name, "reason": str(e)})
            continue
        src = inbox / fields["filename"]
        if not src.is_file():
            result["rejected"].append({"line": n, "filename": name, "reason": "file not found in inbox/"})
            continue
        # Work on a private copy so the hash, the check and the archived bytes are the same bytes.
        fd, tmp_name = tempfile.mkstemp(prefix=".tmp-ingest-", dir=files_dir)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            shutil.copyfile(src, tmp)
            sha = sha256_file(tmp)
            if sha in known:
                # First row wins. Say which file was kept, so a better-described duplicate is noticed.
                result["duplicate"].append({"line": n, "filename": name, "same_as": known[sha][0],
                                            "kept_file": known[sha][1]})
                continue
            try:
                info, ext = file_check(tmp)
            except RowError as e:
                result["rejected"].append({"line": n, "filename": name, "reason": str(e)})
                continue
            final = files_dir / f"mag_{sha[:16]}{ext}"
            try:
                place_without_overwrite(tmp, final)
            except FetchError as e:
                result["rejected"].append({"line": n, "filename": name, "reason": e.detail})
                continue
            if sha256_file(final) != sha:
                final.unlink()
                result["rejected"].append({"line": n, "filename": name, "reason": "hash changed after copy"})
                continue
            rec = build_record(fields, info, sha, final.stat().st_size, final.relative_to(archive).as_posix())
            append_manifest(manifest, rec)
            known[sha] = (rec["record_id"], fields["filename"])
            result["ingested"].append({"line": n, "filename": name, "record_id": rec["record_id"],
                                       "file_type": rec["file_type"]})
        finally:
            if tmp.exists():
                tmp.unlink()
    return result


def cmd_validate(archive: Path) -> dict:
    archive = archive.resolve()
    errors, records, seen = [], 0, {}
    manifest = manifest_path(archive)
    if not manifest.exists():
        return {"status": "no_manifest", "records": 0, "errors": []}
    referenced = set()
    with open(manifest, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append({"line": n, "code": "invalid_jsonl", "detail": str(e)})
                continue
            records += 1
            rid = rec.get("record_id")
            if rec.get("rights_status") not in RIGHTS:
                errors.append({"line": n, "record_id": rid, "code": "bad_rights_status"})
            rel = rec.get("local_file_path") or ""
            path = (archive / rel).resolve()
            if archive not in path.parents:
                errors.append({"line": n, "record_id": rid, "code": "path_outside_archive", "detail": rel})
                continue
            referenced.add(path)
            if not path.is_file():
                errors.append({"line": n, "record_id": rid, "code": "file_missing", "detail": rel})
                continue
            actual = sha256_file(path)
            if actual != rec.get("sha256"):
                errors.append({"line": n, "record_id": rid, "code": "sha256_mismatch", "detail": rel})
            if path.stat().st_size != rec.get("file_size_bytes"):
                errors.append({"line": n, "record_id": rid, "code": "size_mismatch", "detail": rel})
            if actual in seen:
                errors.append({"line": n, "record_id": rid, "code": "duplicate_sha256", "detail": seen[actual]})
            seen.setdefault(actual, rid)
            try:
                file_check(path)
            except RowError as e:
                errors.append({"line": n, "record_id": rid, "code": "file_invalid", "detail": str(e)})
    files_dir = archive / "files"
    if files_dir.is_dir():
        for p in sorted(files_dir.iterdir()):
            if p.is_file() and not p.name.startswith(".") and p.resolve() not in referenced:
                errors.append({"line": None, "code": "orphan_file", "detail": p.name})
    status = "invalid" if errors else ("valid" if records else "empty")
    return {"status": status, "records": records, "errors": errors,
            "image_decoder": f"Pillow {Image.__version__}" if Image is not None else "none"}


def cmd_gallery(archive: Path) -> Path:
    recs = read_manifest(manifest_path(archive))
    recs.sort(key=lambda r: (r.get("magazine") or "", r.get("issue_date") or "", r.get("page") or ""))
    e = lambda v: html.escape(str(v)) if v not in (None, "") else "&mdash;"
    cards = []
    for r in recs:
        src = "../" + e(r["local_file_path"])
        media = (f'<img src="{src}" loading="lazy">' if r.get("file_type") == "image"
                 else f'<object data="{src}" type="application/pdf"><a href="{src}">PDF</a></object>')
        link = f'<a href="{e(r["source_url"])}">source</a>' if r.get("source_url") else "no source URL"
        cards.append(f"""<figure data-mag="{e(r['magazine'])}" data-type="{e(r.get('page_type'))}">
<a href="{src}">{media}</a><figcaption><b>{e(r['magazine'])}</b> {e(r.get('edition'))} &middot; {e(r.get('issue_date'))}
&middot; p.{e(r.get('page'))}<br>{e(r.get('page_type'))} &middot; <span class="r">{e(r['rights_status'])}</span><br>
<small>{e(r.get('notes'))}<br>{link} &middot; {e(r['record_id'])}</small></figcaption></figure>""")
    mags = sorted({r.get("magazine") or "" for r in recs})
    types = sorted({r.get("page_type") or "" for r in recs} - {""})
    opt = lambda vals: "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in vals)
    page = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Magazine Pages</title><style>
body{{font:14px -apple-system,sans-serif;margin:16px;background:#fafafa;color:#222}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
figure{{margin:0;background:#fff;padding:8px;border:1px solid #ddd}}
img,object{{width:100%;height:340px;object-fit:contain;background:#eee;display:block}}
.r{{font-size:12px;color:#a33}} select{{margin-right:8px}}
@media (prefers-color-scheme:dark){{body{{background:#111;color:#ddd}}figure{{background:#1b1b1b;border-color:#333}}a{{color:#8ab4f8}}}}
</style><h1>Magazine pages &middot; {len(recs)}</h1>
<p>Personal research reference. Copyright remains with the rights holders. Do not redistribute.</p>
<p><select id="m"><option value="">all magazines</option>{opt(mags)}</select>
<select id="t"><option value="">all page types</option>{opt(types)}</select></p>
<main>{''.join(cards)}</main>
<script>
function f(){{var m=document.getElementById('m').value,t=document.getElementById('t').value;
document.querySelectorAll('figure').forEach(function(x){{x.style.display=
((!m||x.dataset.mag===m)&&(!t||x.dataset.type===t))?'':'none';}});}}
document.getElementById('m').onchange=f;document.getElementById('t').onchange=f;
</script>"""
    out = archive / "reports" / "gallery.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("init", "ingest", "validate", "gallery"))
    ap.add_argument("--inbox", type=Path, default=INBOX_DIR)
    ap.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR)
    a = ap.parse_args(argv)
    archive = a.archive_dir.resolve()
    if a.command == "init":
        r = cmd_init(a.inbox, archive)
        print(f"{len(r['new_rows'])} new row(s) added to {r['csv']}")
        for name in r["new_rows"]:
            print("  +", name)
        print("Fill in magazine and rights_status (required) and the other columns, then run `ingest`.")
        print("rights_status:", ", ".join(sorted(RIGHTS)))
        print("page_type:", ", ".join(PAGE_TYPES))
        return 0
    if a.command == "ingest":
        r = cmd_ingest(a.inbox, archive)
        for key in ("ingested", "duplicate", "incomplete", "rejected"):
            print(f"{key}: {len(r[key])}")
            for item in r[key]:
                print("   ", json.dumps(item, ensure_ascii=False))
        print("gallery:", cmd_gallery(archive))
        return 1 if r["rejected"] else 0
    if a.command == "validate":
        r = cmd_validate(archive)
        print(f"status={r['status']} records={r['records']} errors={len(r['errors'])} "
              f"decoder={r.get('image_decoder', '-')}")
        for err in r["errors"]:
            print("  ERROR", json.dumps(err, ensure_ascii=False))
        return {"valid": 0, "invalid": 1}.get(r["status"], 3)
    print("gallery:", cmd_gallery(archive))
    return 0


if __name__ == "__main__":
    sys.exit(main())
