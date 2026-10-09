import contextlib
import io
import json
import logging
import threading
import urllib.error
import urllib.request
from pathlib import Path

from helpers import FIXTURES, make_app
from test_pipeline_fixtures import discover, fixture_app

from magref import cli
from magref.downloader import Downloader
from magref.logutil import RedactingFilter, redact, setup_logging
from magref.web import make_server


def run_cli(tmp_path, *argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["--data-dir", str(tmp_path / "data"), "--fixtures", str(FIXTURES / "web"), *argv])
    return code, out.getvalue(), err.getvalue()


def test_cli_end_to_end_with_exit_codes(tmp_path):
    assert run_cli(tmp_path, "init")[0] == 0
    assert run_cli(tmp_path, "source", "import", str(FIXTURES / "sources.fixture.json"))[0] == 0
    assert run_cli(tmp_path, "discover", "--source", "disabled-demo")[0] == 4
    assert run_cli(tmp_path, "discover", "--source", "restricted-demo")[0] == 4
    assert run_cli(tmp_path, "discover", "--source", "nope")[0] == 3
    code, out, _ = run_cli(tmp_path, "discover", "--source", "atelier")
    assert code == 6 and "http_404" in out                      # partial: one sitemap missing
    code, out, _ = run_cli(tmp_path, "crawl", "--source", "atelier")
    assert code == 6 and "robots_disallowed" in out
    assert run_cli(tmp_path, "discover", "--source", "open-archive")[0] == 0
    assert run_cli(tmp_path, "download")[0] == 2                # --approved is mandatory
    code, out, _ = run_cli(tmp_path, "download", "--approved", "--limit", "100")
    assert code == 6 and "host_not_allowed" in out             # one blocked, rest stored
    code, out, _ = run_cli(tmp_path, "--json", "search", "-q", "minimalist editorial whitespace", "--kind", "pages")
    hits = json.loads(out)
    assert code == 0 and hits[0]["url"].endswith("quiet-volume.html")
    exp = tmp_path / "exp.json"
    assert run_cli(tmp_path, "export", "--format", "json", "--kind", "images", "-o", str(exp))[0] == 0
    assert run_cli(tmp_path, "validate", str(exp))[0] == 0
    bad = json.loads(exp.read_text())
    bad["references"][0]["id"] = "not-an-id"
    exp.write_text(json.dumps(bad))
    assert run_cli(tmp_path, "validate", str(exp))[0] == 5
    assert run_cli(tmp_path, "verify", "--all")[0] == 0
    assert run_cli(tmp_path, "analyze")[0] == 0
    code, out, _ = run_cli(tmp_path, "trend", "compare", "--feature", "orientation", "--a", "1980-1989",
                           "--b", "2010-2019")
    assert code == 0 and "In this collection" in out
    assert run_cli(tmp_path, "trend", "compare", "--feature", "x", "--a", "1990-1980", "--b", "2000")[0] == 2
    code, out, _ = run_cli(tmp_path, "research", "claim-add", "--text", "x", "--type", "other")
    assert code == 0
    assert run_cli(tmp_path, "research", "claim-review", "--claim", "1", "--status", "verified",
                   "--reviewer", "r")[0] == 4
    code, out, _ = run_cli(tmp_path, "status")
    assert code == 0 and "recent errors" in out
    assert run_cli(tmp_path, "show", "--id", "mi_00000000000000000000")[0] == 3


def test_logs_redact_secrets_and_home_paths(tmp_path):
    msg = ("GET https://api.test/x?api_key=SECRET1&q=a Authorization: Bearer abc.def token=XYZ "
           f"password=hunter2 path={Path.home()}/private/file")
    red = redact(msg)
    for secret in ("SECRET1", "abc.def", "XYZ", "hunter2", str(Path.home()) + "/private"):
        assert secret not in red, secret
    assert "q=a" in red
    log_file = tmp_path / "logs" / "magref.log"
    setup_logging("INFO", log_file)
    logging.getLogger("magref.test").warning("retry for %s", "https://m.test/a?token=SECRET2")
    for h in logging.getLogger("magref").handlers:
        h.flush()
    assert "SECRET2" not in log_file.read_text() and "[REDACTED]" in log_file.read_text()
    assert any(isinstance(f, RedactingFilter) for h in logging.getLogger("magref").handlers for f in h.filters)


def test_web_ui_screens_and_safety(tmp_path):
    app = fixture_app(tmp_path)
    discover(app, "open-archive")
    discover(app, "northlight")
    Downloader(app.conn, app.fetcher, app.settings, app.layout, sleep=lambda s: None).run("download", limit=100)
    srv = make_server(app, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def get(path):
        try:
            r = urllib.request.urlopen(base + path)
            return r.status, r.read().decode("utf-8", "replace"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e.headers
    try:
        code, body, headers = get("/")
        assert code == 200 and "Assets by decade" in body and "Content-Security-Policy" in headers
        code, body, _ = get("/explore?q=poster&years=1980-1984&country=JP")
        assert code == 200 and "Synthetic poster study" in body
        assert "No results" in get("/explore?q=zzzz")[1]
        aid = app.conn.execute("SELECT id FROM image_refs WHERE source_id='northlight' LIMIT 1").fetchone()[0]
        code, body, _ = get(f"/asset/{aid}")
        assert code == 200 and "no local file" in body and "unknown" in body
        assert get(f"/file/{aid}")[0] == 404                       # nothing stored for unknown policy
        stored = app.conn.execute("SELECT id FROM image_refs WHERE download_status='downloaded' LIMIT 1").fetchone()[0]
        code, body, headers = get(f"/file/{stored}")
        assert code == 200 and headers["Content-Type"] == "image/png"
        assert get(f"/thumb/{stored}")[0] == 200                  # thumbnail, or the file if none yet
        assert get("/file/..%2F..%2Fetc%2Fpasswd")[0] == 404
        for path in ("/timeline", "/trends?feature=brightness_level", "/contexts", "/projects"):
            assert get(path)[0] == 200, path
        assert "insufficient" in get("/trends?feature=brightness_level&a=1980-1981&b=2010-2011")[1].lower()
        # cross-site POST refused; same-origin POST works
        req = urllib.request.Request(base + "/projects", data=b"title=X", method="POST")
        try:
            urllib.request.urlopen(req)
            raise AssertionError("cross-site POST accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        req = urllib.request.Request(base + "/projects", data=b"title=Relaunch&brief=b", method="POST",
                                     headers={"Origin": base})
        r = urllib.request.urlopen(req)
        assert r.status == 200 and "Relaunch" in r.read().decode()
        assert "&lt;script&gt;" in get("/explore?q=<script>alert(1)</script>")[1]
    finally:
        srv.shutdown()
        srv.server_close()
