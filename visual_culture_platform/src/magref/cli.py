"""Command-line interface: `magref <command>` (also `python -m magref`).

Exit codes
    0  success
    1  operational failure (nothing succeeded, unexpected error)
    2  usage error (bad arguments / configuration)
    3  not found (source, asset, project ...)
    4  refused by policy (disabled or restricted source, trust rule)
    5  validation failure (export/import/schema)
    6  completed with errors (some items failed; see output and `magref status`)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .app import App, open_app
from .config import ConfigError, load_settings
from .logutil import setup_logging
from .registry import NotFound, Registry, RegistryError, Source

EXIT_OK, EXIT_FAIL, EXIT_USAGE, EXIT_NOT_FOUND, EXIT_POLICY, EXIT_INVALID, EXIT_PARTIAL = 0, 1, 2, 3, 4, 5, 6
log = logging.getLogger("magref.cli")


class CliError(Exception):
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


def out(args, data, text: str | None = None) -> None:
    if args.json or text is None:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(text)


def _years(spec: str) -> tuple[int, int]:
    try:
        a, _, b = spec.partition("-")
        start, end = int(a), int(b or a)
    except ValueError as exc:
        raise CliError(f"period must look like 1980-1989, got {spec!r}", EXIT_USAGE) from exc
    if start > end:
        raise CliError("period start must be <= end", EXIT_USAGE)
    return start, end


# --------------------------------------------------------------------------- sources & policy

def usable_source(app: App, source_id: str, action: str) -> Source:
    src = Registry(app.conn).get(source_id)
    if not src.enabled:
        raise CliError(f"source '{source_id}' is disabled; enable it with `magref source enable "
                       f"{source_id}` before {action}", EXIT_POLICY)
    if src.policy_status == "restricted":
        raise CliError(f"source '{source_id}' is restricted (policy review); {action} refused", EXIT_POLICY)
    return src


def cmd_init(app, args):
    from . import db
    out(args, {"database": str(app.settings.database_path), "schema_version": db.current_version(app.conn),
               "data_dir": str(app.layout.root)},
        f"database ready: {app.settings.database_path} (schema v{db.current_version(app.conn)})\n"
        f"data directory: {app.layout.root}")
    return EXIT_OK


def cmd_source(app, args):
    reg = Registry(app.conn)
    if args.action == "list":
        rows = [s.to_dict() for s in reg.list()]
        lines = [f"{'ID':<20} {'METHOD':<12} {'POLICY':<16} {'ENABLED':<8} LAST RUN"]
        for s in rows:
            lines.append(f"{s['id']:<20} {s['discovery_method']:<12} {s['policy_status']:<16} "
                         f"{'yes' if s['enabled'] else 'no':<8} {s['last_run_kind'] or '-'} "
                         f"{s['last_run_status'] or ''}")
        out(args, rows, "\n".join(lines) if rows else "(no sources registered)")
    elif args.action == "add":
        src = reg.add(Source(id=args.id, name=args.name, base_url=args.base_url,
                             discovery_method=args.method, entry_urls=args.entry_url or [],
                             include_patterns=args.include or [], exclude_patterns=args.exclude or [],
                             allowed_asset_hosts=args.asset_host or [],
                             catalog_mapping=json.loads(args.catalog_mapping) if args.catalog_mapping else None,
                             max_pages=args.max_pages, enabled=not args.disabled))
        out(args, src.to_dict(), f"added source {src.id} (policy: {src.policy_status})")
    elif args.action == "show":
        src = reg.get(args.id)
        data = src.to_dict()
        data["policy_history"] = reg.review_history("source", src.id)
        out(args, data)
    elif args.action in ("enable", "disable"):
        src = reg.set_enabled(args.id, args.action == "enable")
        out(args, src.to_dict(), f"source {src.id} {'enabled' if src.enabled else 'disabled'}")
    elif args.action == "import":
        srcs = reg.import_file(Path(args.file), replace=args.replace)
        out(args, [s.id for s in srcs], f"imported {len(srcs)} source(s): {', '.join(s.id for s in srcs)}")
    return EXIT_OK


def cmd_policy_review(app, args):
    reg = Registry(app.conn)
    if args.set:
        if args.source:
            src = reg.review_source(args.source, args.set, license=args.license,
                                    evidence_url=args.evidence_url, terms_url=args.terms_url,
                                    robots_note=args.robots_note, note=args.note, reviewer=args.reviewer)
            out(args, src.to_dict(), f"source {src.id}: policy -> {src.policy_status}")
        elif args.image:
            reg.review_image(args.image, args.set, license=args.license, evidence_url=args.evidence_url,
                             note=args.note, reviewer=args.reviewer)
            out(args, reg.latest_review("image", args.image), f"image {args.image}: policy -> {args.set}")
        else:
            raise CliError("--set needs --source or --image", EXIT_USAGE)
        return EXIT_OK
    if args.history:
        out(args, reg.review_history())
        return EXIT_OK
    # --pending (default): what still needs a decision
    sources = [s for s in reg.list() if s.policy_status in ("unknown", "review_required")]
    pending_images = []
    for row in app.conn.execute("SELECT id, source_id, url, download_status FROM image_refs ORDER BY id"):
        src = reg.get(row["source_id"])
        pol = reg.effective_image_policy(row["id"], src)
        if pol["status"] in ("unknown", "review_required"):
            pending_images.append({"id": row["id"], "source_id": row["source_id"], "url": row["url"],
                                   "policy": pol["status"], "scope": pol["scope"]})
    data = {"sources": [{"id": s.id, "policy_status": s.policy_status, "base_url": s.base_url}
                        for s in sources],
            "images_pending": len(pending_images), "images": pending_images[: args.limit]}
    lines = ["Sources awaiting policy review:"]
    lines += [f"  {s.id:<20} {s.policy_status:<16} {s.base_url}" for s in sources] or ["  (none)"]
    lines.append(f"Images whose effective policy is unknown/review_required: {len(pending_images)}")
    lines += [f"  {i['id']} [{i['source_id']}] {i['url']}" for i in pending_images[: args.limit]]
    lines.append("Set a decision with: magref policy-review --source ID --set allowed "
                 "--license LICENSE --evidence-url URL --reviewer NAME")
    out(args, data, "\n".join(lines))
    return EXIT_OK


def cmd_discover(app, args):
    from .discovery import Discoverer
    src = usable_source(app, args.source, "discovery")
    limit = min(args.limit or app.settings.max_pages_per_run, src.max_pages or 10**9)
    res = Discoverer(app.conn, app.fetcher, limit).run(src)
    status = "ok" if not res.errors else ("partial" if res.pages_found or res.images_found else "failed")
    Registry(app.conn).record_run(src.id, "discover", status, res.errors[0]["code"] if res.errors else None)
    out(args, res.as_dict(),
        f"discover {src.id}: pages found {res.pages_found} (new {res.pages_new}, already known "
        f"{res.pages_duplicate}, filtered {res.pages_filtered}); images found {res.images_found} "
        f"(new {res.images_new}); errors {len(res.errors)}"
        + "".join(f"\n  ! {e['code']}: {e['url']}" for e in res.errors[:10]))
    return EXIT_OK if status == "ok" else EXIT_PARTIAL if status == "partial" else EXIT_FAIL


def cmd_crawl(app, args):
    from .pages import Crawler
    src = usable_source(app, args.source, "crawl")
    limit = min(args.limit or app.settings.max_pages_per_run, src.max_pages or 10**9)
    res = Crawler(app.conn, app.fetcher, app.settings).run(src, limit, retry_failed=args.retry_failed)
    bad = res.failed + res.blocked
    status = "ok" if not bad else ("partial" if res.fetched else "failed")
    Registry(app.conn).record_run(src.id, "crawl", status, res.errors[0]["code"] if res.errors else None)
    out(args, res.as_dict(),
        f"crawl {src.id}: attempted {res.attempted}, fetched {res.fetched}, new {res.new_references}, "
        f"updated {res.updated_references}, duplicates {res.duplicates}, skipped {res.skipped}, "
        f"blocked {res.blocked}, failed {res.failed}; image candidates {res.images_found}"
        + "".join(f"\n  ! {e['code']}: {e['url']}" for e in res.errors[:10]))
    if res.attempted == 0:
        return EXIT_OK
    return EXIT_OK if status == "ok" else EXIT_PARTIAL if status == "partial" else EXIT_FAIL


def _job_exit(res) -> int:
    if res.failed_transient or res.failed_permanent or res.blocked:
        return EXIT_PARTIAL if (res.downloaded or res.duplicates) else EXIT_FAIL
    return EXIT_OK


def _job_text(res) -> str:
    text = (f"{res.kind} job #{res.job_id}: selected {res.selected}, downloaded {res.downloaded}, "
            f"already stored (same SHA-256) {res.duplicates}, failed transient {res.failed_transient}, "
            f"failed permanent {res.failed_permanent}, blocked {res.blocked}, bytes {res.bytes_received}"
            f"; not eligible (policy not 'allowed' or source disabled): {res.skipped_not_allowed}")
    if res.stopped_by_budget:
        text += "\n  stopped: byte budget for this run reached (raise --max-bytes to continue)"
    for item in res.items:
        if item.get("code"):
            text += f"\n  ! {item['id']} {item['outcome']} {item['code']}"
    return text


def cmd_download(app, args):
    from .downloader import Downloader
    if not args.approved:
        raise CliError("download only processes policy-approved items; pass --approved to confirm",
                       EXIT_USAGE)
    if args.source:
        usable_source(app, args.source, "download")
    res = Downloader(app.conn, app.fetcher, app.settings, app.layout).run(
        "download", limit=args.limit, max_total_bytes=args.max_bytes, source=args.source, ids=args.id)
    out(args, res.as_dict(), _job_text(res))
    return _job_exit(res)


def cmd_retry(app, args):
    from .downloader import Downloader
    if not args.failed:
        raise CliError("retry needs --failed (only transient failures are retried)", EXIT_USAGE)
    res = Downloader(app.conn, app.fetcher, app.settings, app.layout).run(
        "retry", limit=args.limit, max_total_bytes=args.max_bytes, source=args.source,
        include_missing=args.include_missing)
    out(args, res.as_dict(), _job_text(res))
    return _job_exit(res)


def cmd_reset(app, args):
    from .assets import AssetRepo
    repo = AssetRepo(app.conn)
    a = repo.get(args.id)
    if a is None:
        raise NotFound(f"asset {args.id} not found")
    if a["download_status"] not in ("failed_permanent", "blocked", "missing_file"):
        raise CliError(f"nothing to reset: status is {a['download_status']}", EXIT_USAGE)
    repo.set_status(args.id, "pending", error=None, error_class=None)
    app.conn.commit()
    out(args, {"id": args.id, "download_status": "pending"}, f"{args.id}: reset to pending")
    return EXIT_OK


def cmd_search(app, args):
    from .search import KeywordSearch, SearchQuery
    filters = {"source": args.source, "publisher": args.publisher, "category": args.category,
               "page_type": args.page_type, "language": args.language, "feature": args.feature,
               "genre": args.genre, "country": args.country, "region": args.region,
               "image_type": args.image_type, "media_type": args.media_type,
               "downloaded_only": args.downloaded_only}
    if args.years:
        filters["year_from"], filters["year_to"] = _years(args.years)
    hits = KeywordSearch(app.conn).search(SearchQuery(args.query or "", args.kind,
                                                      {k: v for k, v in filters.items() if v}, args.limit))
    lines = [f"{len(hits)} result(s) -- keyword search (not semantic)"]
    for h in hits:
        lines.append(f"{h.score:7.3f}  {h.id}  {h.title or '(untitled)'}\n         {h.url}"
                     + (f"\n         page: {h.source_page_url}" if h.source_page_url else "")
                     + f"\n         why: {'; '.join(h.explanation)}"
                     + (f"\n         missing terms: {', '.join(h.missing_terms)}" if h.missing_terms else ""))
    out(args, [h.as_dict() for h in hits], "\n".join(lines))
    return EXIT_OK


def cmd_show(app, args):
    rid = args.id or args.ref
    if not rid:
        raise CliError("give an id: magref show --id ID", EXIT_USAGE)
    if rid.startswith("mi_"):
        from .assets import AssetRepo
        from .export import image_record
        from .research import ContextRepo
        data = image_record(app.conn, rid) if AssetRepo(app.conn).get(rid) else None
        if data is not None:
            data["attempts"] = AssetRepo(app.conn).attempts(rid)
            data["contexts"] = ContextRepo(app.conn).for_asset(rid)
    else:
        from .export import page_record
        from .pages import PageRepo
        ref = PageRepo(app.conn).get(rid)
        data = page_record(app.conn, ref) if ref else None
    if data is None:
        raise NotFound(f"no reference with id or URL {rid}")
    out(args, data)
    return EXIT_OK


def cmd_verify(app, args):
    from . import maintenance
    if not (args.all or args.orphans):
        raise CliError("use --all (check files) and/or --orphans (find unrecorded files)", EXIT_USAGE)
    data = {}
    if args.all:
        data["verify"] = maintenance.verify(app.conn, app.layout, relocate=args.relocate)
    if args.orphans or args.all:
        data["orphans"] = maintenance.orphans(app.conn, app.layout)
    problems = 0
    if "verify" in data:
        v = data["verify"]
        problems += len(v["missing"]) + len(v["corrupt"]) + (0 if args.relocate else len(v["relocated"]))
    lines = []
    if "verify" in data:
        v = data["verify"]
        lines.append(f"checked {v['checked']} file(s): ok {v['ok']}, missing {len(v['missing'])}, "
                     f"corrupt {len(v['corrupt'])}, relocated {len(v['relocated'])}; assets marked "
                     f"missing_file: {v['assets_marked']}")
        lines += [f"  missing: {m['sha256'][:12]} {m['path']}" for m in v["missing"]]
        lines += [f"  corrupt: {c['sha256'][:12]} -> {c['quarantined_to']}" for c in v["corrupt"]]
        lines += [f"  relocated: {r['old']} -> {r['new']}" + ("" if args.relocate else " (run with --relocate)")
                  for r in v["relocated"]]
    o = data["orphans"]
    lines.append(f"orphan files (not in database): {len(o['orphan_files'])}; leftover temp files: "
                 f"{len(o['stale_temp_files'])}")
    lines += [f"  orphan: {p}" for p in o["orphan_files"]]
    out(args, data, "\n".join(lines))
    return EXIT_PARTIAL if problems else EXIT_OK


def cmd_repair(app, args):
    from . import maintenance
    data = maintenance.repair(app.conn, app.layout)
    out(args, data, f"repair: recovered {len(data['recovered'])}, already recorded "
                    f"{len(data['already_recorded'])}, dropped {len(data['dropped'])}")
    return EXIT_OK


def cmd_dedup(app, args):
    from . import maintenance
    data = maintenance.deduplicate(app.conn, app.layout, apply=args.apply)
    out(args, data, f"[{data['mode']}] shared files: {len(data['same_file_different_urls'])}; "
                    f"duplicate copies on disk: {len(data['duplicate_copies_on_disk'])}"
                    + (" (moved to quarantine)" if args.apply else "")
                    + f"; unrecorded files: {len(data['unrecorded_files'])}\n{data['note']}")
    return EXIT_OK


def cmd_clean_temp(app, args):
    from . import maintenance
    n = maintenance.clean_temp(app.layout)
    out(args, {"removed": n}, f"removed {n} leftover temp file(s)")
    return EXIT_OK


def cmd_export(app, args):
    from .export import build_export, write_export
    filters = {"source": args.source, "status": args.status, "publisher": args.publisher}
    if args.years:
        filters["year_from"], filters["year_to"] = _years(args.years)
    doc = build_export(app.conn, args.kind, filters)
    output = None if args.output in (None, "-") else Path(args.output)
    text = write_export(doc, output, args.format)
    if output is None:
        sys.stdout.write(text)
    else:
        print(f"exported {doc['count']} {args.kind} record(s) to {output} ({args.format}, validated)")
    return EXIT_OK


def cmd_import(app, args):
    from .export import import_file
    res = import_file(app.conn, Path(args.file))
    out(args, res, f"imported {res['kind']}: created {res['created']}, updated {res['updated']}")
    return EXIT_OK


def cmd_validate(app, args):
    from .export import validate_export_doc
    from .models import ValidationError
    try:
        doc = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError([f"cannot read {args.file}: {exc}"]) from exc
    errs = validate_export_doc(doc)
    if errs:
        raise ValidationError(errs)
    out(args, {"valid": True, "count": doc["count"], "kind": doc["kind"]},
        f"valid: {doc['count']} {doc['kind']} record(s)")
    return EXIT_OK


def cmd_schema(app, args):
    from .models import json_schema
    print(json.dumps(json_schema(), indent=2))
    return EXIT_OK


def cmd_status(app, args):
    c = app.conn
    q = lambda sql, *a: c.execute(sql, a).fetchall()  # noqa: E731
    data = {
        "database": str(app.settings.database_path), "data_dir": str(app.layout.root),
        "sources": [dict(r) for r in q("SELECT id, enabled, policy_status, last_run_kind, last_run_status, "
                                        "last_run_at, last_error FROM sources ORDER BY id")],
        "discovered_urls": {r[0]: r[1] for r in q("SELECT crawl_status, COUNT(*) FROM discovered_urls GROUP BY 1")},
        "page_references": q("SELECT COUNT(*) FROM refs")[0][0],
        "images": {r[0]: r[1] for r in q("SELECT download_status, COUNT(*) FROM image_refs GROUP BY 1")},
        "stored_files": {r[0]: r[1] for r in q("SELECT file_status, COUNT(*) FROM image_files GROUP BY 1")},
        "stored_bytes": q("SELECT COALESCE(SUM(size_bytes),0) FROM image_files")[0][0],
        "pending_journal_entries": len(app.layout.journal_entries()),
        "recent_errors": [dict(r) for r in q("SELECT occurred_at, source_id, target_kind, stage, code, "
                                              "error_class, url FROM processing_errors ORDER BY id DESC LIMIT 10")],
        "last_jobs": [dict(r) for r in q("SELECT id, kind, status, started_at, finished_at FROM download_jobs "
                                          "ORDER BY id DESC LIMIT 5")],
        "research": {"genres": q("SELECT COUNT(*) FROM genres")[0][0],
                     "contexts": q("SELECT COUNT(*) FROM context_records")[0][0],
                     "claims_needing_review": q("SELECT COUNT(*) FROM research_claims WHERE "
                                                "verification_status IN ('unverified','hypothesis')")[0][0],
                     "projects": q("SELECT COUNT(*) FROM design_projects")[0][0]},
    }
    lines = [f"database: {data['database']}", f"data dir: {data['data_dir']}", "sources:"]
    lines += [f"  {s['id']:<20} enabled={s['enabled']} policy={s['policy_status']} last={s['last_run_kind'] or '-'}"
              f" {s['last_run_status'] or ''} {s['last_error'] or ''}" for s in data["sources"]] or ["  (none)"]
    lines.append(f"discovered URLs: {data['discovered_urls'] or '{}'}")
    lines.append(f"page references: {data['page_references']}")
    lines.append(f"images: {data['images'] or '{}'}")
    lines.append(f"stored files: {data['stored_files'] or '{}'} ({data['stored_bytes']} bytes)")
    if data["pending_journal_entries"]:
        lines.append(f"!! {data['pending_journal_entries']} interrupted download(s): run `magref repair`")
    lines.append(f"research: {data['research']}")
    lines.append("recent errors:")
    lines += [f"  {e['occurred_at']} {e['source_id'] or '-'} {e['target_kind']}/{e['stage']} {e['code']} "
              f"{e['error_class'] or ''} {e['url'] or ''}" for e in data["recent_errors"]] or ["  (none)"]
    out(args, data, "\n".join(lines))
    return EXIT_OK


# --------------------------------------------------------------------------- research platform

def cmd_analyze(app, args):
    from . import analysis
    if args.id:
        results = [analysis.analyze_asset(app.conn, app.layout, i) for i in args.id]
    else:
        results = analysis.analyze_pending(app.conn, app.layout, limit=args.limit, redo=args.redo)
    failed = [r for r in results if r["status"] == "failed"]
    out(args, results, f"analyzed {len(results)} asset(s): "
                       f"{sum(r['status'] == 'measured' for r in results)} measured, {len(failed)} failed, "
                       f"{sum(r['status'] == 'not_applicable' for r in results)} without a file")
    return EXIT_PARTIAL if failed else EXIT_OK


def cmd_asset(app, args):
    from .assets import AssetRepo
    from .research import GenreRepo
    repo = AssetRepo(app.conn)
    if repo.get(args.id) is None:
        raise NotFound(f"asset {args.id} not found")
    if args.action == "set":
        fields = {k: getattr(args, k) for k in ("title", "description", "creator", "publication_date",
                                                "creation_date", "upload_date", "year_start", "year_end",
                                                "year_basis", "country", "region", "media_type",
                                                "image_type", "review_status") if getattr(args, k) is not None}
        try:
            data = repo.update_metadata(args.id, **fields)
        except ValueError as exc:
            raise CliError(str(exc), EXIT_INVALID) from exc
        out(args, data, f"updated {args.id}: {', '.join(fields) or 'nothing'}")
    elif args.action == "genre":
        g = GenreRepo(app.conn)
        for name in args.add or []:
            g.link_asset(args.id, g.ensure(name), "human")
        for name in args.remove or []:
            row = g.get(name)
            if row:
                g.unlink_asset(args.id, row["id"])
        out(args, repo.genres(args.id), "genres: " + ", ".join(x["name"] for x in repo.genres(args.id)))
    return EXIT_OK


def cmd_genre(app, args):
    from .research import GenreRepo
    g = GenreRepo(app.conn)
    if args.action == "add":
        gid = g.ensure(args.name, args.description)
        out(args, g.get(gid), f"genre #{gid}: {args.name}")
    else:
        rows = g.all()
        by_id = {r["id"]: r for r in rows}
        out(args, rows, "\n".join(
            f"#{r['id']:<4} {r['name']:<30} parent={by_id[r['parent_id']]['name'] if r['parent_id'] else '-'} "
            f"assets={r['asset_count']}" for r in rows) or "(no genres)")
    return EXIT_OK


def cmd_feature(app, args):
    from .research import FeatureRepo
    repo = FeatureRepo(app.conn)
    if args.action == "add":
        fid = repo.add_semantic(args.id, args.type, args.value, origin=args.origin,
                                method=args.method or ("manual annotation" if args.origin == "human"
                                                       else "model suggestion"),
                                tool=args.tool, confidence=args.confidence, evidence_note=args.note,
                                reviewer=args.reviewer)
        out(args, {"id": fid}, f"feature #{fid} recorded ({'human_entered' if args.origin == 'human' else 'ai_suggested'})")
    elif args.action == "review":
        row = repo.review(args.feature_id, "accept" if args.accept else "reject", args.reviewer, args.note)
        out(args, row, f"feature #{row['id']}: {row['review_status']}")
    else:
        rows = repo.for_asset(args.id, include_rejected=True)
        out(args, rows, "\n".join(f"#{r['id']:<5} {r['kind']:<9} {r['feature_type']:<20} {r['feature_value'][:60]:<60} "
                                  f"{r['review_status']} ({r['tool'] or r['method']})" for r in rows) or "(no features)")
    return EXIT_OK


def cmd_research(app, args):
    from .research import ClaimRepo, ContextRepo, ResearchSourceRepo
    if args.action == "source-add":
        sid = ResearchSourceRepo(app.conn).add(args.title, args.type, author=args.author,
                                               publisher=args.publisher, publication_date=args.date,
                                               url=args.url, identifier=args.identifier,
                                               accessed_at=args.accessed_at, notes=args.notes)
        out(args, {"id": sid}, f"research source #{sid}")
    elif args.action == "sources":
        rows = ResearchSourceRepo(app.conn).all()
        out(args, rows, "\n".join(f"#{r['id']:<4} [{r['source_type']}] {r['title']} {r['url'] or ''}" for r in rows)
            or "(no research sources)")
    elif args.action == "claim-add":
        cid = ClaimRepo(app.conn).add(args.text, args.type, context_id=args.context,
                                      alternative_explanations=args.alternatives)
        out(args, {"id": cid}, f"claim #{cid} (unverified)")
    elif args.action == "claim-link":
        ClaimRepo(app.conn).link_source(args.claim, args.source, args.relation, args.access,
                                        locator=args.locator, quote=args.quote, note=args.note)
        out(args, ClaimRepo(app.conn).get(args.claim), f"claim #{args.claim} <- source #{args.source} "
                                                       f"({args.relation}, read: {args.access})")
    elif args.action == "claim-review":
        c = ClaimRepo(app.conn).set_status(args.claim, args.status, reviewer=args.reviewer,
                                           confidence=args.confidence,
                                           alternative_explanations=args.alternatives)
        out(args, c, f"claim #{c['id']}: {c['verification_status']}")
    elif args.action == "claim-show":
        c = ClaimRepo(app.conn).get(args.claim)
        if c is None:
            raise NotFound(f"claim {args.claim} not found")
        c["allowed_statuses"] = ClaimRepo(app.conn).allowed_statuses(args.claim)
        out(args, c)
    elif args.action == "context-add":
        cid = ContextRepo(app.conn).add(args.title, args.description, args.type, start_year=args.start,
                                        end_year=args.end, period_precision=args.precision,
                                        country=args.country, region=args.region,
                                        related_people=args.person, genres=args.genre,
                                        alternative_interpretations=args.alternatives)
        out(args, {"id": cid}, f"context #{cid} (unverified)")
    elif args.action == "context-source":
        ContextRepo(app.conn).link_source(args.context, args.source, args.note)
        out(args, {"ok": True}, f"context #{args.context} <- source #{args.source}")
    elif args.action == "context-review":
        c = ContextRepo(app.conn).set_status(args.context, args.status, reviewer=args.reviewer)
        out(args, c, f"context #{c['id']}: {c['verification_status']}")
    elif args.action == "context-show":
        c = ContextRepo(app.conn).get(args.context)
        if c is None:
            raise NotFound(f"context {args.context} not found")
        out(args, c)
    elif args.action == "contexts":
        rows = ContextRepo(app.conn).search(args.text, country=args.country)
        out(args, rows, "\n".join(f"#{r['id']:<4} {r['start_year'] or '?'}-{r['end_year'] or '?'} "
                                  f"[{r['verification_status']}] {r['title']}" for r in rows) or "(no contexts)")
    elif args.action == "relate":
        r = ContextRepo(app.conn).relate_asset(args.asset, args.context, args.relation,
                                               explanation=args.explanation, claim_id=args.claim)
        out(args, r, f"{args.asset} -[{args.relation}, {r['evidence_status']}]-> context #{args.context}")
    return EXIT_OK


def cmd_trend(app, args):
    from . import trends
    filters = {"genre": args.genre, "country": args.country, "region": args.region,
               "source": args.source, "media_type": args.media_type}
    kw = dict(include_ai=args.include_ai, min_sample=args.min_sample)
    if args.action == "compare":
        res = trends.compare_periods(app.conn, args.feature, _years(args.a), _years(args.b), **kw, **filters)
        if args.save:
            res["observation_id"] = trends.save_observation(app.conn, res, args.save)
        text = res["statement"]
    elif args.action == "frequency":
        res = trends.frequency_by(app.conn, args.feature, args.by, **kw, **filters)
        text = "\n".join(f"{g['group']:<24} n={g['sample_size']:<4} with feature={g['with_feature']:<4} "
                         f"{'' if g['sufficient'] else '(insufficient) '}"
                         + ", ".join(f"{v['value']} {v['share']:.0%}" for v in g["values"][:5])
                         for g in res["groups"]) or "(no data)"
    elif args.action == "emergence":
        res = trends.emergence(app.conn, args.feature, args.value, bucket=args.bucket, **kw, **filters)
        text = "\n".join(f"{s['from']}-{s['to']}: {s['matches']}/{s['with_feature']} "
                         f"({s['share']:.0%}){'' if s['sufficient'] else ' insufficient'}" for s in res["series"])
        text = (text or "(no dated assets with this feature)") + f"\n{res['note']}"
    elif args.action == "common":
        res = trends.common_features(app.conn, [g.strip() for g in args.genres.split(",")], args.feature,
                                     threshold=args.threshold, **kw,
                                     **{k: v for k, v in filters.items() if k != "genre"})
        text = ("common: " + ", ".join(c["value"] for c in res["common"])) if res["common"] else \
            "no feature value reaches the threshold in every genre"
        text += f"\n{res['note']}"
    else:
        y = _years(args.years) if args.years else (None, None)
        res = trends.timeline(app.conn, year_from=y[0], year_to=y[1], bucket=args.bucket, **filters)
        text = "\n".join(f"{r['from']}-{r['to']}: {r['count']} asset(s) {r['sources']}" for r in res["rows"]) \
            or "(no dated assets)"
    out(args, res, text + "\nLimitations:\n" + "\n".join(f"- {x}" for x in res.get("limitations", [])))
    return EXIT_OK


def cmd_project(app, args):
    from .projects import ProjectRepo
    repo = ProjectRepo(app.conn)
    if args.action == "create":
        pid = repo.create(args.title, brief=args.brief, target_audience=args.audience, medium=args.medium,
                          constraints=args.constraints, excluded_styles=args.exclude,
                          direction_notes=args.direction, reference_genres=args.genre or [],
                          reference_periods=args.period or [], reference_regions=args.region or [])
        out(args, repo.get(pid), f"project #{pid}: {args.title}")
    elif args.action == "list":
        rows = repo.all()
        out(args, rows, "\n".join(f"#{r['id']:<4} {r['title']} ({r['asset_count']} references)" for r in rows)
            or "(no projects)")
    elif args.action == "show":
        out(args, repo.get(args.project))
    elif args.action == "add-asset":
        for aid in args.asset:
            repo.add_asset(args.project, aid, args.group, args.note)
        out(args, repo.get(args.project)["assets"], f"added {len(args.asset)} reference(s)")
    elif args.action == "add-context":
        repo.add_context(args.project, args.context, args.note)
        out(args, {"ok": True}, f"context #{args.context} linked")
    elif args.action == "add-feature":
        repo.add_feature(args.project, args.feature_type, args.feature_value, args.note)
        out(args, {"ok": True}, "feature noted")
    elif args.action == "note":
        nid = repo.add_note(args.project, args.text)
        out(args, {"id": nid}, f"note #{nid}")
    elif args.action == "report":
        rid, content = repo.save_report(args.project, args.format)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(content, encoding="utf-8")
            print(f"report #{rid} written to {args.output}")
        else:
            sys.stdout.write(content)
    return EXIT_OK


def cmd_serve(app, args):
    from .web import serve
    serve(app, args.host, args.port)
    return EXIT_OK


# --------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="magref", description="Visual Culture Research Platform -- "
                                "magazine/visual reference collection, research and planning.")
    p.add_argument("--version", action="version", version=f"magref {__version__}")
    p.add_argument("--env-file", help="KEY=VALUE file (default: ./.env if present)")
    p.add_argument("--data-dir", help="data root (overrides MAGREF_DATA_DIR / VC_ARCHIVE_DIR)")
    p.add_argument("--db", help="SQLite path (default: <data-dir>/database/references.sqlite3)")
    p.add_argument("--fixtures", help="serve all HTTP from this local fixture directory (offline mode)")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create or migrate the database and data directories")

    s = sub.add_parser("source", help="source registry")
    ss = s.add_subparsers(dest="action", required=True)
    ss.add_parser("list")
    a = ss.add_parser("add")
    a.add_argument("--id", required=True)
    a.add_argument("--name", required=True)
    a.add_argument("--base-url", required=True)
    a.add_argument("--method", required=True, choices=("sitemap", "rss", "html", "json_catalog"))
    a.add_argument("--entry-url", action="append", help="sitemap/feed/catalog/start page URL (repeatable)")
    a.add_argument("--include", action="append", help="regex a page URL must match (repeatable)")
    a.add_argument("--exclude", action="append", help="regex that excludes a page URL (repeatable)")
    a.add_argument("--asset-host", action="append", help="extra host allowed for image downloads")
    a.add_argument("--catalog-mapping", help="JSON object for json_catalog field paths")
    a.add_argument("--max-pages", type=int)
    a.add_argument("--disabled", action="store_true")
    for name in ("show", "enable", "disable"):
        ss.add_parser(name).add_argument("id")
    i = ss.add_parser("import")
    i.add_argument("file")
    i.add_argument("--replace", action="store_true", help="update sources that already exist")

    pr = sub.add_parser("policy-review", help="list pending policy decisions or record one")
    pr.add_argument("--pending", action="store_true", help="list items awaiting review (default)")
    pr.add_argument("--history", action="store_true")
    pr.add_argument("--source")
    pr.add_argument("--image")
    pr.add_argument("--set", choices=("unknown", "review_required", "allowed", "restricted"))
    pr.add_argument("--license")
    pr.add_argument("--evidence-url")
    pr.add_argument("--terms-url")
    pr.add_argument("--robots-note")
    pr.add_argument("--note")
    pr.add_argument("--reviewer")
    pr.add_argument("--limit", type=int, default=50)

    d = sub.add_parser("discover", help="find page/image URLs for a source")
    d.add_argument("--source", required=True)
    d.add_argument("--limit", type=int)
    c = sub.add_parser("crawl", help="fetch discovered pages and extract metadata")
    c.add_argument("--source", required=True)
    c.add_argument("--limit", type=int)
    c.add_argument("--retry-failed", action="store_true")

    dl = sub.add_parser("download", help="download image files whose policy is 'allowed'")
    dl.add_argument("--approved", action="store_true", help="required: confirm policy-approved only")
    dl.add_argument("--limit", type=int)
    dl.add_argument("--max-bytes", type=int, help="total byte budget for this run")
    dl.add_argument("--source")
    dl.add_argument("--id", action="append")
    rt = sub.add_parser("retry", help="retry transient download failures")
    rt.add_argument("--failed", action="store_true")
    rt.add_argument("--include-missing", action="store_true", help="also re-download missing/corrupt files")
    rt.add_argument("--limit", type=int)
    rt.add_argument("--max-bytes", type=int)
    rt.add_argument("--source")
    rs = sub.add_parser("reset", help="explicitly reset a permanently failed/blocked image to pending")
    rs.add_argument("--id", required=True)

    se = sub.add_parser("search", help="keyword search (deterministic, not semantic)")
    se.add_argument("--query", "-q", default="")
    se.add_argument("--kind", choices=("images", "pages"), default="images")
    se.add_argument("--limit", type=int, default=20)
    for f in ("source", "publisher", "category", "page-type", "language", "feature", "genre", "country",
              "region", "image-type", "media-type"):
        se.add_argument(f"--{f}")
    se.add_argument("--years", help="e.g. 1990-1999 (undated assets are excluded)")
    se.add_argument("--downloaded-only", action="store_true")

    sh = sub.add_parser("show", help="show one page (mr_) or image (mi_) record")
    sh.add_argument("ref", nargs="?")
    sh.add_argument("--id")

    v = sub.add_parser("verify", help="check stored files against the database")
    v.add_argument("--all", action="store_true")
    v.add_argument("--orphans", action="store_true")
    v.add_argument("--relocate", action="store_true", help="accept files found under the current data dir")
    sub.add_parser("repair", help="recover downloads interrupted between file move and DB commit")
    dd = sub.add_parser("deduplicate", help="report (default) or quarantine duplicate copies")
    g = dd.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--apply", action="store_true")
    sub.add_parser("clean-temp", help="delete leftover partial downloads")

    e = sub.add_parser("export", help="validated JSON export")
    e.add_argument("--format", choices=("json", "jsonl"), default="json")
    e.add_argument("--kind", choices=("images", "pages"), default="images")
    e.add_argument("--output", "-o")
    e.add_argument("--source")
    e.add_argument("--status")
    e.add_argument("--publisher")
    e.add_argument("--years")
    sub.add_parser("import", help="validate and import an export file").add_argument("file")
    sub.add_parser("validate", help="validate an export file").add_argument("file")
    sub.add_parser("schema", help="print the JSON Schema of magazine_reference/1")
    sub.add_parser("status", help="counts, last runs, recent errors")

    an = sub.add_parser("analyze", help="measure visual features from stored files")
    an.add_argument("--id", action="append")
    an.add_argument("--limit", type=int, default=100)
    an.add_argument("--redo", action="store_true")

    asx = sub.add_parser("asset", help="edit asset metadata / genres")
    asub = asx.add_subparsers(dest="action", required=True)
    st = asub.add_parser("set")
    st.add_argument("--id", required=True)
    for f in ("title", "description", "creator", "publication-date", "creation-date", "upload-date",
              "country", "region"):
        st.add_argument(f"--{f}")
    st.add_argument("--year-start", type=int)
    st.add_argument("--year-end", type=int)
    st.add_argument("--year-basis", choices=("publication", "creation", "circa", "source_declared"))
    st.add_argument("--media-type")
    st.add_argument("--image-type")
    st.add_argument("--review-status", choices=("unreviewed", "reviewed", "needs_attention"))
    gg = asub.add_parser("genre")
    gg.add_argument("--id", required=True)
    gg.add_argument("--add", action="append")
    gg.add_argument("--remove", action="append")

    ge = sub.add_parser("genre", help="genre taxonomy")
    gsub = ge.add_subparsers(dest="action", required=True)
    gsub.add_parser("list")
    ga = gsub.add_parser("add")
    ga.add_argument("name", help="'parent/child' creates both")
    ga.add_argument("--description")

    fe = sub.add_parser("feature", help="semantic features and reviews")
    fsub = fe.add_subparsers(dest="action", required=True)
    fa = fsub.add_parser("add")
    fa.add_argument("--id", required=True)
    fa.add_argument("--type", required=True)
    fa.add_argument("--value", required=True)
    fa.add_argument("--origin", choices=("human", "ai"), required=True)
    fa.add_argument("--tool", help="model/tool name (required for --origin ai)")
    fa.add_argument("--method")
    fa.add_argument("--confidence", type=float)
    fa.add_argument("--note")
    fa.add_argument("--reviewer")
    fr = fsub.add_parser("review")
    fr.add_argument("--feature-id", type=int, required=True)
    grp = fr.add_mutually_exclusive_group(required=True)
    grp.add_argument("--accept", action="store_true")
    grp.add_argument("--reject", action="store_true")
    fr.add_argument("--reviewer", required=True)
    fr.add_argument("--note")
    fsub.add_parser("list").add_argument("--id", required=True)

    re_ = sub.add_parser("research", help="sources, claims, context records")
    rsub = re_.add_subparsers(dest="action", required=True)
    x = rsub.add_parser("source-add")
    x.add_argument("--title", required=True)
    x.add_argument("--type", required=True)
    for f in ("author", "publisher", "date", "url", "identifier", "accessed-at", "notes"):
        x.add_argument(f"--{f}")
    rsub.add_parser("sources")
    x = rsub.add_parser("claim-add")
    x.add_argument("--text", required=True)
    x.add_argument("--type", required=True)
    x.add_argument("--context", type=int)
    x.add_argument("--alternatives")
    x = rsub.add_parser("claim-link")
    x.add_argument("--claim", type=int, required=True)
    x.add_argument("--source", type=int, required=True)
    x.add_argument("--relation", required=True, choices=("supports", "partially_supports", "contradicts", "mentions"))
    x.add_argument("--access", required=True, choices=("title_only", "abstract", "excerpt", "full_text"))
    x.add_argument("--locator")
    x.add_argument("--quote")
    x.add_argument("--note")
    x = rsub.add_parser("claim-review")
    x.add_argument("--claim", type=int, required=True)
    x.add_argument("--status", required=True)
    x.add_argument("--reviewer", required=True)
    x.add_argument("--confidence", type=float)
    x.add_argument("--alternatives")
    rsub.add_parser("claim-show").add_argument("--claim", type=int, required=True)
    x = rsub.add_parser("context-add")
    x.add_argument("--title", required=True)
    x.add_argument("--description", required=True)
    x.add_argument("--type", required=True)
    x.add_argument("--start", type=int)
    x.add_argument("--end", type=int)
    x.add_argument("--precision", default="approximate", choices=("exact", "approximate", "unknown"))
    x.add_argument("--country")
    x.add_argument("--region")
    x.add_argument("--person", action="append")
    x.add_argument("--genre", action="append")
    x.add_argument("--alternatives")
    x = rsub.add_parser("context-source")
    x.add_argument("--context", type=int, required=True)
    x.add_argument("--source", type=int, required=True)
    x.add_argument("--note")
    x = rsub.add_parser("context-review")
    x.add_argument("--context", type=int, required=True)
    x.add_argument("--status", required=True)
    x.add_argument("--reviewer", required=True)
    rsub.add_parser("context-show").add_argument("--context", type=int, required=True)
    x = rsub.add_parser("contexts")
    x.add_argument("--text")
    x.add_argument("--country")
    x = rsub.add_parser("relate")
    x.add_argument("--asset", required=True)
    x.add_argument("--context", type=int, required=True)
    x.add_argument("--relation", required=True)
    x.add_argument("--explanation")
    x.add_argument("--claim", type=int)

    tr = sub.add_parser("trend", help="descriptive comparisons over this collection")
    tsub = tr.add_subparsers(dest="action", required=True)
    common_args = argparse.ArgumentParser(add_help=False)
    for f in ("genre", "country", "region", "source", "media-type"):
        common_args.add_argument(f"--{f}")
    common_args.add_argument("--include-ai", action="store_true", help="also count unreviewed AI suggestions")
    common_args.add_argument("--min-sample", type=int, default=10)
    x = tsub.add_parser("compare", parents=[common_args])
    x.add_argument("--feature", required=True)
    x.add_argument("--a", required=True, help="period A, e.g. 1980-1989")
    x.add_argument("--b", required=True, help="period B, e.g. 2010-2019")
    x.add_argument("--save", metavar="TITLE", help="store as a trend observation (unverified)")
    x = tsub.add_parser("frequency", parents=[common_args])
    x.add_argument("--feature", required=True)
    x.add_argument("--by", required=True, choices=("genre", "country", "region", "decade", "source"))
    x = tsub.add_parser("emergence", parents=[common_args])
    x.add_argument("--feature", required=True)
    x.add_argument("--value", required=True)
    x.add_argument("--bucket", type=int, default=10)
    x = tsub.add_parser("common", parents=[common_args])
    x.add_argument("--genres", required=True, help="comma-separated")
    x.add_argument("--feature", required=True)
    x.add_argument("--threshold", type=float, default=0.5)
    x = tsub.add_parser("timeline", parents=[common_args])
    x.add_argument("--years")
    x.add_argument("--bucket", type=int, default=10)

    pj = sub.add_parser("project", help="design planning workspace")
    psub = pj.add_subparsers(dest="action", required=True)
    x = psub.add_parser("create")
    x.add_argument("--title", required=True)
    for f in ("brief", "audience", "medium", "constraints", "exclude", "direction"):
        x.add_argument(f"--{f}")
    x.add_argument("--genre", action="append")
    x.add_argument("--period", action="append")
    x.add_argument("--region", action="append")
    psub.add_parser("list")
    psub.add_parser("show").add_argument("--project", type=int, required=True)
    x = psub.add_parser("add-asset")
    x.add_argument("--project", type=int, required=True)
    x.add_argument("--asset", action="append", required=True)
    x.add_argument("--group", default="default")
    x.add_argument("--note")
    x = psub.add_parser("add-context")
    x.add_argument("--project", type=int, required=True)
    x.add_argument("--context", type=int, required=True)
    x.add_argument("--note")
    x = psub.add_parser("add-feature")
    x.add_argument("--project", type=int, required=True)
    x.add_argument("--feature-type", required=True)
    x.add_argument("--feature-value", required=True)
    x.add_argument("--note")
    x = psub.add_parser("note")
    x.add_argument("--project", type=int, required=True)
    x.add_argument("--text", required=True)
    x = psub.add_parser("report")
    x.add_argument("--project", type=int, required=True)
    x.add_argument("--format", choices=("markdown", "json", "html"), default="markdown")
    x.add_argument("--output", "-o")

    sv = sub.add_parser("serve", help="local web UI (binds 127.0.0.1 by default)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8765)
    return p


HANDLERS = {
    "init": cmd_init, "source": cmd_source, "policy-review": cmd_policy_review, "discover": cmd_discover,
    "crawl": cmd_crawl, "download": cmd_download, "retry": cmd_retry, "reset": cmd_reset,
    "search": cmd_search, "show": cmd_show, "verify": cmd_verify, "repair": cmd_repair,
    "deduplicate": cmd_dedup, "clean-temp": cmd_clean_temp, "export": cmd_export, "import": cmd_import,
    "validate": cmd_validate, "schema": cmd_schema, "status": cmd_status, "analyze": cmd_analyze,
    "asset": cmd_asset, "genre": cmd_genre, "feature": cmd_feature, "research": cmd_research,
    "trend": cmd_trend, "project": cmd_project, "serve": cmd_serve,
}


def main(argv: list[str] | None = None, transport=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_settings(env_file=Path(args.env_file) if args.env_file else None)
        overrides = {}
        if args.data_dir:
            overrides["data_dir"] = Path(args.data_dir).expanduser()
        if args.db:
            overrides["db_path"] = Path(args.db).expanduser()
        if args.fixtures:
            fx = Path(args.fixtures)
            if not fx.is_dir():
                raise ConfigError(f"fixture directory not found: {fx}")
            overrides["fixture_dir"] = fx
        settings = settings.with_overrides(**overrides)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    setup_logging("DEBUG" if args.verbose else settings.log_level,
                  Path(settings.data_dir).expanduser() / "logs" / "magref.log")
    app = None
    try:
        app = open_app(settings, transport=transport)
        return HANDLERS[args.command](app, args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except (NotFound, KeyError) as exc:
        print(f"not found: {str(exc).strip(chr(39))}", file=sys.stderr)
        return EXIT_NOT_FOUND
    except RegistryError as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 -- map known families, report the rest
        from .models import ValidationError
        from .projects import ProjectError
        from .research import RuleError
        from .assets import InvalidTransition
        if isinstance(exc, ValidationError):
            print("validation failed:", file=sys.stderr)
            for e in exc.errors[:50]:
                print(f"  - {e}", file=sys.stderr)
            return EXIT_INVALID
        if isinstance(exc, RuleError):
            print(f"refused: {exc}", file=sys.stderr)
            return EXIT_POLICY
        if isinstance(exc, ProjectError):
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_NOT_FOUND if "not found" in str(exc) else EXIT_USAGE
        if isinstance(exc, InvalidTransition):
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        log.exception("unexpected error")
        print(f"unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_FAIL
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
