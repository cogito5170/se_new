from helpers import MockTransport, Sleeps, raises, settings, timeout_error

from magref.http import Fetcher, FetchError, PolicyBlocked, classify_status

ROBOTS = ("https://m.test/robots.txt", (200, {"content-type": "text/plain"},
                                         "User-agent: *\nDisallow: /private/\nCrawl-delay: 1\n"))


def fetcher(tmp_path, routes, **kw):
    sleeps = Sleeps()
    t = MockTransport(dict([ROBOTS], **routes))
    return Fetcher(settings(tmp_path, **kw), t, sleep=sleeps), t, sleeps


def test_retry_classification():
    assert [classify_status(s) for s in (408, 429, 500, 502, 503, 504)] == ["transient"] * 6
    assert [classify_status(s) for s in (400, 401, 403, 404, 410, 501)] == ["permanent"] * 6


def test_429_honours_retry_after_then_succeeds(tmp_path):
    f, t, sleeps = fetcher(tmp_path, {"https://m.test/a": [
        (429, {"Retry-After": "3"}, ""), (200, {"content-type": "text/html"}, "<p>ok</p>")]})
    r = f.fetch("https://m.test/a")
    assert r.status == 200 and t.calls.count("https://m.test/a") == 2
    assert 3.0 in sleeps                                     # Retry-After respected (> backoff)


def test_retries_are_bounded_and_classified_transient(tmp_path):
    f, t, sleeps = fetcher(tmp_path, {"https://m.test/a": (500, {}, "err")}, max_retries=2)
    err = raises(FetchError, f.fetch, "https://m.test/a")
    assert err.http_status == 500 and err.error_class == "transient"
    assert t.calls.count("https://m.test/a") == 3             # 1 try + 2 retries, no more


def test_403_and_404_are_not_retried(tmp_path):
    f, t, _ = fetcher(tmp_path, {"https://m.test/x": (403, {}, ""), "https://m.test/y": (404, {}, "")})
    assert raises(FetchError, f.fetch, "https://m.test/x").error_class == "permanent"
    assert raises(FetchError, f.fetch, "https://m.test/y").http_status == 404
    assert t.calls.count("https://m.test/x") == 1 and t.calls.count("https://m.test/y") == 1


def test_timeouts_retry_then_fail(tmp_path):
    f, t, _ = fetcher(tmp_path, {"https://m.test/t": [timeout_error(), timeout_error(), timeout_error()]})
    err = raises(FetchError, f.fetch, "https://m.test/t")
    assert err.code == "timeout" and err.transient and t.calls.count("https://m.test/t") == 3


def test_retry_after_longer_than_cap_gives_up(tmp_path):
    f, t, sleeps = fetcher(tmp_path, {"https://m.test/a": (429, {"Retry-After": "3600"}, "")})
    assert raises(FetchError, f.fetch, "https://m.test/a").code == "retry_after_too_long"
    assert 3600 not in sleeps


def test_robots_disallow_and_crawl_delay(tmp_path):
    f, t, sleeps = fetcher(tmp_path, {"https://m.test/private/x": (200, {}, "secret")})
    err = raises(PolicyBlocked, f.fetch, "https://m.test/private/x")
    assert err.code == "robots_disallowed"
    assert "https://m.test/private/x" not in t.calls
    assert f.crawl_delay("https://m.test/") == 1.0


def test_robots_404_allows_and_5xx_disallows(tmp_path):
    t = MockTransport({"https://a.test/robots.txt": (404, {}, ""), "https://a.test/p": (200, {}, "ok"),
                       "https://b.test/robots.txt": (503, {}, ""), "https://b.test/p": (200, {}, "ok")})
    f = Fetcher(settings(tmp_path, max_retries=0), t, sleep=Sleeps())
    assert f.fetch("https://a.test/p").status == 200
    assert raises(PolicyBlocked, f.fetch, "https://b.test/p").code == "robots_disallowed"


def test_redirects_followed_bounded_and_rechecked(tmp_path):
    f, t, _ = fetcher(tmp_path, {
        "https://m.test/old": (301, {"Location": "/new"}, ""),
        "https://m.test/new": (200, {"content-type": "text/html"}, "new"),
        "https://m.test/loop1": (302, {"Location": "/loop2"}, ""),
        "https://m.test/loop2": (302, {"Location": "/loop1"}, ""),
        "https://m.test/evil": (302, {"Location": "http://169.254.169.254/latest/meta-data/"}, ""),
        "https://m.test/r0": (302, {"Location": "/r1"}, ""), "https://m.test/r1": (302, {"Location": "/r2"}, ""),
        "https://m.test/r2": (302, {"Location": "/r3"}, ""), "https://m.test/r3": (302, {"Location": "/r4"}, ""),
        "https://m.test/r4": (302, {"Location": "/r5"}, ""), "https://m.test/r5": (302, {"Location": "/r6"}, ""),
        "https://m.test/r6": (200, {}, "too far"),
    })
    r = f.fetch("https://m.test/old")
    assert r.url == "https://m.test/new" and r.redirects == ["https://m.test/old"]
    assert raises(FetchError, f.fetch, "https://m.test/loop1").code == "redirect_loop"
    err = raises(PolicyBlocked, f.fetch, "https://m.test/evil")
    assert err.code == "metadata_address"
    assert not any("169.254" in c for c in t.calls), "blocked hop must never be requested"
    assert raises(FetchError, f.fetch, "https://m.test/r0").code == "too_many_redirects"


def test_hop_check_policy_applies_after_redirect(tmp_path):
    f, t, _ = fetcher(tmp_path, {"https://m.test/img": (302, {"Location": "https://cdn.other.test/i.png"}, "")})

    def hop(url):
        if "other.test" in url:
            raise PolicyBlocked("redirect_host_not_allowed", "no", url=url)
    assert raises(PolicyBlocked, f.fetch, "https://m.test/img", hop_check=hop).code == "redirect_host_not_allowed"
    assert "https://cdn.other.test/i.png" not in t.calls


def test_response_size_limit(tmp_path):
    big = "x" * 5000
    f, _, _ = fetcher(tmp_path, {"https://m.test/big": (200, {"content-type": "text/html"}, big)},
                      max_page_bytes=2048)
    assert raises(FetchError, f.fetch, "https://m.test/big").code == "too_large"
