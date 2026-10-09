from helpers import FIXTURES

from magref.extract import extract
from magref.features import build_features, classify_image_type
from magref.models import DESIGN_FEATURES

BASE = "https://atelier-journal.test/stories/"


def page(name):
    return (FIXTURES / "web" / "atelier-journal.test" / "stories" / name).read_text(encoding="utf-8")


def test_jsonld_graph_takes_precedence_and_provenance_is_recorded():
    ex = extract(page("quiet-volume.html"), BASE + "quiet-volume.html")
    assert ex.title == "Quiet Volume: a minimalist fashion editorial"       # JSON-LD beats og:title
    assert ex.field_sources["title"] == "json-ld:headline"
    assert ex.publisher == "Atelier Journal"
    assert ex.published_at == "2026-03-02T00:30:00Z"                        # converted to UTC
    assert ex.modified_at == "2026-03-04"
    assert ex.category == "Fashion" and ex.language == "en" and ex.page_type == "article"
    assert ex.authors == ["Mina Park (fictional)"]
    assert "asymmetric grid" in ex.keywords
    assert ex.canonical_url == BASE + "quiet-volume.html"
    assert ex.access == "free"


def test_images_alt_caption_roles_and_tracking_pixel():
    ex = extract(page("quiet-volume.html"), BASE + "quiet-volume.html")
    urls = [i.url for i in ex.images]
    assert "https://atelier-journal.test/media/quiet-volume-hero.png" in urls
    assert not any("pixel.gif" in u for u in urls), "1x1 tracking pixel must be skipped"
    hero = next(i for i in ex.images if i.url.endswith("quiet-volume-hero.png"))
    assert hero.role == "primary"
    assert hero.alt.startswith("Model in an oversized white coat")
    assert hero.caption.startswith("Cover story")
    assert ex.stats["image_before_first_paragraph"] is True


def test_open_graph_and_meta_fallbacks():
    ex = extract(page("serif-season.html"), BASE + "serif-season.html")
    assert ex.title == "Serif Season" and ex.field_sources["title"] == "html:title"
    assert ex.description.startswith("A long read") and ex.field_sources["description"] == "meta:description"
    assert ex.category == "Typography" and ex.page_type == "article"
    assert ex.published_at == "2025-11-20" and ex.authors == ["J. Doe (fictional)"]
    assert "Playfair Display" in ex.declared_fonts


def test_missing_metadata_stays_null():
    ex = extract(page("bare-page.html"), BASE + "bare-page.html")
    assert ex.title == "Untitled note"
    for field in ("description", "publisher", "canonical_url", "published_at", "language", "category"):
        assert getattr(ex, field) is None, field
    assert ex.authors == [] and ex.keywords == [] and ex.images == []
    assert ex.page_type == "unknown"


def test_malformed_jsonld_and_bad_date_are_warnings_not_failures():
    ex = extract(page("broken-jsonld.html"), BASE + "broken-jsonld.html")
    codes = {e["code"] for e in ex.errors}
    assert "jsonld_parse_error" in codes and "date_unparseable" in codes
    assert ex.title == "Broken metadata" and ex.published_at is None


def test_malformed_html_does_not_crash():
    ex = extract("<html><head><title>x</title><body><p>unclosed <div><img src='/a.png' alt='a'></span></p>"
                 "</article></body", "https://m.test/")
    assert ex.title == "x" and ex.images[0].url == "https://m.test/a.png"


def test_srcset_data_uri_language_and_robots_meta():
    html = ("<html lang='ko_kr'><head><meta name='robots' content='noindex,nofollow'></head><body>"
            "<img srcset='/s.jpg 320w, /l.jpg 1280w' alt='big'><img src='data:image/png;base64,AAAA'>"
            "</body></html>")
    ex = extract(html, "https://m.test/p")
    assert [i.url for i in ex.images] == ["https://m.test/l.jpg"]
    assert ex.language == "ko-KR"
    assert {"noindex", "nofollow"} <= ex.robots_meta


def test_feature_evidence_levels_are_honest():
    ex = extract(page("quiet-volume.html"), BASE + "quiet-volume.html")
    vf, an, status = build_features(ex, {})
    assert list(vf) == list(DESIGN_FEATURES)
    for name in ("grid_structure", "whitespace", "dominant_colors"):
        assert vf[name]["status"] == "unverified" and vf[name]["value"] is None
    assert vf["text_density"]["status"] == "observed"
    assert vf["aspect_ratio"]["status"] == "inferred"          # declared width/height, not measured
    assert status == "partial"
    measured = {"https://atelier-journal.test/media/quiet-volume-hero.png":
                {"width": 60, "height": 40, "source": "image_header"}}
    vf2, an2, _ = build_features(ex, measured)
    assert vf2["aspect_ratio"]["status"] == "observed"
    assert any(c["claim"] == "hero image likely" for c in an2["inferred"])


def test_image_type_classification_separates_declared_from_inferred():
    assert classify_image_type(declared="cover")[:2] == ("cover", "observed")
    t, status, method, basis = classify_image_type(alt="Magazine cover, spring issue")
    assert (t, status, method) == ("cover", "inferred", "keyword_rule") and "alt text" in basis
    assert classify_image_type(alt="a chair")[:2] == ("other", "unverified")
    assert classify_image_type(page_type="product")[0] == "product_photo"
