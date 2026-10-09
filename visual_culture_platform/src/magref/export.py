"""Export / import of validated JSON.

Envelope (both kinds):
    {"schema": "magazine_reference_export/1", "kind": "pages" | "images",
     "generated_at": ..., "generator": "magref 0.1.0", "count": n, "filters": {...},
     "references": [ <magazine_reference/1 or magazine_image_reference/1 records> ]}

Every record is validated before it is written; an invalid record aborts the
export (exit code 5) instead of producing a file that downstream tools trust.
Import validates the whole file first and writes nothing if anything is invalid.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import __version__
from .assets import AssetRepo, CandidateMeta
from .image_contract import IMAGE_SCHEMA_VERSION, validate_image_record
from .models import EXPORT_SCHEMA_VERSION, SCHEMA_VERSION, ValidationError, validate_reference
from .pages import PageRepo
from .registry import Registry, Source
from .research import FeatureRepo
from .timeutil import utcnow
from .urls import origin_of


def page_record(conn: sqlite3.Connection, ref: dict) -> dict:
    src = Registry(conn).get(ref["source_id"])
    errors = [{"stage": e["stage"], "code": e["code"], "message": e["message"],
               "severity": e.get("severity", "error"), "at": e.get("at") or ref["updated_at"]}
              for e in ref["errors"]]
    return {
        "schema": SCHEMA_VERSION,
        "id": ref["id"],
        "source": {"source_id": src.id, "name": src.name, "publisher": ref["publisher"],
                   "url": ref["url"], "canonical_url": ref["canonical_url"],
                   "discovery_method": ref["discovery_method"],
                   "discovered_from": ref["discovered_from"], "policy_status": src.policy_status,
                   "robots": ref["robots_status"]},
        "content": {"title": ref["title"], "description": ref["description"],
                    "category": ref["category"], "published_at": ref["published_at"],
                    "modified_at": ref["modified_at"], "language": ref["language"],
                    "page_type": ref["page_type"], "authors": ref["authors"],
                    "keywords": ref["keywords"], "access": ref["access"]},
        "assets": ref["assets"],
        "visual_features": ref["visual_features"],
        "analysis": ref["analysis"] or {"observed": [], "inferred": [], "unverified": []},
        "processing": {"crawl_status": ref["crawl_status"], "analysis_status": ref["analysis_status"],
                       "http_status": ref["http_status"], "errors": errors,
                       "first_seen_at": ref["first_seen_at"], "last_crawled_at": ref["last_crawled_at"],
                       "extractor_version": ref["extractor_version"]},
        "provenance": {"fetched_url": ref["fetched_url"], "fetched_at": ref["fetched_at"],
                       "field_sources": ref["field_sources"],
                       "aliases": PageRepo(conn).aliases(ref["id"])},
    }


def image_record(conn: sqlite3.Connection, asset_id: str) -> dict:
    repo = AssetRepo(conn)
    a = repo.get(asset_id)
    if a is None:
        raise KeyError(asset_id)
    reg = Registry(conn)
    policy = reg.effective_image_policy(a["id"], reg.get(a["source_id"]))
    stored = a["file_sha256"] is not None
    feats = FeatureRepo(conn).for_asset(a["id"])

    def feat(f: dict) -> dict:
        return {"feature_type": f["feature_type"], "feature_value": f["feature_value"],
                "method": f["method"], "tool": f["tool"], "confidence": f["confidence"],
                "review_status": f["review_status"], "evidence_note": f["evidence_note"]}

    return {
        "schema": IMAGE_SCHEMA_VERSION,
        "id": a["id"],
        "image": {"type": a["image_type"],
                  "type_evidence": {"status": a["type_status"], "method": a["type_method"],
                                    "basis": a["type_basis"]},
                  "original_url": a["url"], "final_url": a["final_url"],
                  "local_path": a["abs_path"] if stored else None,
                  "relative_path": a["rel_path"] if stored else None,
                  "mime_type": a["mime_type"] if stored else None,
                  "width": a["width"] if stored else None, "height": a["height"] if stored else None,
                  "size_bytes": a["size_bytes"] if stored else None,
                  "sha256": a["file_sha256"], "file_status": a["file_status"] if stored else None,
                  "media_type": a["media_type"]},
        "work": {"title": a["title"], "creator": a["creator"], "description": a["description"],
                 "alt": a["alt"], "caption": a["caption"], "publication_date": a["publication_date"],
                 "creation_date": a["creation_date"], "upload_date": a["upload_date"],
                 "year_start": a["year_start"], "year_end": a["year_end"], "year_basis": a["year_basis"],
                 "country": a["country"], "region": a["region"],
                 "genres": [g["name"] for g in repo.genres(a["id"])]},
        "source": {"source_id": a["source_id"], "publisher": a["publisher"],
                   "source_page_url": a["source_page_url"], "page_reference_id": a["reference_id"],
                   "discovery_method": a["discovery_method"]},
        "rights": {"policy_status": policy["status"], "policy_scope": policy["scope"],
                   "license": policy["license"], "declared_license": a["declared_license"],
                   "evidence_url": policy["evidence_url"], "reviewed_at": policy["reviewed_at"],
                   "note": policy["note"]},
        "download": {"status": a["download_status"], "attempt_count": a["attempt_count"],
                     "last_attempt_at": a["last_attempt_at"], "last_error": a["last_error"],
                     "last_error_class": a["last_error_class"]},
        "features": {"measured": [feat(f) for f in feats if f["kind"] == "measured"],
                     "semantic": [feat(f) for f in feats if f["kind"] == "semantic"]},
        "duplicates": {"same_file_as": repo.same_file(a["id"])},
        "timestamps": {"discovered_at": a["discovered_at"], "updated_at": a["updated_at"]},
    }


def build_export(conn: sqlite3.Connection, kind: str, filters: dict | None = None) -> dict:
    filters = {k: v for k, v in (filters or {}).items() if v is not None}
    if kind == "pages":
        records = [page_record(conn, r) for r in PageRepo(conn).all(
            source_id=filters.get("source"), publisher=filters.get("publisher"),
            category=filters.get("category"), page_type=filters.get("page_type"))
                   if r["crawl_status"] == "fetched"]
        validator = validate_reference
    elif kind == "images":
        rows = AssetRepo(conn).query(source=filters.get("source"), status=filters.get("status"),
                                     year_from=filters.get("year_from"), year_to=filters.get("year_to"),
                                     country=filters.get("country"))
        records = [image_record(conn, r["id"]) for r in rows]
        validator = validate_image_record
    else:
        raise ValueError("kind must be 'pages' or 'images'")
    problems = []
    for rec in records:
        problems += [f"{rec.get('id')}: {e}" for e in validator(rec)]
    if problems:
        raise ValidationError(problems)
    return {"schema": EXPORT_SCHEMA_VERSION, "kind": kind, "generated_at": utcnow(),
            "generator": f"magref {__version__}", "count": len(records), "filters": filters,
            "references": records}


def validate_export_doc(doc) -> list[str]:
    if not isinstance(doc, dict):
        return ["$: must be an object"]
    errs = []
    for key in ("schema", "kind", "generated_at", "generator", "count", "filters", "references"):
        if key not in doc:
            errs.append(f"$: missing required field '{key}'")
    extra = set(doc) - {"schema", "kind", "generated_at", "generator", "count", "filters", "references"}
    errs += [f"$: unexpected field '{k}'" for k in sorted(extra)]
    if doc.get("schema") != EXPORT_SCHEMA_VERSION:
        errs.append(f"$.schema: must be '{EXPORT_SCHEMA_VERSION}'")
    kind = doc.get("kind")
    if kind not in ("pages", "images"):
        errs.append("$.kind: must be 'pages' or 'images'")
        return errs
    refs = doc.get("references")
    if not isinstance(refs, list):
        return errs + ["$.references: must be an array"]
    if doc.get("count") != len(refs):
        errs.append(f"$.count: is {doc.get('count')} but {len(refs)} references are present")
    validator = validate_reference if kind == "pages" else validate_image_record
    seen = set()
    for i, rec in enumerate(refs):
        errs += [f"$.references[{i}]{e[1:]}" for e in validator(rec)]
        rid = rec.get("id") if isinstance(rec, dict) else None
        if rid in seen:
            errs.append(f"$.references[{i}].id: duplicate id {rid}")
        seen.add(rid)
    return errs


def write_export(doc: dict, output: Path | None, fmt: str = "json") -> str:
    if fmt == "json":
        text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    elif fmt == "jsonl":
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in doc["references"])
    else:
        raise ValueError("format must be json or jsonl")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(output.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(output)
    return text


def _ensure_source(conn, source_id: str, url: str) -> None:
    reg = Registry(conn)
    try:
        reg.get(source_id)
    except LookupError:
        # Placeholder only: disabled, policy 'unknown', no discovery configuration copied.
        reg.add(Source(id=source_id, name=f"{source_id} (imported)", base_url=origin_of(url),
                       discovery_method="html", enabled=False))


def import_file(conn: sqlite3.Connection, path: Path) -> dict:
    """Validate an export file and load it. Image records come in as metadata only:
    files are never trusted from an import -- download status resets to 'pending'
    and the source policy is NOT taken from the file (imported sources start 'unknown',
    disabled)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError([f"cannot read {path}: {exc}"]) from exc
    errs = validate_export_doc(doc)
    if errs:
        raise ValidationError(errs)
    created = updated = 0
    if doc["kind"] == "images":
        repo = AssetRepo(conn)
        for rec in doc["references"]:
            s, w = rec["source"], rec["work"]
            _ensure_source(conn, s["source_id"], rec["image"]["original_url"])
            _, new = repo.upsert_candidate(s["source_id"], rec["image"]["original_url"], "import",
                                           CandidateMeta(
                source_page_url=s["source_page_url"], publisher=s["publisher"], title=w["title"],
                alt=w["alt"], caption=w["caption"], description=w["description"],
                creator=w["creator"], publication_date=w["publication_date"],
                creation_date=w["creation_date"], upload_date=w["upload_date"],
                year_start=w["year_start"], year_end=w["year_end"], country=w["country"],
                region=w["region"], media_type=rec["image"]["media_type"],
                declared_license=rec["rights"]["declared_license"],
                declared_type=rec["image"]["type"] if rec["image"]["type_evidence"]["status"] == "observed" else None,
                genres=w["genres"] or None))
            created += new
            updated += not new
    else:
        now = utcnow()
        for rec in doc["references"]:
            s, c = rec["source"], rec["content"]
            _ensure_source(conn, s["source_id"], s["url"])
            exists = conn.execute("SELECT 1 FROM refs WHERE id=?", (rec["id"],)).fetchone()
            values = {
                "source_id": s["source_id"], "url": s["url"], "canonical_url": s["canonical_url"],
                "fetched_url": rec["provenance"]["fetched_url"], "discovery_method": "import",
                "discovered_from": s["discovered_from"], "robots_status": s["robots"],
                "title": c["title"], "description": c["description"], "publisher": s["publisher"],
                "category": c["category"], "published_at": c["published_at"],
                "modified_at": c["modified_at"], "language": c["language"], "page_type": c["page_type"],
                "access": c["access"], "authors": json.dumps(c["authors"]),
                "keywords": json.dumps(c["keywords"]), "assets": json.dumps(rec["assets"]),
                "visual_features": json.dumps(rec["visual_features"]),
                "analysis": json.dumps(rec["analysis"]),
                "field_sources": json.dumps(rec["provenance"]["field_sources"]),
                "errors": json.dumps(rec["processing"]["errors"]),
                "search_text": " ".join(filter(None, [c["title"], c["description"]])),
                "crawl_status": rec["processing"]["crawl_status"],
                "analysis_status": rec["processing"]["analysis_status"],
                "http_status": rec["processing"]["http_status"],
                "extractor_version": rec["processing"]["extractor_version"],
                "last_crawled_at": rec["processing"]["last_crawled_at"],
                "fetched_at": rec["provenance"]["fetched_at"], "updated_at": now,
            }
            if exists:
                conn.execute(f"UPDATE refs SET {', '.join(k + '=?' for k in values)} WHERE id=?",
                             list(values.values()) + [rec["id"]])
                updated += 1
            else:
                values.update(id=rec["id"], first_seen_at=rec["processing"]["first_seen_at"])
                conn.execute(f"INSERT INTO refs ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
                             list(values.values()))
                created += 1
            for alias in rec["provenance"]["aliases"]:
                conn.execute("INSERT OR IGNORE INTO ref_urls VALUES (?,?,?,?)",
                             (alias, rec["id"], "alias", now))
        conn.commit()
    return {"kind": doc["kind"], "created": created, "updated": updated}
