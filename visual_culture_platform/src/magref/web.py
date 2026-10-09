"""Local web UI (standard library only: http.server + server-rendered HTML).

Why this technology: the repository had no UI, the Antigravity VM must run
the project without a JavaScript toolchain, and every screen is a view over
SQLite queries that already exist for the CLI. Server-rendered pages keep one
code path, are testable with plain HTTP requests, and need no build step.

Safety: binds 127.0.0.1 by default; all output is HTML-escaped; image bytes are
served only for downloaded assets, by asset ID (paths come from the database
and are resolved inside the data root); POST requests must come from the same
host (Origin/Referer check); a restrictive Content-Security-Policy is sent.
Requests are serialized (one SQLite connection).
"""
from __future__ import annotations

import html
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .assets import AssetRepo
from .registry import Registry
from .research import ClaimRepo, ContextRepo, FeatureRepo, GenreRepo
from .search import KeywordSearch, SearchQuery
from .storage import StorageError

E = html.escape
STATUS_CLASS = {"verified": "ok", "partially_supported": "warn", "hypothesis": "warn",
                "unverified": "bad", "contradicted": "bad", "allowed": "ok", "restricted": "bad",
                "unknown": "bad", "review_required": "warn"}
CSS = """
:root{--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e6;--bg:#fafafa;--ok:#1f7a3a;--warn:#9a6700;--bad:#b42318}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,sans-serif;color:var(--fg);background:var(--bg)}
header{background:#111;color:#fff;padding:.6rem 1rem;display:flex;gap:1rem;flex-wrap:wrap;align-items:center}
header a{color:#fff;text-decoration:none;opacity:.85}header a:hover{opacity:1}header b{margin-right:1rem}
main{max-width:1180px;margin:0 auto;padding:1rem}h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:1.6rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0}td,th{border-bottom:1px solid var(--line);padding:.35rem .5rem;text-align:left;vertical-align:top}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:.8rem}
.card{background:#fff;border:1px solid var(--line);border-radius:6px;padding:.5rem;font-size:.85rem;overflow-wrap:anywhere}
.card img,.thumb{width:100%;height:140px;object-fit:contain;background:#f0f0f2;display:block}
.nofile{height:140px;display:flex;align-items:center;justify-content:center;background:#f0f0f2;color:var(--muted);text-align:center;font-size:.8rem;padding:.5rem}
.badge{display:inline-block;padding:0 .4rem;border-radius:3px;font-size:.75rem;border:1px solid currentColor}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.muted{color:var(--muted)}
.bar{background:#c9c9cf;height:.8rem;display:inline-block;vertical-align:middle}
form.inline{display:flex;gap:.4rem;flex-wrap:wrap;align-items:end;margin:.5rem 0}
input,select,textarea{font:inherit;padding:.3rem;border:1px solid #c9c9cf;border-radius:4px}textarea{width:100%;min-height:4rem}
.notice{background:#fff8e6;border:1px solid #f0d58c;padding:.5rem .8rem;border-radius:4px;margin:.6rem 0}
.empty{color:var(--muted);font-style:italic}
"""


def badge(status: str | None) -> str:
    s = status or "unknown"
    return f'<span class="badge {STATUS_CLASS.get(s, "muted")}">{E(s)}</span>'


def pct(x: float | None, signed: bool = False) -> str:
    if x is None:
        return ""
    return format(x, "+.0%" if signed else ".0%")


def years(a: dict) -> str:
    if a.get("year_start") is None:
        return '<span class="muted">year unknown</span>'
    y = str(a["year_start"]) if a["year_start"] == a["year_end"] else f"{a['year_start']}-{a['year_end']}"
    return E(y) + (f' <span class="muted">({E(a["year_basis"])})</span>' if a.get("year_basis") else "")


def thumb(a: dict) -> str:
    if a.get("download_status") == "downloaded":
        return (f'<img src="/thumb/{E(a["id"])}" alt="{E(a.get("alt") or a.get("title") or "image")}" '
                f'loading="lazy">')
    return f'<div class="nofile">no local file<br>({E(a.get("download_status") or "pending")})</div>'


