import json

from helpers import FIXTURES, ROOT, make_app, raises
from test_pipeline_fixtures import crawl, discover, fixture_app

from magref.downloader import Downloader
from magref.export import build_export, import_file, validate_export_doc, write_export
from magref.image_contract import validate_image_record
from magref.models import ValidationError, json_schema, validate_reference
from magref.search import KeywordSearch, SearchQuery, score_document, stem, tokenize


def populated(tmp_path):
    app = fixture_app(tmp_path)
    for sid in ("atelier", "open-archive"):
        discover(app, sid)
    crawl(app, "atelier")
    Downloader(app.conn, app.fetcher, app.settings, app.layout, sleep=lambda s: None).run("download", limit=100)
    return app


def test_tokenizer_is_light_and_deterministic():
    assert stem("minimalist") == "minimal" and stem("images") == "image" and stem("grids") == "grid"
    assert tokenize("Find references with LARGE hero images") == ["large", "hero", "image"]
    assert tokenize("한국 잡지 표지") == ["한국", "잡지", "표지"]


def test_ranking_weights_and_coverage():
    terms = tokenize("minimal grid")
    full, m1, miss1, _ = score_document(terms, {"title": "Minimal grid", "keywords": ""}, {"title": 3, "keywords": 2})
    half, m2, miss2, _ = score_document(terms, {"title": "Minimal", "keywords": ""}, {"title": 3, "keywords": 2})
    assert full > half and miss1 == [] and miss2 == ["grid"]


def test_page_search_returns_source_backed_ranked_results(tmp_path):
    app = populated(tmp_path)
    q = SearchQuery("large hero images, generous whitespace, asymmetric grids, restrained typography, "
                    "minimalist fashion", "pages", {}, 10)
    hits = KeywordSearch(app.conn).search(q)
    assert hits[0].title.startswith("Quiet Volume")
    assert hits[0].url == "https://atelier-journal.test/stories/quiet-volume.html"
    assert any("whitespace" in e for e in hits[0].explanation)
    assert [h.id for h in hits] == [h.id for h in KeywordSearch(app.conn).search(q)]   # deterministic
    assert KeywordSearch(app.conn).search(SearchQuery("zzzz-nothing", "pages")) == []
    cat = KeywordSearch(app.conn).search(SearchQuery("", "pages", {"category": "Typography"}))
    assert [h.title for h in cat] == ["Serif Season"]


def test_image_search_filters_year_region_genre_feature(tmp_path):
    app = populated(tmp_path)
    s = KeywordSearch(app.conn)
    eighties = s.search(SearchQuery("poster", "images", {"year_from": 1980, "year_to": 1984, "country": "JP"}, 50))
    assert eighties and all(1980 <= h.extra["year_start"] <= 1984 and h.extra["country"] == "JP" for h in eighties)
    covers = s.search(SearchQuery("", "images", {"genre": "editorial design"}, 50))      # parent genre
    assert len(covers) == 12 and all("magazine cover" in h.extra["genres"] for h in covers)
    undated = s.search(SearchQuery("photograph", "images", {"year_from": 1900, "year_to": 2100}, 50))
    assert undated == []                                    # undated items never placed in a period


def test_exports_validate_and_round_trip(tmp_path):
    app = populated(tmp_path)
    for kind in ("pages", "images"):
        doc = build_export(app.conn, kind)
        assert doc["count"] == len(doc["references"]) > 0
        assert validate_export_doc(doc) == []
        out = tmp_path / f"{kind}.json"
        write_export(doc, out)
        app2 = make_app(tmp_path / "second")
        res = import_file(app2.conn, out)
        assert res["created"] == doc["count"]
        if kind == "images":
            row = app2.conn.execute("SELECT download_status, source_id FROM image_refs LIMIT 1").fetchone()
            assert row[0] == "pending"                       # files are never trusted from an import
            src = app2.conn.execute("SELECT enabled, policy_status FROM sources").fetchone()
            assert (src[0], src[1]) == (0, "unknown")        # nor is the policy
    rec = build_export(app.conn, "images")["references"][0]
    assert rec["schema"] == "magazine_image_reference/1" and rec["rights"]["policy_status"] == "allowed"


def test_invalid_documents_are_rejected_with_reasons(tmp_path):
    app = populated(tmp_path)
    doc = build_export(app.conn, "images")
    bad = json.loads(json.dumps(doc))
    bad["references"][0]["image"]["type"] = "poster"
    bad["references"][0]["work"]["year_start"] = 1999                     # year_end still null
    bad["references"][1]["rights"]["policy_status"] = "probably-fine"
    bad["count"] = 999
    errs = validate_export_doc(bad)
    joined = "\n".join(errs)
    assert "image.type" in joined and "year_end" in joined and "policy_status" in joined and "$.count" in joined
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    raises(ValidationError, import_file, make_app(tmp_path / "x").conn, path)
    page = build_export(app.conn, "pages")["references"][0]
    page["visual_features"]["whitespace"] = {"status": "unverified", "value": "generous", "method": None, "basis": None}
    assert any("unverified feature must have value null" in e for e in validate_reference(page))
    rec = doc["references"][0]
    rec["features"]["semantic"] = [{"feature_type": "style", "feature_value": "minimal", "method": "m",
                                    "tool": None, "confidence": None, "review_status": "ai_suggested",
                                    "evidence_note": None}]
    assert any("AI suggestions must name" in e for e in validate_image_record(rec))


def test_schema_file_matches_generated_schema_and_jsonschema_crosscheck(tmp_path):
    on_disk = json.loads((ROOT / "schema" / "magazine_reference-1.schema.json").read_text())
    assert on_disk == json_schema(), "run: magref schema > schema/magazine_reference-1.schema.json"
    try:
        import jsonschema
    except ImportError:
        print("  (jsonschema not installed: cross-check skipped)")
        return
    app = populated(tmp_path)
    for rec in build_export(app.conn, "pages")["references"]:
        jsonschema.validate(rec, on_disk)
