from helpers import raises  # noqa: F401  (sets sys.path)

from magref.urls import InvalidURL, normalize_url, redact_url, reference_id, same_site


def test_normalization_rules():
    assert normalize_url("HTTPS://Example.TEST:443/a/./b/../c?b=2&a=1#frag") == "https://example.test/a/c?a=1&b=2"
    assert normalize_url("http://example.test:80") == "http://example.test/"
    assert normalize_url("https://example.test:8443/x") == "https://example.test:8443/x"


def test_tracking_parameters_removed_but_others_kept():
    url = "https://m.test/story?utm_source=nl&utm_medium=email&fbclid=abc&id=7&gclid=z"
    assert normalize_url(url) == "https://m.test/story?id=7"


def test_trailing_slash_is_significant_and_percent_encoding_normalized():
    assert normalize_url("https://m.test/a/") != normalize_url("https://m.test/a")
    assert normalize_url("https://m.test/%7euser/caf%c3%a9") == "https://m.test/~user/caf%C3%A9"


def test_relative_resolution_and_invalid_schemes():
    assert normalize_url("../img/x.png", base="https://m.test/a/b/page.html") == "https://m.test/a/img/x.png"
    for bad in ("javascript:alert(1)", "mailto:x@y.test", "ftp://m.test/x", "", "file:///etc/passwd"):
        raises(InvalidURL, normalize_url, bad)


def test_stable_ids_and_same_site():
    a = reference_id(normalize_url("https://m.test/story?utm_source=x"))
    b = reference_id(normalize_url("https://M.test/story#top"))
    assert a == b and a.startswith("mr_") and len(a) == 23
    assert same_site("https://www.m.test/x", "https://m.test/")
    assert not same_site("https://other.test/x", "https://m.test/")


def test_redact_url_hides_credentials():
    out = redact_url("https://api.test/v1?api_key=SECRET123&q=poster&token=abc")
    assert "SECRET123" not in out and "abc" not in out and "q=poster" in out
