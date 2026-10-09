"""Discovery + crawl + download over the offline fixture web (no network)."""
from helpers import FIXTURES, make_app, raises

from magref.assets import AssetRepo
from magref.discovery import Discoverer, DiscoveryError, parse_sitemap
from magref.downloader import Downloader
from magref.http import FixtureTransport
from magref.pages import Crawler, PageRepo
from magref.registry import Registry

WEB = FIXTURES / "web"


def fixture_app(tmp_path, **kw):
    app = make_app(tmp_path, transport=FixtureTransport(WEB), fixture_dir=WEB, **kw)
    Registry(app.conn).import_file(FIXTURES / "sources.fixture.json")
    return app


def discover(app, sid, limit=200):
    return Discoverer(app.conn, app.fetcher, limit).run(Registry(app.conn).get(sid))


def crawl(app, sid, limit=200):
    return Crawler(app.conn, app.fetcher, app.settings).run(Registry(app.conn).get(sid), limit)


def disc_status(app):
    return {r[0].replace("https://atelier-journal.test", ""): r[1] for r in
            app.conn.execute("SELECT url, crawl_status FROM discovered_urls WHERE source_id='atelier'")}


def test_sitemap_discovery_dedup_filter_and_error_recording(tmp_path):
    app = fixture_app(tmp_path)
    res = discover(app, "atelier")
    assert res.pages_new == 10 and res.pages_duplicate == 1      # utm variant == same URL
    assert res.pages_filtered == 1                                 # other host in the sitemap
    assert [e["code"] for e in res.errors] == ["http_404"]         # missing child sitemap recorded
    assert res.images_new == 1                                     # image:image entry
    again = discover(app, "atelier")
    assert again.pages_new == 0 and again.pages_duplicate == 11    # rerun creates nothing new
    n = app.conn.execute("SELECT COUNT(*) FROM processing_errors WHERE code='http_404'").fetchone()[0]
    assert n == 2


def test_crawl_outcomes_and_canonical_dedup(tmp_path):
    app = fixture_app(tmp_path)
    discover(app, "atelier")
    res = crawl(app, "atelier")
    st = disc_status(app)
    assert st["/private/draft.html"] == "blocked"                 # robots.txt
    assert st["/stories/forbidden.html"] == "blocked"             # HTTP 403
    assert st["/stories/gone.html"] == "failed"                   # HTTP 404
    assert st["/stories/noindex.html"] == "skipped"               # meta robots noindex
    assert res.new_references == 5 and res.blocked == 2 and res.failed == 1
    pages = PageRepo(app.conn)
    canonical = pages.get("https://atelier-journal.test/stories/quiet-volume.html")
    assert canonical["title"] == "Quiet Volume: a minimalist fashion editorial"
    aliases = pages.aliases(canonical["id"])
    assert "https://atelier-journal.test/stories/quiet-volume-amp.html" in aliases
    assert app.conn.execute("SELECT COUNT(*) FROM refs WHERE title LIKE 'Quiet Volume%'").fetchone()[0] == 1
    bare = pages.get("https://atelier-journal.test/stories/bare-page.html")
    assert bare["description"] is None and bare["publisher"] is None and bare["published_at"] is None
    broken = pages.get("https://atelier-journal.test/stories/broken-jsonld.html")
    assert {e["code"] for e in broken["errors"]} >= {"jsonld_parse_error", "date_unparseable"}
    hero = canonical["visual_features"]["aspect_ratio"]
    assert hero["status"] == "observed" and hero["value"]["primary"]["orientation"] == "landscape"
    # rerun is idempotent: nothing pending, nothing new
    assert crawl(app, "atelier").attempted == 0


def test_rss_and_html_discovery(tmp_path):
    app = fixture_app(tmp_path)
    r = discover(app, "northlight")
    assert r.pages_new == 3 and r.images_new == 3
    h = discover(app, "folio")
    urls = {u for (u,) in app.conn.execute("SELECT url FROM discovered_urls WHERE source_id='folio'")}
    assert urls == {"https://folio-review.test/reviews/layout-notes.html",
                    "https://folio-review.test/reviews/grid-study.html"}
    assert h.pages_duplicate == 1                                  # fragment variant
    assert h.pages_filtered == 3                                   # external, nofollow, pdf


def test_catalog_years_are_never_invented(tmp_path):
    app = fixture_app(tmp_path)
    discover(app, "open-archive")
    rows = {r["title"]: r for r in AssetRepo(app.conn).query(source="open-archive")}
    undated = rows["Undated photograph 25"]
    assert undated["year_start"] is None and undated["year_end"] is None and undated["year_basis"] is None
    dated = rows["Synthetic magazine cover 13"]
    assert dated["publication_date"] == "2010-01-15" and dated["year_start"] == 2010
    assert dated["year_basis"] == "publication" and dated["upload_date"] is None
    poster = rows["Synthetic poster study 1"]
    assert poster["year_start"] == 1980 and poster["year_basis"] == "source_declared"
    # page-level dates of crawled articles are online dates, never work years
    discover(app, "atelier")
    crawl(app, "atelier")
    for a in AssetRepo(app.conn).query(source="atelier"):
        assert a["year_start"] is None


def test_fixture_downloads_dedup_and_host_policy(tmp_path):
    app = fixture_app(tmp_path)
    discover(app, "open-archive")
    res = Downloader(app.conn, app.fetcher, app.settings, app.layout, sleep=lambda s: None).run("download", limit=100)
    assert res.blocked == 1                                        # cdn.unrelated.test not allowed
    assert res.downloaded + res.duplicates == 28                    # 29 catalog items - 1 blocked
    files = app.conn.execute("SELECT COUNT(*) FROM image_files").fetchone()[0]
    assert files == res.downloaded
    copy = AssetRepo(app.conn).query(source="open-archive")
    by_url = {a["url"]: a for a in copy}
    a, b = by_url["https://open-archive.test/media/work-001.png"], by_url["https://open-archive.test/media/work-001-copy.png"]
    assert a["file_sha256"] == b["file_sha256"] and a["id"] != b["id"]


def test_unknown_policy_source_keeps_metadata_but_downloads_nothing(tmp_path):
    app = fixture_app(tmp_path)
    discover(app, "northlight")
    res = Downloader(app.conn, app.fetcher, app.settings, app.layout).run("download")
    assert res.selected == 0 and res.skipped_not_allowed == 3
    assert all(a["download_status"] == "pending" and a["abs_path"] is None
               for a in AssetRepo(app.conn).query(source="northlight"))
    assert not any("/img/" in u for u in app.transport.requests)


def test_malformed_and_hostile_xml_rejected():
    raises(DiscoveryError, parse_sitemap, b"<urlset><url><loc>x</loc></url")
    bomb = b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><urlset>&lol;</urlset>'
    raises(DiscoveryError, parse_sitemap, bomb)
    raises(DiscoveryError, parse_sitemap, b"<html><body>not a sitemap</body></html>")
