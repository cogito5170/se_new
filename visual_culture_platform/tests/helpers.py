"""Shared test helpers: apps on temp dirs, fake transports, a local HTTP server, PNG bytes."""
from __future__ import annotations

import json
import struct
import sys
import threading
import zlib
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from magref.app import open_app                     # noqa: E402
from magref.config import Settings                  # noqa: E402
from magref.http import RawResponse, TransportError, _bytes_response  # noqa: E402

FIXTURES = ROOT / "fixtures"


def png(width: int = 30, height: int = 20, rgb=(200, 30, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class Sleeps(list):
    def __call__(self, seconds):
        self.append(seconds)


def settings(tmp_path: Path, **kw) -> Settings:
    base = dict(data_dir=tmp_path / "data", request_interval=0.0, backoff_base=0.01, max_retries=2,
                timeout=5.0, image_mode="header")
    base.update(kw)
    return Settings(**base)


def make_app(tmp_path: Path, transport=None, sleep=None, **kw):
    return open_app(settings(tmp_path, **kw), transport=transport, sleep=sleep or Sleeps())


class MockTransport:
    """url -> list of responses (consumed in order; last one repeats).
    A response is (status, headers, body) or an Exception instance to raise."""

    def __init__(self, routes: dict):
        self.routes = {k: list(v) if isinstance(v, list) else [v] for k, v in routes.items()}
        self.calls: list[str] = []

    def open(self, method, url, headers, timeout):
        self.calls.append(url)
        seq = self.routes.get(url)
        if seq is None:
            return _bytes_response(404, {"content-type": "text/plain"}, url, b"nope")
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, Exception):
            raise item
        status, hdrs, body = item
        return _bytes_response(status, {k.lower(): v for k, v in hdrs.items()}, url,
                               body if isinstance(body, bytes) else body.encode())


def timeout_error():
    return TransportError("timeout", "request timed out")


# --------------------------------------------------------------------------- local server

class Scenario(BaseHTTPRequestHandler):
    routes: dict = {}
    hits: dict = {}

    def log_message(self, *a):
        return

    def do_GET(self):
        path = self.path.split("?")[0]
        Scenario.hits[path] = Scenario.hits.get(path, 0) + 1
        spec = Scenario.routes.get(path)
        if spec is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if callable(spec):
            spec = spec(Scenario.hits[path])
        status = spec.get("status", 200)
        body = spec.get("body", b"")
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        headers = {"Content-Type": spec.get("ctype", "image/png")}
        headers.update(spec.get("headers", {}))
        if spec.get("omit_length"):
            pass                                  # HTTP/1.0: body ends when the connection closes
        elif "content_length" in spec:
            headers["Content-Length"] = str(spec["content_length"])
        elif "Content-Length" not in headers:
            headers["Content-Length"] = str(len(body))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if spec.get("abort_after") is not None:
            self.wfile.write(body[: spec["abort_after"]])
            self.wfile.flush()
            self.connection.shutdown(2)
            return
        self.wfile.write(body)


@contextmanager
def local_server(routes: dict):
    Scenario.routes = {"/robots.txt": {"ctype": "text/plain", "body": "User-agent: *\nAllow: /\n"}, **routes}
    Scenario.hits = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Scenario)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def register(app, base: str, sid: str = "src", policy: str = "allowed", **kw):
    from magref.registry import Registry, Source
    reg = Registry(app.conn)
    extra = {"license": "CC0-1.0", "evidence_url": "https://example.org/terms"} if policy == "allowed" else {}
    return reg.add(Source(id=sid, name=sid, base_url=base + "/", discovery_method="html",
                          policy_status=policy, **extra, **kw))


def add_image(app, sid: str, url: str, **meta):
    from magref.assets import AssetRepo, CandidateMeta
    from magref.urls import normalize_url
    aid, _ = AssetRepo(app.conn).upsert_candidate(sid, normalize_url(url), "html", CandidateMeta(**meta))
    return aid


def raises(exc_type, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}")


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
