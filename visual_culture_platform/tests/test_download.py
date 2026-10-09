"""Download path against a real local HTTP server (SafeTransport, loopback allowed for tests only)."""
import os

from helpers import add_image, local_server, make_app, png, raises, register

from magref import maintenance
from magref.assets import AssetRepo, InvalidTransition
from magref.downloader import Downloader
from magref.registry import Registry
from magref.storage import Layout, StorageError, sha256_file

PNG = png(30, 20)


def run(app, ids=None, kind="download", **kw):
    return Downloader(app.conn, app.fetcher, app.settings, app.layout, sleep=lambda s: None).run(
        kind, ids=ids, **kw)


def status(app, aid):
    return AssetRepo(app.conn).get(aid)


def setup(tmp_path, routes, policy="allowed", **kw):
    ctx = local_server(routes)
    base = ctx.__enter__()
    app = make_app(tmp_path, allow_loopback=True, **kw)
    register(app, base, policy=policy)
    return ctx, base, app


def test_normal_download_is_stored_verified_and_content_addressed(tmp_path):
    ctx, base, app = setup(tmp_path, {"/a.png": {"body": PNG}})
    try:
        aid = add_image(app, "src", base + "/a.png")
        res = run(app)
        a = status(app, aid)
        assert res.downloaded == 1 and a["download_status"] == "downloaded"
        assert a["mime_type"] == "image/png" and (a["width"], a["height"]) == (30, 20)
        assert a["size_bytes"] == len(PNG) and a["file_sha256"] == sha256_file(a["abs_path"])
        assert a["abs_path"].endswith(f"{a['file_sha256']}.png") and os.path.isabs(a["abs_path"])
        assert a["final_url"] == base + "/a.png"
        assert list(app.layout.tmp.glob("*.part")) == []
        # rerun: already downloaded -> not selected, not fetched again
        hits = __import__("helpers").Scenario.hits.get("/a.png")
        run(app)
        assert __import__("helpers").Scenario.hits.get("/a.png") == hits
    finally:
        ctx.__exit__(None, None, None)


def test_failure_modes_are_classified_and_leave_no_temp_files(tmp_path):
    routes = {
        "/empty.png": {"body": b""},
        "/html.jpg": {"ctype": "image/jpeg", "body": "<!DOCTYPE html><html><body>error</body></html>"},
        "/textual.png": {"ctype": "text/html", "body": "<html></html>"},
        "/short.png": {"body": PNG, "content_length": len(PNG) + 500, "abort_after": len(PNG)},
        "/cut.png": {"body": PNG * 10, "abort_after": 200},
        "/huge.png": {"body": PNG + b"\0" * 5000},
        "/huge-stream.png": {"body": PNG + b"\0" * 5000, "omit_length": True},
        "/truncated.png": {"body": PNG[:60]},
        "/forbidden.png": {"status": 403, "body": b"no"},
        "/mismatch.png": {"ctype": "image/gif", "body": PNG},
        "/svg.svg": {"ctype": "image/svg+xml", "body": "<svg/>"},
    }
    ctx, base, app = setup(tmp_path, routes, max_file_bytes=2048, max_retries=1)
    try:
        ids = {p: add_image(app, "src", base + p) for p in routes}
        run(app, limit=50)
        got = {p: (status(app, i)["download_status"], status(app, i)["last_error"].split(":")[0]) for p, i in ids.items()}
        assert got["/empty.png"] == ("failed_permanent", "empty_response")
        assert got["/html.jpg"] == ("failed_permanent", "html_instead_of_image")
        assert got["/textual.png"] == ("failed_permanent", "not_image_content_type")
        assert got["/short.png"][0] == "failed_transient"          # length mismatch / interrupted
        assert got["/cut.png"][0] == "failed_transient"
        assert got["/huge.png"] == ("failed_permanent", "too_large")         # Content-Length check
        assert got["/huge-stream.png"] == ("failed_permanent", "too_large")  # streaming cap
        assert got["/truncated.png"] == ("failed_permanent", "truncated_image")
        assert got["/forbidden.png"] == ("blocked", "http_403")
        assert got["/mismatch.png"] == ("failed_permanent", "mime_mismatch")
        assert got["/svg.svg"] == ("failed_permanent", "unsupported_format")
        assert app.conn.execute("SELECT COUNT(*) FROM image_files").fetchone()[0] == 0
        assert list(app.layout.tmp.glob("*")) == [], "partial files must be cleaned up"
        assert list(app.layout.images.rglob("*.*")) == [], "nothing invalid may reach the final directory"
        # 403 is never retried automatically; transient ones were retried within the limit
        from helpers import Scenario
        assert Scenario.hits["/forbidden.png"] == 1 and Scenario.hits["/empty.png"] == 1
        assert Scenario.hits["/cut.png"] == 2                      # 1 + max_retries(1)
        errs = app.conn.execute("SELECT COUNT(*) FROM processing_errors WHERE target_kind='image'").fetchone()[0]
        assert errs == len(routes)
    finally:
        ctx.__exit__(None, None, None)