class UI:
    def __init__(self, app):
        self.app = app
        self.conn = app.conn
        self.lock = threading.Lock()

    def page(self, title: str, body: str) -> str:
        nav = "".join(f'<a href="{h}">{t}</a>' for h, t in (
            ("/", "Dashboard"), ("/explore", "Explore"), ("/timeline", "Timeline"),
            ("/trends", "Trend comparison"), ("/contexts", "Context explorer"), ("/projects", "Design workspace")))
        return (f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' "
                f"content='width=device-width,initial-scale=1'><title>{E(title)} - Visual Culture Research</title>"
                f"<style>{CSS}</style><header><b>Visual Culture Research</b>{nav}</header><main>{body}</main></html>")

    # -- screens -------------------------------------------------------------------
    def dashboard(self, q) -> str:
        c = self.conn
        total = c.execute("SELECT COUNT(*) FROM image_refs").fetchone()[0]
        stored = c.execute("SELECT COUNT(*) FROM image_refs WHERE download_status='downloaded'").fetchone()[0]
        decades = c.execute("""SELECT (year_start/10)*10 AS d, COUNT(*) FROM image_refs WHERE year_start IS NOT NULL
                               GROUP BY d ORDER BY d""").fetchall()
        undated = c.execute("SELECT COUNT(*) FROM image_refs WHERE year_start IS NULL").fetchone()[0]
        genres = GenreRepo(c).all()
        recent = [dict(r) for r in c.execute("SELECT * FROM image_refs ORDER BY discovered_at DESC, id LIMIT 8")]
        pending_analysis = c.execute("SELECT COUNT(*) FROM image_refs WHERE download_status='downloaded' "
                                     "AND analysis_status='pending'").fetchone()[0]
        claims = ClaimRepo(c).pending_review()
        policy = [s for s in Registry(c).list() if s.policy_status in ("unknown", "review_required")]
        mx = max([n for _, n in decades] + [1])
        body = [f"<h1>Dashboard</h1><p>{total} asset record(s), {stored} with a stored file. "
                f"{undated} without a known year (not placed on the timeline).</p>"]
        if total == 0:
            body.append("<p class='empty'>No assets yet. Run <code>magref discover</code> and "
                        "<code>magref download --approved</code>.</p>")
        body.append("<h2>Assets by decade</h2><table>" + "".join(
            f"<tr><td>{d}s</td><td><span class='bar' style='width:{int(300 * n / mx)}px'></span> {n}</td></tr>"
            for d, n in decades) + "</table>" if decades else "<h2>Assets by decade</h2><p class='empty'>no dated assets</p>")
        body.append("<h2>Assets by genre</h2>" + ("<table>" + "".join(
            f"<tr><td><a href='/explore?genre={E(g['name'])}'>{E(g['name'])}</a></td><td>{g['asset_count']}</td></tr>"
            for g in genres) + "</table>" if genres else "<p class='empty'>no genres</p>"))
        body.append("<h2>Recently collected</h2><div class='grid'>" + "".join(self.card(a) for a in recent)
                    + "</div>" if recent else "")
        body.append(f"<h2>Waiting</h2><ul><li>{pending_analysis} downloaded asset(s) waiting for analysis "
                    f"(<code>magref analyze</code>)</li><li>{len(policy)} source(s) awaiting policy review: "
                    + ", ".join(f"{E(s.id)} {badge(s.policy_status)}" for s in policy)
                    + f"</li><li>{len(claims)} claim(s) unverified or hypothesis</li></ul>")
        if claims:
            body.append("<table>" + "".join(f"<tr><td>#{x['id']}</td><td>{E(x['claim_text'])}</td>"
                                            f"<td>{badge(x['verification_status'])}</td></tr>" for x in claims[:10])
                        + "</table>")
        return self.page("Dashboard", "".join(body))

    def card(self, a: dict) -> str:
        return (f"<div class='card'><a href='/asset/{E(a['id'])}'>{thumb(a)}</a>"
                f"<div><a href='/asset/{E(a['id'])}'>{E(a.get('title') or a.get('alt') or a['id'])}</a></div>"
                f"<div>{years(a)} &middot; {E(a.get('country') or 'country unknown')}</div>"
                f"<div class='muted'>{E(a['image_type'])} ({E(a['type_status'])})</div></div>")

    def explore(self, q) -> str:
        g = lambda k: (q.get(k) or [""])[0].strip()  # noqa: E731
        filters = {k: g(k) for k in ("genre", "country", "region", "feature", "source", "media_type")
                   if g(k)}
        err = ""
        if g("years"):
            try:
                a, _, b = g("years").partition("-")
                filters["year_from"], filters["year_to"] = int(a), int(b or a)
            except ValueError:
                err = "<div class='notice'>Year range must look like 1990-1999.</div>"
        hits = KeywordSearch(self.conn).search(SearchQuery(g("q"), "images", filters, 120))
        repo = AssetRepo(self.conn)
        form = ("<form class='inline' method='get'>"
                + "".join(f"<label>{lab}<br><input name='{k}' value='{E(g(k))}' size='{w}'></label>"
                          for k, lab, w in (("q", "keywords", 24), ("genre", "genre", 14), ("years", "years", 10),
                                            ("country", "country", 6), ("region", "region", 10),
                                            ("feature", "feature (type=value)", 18)))
                + "<button>Search</button></form>")
        cards = [self.card(repo.get(h.id)) for h in hits]
        body = (f"<h1>Explore</h1>{form}{err}<p class='muted'>{len(hits)} result(s). Keyword search with "
                f"filters (not semantic). Assets without a known year are excluded when a year range is set.</p>"
                + ("<div class='grid'>" + "".join(cards) + "</div>" if cards else
                   "<p class='empty'>No results for these filters.</p>"))
        return self.page("Explore", body)

    def asset(self, asset_id: str) -> str | None:
        repo = AssetRepo(self.conn)
        a = repo.get(asset_id)
        if a is None:
            return None
        reg = Registry(self.conn)
        pol = reg.effective_image_policy(a["id"], reg.get(a["source_id"]))
        feats = FeatureRepo(self.conn).for_asset(a["id"])
        ctx = ContextRepo(self.conn).for_asset(a["id"])
        genres = ", ".join(E(x["name"]) for x in repo.genres(a["id"])) or "<span class='muted'>none</span>"
        rows = [("Title", E(a["title"] or "")), ("Creator", E(a["creator"] or "unknown")),
                ("Work year", years(a)), ("Publication date", E(a["publication_date"] or "unknown")),
                ("Creation date", E(a["creation_date"] or "unknown")),
                ("Upload / online date", E(a["upload_date"] or "unknown")),
                ("Country / region", E(f"{a['country'] or 'unknown'} / {a['region'] or 'unknown'}")),
                ("Genres", genres), ("Media type", E(a["media_type"])),
                ("Image type", f"{E(a['image_type'])} <span class='muted'>({E(a['type_status'])}: "
                               f"{E(a['type_basis'] or '')})</span>"),
                ("Alt / caption", E(" / ".join(filter(None, [a["alt"], a["caption"]])) or "none")),
                ("Original image URL", f"<a href='{E(a['url'])}' rel='noreferrer'>{E(a['url'])}</a>"),
                ("Final URL", E(a["final_url"] or "-")),
                ("Source page", f"<a href='{E(a['source_page_url'])}' rel='noreferrer'>{E(a['source_page_url'])}</a>"
                 if a["source_page_url"] else "<span class='muted'>none</span>"),
                ("Source", E(a["source_id"])), ("Rights", f"{badge(pol['status'])} scope {E(pol['scope'])}; "
                                                          f"licence {E(pol['license'] or 'none recorded')}"),
                ("Download", f"{E(a['download_status'])} (attempts {a['attempt_count']}) {E(a['last_error'] or '')}"),
                ("File", E(f"{a['abs_path']} ({a['mime_type']}, {a['width']}x{a['height']}, {a['size_bytes']} bytes, "
                           f"sha256 {a['file_sha256']}, {a['file_status']})") if a["file_sha256"] else "none")]
        measured = [f for f in feats if f["kind"] == "measured"]
        semantic = [f for f in feats if f["kind"] == "semantic"]
        projects = [dict(r) for r in self.conn.execute("SELECT id, title FROM design_projects ORDER BY id")]
        body = [f"<h1>{E(a['title'] or a['alt'] or a['id'])}</h1><div style='max-width:420px'>{thumb(a)}</div>",
                "<table>" + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows) + "</table>",
                "<h2>Measured features <span class='muted'>(computed from the stored file)</span></h2>",
                ("<table>" + "".join(f"<tr><td>{E(f['feature_type'])}</td><td>{E(f['feature_value'][:120])}</td>"
                                     f"<td class='muted'>{E(f['tool'] or '')}</td></tr>" for f in measured)
                 + "</table>") if measured else "<p class='empty'>No measurements yet (needs a stored file and "
                                                "<code>magref analyze</code>).</p>",
                "<h2>Interpretations <span class='muted'>(semantic; review status shown)</span></h2>",
                ("<table>" + "".join(f"<tr><td>{E(f['feature_type'])}</td><td>{E(f['feature_value'])}</td><td>"
                                     f"{E(f['review_status'])}</td><td class='muted'>{E(f['tool'] or f['method'])}</td></tr>"
                                     for f in semantic) + "</table>") if semantic else
                "<p class='empty'>No interpretations recorded.</p>",
                "<h2>Context</h2>",
                ("<table>" + "".join(f"<tr><td><a href='/context/{c['context_id']}'>{E(c['title'])}</a></td>"
                                     f"<td>{E(c['relation_type'])}</td><td>{badge(c['evidence_status'])}</td>"
                                     f"<td class='muted'>{E(c['explanation'] or '')}</td></tr>" for c in ctx)
                 + "</table>") if ctx else "<p class='empty'>No context linked.</p>"]
        if projects:
            body.append("<h2>Add to a design project</h2><form class='inline' method='post' action='/project-add-asset'>"
                        f"<input type='hidden' name='asset' value='{E(a['id'])}'><select name='project'>"
                        + "".join(f"<option value='{p['id']}'>{E(p['title'])}</option>" for p in projects)
                        + "</select><input name='group' placeholder='group' value='default'>"
                          "<input name='note' placeholder='note'><button>Add</button></form>")
        return self.page(a["title"] or a["id"], "".join(body))

    def timeline(self, q) -> str:
        from . import trends
        g = lambda k, d="": (q.get(k) or [d])[0].strip()  # noqa: E731
        try:
            bucket = max(1, int(g("bucket", "10")))
        except ValueError:
            bucket = 10
        filters = {k: g(k) or None for k in ("genre", "country", "region")}
        res = trends.timeline(self.conn, bucket=bucket, **filters)
        repo = AssetRepo(self.conn)
        rows = []
        for r in res["rows"]:
            ctx = [c for c in res["contexts"] if (c["start_year"] is None or c["start_year"] <= r["to"])
                   and (c["end_year"] is None or c["end_year"] >= r["from"])]
            rows.append(f"<h2>{r['from']}-{r['to']} <span class='muted'>({r['count']} asset(s); sources: "
                        f"{E(', '.join(f'{k} {v}' for k, v in r['sources'].items()))})</span></h2>"
                        + ("<p>Context: " + "; ".join(f"<a href='/context/{c['id']}'>{E(c['title'])}</a> "
                                                     f"{badge(c['verification_status'])}" for c in ctx) + "</p>" if ctx else "")
                        + "<div class='grid'>" + "".join(self.card(repo.get(i)) for i in r["asset_ids"][:12]) + "</div>")
        form = ("<form class='inline'>" + "".join(f"<label>{k}<br><input name='{k}' value='{E(g(k))}'></label>"
                                                  for k in ("genre", "country", "region"))
                + f"<label>bucket (years)<br><input name='bucket' value='{bucket}' size='4'></label><button>Show</button></form>")
        note = "<div class='notice'>" + " ".join(E(x) for x in res["limitations"][:3]) + "</div>"
        return self.page("Timeline", f"<h1>Timeline</h1>{form}{note}"
                         + ("".join(rows) if rows else "<p class='empty'>No dated assets match.</p>"))

    def trends(self, q) -> str:
        from . import trends
        g = lambda k, d="": (q.get(k) or [d])[0].strip()  # noqa: E731
        feature = g("feature", "brightness_level")
        filters = {k: g(k) or None for k in ("genre", "country", "region")}
        form = ("<form class='inline'>" + "".join(
            f"<label>{lab}<br><input name='{k}' value='{E(g(k, d))}' size='12'></label>"
            for k, lab, d in (("feature", "feature", "brightness_level"), ("a", "period A", "1980-1989"),
                              ("b", "period B", "2010-2019"), ("genre", "genre", ""), ("country", "country", ""),
                              ("region", "region", ""), ("by", "group by", "genre")))
                + "<button>Compare</button></form>")
        body = [f"<h1>Trend comparison</h1>{form}"]
        try:
            pa = tuple(int(x) for x in g("a", "1980-1989").split("-"))
            pb = tuple(int(x) for x in g("b", "2010-2019").split("-"))
            res = trends.compare_periods(self.conn, feature, (pa[0], pa[-1]), (pb[0], pb[-1]), **filters)
        except ValueError:
            return self.page("Trends", "".join(body) + "<div class='notice'>Periods must look like 1980-1989.</div>")
        cls = "notice" if not res["sufficient"] else ""
        body.append(f"<p class='{cls}'>{E(res['statement'])}</p>")
        for key in ("period_a", "period_b"):
            p = res[key]
            body.append(f"<p><b>{p['years'][0]}-{p['years'][1]}</b>: sample {p['sample_size']}, with feature "
                        f"{p['with_feature']}, missing {p['missing_feature']}; sources "
                        f"{E(json.dumps(p['sources']))}</p>")
        body.append("<table><tr><th>value</th><th>share A</th><th>share B</th><th>difference</th></tr>" + "".join(
            f"<tr><td>{E(r['value'])}</td><td>{pct(r['share_a'])}</td><td>{pct(r['share_b'])}</td>"
            f"<td>{pct(r['difference'], signed=True)}</td></tr>" for r in res["rows"]) + "</table>")
        by = g("by", "genre")
        if by in ("genre", "country", "region", "decade", "source"):
            fr = trends.frequency_by(self.conn, feature, by, **filters)
            body.append(f"<h2>Frequency by {E(by)}</h2><table><tr><th>{E(by)}</th><th>n</th><th>with feature</th>"
                        "<th>values</th></tr>" + "".join(
                f"<tr><td>{E(x['group'])}</td><td>{x['sample_size']}</td><td>{x['with_feature']}"
                f"{'' if x['sufficient'] else ' <span class=bad>(insufficient)</span>'}</td><td>"
                + E(", ".join(f"{v['value']} {v['share']:.0%}" for v in x["values"][:6])) + "</td></tr>"
                for x in fr["groups"]) + "</table>")
        body.append("<h2>Limitations</h2><ul>" + "".join(f"<li>{E(x)}</li>" for x in res["limitations"]) + "</ul>")
        return self.page("Trend comparison", "".join(body))

    def contexts(self, q) -> str:
        text = (q.get("q") or [""])[0].strip()
        rows = ContextRepo(self.conn).search(text or None)
        body = ("<h1>Context explorer</h1><form class='inline'><input name='q' value='" + E(text)
                + "' placeholder='search title/description'><button>Search</button></form>"
                + ("<table>" + "".join(f"<tr><td>{r['start_year'] or '?'}-{r['end_year'] or '?'}</td><td>"
                                       f"<a href='/context/{r['id']}'>{E(r['title'])}</a></td><td>{E(r['context_type'])}"
                                       f"</td><td>{badge(r['verification_status'])}</td></tr>" for r in rows)
                   + "</table>" if rows else "<p class='empty'>No context records.</p>"))
        return self.page("Context explorer", body)

    def context(self, cid: int) -> str | None:
        c = ContextRepo(self.conn).get(cid)
        if c is None:
            return None
        repo = AssetRepo(self.conn)
        body = [f"<h1>{E(c['title'])} {badge(c['verification_status'])}</h1>",
                f"<p>{E(c['description'])}</p><p class='muted'>{c['start_year'] or '?'}-{c['end_year'] or '?'} "
                f"({E(c['period_precision'])}); {E(c['country'] or 'country unknown')}; type {E(c['context_type'])}; "
                f"genres: {E(', '.join(c['genres']) or 'none')}</p>"]
        if c["verification_status"] != "verified":
            body.append("<div class='notice'>Not verified: treat as a research lead, not a fact.</div>")
        body.append("<h2>Alternative interpretations</h2>" + (f"<p>{E(c['alternative_interpretations'])}</p>"
                    if c["alternative_interpretations"] else "<p class='empty'>none recorded</p>"))
        body.append("<h2>Claims and evidence</h2>")
        for cl in c["claims"]:
            body.append(f"<p><b>#{cl['id']}</b> {E(cl['claim_text'])} {badge(cl['verification_status'])}</p><ul>"
                        + "".join(f"<li>{E(e['relation'])} &middot; read: {E(e['access_level'])} &middot; "
                                  f"{E(e['title'])} {E(e['locator'] or '')}</li>" for e in cl["evidence"])
                        + ("" if cl["evidence"] else "<li class='empty'>no sources linked</li>") + "</ul>")
            if cl["alternative_explanations"]:
                body.append(f"<p class='muted'>Alternatives: {E(cl['alternative_explanations'])}</p>")
        if not c["claims"]:
            body.append("<p class='empty'>No claims recorded.</p>")
        body.append("<h2>Sources</h2>" + ("<ul>" + "".join(f"<li>{E(s['title'])} ({E(s['source_type'])})</li>"
                                                         for s in c["sources"]) + "</ul>" if c["sources"] else
                                         "<p class='empty'>none</p>"))
        body.append("<h2>Related assets</h2><div class='grid'>" + "".join(
            self.card(repo.get(r["asset_id"])) + f"<div class='muted'>{E(r['relation_type'])} "
            f"{badge(r['evidence_status'])}</div>" for r in c["assets"]) + "</div>"
                    if c["assets"] else "<h2>Related assets</h2><p class='empty'>none</p>")
        return self.page(c["title"], "".join(body))

    def projects(self, q) -> str:
        from .projects import ProjectRepo
        rows = ProjectRepo(self.conn).all()
        form = ("<h2>New project</h2><form method='post' action='/projects'>"
                + "".join(f"<p><label>{lab}<br><input name='{k}' size='60'></label></p>"
                          for k, lab in (("title", "Title *"), ("brief", "Design goal"), ("target_audience", "Audience"),
                                         ("medium", "Medium"), ("constraints", "Constraints"),
                                         ("excluded_styles", "Excluded styles")))
                + "<button>Create</button></form>")
        return self.page("Design workspace", "<h1>Design workspace</h1>" + (
            "<table>" + "".join(f"<tr><td><a href='/project/{r['id']}'>{E(r['title'])}</a></td>"
                                f"<td>{r['asset_count']} reference(s)</td><td class='muted'>{E(r['updated_at'])}</td></tr>"
                                for r in rows) + "</table>" if rows else "<p class='empty'>No projects yet.</p>") + form)

    def project(self, pid: int) -> str | None:
        from .projects import ProjectError, ProjectRepo, render_html
        try:
            p = ProjectRepo(self.conn).get(pid)
        except ProjectError:
            return None
        repo = AssetRepo(self.conn)
        groups: dict[str, list] = {}
        for pa in p["assets"]:
            groups.setdefault(pa["group_name"], []).append(pa)
        body = [f"<h1>{E(p['title'])}</h1><p>{E(p['brief'] or '')}</p><p class='muted'>audience: "
                f"{E(p['target_audience'] or '-')}; medium: {E(p['medium'] or '-')}; constraints: "
                f"{E(p['constraints'] or '-')}; excluded: {E(p['excluded_styles'] or '-')}</p>"]
        for gname, items in sorted(groups.items()):
            body.append(f"<h2>Group: {E(gname)}</h2><div class='grid'>" + "".join(
                self.card(repo.get(i["asset_id"])) for i in items if repo.get(i["asset_id"])) + "</div>")
        if not groups:
            body.append("<p class='empty'>No references yet -- add them from an asset page.</p>")
        body.append("<h2>Notes</h2>" + "".join(f"<p>{E(n['body'])} <span class='muted'>{E(n['created_at'])}</span></p>"
                                               for n in p["notes"])
                    + f"<form method='post' action='/project/{pid}/note'><textarea name='body'></textarea>"
                      "<button>Add note</button></form>")
        ctx = ContextRepo(self.conn).search()
        body.append("<h2>Context</h2>" + "".join(f"<p>#{c['context_id']} {E(c['note'] or '')}</p>" for c in p["contexts"])
                    + (f"<form class='inline' method='post' action='/project/{pid}/context'><select name='context'>"
                       + "".join(f"<option value='{c['id']}'>{E(c['title'])} ({E(c['verification_status'])})</option>"
                                 for c in ctx) + "</select><button>Link context</button></form>" if ctx else ""))
        body.append(f"<h2>Planning report</h2><form method='post' action='/project/{pid}/report'>"
                    "<button>Generate report</button></form>")
        last = self.conn.execute("SELECT content, format, generated_at FROM project_reports WHERE project_id=? "
                                 "AND format='json' ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
        if last:
            report = json.loads(last["content"])
            body.append(f"<p class='muted'>Latest report {E(last['generated_at'])} -- "
                        f"<a href='/project/{pid}/report.md'>download Markdown</a></p>"
                        "<div class='card' style='padding:1rem'>"
                        + render_html(report).split("</style>", 1)[1] + "</div>")
        return self.page(p["title"], "".join(body))

    # -- POST actions ----------------------------------------------------------------
    def post(self, path: str, form: dict) -> str:
        from .projects import ProjectRepo
        f = lambda k: (form.get(k) or [""])[0].strip()  # noqa: E731
        repo = ProjectRepo(self.conn)
        if path == "/projects":
            pid = repo.create(f("title"), brief=f("brief") or None, target_audience=f("target_audience") or None,
                              medium=f("medium") or None, constraints=f("constraints") or None,
                              excluded_styles=f("excluded_styles") or None)
            return f"/project/{pid}"
        if path == "/project-add-asset":
            pid = int(f("project"))
            repo.add_asset(pid, f("asset"), f("group") or "default", f("note") or None)
            return f"/project/{pid}"
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "project" and parts[1].isdigit():
            pid = int(parts[1])
            if parts[2] == "note":
                repo.add_note(pid, f("body"))
            elif parts[2] == "context":
                repo.add_context(pid, int(f("context")))
            elif parts[2] == "report":
                repo.save_report(pid, "json")
                repo.save_report(pid, "markdown")
            else:
                raise LookupError(path)
            return f"/project/{pid}"
        raise LookupError(path)


def make_handler(ui: UI):
    class Handler(BaseHTTPRequestHandler):
        server_version = "magref-ui"

        def log_message(self, fmt, *args):  # keep request logs out of stderr noise
            return

        def _send(self, status: int, body: bytes, ctype: str = "text/html; charset=utf-8", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; form-action 'self'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parts = urlsplit(self.path)
            q = parse_qs(parts.query)
            path = parts.path
            with ui.lock:
                try:
                    if path.startswith("/file/"):
                        return self._file(path[len("/file/"):])
                    if path.startswith("/thumb/"):
                        return self._file(path[len("/thumb/"):], thumb=True)
                    if path.startswith("/project/") and path.endswith("/report.md"):
                        pid = path.split("/")[2]
                        row = ui.conn.execute("SELECT content FROM project_reports WHERE project_id=? AND "
                                              "format='markdown' ORDER BY id DESC LIMIT 1",
                                              (int(pid) if pid.isdigit() else -1,)).fetchone()
                        if row is None:
                            return self._send(404, b"no report yet", "text/plain; charset=utf-8")
                        return self._send(200, row[0].encode("utf-8"), "text/markdown; charset=utf-8",
                                          {"Content-Disposition": f"attachment; filename=project-{pid}-report.md"})
                    routes = {"/": ui.dashboard, "/explore": ui.explore, "/timeline": ui.timeline,
                              "/trends": ui.trends, "/contexts": ui.contexts, "/projects": ui.projects}
                    if path in routes:
                        page = routes[path](q)
                    elif path.startswith("/asset/"):
                        page = ui.asset(path[len("/asset/"):])
                    elif path.startswith("/context/") and path[9:].isdigit():
                        page = ui.context(int(path[9:]))
                    elif path.startswith("/project/") and path[9:].isdigit():
                        page = ui.project(int(path[9:]))
                    else:
                        page = None
                    if page is None:
                        return self._send(404, ui.page("Not found", "<h1>Not found</h1>").encode())
                    return self._send(200, page.encode("utf-8"))
                except Exception as exc:  # noqa: BLE001 -- show an error page, keep serving
                    return self._send(500, ui.page("Error", f"<h1>Error</h1><p>{E(type(exc).__name__)}: "
                                                            f"{E(str(exc))}</p>").encode())

        def _file(self, asset_id: str, thumb: bool = False):
            row = ui.conn.execute(
                """SELECT f.rel_path, f.mime_type FROM image_refs r JOIN image_files f ON f.sha256=r.file_sha256
                   WHERE r.id=? AND r.download_status='downloaded'""", (asset_id,)).fetchone()
            if row is None:
                return self._send(404, b"no stored file", "text/plain; charset=utf-8")
            try:
                path = ui.app.layout.resolve(row["rel_path"])
                sha = path.stem
                thumb_path = ui.app.layout.thumbnails / sha[:2] / f"{sha}.jpg"
                if thumb and thumb_path.is_file():
                    return self._send(200, thumb_path.read_bytes(), "image/jpeg", {"Cache-Control": "max-age=3600"})
                data = path.read_bytes()
            except (StorageError, OSError):
                return self._send(404, b"file missing on disk (run magref verify --all)", "text/plain; charset=utf-8")
            return self._send(200, data, row["mime_type"], {"Cache-Control": "max-age=3600"})

        def do_POST(self):
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
            if not origin or urlsplit(origin).netloc != host:
                return self._send(403, b"cross-site request refused", "text/plain; charset=utf-8")
            length = int(self.headers.get("Content-Length") or 0)
            if length > 100_000:
                return self._send(413, b"form too large", "text/plain; charset=utf-8")
            form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
            with ui.lock:
                try:
                    target = ui.post(urlsplit(self.path).path, form)
                except LookupError:
                    return self._send(404, ui.page("Not found", "<h1>Not found</h1>").encode())
                except Exception as exc:  # noqa: BLE001 -- validation errors from repos
                    return self._send(400, ui.page("Error", f"<h1>Could not save</h1><p>{E(str(exc))}</p>").encode())
            self.send_response(303)
            self.send_header("Location", target)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Handler


def make_server(app, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(UI(app)))


def serve(app, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = make_server(app, host, port)
    print(f"Visual Culture Research UI on http://{host}:{server.server_address[1]}/ (Ctrl+C to stop)")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("WARNING: listening beyond localhost; there is no authentication.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
