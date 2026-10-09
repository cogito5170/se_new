#!/usr/bin/env python3
"""Validate the pilot archive: manifest records, local files, hashes, images, rights, provenance.

    python3 validate_collection.py                 # validates ./manifests/collection_manifest.jsonl
    python3 validate_collection.py --allow-empty    # an empty manifest is not an error

Exit codes: 0 every record valid (and at least one, unless --allow-empty) ·
1 at least one error · 3 manifest missing or empty.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from collector import (
    ARCHIVE_DIR, IMAGE_FORMAT_EXT, LICENSE_ID, OFFICIAL_IMAGE_HOSTS, REQUIRED_FIELDS,
    RIGHTS_POLICY_URL, SOURCE_DESCRIPTIVE_FIELDS, FetchError, Image, inspect_image, sha256_file,
    signature_check,
)
import urllib.parse

CLAIM_REQUIRED_KEYS = ("claim", "source_citation")


def _issue(issues, line, record_id, code, detail):
    issues.append({"line": line, "record_id": record_id, "code": code, "detail": detail})


def check_record(rec: dict, line: int, archive: Path, issues: list) -> "str | None":
    """Check one record in place; append issues; return the sha256 that is actually on disk."""
    rid = rec.get("record_id")
    missing = [f for f in REQUIRED_FIELDS if f not in rec]
    if missing:
        _issue(issues, line, rid, "missing_required_keys", missing)

    if not (isinstance(rid, str) and rid.startswith("met:") and rid[4:].isdigit()):
        _issue(issues, line, rid, "bad_record_id", "expected met:<objectID>")
    elif rec.get("source_object_id") is not None and str(rec["source_object_id"]) != rid[4:]:
        _issue(issues, line, rid, "record_id_mismatch", "record_id does not match source_object_id")

    # Rights must have been checked and documented.
    if rec.get("is_public_domain") is not True:
        _issue(issues, line, rid, "rights_not_confirmed", "is_public_domain is not true")
    if rec.get("license") != LICENSE_ID:
        _issue(issues, line, rid, "license_unexpected", rec.get("license"))
    if rec.get("license_evidence_url") != RIGHTS_POLICY_URL:
        _issue(issues, line, rid, "license_evidence_missing", rec.get("license_evidence_url"))
    ev = rec.get("rights_evidence")
    if not isinstance(ev, dict) or ev.get("api_field") != "isPublicDomain" or ev.get("api_value") is not True:
        _issue(issues, line, rid, "rights_evidence_missing", "rights_evidence must record isPublicDomain=true")

    # Provenance.
    img_url = rec.get("original_image_url")
    host = urllib.parse.urlparse(img_url).hostname if isinstance(img_url, str) else None
    if host not in OFFICIAL_IMAGE_HOSTS:
        _issue(issues, line, rid, "image_url_not_official", img_url)
    if rec.get("source_institution") != "The Metropolitan Museum of Art":
        _issue(issues, line, rid, "source_institution_unexpected", rec.get("source_institution"))
    if not rec.get("source_record_url") and not rec.get("api_record_url"):
        _issue(issues, line, rid, "no_source_url", "neither source_record_url nor api_record_url")
    for key in ("creation_year", "publication_year"):
        v = rec.get(key)
        if v is not None and (not isinstance(v, int) or isinstance(v, bool)):
            _issue(issues, line, rid, "bad_year", f"{key}={v!r}")

    # Source metadata vs. generated interpretation.
    claims = rec.get("context_claims")
    if not isinstance(claims, list):
        _issue(issues, line, rid, "context_claims_not_list", type(claims).__name__)
    else:
        for c in claims:
            if not isinstance(c, dict) or any(not c.get(k) for k in CLAIM_REQUIRED_KEYS):
                _issue(issues, line, rid, "uncited_context_claim", c)
    prov = rec.get("field_provenance")
    if not isinstance(prov, dict):
        _issue(issues, line, rid, "field_provenance_missing", "")
    else:
        for f in SOURCE_DESCRIPTIVE_FIELDS:
            p = prov.get(f, "")
            if rec.get(f) is not None and not str(p).startswith("api:"):
                _issue(issues, line, rid, "descriptive_field_not_from_source", f"{f} provenance={p!r}")

    # Snapshot of the API record.
    snap = rec.get("metadata_snapshot_path")
    if not snap:
        _issue(issues, line, rid, "metadata_snapshot_missing", "no metadata_snapshot_path")
    else:
        sp = (archive / snap).resolve()
        if not sp.is_file() or archive not in sp.parents:
            _issue(issues, line, rid, "metadata_snapshot_missing", snap)
        else:
            if rec.get("metadata_snapshot_sha256") and sha256_file(sp) != rec["metadata_snapshot_sha256"]:
                _issue(issues, line, rid, "metadata_snapshot_hash_mismatch", snap)
            try:
                obj = json.loads(sp.read_text(encoding="utf-8"))
                if f"met:{obj.get('objectID')}" != rid:
                    _issue(issues, line, rid, "metadata_snapshot_mismatch", f"snapshot objectID {obj.get('objectID')}")
                elif obj.get("primaryImage", "").strip() != img_url:
                    _issue(issues, line, rid, "metadata_snapshot_mismatch", "primaryImage differs from snapshot")
                elif obj.get("isPublicDomain") is not True:
                    _issue(issues, line, rid, "metadata_snapshot_mismatch", "snapshot isPublicDomain is not true")
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as e:
                _issue(issues, line, rid, "metadata_snapshot_unreadable", str(e))

    # The file itself.
    rel = rec.get("local_file_path")
    if not isinstance(rel, str) or not rel:
        _issue(issues, line, rid, "local_file_path_missing", rel)
        return None
    path = (archive / rel).resolve()
    if archive not in path.parents:
        _issue(issues, line, rid, "local_file_outside_archive", rel)
        return None
    if not path.is_file():
        _issue(issues, line, rid, "local_file_missing", rel)
        return None
    size = path.stat().st_size
    if rec.get("file_size_bytes") != size:
        _issue(issues, line, rid, "file_size_mismatch", f"manifest {rec.get('file_size_bytes')} vs disk {size}")
    actual = sha256_file(path)
    if rec.get("sha256") != actual:
        _issue(issues, line, rid, "sha256_mismatch", f"manifest {rec.get('sha256')} vs disk {actual}")
    sig = signature_check(path)
    if sig["signature_format"] is None or IMAGE_FORMAT_EXT.get(sig["signature_format"]) != path.suffix:
        _issue(issues, line, rid, "signature_mismatch", f"signature {sig['signature_format']} for {path.name}")
    elif sig["end_marker_ok"] is False:
        _issue(issues, line, rid, "signature_end_marker_missing", f"{path.name} lacks its end marker")
    if Image is None:
        # Never pass a record on signature alone: that is not a decode.
        _issue(issues, line, rid, "image_decode_not_run", "Pillow unavailable; only the magic-byte check ran")
    else:
        try:
            info = inspect_image(path)
            if IMAGE_FORMAT_EXT.get(info["format"]) != path.suffix:
                _issue(issues, line, rid, "extension_mismatch", f"{info['format']} in {path.name}")
        except FetchError as e:
            _issue(issues, line, rid, "image_invalid", e.detail)
    if rec.get("image_validation_status") != "valid":
        _issue(issues, line, rid, "image_validation_status_not_valid", rec.get("image_validation_status"))
    return actual


def validate(archive: Path) -> dict:
    archive = archive.resolve()
    manifest = archive / "manifests" / "collection_manifest.jsonl"
    images = archive / "images"
    issues, warnings, records = [], [], 0
    if not manifest.exists():
        return {"status": "no_manifest", "records": 0, "errors": [], "warnings": [], "manifest": str(manifest)}

    seen_ids, seen_hashes, referenced = {}, {}, set()
    with open(manifest, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                _issue(issues, n, None, "invalid_jsonl", str(e))
                continue
            if not isinstance(rec, dict):
                _issue(issues, n, None, "invalid_jsonl", "line is not a JSON object")
                continue
            records += 1
            rid = rec.get("record_id")
            if rid in seen_ids:
                _issue(issues, n, rid, "duplicate_record_id", f"also on line {seen_ids[rid]}")
            seen_ids.setdefault(rid, n)
            actual = check_record(rec, n, archive, issues)
            if actual:
                if actual in seen_hashes:
                    _issue(issues, n, rid, "duplicate_sha256", f"same file content as {seen_hashes[actual]}")
                seen_hashes.setdefault(actual, rid)
            if isinstance(rec.get("local_file_path"), str):
                referenced.add((archive / rec["local_file_path"]).resolve())

    if images.is_dir():
        for p in sorted(images.iterdir()):
            if p.name.startswith(".tmp-"):
                warnings.append({"code": "leftover_temp_file", "detail": p.name})
            elif p.is_file() and p.resolve() not in referenced:
                issues.append({"line": None, "record_id": None, "code": "orphan_image", "detail": p.name})

    if issues:
        status = "invalid"
    elif records == 0:
        status = "empty"
    else:
        status = "valid"
    return {"status": status, "records": records,
            "image_decoder": f"Pillow {Image.__version__}" if Image is not None else "none (decode NOT run)",
            "valid_images": len(seen_hashes) if not issues else 0,
            "errors": issues, "warnings": warnings, "manifest": str(manifest)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR)
    ap.add_argument("--allow-empty", action="store_true")
    ap.add_argument("--report", type=Path, help="write the JSON result here (default reports/validation_result.json)")
    args = ap.parse_args(argv)
    result = validate(args.archive_dir)
    out = args.report or (args.archive_dir / "reports" / "validation_result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"status={result['status']} records={result.get('records')} valid_images={result.get('valid_images', 0)} "
          f"decoder={result.get('image_decoder', '-')} errors={len(result['errors'])} "
          f"warnings={len(result['warnings'])} -> {out}")
    for e in result["errors"][:50]:
        print(f"  ERROR line={e['line']} {e['record_id']} {e['code']}: {e['detail']}")
    if result["status"] == "invalid":
        return 1
    if result["status"] in ("no_manifest", "empty") and not args.allow_empty:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