def test_429_with_retry_after_then_success_and_500_exhausted(tmp_path):
    def flaky(n):
        return {"status": 429, "headers": {"Retry-After": "0"}, "body": b""} if n == 1 else {"body": PNG}
    ctx, base, app = setup(tmp_path, {"/flaky.png": flaky, "/down.png": {"status": 500, "body": b"x"}})
    try:
        ok = add_image(app, "src", base + "/flaky.png")
        bad = add_image(app, "src", base + "/down.png")
        run(app)
        assert status(app, ok)["download_status"] == "downloaded"
        b = status(app, bad)
        assert b["download_status"] == "failed_transient" and b["last_error_class"] == "transient"
        from helpers import Scenario
        assert Scenario.hits["/down.png"] == 1 + app.settings.max_retries
        # `retry --failed` picks it up again; still bounded
        res = run(app, kind="retry")
        assert res.selected == 1 and status(app, bad)["download_status"] == "failed_transient"
    finally:
        ctx.__exit__(None, None, None)


def test_redirects_to_private_ip_or_foreign_host_are_blocked(tmp_path):
    ctx, base, app = setup(tmp_path, {
        "/to-private.png": {"status": 302, "headers": {"Location": "http://10.0.0.5/x.png"}},
        "/to-meta.png": {"status": 302, "headers": {"Location": "http://169.254.169.254/latest/"}},
        "/to-foreign.png": {"status": 302, "headers": {"Location": "https://cdn.elsewhere.test/x.png"}},
        "/ok-redirect.png": {"status": 301, "headers": {"Location": "/real.png"}},
        "/real.png": {"body": PNG},
    })
    try:
        ids = {p: add_image(app, "src", base + p) for p in ("/to-private.png", "/to-meta.png",
                                                            "/to-foreign.png", "/ok-redirect.png")}
        run(app)
        assert status(app, ids["/to-private.png"])["last_error"].startswith("private_address")
        assert status(app, ids["/to-meta.png"])["last_error"].startswith("metadata_address")
        assert status(app, ids["/to-foreign.png"])["last_error"].startswith("redirect_host_not_allowed")
        for p in ("/to-private.png", "/to-meta.png", "/to-foreign.png"):
            assert status(app, ids[p])["download_status"] == "blocked"
        ok = status(app, ids["/ok-redirect.png"])
        assert ok["download_status"] == "downloaded" and ok["final_url"] == base + "/real.png"
        assert ok["url"] == base + "/ok-redirect.png"            # original and final URL kept apart
    finally:
        ctx.__exit__(None, None, None)


def test_loopback_is_blocked_without_the_test_flag(tmp_path):
    with local_server({"/a.png": {"body": PNG}}) as base:
        app = make_app(tmp_path)                                 # allow_loopback defaults to False
        register(app, base)
        aid = add_image(app, "src", base + "/a.png")
        run(app)
        a = status(app, aid)
        assert a["download_status"] == "blocked" and a["last_error"].startswith("loopback_address")


