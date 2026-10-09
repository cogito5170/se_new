"""Local HTML files as input: same extraction/storage as a crawl, nothing fetched."""
from helpers import FIXTURES, MockTransport, make_app, raises

from magref.assets import AssetRepo
from magref.export import build_export, validate_export_doc
from magref.ingest import IngestError, Ingester, find_origin, read_html
from magref.pages import PageRepo
from magref.registry import Registry
from magref.search import KeywordSearch, SearchQuery

LOCAL = FIXTURES / "local_html"


def app_with_sources(tmp_path):
    t = MockTransport({})
    app = make_app(tmp_path, transport=t)
    Registry(app.conn).import_file(FIXTURES / "sources.fixture.json")
    return app, t


def ingest(app, sid, *paths, **kw):
    return Ingester(app.conn, app.settings, app.fetcher).run(Registry(app.conn).get(sid),
                                                             [str(p) for p in paths], **kw)


def test_saved_page_becomes_a_page_reference_without_any_network(tmp_path):
    app, transport = app_with_sources(tmp_path)
    res = ingest(app, "atelier", LOCAL / "saved_quiet_volume.html")
    assert res.pages_new == 1 and res.failed == 0 and res.skipped_local_images == 1
    assert transport.calls == [], "ingest must not fetch anything by default"
    ref = PageRepo(app.conn).get("https://atelier-journal.test/stories/quiet-volume.html")
    assert ref["title"] == "Quiet Volume | Atelier Journal" and ref["discovery_method"] == "import"
    assert ref["fetched_url"] is None and ref["http_status"] is None
    assert "saved-from comment" in ref["field_sources"]["_input"]
    assert "/" not in ref["discovered_from"].replace("local HTML file ", "")   # file name only
    imgs = AssetRepo(app.conn).query(source="atelier")
    assert [a["url"] for a in imgs] == ["https://atelier-journal.test/media/quiet-volume-spread.png"]
    assert imgs[0]["source_page_url"] == ref["url"] and imgs[0]["year_start"] is None
    hits = KeywordSearch(app.conn).search(SearchQuery("asymmetric grid whitespace", "pages"))
    assert hits and hits[0].id == ref["id"]
    doc = build_export(app.conn, "pages")
    assert validate_export_doc(doc) == []


def test_canonical_and_legacy_korean_encoding(tmp_path):
    app, _ = app_with_sources(tmp_path)
    assert "세리프" in read_html(LOCAL / "canonical_serif_euckr.html", 10**6)
    res = ingest(app, "atelier", LOCAL / "canonical_serif_euckr.html")
    assert res.pages_new == 1
    ref = PageRepo(app.conn).get("https://atelier-journal.test/stories/serif-season.html")
    assert ref["title"] == "세리프의 계절" and ref["language"] == "ko" and ref["category"] == "타이포그래피"
    img = AssetRepo(app.conn).query(source="atelier")[0]
    assert img["url"] == "https://atelier-journal.test/media/serif-cover.png"   # resolved against canonical
    assert img["image_type"] == "cover" and img["type_status"] == "inferred"


def test_document_without_origin_gives_links_and_host_report_not_a_page(tmp_path):
    app, _ = app_with_sources(tmp_path)
    res = ingest(app, "atelier", LOCAL / "claude_report.html", links=True)
    assert res.without_origin == 1 and res.pages_new == 0
    assert app.conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0] == 0
    urls = {r[0] for r in app.conn.execute("SELECT url FROM discovered_urls WHERE source_id='atelier'")}
    assert urls == {"https://atelier-journal.test/stories/quiet-volume.html",
                    "https://atelier-journal.test/stories/gallery-blue-hour.html"}
    assert res.other_hosts == {"northlight-mag.test": 1, "unknown-zine.test": 1, "cdn.unknown-zine.test": 1}
    imgs = AssetRepo(app.conn).query(source="atelier")
    assert [a["url"] for a in imgs] == ["https://atelier-journal.test/media/blue-hour-1.png"]
    assert imgs[0]["source_page_url"] is None


def test_wrong_site_binary_restricted_and_url_flag(tmp_path):
    app, _ = app_with_sources(tmp_path)
    res = ingest(app, "atelier", LOCAL / "wrong_site.html", LOCAL / "not_html.html")
    assert res.failed == 2 and res.pages_new == 0
    reasons = " ".join(i["reason"] for i in res.items)
    assert "not on source 'atelier'" in reasons and "not a text/HTML file" in reasons
    raises(IngestError, ingest, app, "atelier", LOCAL / "saved_quiet_volume.html", LOCAL / "wrong_site.html",
           url="https://atelier-journal.test/x")
    raises(IngestError, find_origin, "<html></html>", "ftp://x")
    res = ingest(app, "northlight", LOCAL / "wrong_site.html")        # right source -> accepted
    assert res.pages_new == 1


def test_cli_ingest_exit_codes(tmp_path):
    from test_cli_web_logging import run_cli
    run_cli(tmp_path, "source", "import", str(FIXTURES / "sources.fixture.json"))
    code, out, _ = run_cli(tmp_path, "ingest-html", str(LOCAL / "saved_quiet_volume.html"), "--source", "atelier")
    assert code == 0 and "pages new 1" in out
    assert run_cli(tmp_path, "ingest-html", str(LOCAL), "--source", "atelier")[0] == 6   # some files fail
    assert run_cli(tmp_path, "ingest-html", str(LOCAL), "--source", "restricted-demo")[0] == 4
    assert run_cli(tmp_path, "ingest-html", str(tmp_path / "nothing"), "--source", "atelier")[0] == 1
