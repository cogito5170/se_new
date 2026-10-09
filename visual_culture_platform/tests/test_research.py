import sqlite3

from helpers import add_image, make_app, raises, register
from test_pipeline_fixtures import discover, fixture_app

from magref import analysis, trends
from magref.downloader import Downloader
from magref.projects import ProjectRepo
from magref.research import (ClaimRepo, ContextRepo, FeatureRepo, GenreRepo, ResearchSourceRepo,
                             RuleError)


def base(tmp_path):
    app = make_app(tmp_path)
    register(app, "https://m.test")
    return app


def test_asset_metadata_roundtrip_and_many_genres(tmp_path):
    app = base(tmp_path)
    aid = add_image(app, "src", "https://m.test/a.png", title="Poster", creator="Studio X",
                    publication_date="1994-05-01", country="KR", region="East Asia",
                    genres=["graphic design/poster", "music/album art"])
    from magref.assets import AssetRepo
    a = AssetRepo(app.conn).get(aid)
    assert (a["title"], a["creator"], a["year_start"], a["year_basis"]) == ("Poster", "Studio X", 1994, "publication")
    assert sorted(g["name"] for g in AssetRepo(app.conn).genres(aid)) == ["album art", "poster"]
    g = GenreRepo(app.conn)
    assert set(g.with_descendants("graphic design")) == {g.get("graphic design")["id"], g.get("poster")["id"]}
    raises(ValueError, AssetRepo(app.conn).update_metadata, aid, year_start=2000, year_end=1990)
    raises(ValueError, AssetRepo(app.conn).update_metadata, aid, sha256="x")


def test_unknown_years_stay_unknown(tmp_path):
    app = base(tmp_path)
    from magref.assets import AssetRepo, coerce_year
    assert coerce_year("c. 1990s") is None and coerce_year("1990s") is None and coerce_year(True) is None
    aid = add_image(app, "src", "https://m.test/u.png", upload_date="2024-01-01", title="scan")
    a = AssetRepo(app.conn).get(aid)
    assert a["year_start"] is None and a["upload_date"] == "2024-01-01"     # upload date is not a work year
    assert AssetRepo(app.conn).query(year_from=1900, year_to=2100) == []
    assert len(AssetRepo(app.conn).query(year_from=1900, year_to=2100, include_undated=True)) == 1


def test_claims_never_auto_verify(tmp_path):
    app = base(tmp_path)
    claims, sources = ClaimRepo(app.conn), ResearchSourceRepo(app.conn)
    cid = claims.add("Style X spread in 1985 (fictional)", "historical_fact")
    assert claims.get(cid)["verification_status"] == "unverified"
    raises(RuleError, claims.set_status, cid, "verified", reviewer="r")
    sid = sources.add("A search hit", "website", url="https://m.test/hit")
    raises(RuleError, claims.link_source, cid, sid, "supports", "title_only")   # title only cannot support
    claims.link_source(cid, sid, "supports", "abstract")
    raises(RuleError, claims.set_status, cid, "verified", reviewer="r")         # abstract is not enough
    claims.set_status(cid, "partially_supported", reviewer="r")
    raises(RuleError, claims.set_status, cid, "verified", reviewer="")           # needs a reviewer
    book = sources.add("Fictional monograph", "book", author="A. Author")
    claims.link_source(cid, book, "supports", "full_text", locator="pp. 12-14")
    contra = sources.add("Fictional rebuttal", "journal_article")
    claims.link_source(cid, contra, "contradicts", "excerpt")
    raises(RuleError, claims.set_status, cid, "verified", reviewer="r")         # read contradiction
    claims.set_status(cid, "contradicted", reviewer="r", alternative_explanations="see rebuttal")
    # the database refuses a direct write too (trigger backstop)
    c2 = claims.add("Another", "interpretation")
    raises(sqlite3.IntegrityError, app.conn.execute,
           "UPDATE research_claims SET verification_status='verified' WHERE id=?", (c2,))
    raises(sqlite3.IntegrityError, app.conn.execute,
           "INSERT INTO research_claims (claim_text, claim_type, verification_status, created_at, updated_at) "
           "VALUES ('x','other','verified','t','t')")


def test_context_relations_follow_evidence(tmp_path):
    app = base(tmp_path)
    ctx, claims, sources = ContextRepo(app.conn), ClaimRepo(app.conn), ResearchSourceRepo(app.conn)
    aid = add_image(app, "src", "https://m.test/p.png", year_start=1986, year_end=1986)
    undated = add_image(app, "src", "https://m.test/u.png")
    cid = ctx.add("Fictional scene", "SYNTHETIC", "subculture", start_year=1984, end_year=1990, country="JP")
    rel = ctx.relate_asset(aid, cid, "same_period")
    assert "does not imply influence" in rel["explanation"] and rel["evidence_status"] == "unverified"
    raises(RuleError, ctx.relate_asset, undated, cid, "same_period")
    raises(RuleError, ctx.relate_asset, aid, cid, "documented_influence")
    claim = claims.add("Scene influenced poster (fictional)", "influence", context_id=cid)
    raises(RuleError, ctx.relate_asset, aid, cid, "documented_influence", claim_id=claim)
    raises(sqlite3.IntegrityError, app.conn.execute,
           "INSERT INTO asset_context (asset_id, context_id, relation_type, claim_id, created_at) "
           "VALUES (?,?,?,?,?)", (aid, cid, "documented_influence", claim, "t"))
    hyp = ctx.relate_asset(aid, cid, "research_hypothesis", explanation="looks related")
    assert hyp["evidence_status"] == "hypothesis"
    raises(RuleError, ctx.set_status, cid, "verified", reviewer="r")
    s = sources.add("Fictional archive record", "museum_archive")
    claims.link_source(claim, s, "supports", "full_text")
    claims.set_status(claim, "verified", reviewer="r")
    assert ctx.relate_asset(aid, cid, "documented_influence", claim_id=claim)["evidence_status"] == "verified"
    assert ctx.set_status(cid, "verified", reviewer="r")["verification_status"] == "verified"