def test_same_bytes_from_two_urls_and_two_sources_stored_once(tmp_path):
    ctx, base, app = setup(tmp_path, {"/one.png": {"body": PNG}, "/two.png": {"body": PNG}})
    try:
        from magref.registry import Source
        Registry(app.conn).add(Source(id="other", name="other", base_url=base + "/", discovery_method="html",
                                      policy_status="allowed", license="CC-BY-4.0"))
        a1 = add_image(app, "src", base + "/one.png")
        a2 = add_image(app, "other", base + "/two.png", declared_license="CC-BY-4.0")
        res = run(app)
        assert res.downloaded == 1 and res.duplicates == 1
        r1, r2 = status(app, a1), status(app, a2)
        assert r1["file_sha256"] == r2["file_sha256"] and r1["abs_path"] == r2["abs_path"]
        assert r1["source_id"] != r2["source_id"] and r2["declared_license"] == "CC-BY-4.0"
        assert app.conn.execute("SELECT COUNT(*) FROM image_files").fetchone()[0] == 1
        assert len([p for p in app.layout.images.rglob("*") if p.is_file()]) == 1
        report = maintenance.deduplicate(app.conn, app.layout)
        assert report["mode"] == "dry-run" and report["same_file_different_urls"][0]["distinct_sources"] == 2
    finally:
        ctx.__exit__(None, None, None)


def test_crash_between_file_move_and_db_commit_is_repaired(tmp_path):
    ctx, base, app = setup(tmp_path, {"/a.png": {"body": PNG}})
    try:
        aid = add_image(app, "src", base + "/a.png")
        dl = Downloader(app.conn, app.fetcher, app.settings, app.layout, sleep=lambda s: None)

        def crash(path):
            raise RuntimeError("simulated crash after file move")
        dl.before_db_commit = crash
        raises(RuntimeError, dl.run, "download")
        app.conn.rollback()
        assert status(app, aid)["download_status"] == "pending"
        files = [p for p in app.layout.images.rglob("*") if p.is_file()]
        assert len(files) == 1 and len(app.layout.journal_entries()) == 1
        assert maintenance.orphans(app.conn, app.layout)["orphan_files"] == [str(files[0])]
        out = maintenance.repair(app.conn, app.layout)
        assert len(out["recovered"]) == 1
        a = status(app, aid)
        assert a["download_status"] == "downloaded" and a["file_sha256"] == sha256_file(files[0])
        assert maintenance.orphans(app.conn, app.layout)["orphan_files"] == []
        assert app.layout.journal_entries() == []
    finally:
        ctx.__exit__(None, None, None)


def test_missing_and_corrupt_files_are_detected_and_recoverable(tmp_path):
    ctx, base, app = setup(tmp_path, {"/a.png": {"body": PNG}, "/b.png": {"body": png(10, 10, (1, 2, 3))}})
    try:
        a = add_image(app, "src", base + "/a.png")
        b = add_image(app, "src", base + "/b.png")
        run(app)
        os.remove(status(app, a)["abs_path"])
        with open(status(app, b)["abs_path"], "ab") as fh:
            fh.write(b"tamper")
        rep = maintenance.verify(app.conn, app.layout)
        assert len(rep["missing"]) == 1 and len(rep["corrupt"]) == 1 and rep["assets_marked"] == 2
        assert status(app, a)["download_status"] == "missing_file"
        assert status(app, b)["file_status"] == "corrupt"
        res = run(app, kind="retry", include_missing=True)
        assert res.duplicates == 2                                 # same bytes -> restored in place
        assert maintenance.verify(app.conn, app.layout)["ok"] == 2
        assert status(app, a)["download_status"] == "downloaded"
    finally:
        ctx.__exit__(None, None, None)