def test_feature_kinds_and_review(tmp_path):
    app = base(tmp_path)
    aid = add_image(app, "src", "https://m.test/a.png")
    f = FeatureRepo(app.conn)
    raises(RuleError, f.add_semantic, aid, "style", "minimalism", origin="ai", method="m")      # no tool
    raises(RuleError, f.add_semantic, aid, "made_up", "x", origin="human", method="m")
    ai = f.add_semantic(aid, "style", "minimalism", origin="ai", method="caption model", tool="model-x v1",
                        confidence=0.6)
    hu = f.add_semantic(aid, "mood", "calm", origin="human", method="annotation", reviewer="ann")
    rows = {r["id"]: r for r in f.for_asset(aid)}
    assert rows[ai]["review_status"] == "ai_suggested" and rows[hu]["review_status"] == "human_entered"
    assert f.review(ai, "accept", "ann")["review_status"] == "human_reviewed"
    raises(sqlite3.IntegrityError, app.conn.execute,
           "INSERT INTO visual_features (asset_id, feature_type, feature_value, kind, method, review_status, created_at)"
           " VALUES (?, 'width', '10', 'measured', 'x', 'auto_measured', 't')", (aid,))   # measured needs tool+hash


def test_measurements_trends_and_small_samples(tmp_path):
    app = fixture_app(tmp_path)
    discover(app, "open-archive")
    Downloader(app.conn, app.fetcher, app.settings, app.layout, sleep=lambda s: None).run("download", limit=100)
    results = analysis.analyze_pending(app.conn, app.layout)
    assert results and all(r["status"] == "measured" for r in results)
    row = app.conn.execute("SELECT * FROM visual_features WHERE feature_type='width' LIMIT 1").fetchone()
    assert row["kind"] == "measured" and row["file_sha256"] and row["tool"]
    # orientation comes from the image header, so this part runs with or without Pillow
    res = trends.compare_periods(app.conn, "orientation", (1980, 1989), (2010, 2019))
    assert res["sufficient"] and res["period_a"]["with_feature"] >= 10
    assert "In this collection" in res["statement"] and res["limitations"]
    land = next(r for r in res["rows"] if r["value"] == "landscape")
    assert land["share_a"] == 0 and land["share_b"] == 1.0
    small = trends.compare_periods(app.conn, "orientation", (1980, 1981), (2010, 2011))
    assert not small["sufficient"] and "No trend is asserted" in small["statement"]
    assert all(r["difference"] is not None for r in small["rows"])            # numbers shown, no claim
    em = trends.emergence(app.conn, "orientation", "landscape")
    assert em["first_seen_in_collection"] == 2010 and "not a historical first" in em["note"]
    from magref.images import pillow_available
    if pillow_available():
        b = trends.compare_periods(app.conn, "brightness_level", (1980, 1989), (2010, 2019))
        light = next(r for r in b["rows"] if r["value"] == "light")
        assert b["sufficient"] and light["share_a"] < light["share_b"]
    else:
        print("  (Pillow not installed: colour/brightness measurements skipped, as documented)")
        assert app.conn.execute("SELECT COUNT(*) FROM visual_features WHERE feature_type='brightness_level'"
                                ).fetchone()[0] == 0          # absent, not estimated
    oid = trends.save_observation(app.conn, res, "Brightness in fixture covers vs posters")
    obs = app.conn.execute("SELECT * FROM trend_observations WHERE id=?", (oid,)).fetchone()
    assert obs["verification_status"] == "unverified" and obs["sample_size"] > 0 and obs["limitations"]


def test_design_project_roundtrip_and_report(tmp_path):
    app = base(tmp_path)
    a1 = add_image(app, "src", "https://m.test/1.png", title="One", year_start=1990, year_end=1990)
    a2 = add_image(app, "src", "https://m.test/2.png", title="Two")
    cid = ContextRepo(app.conn).add("Fictional movement", "SYNTHETIC", "art_movement", start_year=1985, end_year=1995)
    repo = ProjectRepo(app.conn)
    pid = repo.create("Magazine relaunch", brief="New quarterly", target_audience="designers", medium="print",
                      excluded_styles="no grunge", reference_periods=["1985-1995"])
    repo.add_asset(pid, a1, "calm")
    repo.add_asset(pid, a2, "loud", note="contrast")
    repo.add_context(pid, cid)
    repo.add_note(pid, "Keep the grid but change the type scale")
    p = repo.get(pid)
    assert [x["asset_id"] for x in p["assets"]] == [a1, a2] and p["reference_periods"] == ["1985-1995"]
    rep = repo.build_report(pid)
    s = rep["sections"]
    assert len(s) == 9 and s["1_goal"]["title"] == "Magazine relaunch"
    assert s["5_context"][0]["status"] == "unverified" and "not a fact" in s["5_context"][0]["phrase"]
    assert any("year unknown" in o for o in s["9_open_questions"])
    assert any("no local file" in o for o in s["9_open_questions"])
    assert any("principles" in c for c in s["8_cautions"])
    assert any(d["label"] == "user note" for d in s["7_directions"])
    rid, md = repo.save_report(pid, "markdown")
    assert "## 9. Open questions" in md and "[user note]" in md
    assert repo.get(pid)["reports"][0]["id"] == rid