def test_policy_gate_unknown_restricted_disabled(tmp_path):
    ctx, base, app = setup(tmp_path, {"/a.png": {"body": PNG}}, policy="unknown")
    try:
        reg = Registry(app.conn)
        aid = add_image(app, "src", base + "/a.png")
        res = run(app)
        assert res.selected == 0 and res.skipped_not_allowed == 1
        from helpers import Scenario
        assert "/a.png" not in Scenario.hits, "unknown policy: nothing may be fetched"
        reg.review_image(aid, "allowed", license="CC0-1.0", reviewer="t")
        assert run(app).downloaded == 1                            # image-level approval works
        reg.review_source("src", "restricted", note="terms forbid")
        assert reg.effective_image_policy(aid, reg.get("src"))["status"] == "restricted"
        raises(Exception, reg.review_source, "src", "allowed")      # allowed needs evidence
        reg.review_source("src", "allowed", evidence_url="https://example.org/terms")
        reg.set_enabled("src", False)
        a2 = add_image(app, "src", base + "/a2.png")
        assert run(app).selected == 0
        row = dict(AssetRepo(app.conn).get(a2))
        out = Downloader(app.conn, app.fetcher, app.settings, app.layout).download_one(row, None, 10**9)
        assert out["outcome"] == "blocked" and out["code"] == "source_disabled"
    finally:
        ctx.__exit__(None, None, None)


def test_byte_budget_stops_the_run(tmp_path):
    other = png(30, 20, (1, 2, 3))
    ctx, base, app = setup(tmp_path, {"/a.png": {"body": PNG}, "/b.png": {"body": other}})
    try:
        ids = [add_image(app, "src", base + "/a.png"), add_image(app, "src", base + "/b.png")]
        # whichever is first fits; the second would exceed the budget
        res = run(app, max_total_bytes=len(PNG) + len(other) - 1)
        assert res.downloaded == 1 and res.stopped_by_budget and res.status == "stopped_budget"
        assert sorted(status(app, i)["download_status"] for i in ids) == ["downloaded", "pending"]
        assert list(app.layout.tmp.glob("*")) == []
    finally:
        ctx.__exit__(None, None, None)


def test_state_transitions_and_path_safety(tmp_path):
    app = make_app(tmp_path)
    register(app, "https://m.test")
    aid = add_image(app, "src", "https://m.test/x.png")
    repo = AssetRepo(app.conn)
    raises(InvalidTransition, repo.set_status, aid, "missing_file")      # pending -> missing_file
    repo.set_status(aid, "failed_permanent")
    raises(InvalidTransition, repo.set_status, aid, "downloaded")       # needs explicit reset
    repo.set_status(aid, "pending")
    layout = Layout(tmp_path / "root")
    for bad in ("../etc/passwd", "/etc/passwd", "images/../../x", "images\\..\\x"):
        raises(StorageError, layout.resolve, bad)
    raises(StorageError, layout.relative_image_path, "pub", "2026", "../" + "a" * 61, "png")
    raises(StorageError, layout.relative_image_path, "pub", "2026", "a" * 64, "php")
    rel = layout.relative_image_path("../../Évil Pub/..", "2026", "a" * 64, "png")
    assert rel == "images/vil-pub/2026/aa/" + "a" * 64 + ".png"


def test_blocked_items_are_not_retried_until_policy_changes(tmp_path):
    ctx, base, app = setup(tmp_path, {"/a.png": {"body": PNG}})
    try:
        aid = add_image(app, "src", "https://cdn.elsewhere.test/a.png")
        run(app)
        assert status(app, aid)["download_status"] == "blocked"
        assert run(app).selected == 0                       # a re-run does not hammer blocked items
        reg = Registry(app.conn)
        src = reg.get("src")
        src.allowed_asset_hosts = ["cdn.elsewhere.test"]
        reg.add(src, replace=True)                          # configuration change re-opens them
        assert status(app, aid)["download_status"] == "pending"
    finally:
        ctx.__exit__(None, None, None)
