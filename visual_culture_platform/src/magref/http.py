"""HTTP access: transports, robots.txt, rate limiting, retries, redirects.

Layering
--------
Transport  -- performs exactly ONE request and never follows redirects.
              `SafeTransport` talks to the network (SSRF-pinned connections);
              `FixtureTransport` serves files from a local directory.
Fetcher    -- policy around a transport: URL safety on every hop, robots.txt,
              per-host request interval, bounded retries with exponential
              backoff (Retry-After honoured up to a cap), bounded redirects with
              a per-hop policy callback, response size limits.

Nothing here sends cookies or credentials, and request headers are never logged.
"""
from __future__ import annotations

import http.client
import json
import logging
import socket
import ssl
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Iterator, Protocol
from urllib.parse import urljoin, urlsplit

from . import netsafe
from .config import Settings
from .urls import InvalidURL, host_of, normalize_url, origin_of, redact_url

log = logging.getLogger("magref.http")

TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5


class FetchError(Exception):
    """A request failed. `error_class` is 'transient' or 'permanent'."""

    def __init__(self, code: str, message: str, *, error_class: str = "permanent",
                 http_status: int | None = None, url: str | None = None, stage: str = "fetch"):
        super().__init__(message)
        self.code = code
        self.error_class = error_class
        self.http_status = http_status
        self.url = url
        self.stage = stage

    @property
    def transient(self) -> bool:
        return self.error_class == "transient"


class PolicyBlocked(FetchError):
    def __init__(self, code: str, message: str, url: str | None = None, stage: str = "policy"):
        super().__init__(code, message, error_class="permanent", url=url, stage=stage)


class TransportError(Exception):
    """Low-level failure (timeout, reset, DNS). `transient` says whether to retry."""

    def __init__(self, code: str, message: str, transient: bool = True):
        super().__init__(message)
        self.code = code
        self.transient = transient


def classify_status(status: int) -> str:
    return "transient" if status in TRANSIENT_STATUSES else "permanent"


@dataclass
class RawResponse:
    status: int
    headers: dict[str, str]
    url: str
    _read: Callable[[int], bytes]
    _close: Callable[[], None] = lambda: None

    def read(self, n: int) -> bytes:
        try:
            return self._read(n)
        except TransportError:
            raise
        except (http.client.IncompleteRead, ConnectionError, socket.timeout, TimeoutError,
                ssl.SSLError, OSError, http.client.HTTPException) as exc:
            raise TransportError("stream_interrupted",
                                 f"connection interrupted while reading: {type(exc).__name__}") from exc

    def iter_chunks(self, size: int = 65536) -> Iterator[bytes]:
        while True:
            chunk = self.read(size)
            if not chunk:
                return
            yield chunk

    def close(self) -> None:
        try:
            self._close()
        except Exception:  # noqa: BLE001 -- closing must never mask the real error
            pass


class Transport(Protocol):
    def open(self, method: str, url: str, headers: dict[str, str], timeout: float) -> RawResponse:
        ...


# --------------------------------------------------------------------------- real network

class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout, allow_loopback):
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = ip
        self._allow_loopback = allow_loopback

    def connect(self):
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        netsafe.check_ip(self.sock.getpeername()[0], self._allow_loopback)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, timeout, context, allow_loopback):
        super().__init__(host, port, timeout=timeout, context=context)
        self._pinned_ip = ip
        self._allow_loopback = allow_loopback

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        netsafe.check_ip(sock.getpeername()[0], self._allow_loopback)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class SafeTransport:
    """Direct connections only (proxies are not used), pinned to a vetted IP."""

    def __init__(self, allow_loopback: bool = False, resolver=socket.getaddrinfo):
        self.allow_loopback = allow_loopback
        self.resolver = resolver
        self.context = ssl.create_default_context()

    def open(self, method: str, url: str, headers: dict[str, str], timeout: float) -> RawResponse:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            addresses = netsafe.resolve_public(host, port, self.allow_loopback, self.resolver)
        except netsafe.UnsafeURLError as exc:
            if exc.code == "dns_failure":
                raise TransportError("dns_failure", str(exc), transient=True) from exc
            raise
        ip = addresses[0]
        if parts.scheme == "https":
            conn = _PinnedHTTPSConnection(host, port, ip, timeout, self.context, self.allow_loopback)
        else:
            conn = _PinnedHTTPConnection(host, port, ip, timeout, self.allow_loopback)
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        try:
            conn.request(method, target, headers=headers)
            resp = conn.getresponse()
        except netsafe.UnsafeURLError:
            conn.close()
            raise
        except (socket.timeout, TimeoutError) as exc:
            conn.close()
            raise TransportError("timeout", "request timed out") from exc
        except ssl.SSLCertVerificationError as exc:
            conn.close()
            raise TransportError("tls_verification_failed", "TLS certificate verification failed",
                                 transient=False) from exc
        except (ConnectionError, OSError, http.client.HTTPException) as exc:
            conn.close()
            raise TransportError("connection_error", f"connection failed: {type(exc).__name__}") from exc
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        return RawResponse(resp.status, hdrs, url, resp.read, conn.close)


# --------------------------------------------------------------------------- local fixtures

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".xml": "application/xml", ".rss": "application/rss+xml", ".json": "application/json",
    ".txt": "text/plain; charset=utf-8", ".gz": "application/gzip",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp",
}


class FixtureTransport:
    """Serve `https://<host>/<path>` from `<root>/<host>/<path>`.

    A directory path ("/" or ".../") serves `index.html`. Optional per-host
    `_fixture.json` overrides responses: {"/path": {"status": 403}},
    {"/old": {"status": 301, "headers": {"Location": "/new"}}},
    {"/x.jpg": {"status": 200, "headers": {"Content-Type": "image/jpeg"}, "body": "<html>"}}.
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.requests: list[str] = []

    def _overrides(self, host: str) -> dict:
        path = self.root / host / "_fixture.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def open(self, method: str, url: str, headers: dict[str, str], timeout: float) -> RawResponse:
        self.requests.append(url)
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path or "/"
        override = self._overrides(host)
        key_q = path + (f"?{parts.query}" if parts.query else "")
        spec = override.get(key_q) or override.get(path)
        if spec:
            body = spec.get("body", "").encode("utf-8")
            hdrs = {k.lower(): v for k, v in spec.get("headers", {}).items()}
            if "body_file" in spec:
                body = (self.root / host / spec["body_file"]).read_bytes()
            return _bytes_response(int(spec.get("status", 200)), hdrs, url, body)
        rel = path.lstrip("/")
        if not rel or rel.endswith("/"):
            rel += "index.html"
        target = (self.root / host / rel).resolve()
        if self.root / host not in target.parents or not target.is_file() or target.name == "_fixture.json":
            return _bytes_response(404, {"content-type": "text/html"}, url, b"<h1>Not found</h1>")
        body = target.read_bytes()
        ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        return _bytes_response(200, {"content-type": ctype}, url, body)


def _bytes_response(status: int, headers: dict[str, str], url: str, body: bytes) -> RawResponse:
    headers = dict(headers)
    headers.setdefault("content-length", str(len(body)))
    pos = {"i": 0}

    def read(n: int) -> bytes:
        chunk = body[pos["i"]:pos["i"] + n]
        pos["i"] += len(chunk)
        return chunk

    return RawResponse(status, headers, url, read)


def build_transport(settings: Settings, allow_loopback: bool = False) -> Transport:
    if settings.fixture_dir is not None:
        return FixtureTransport(settings.fixture_dir)
    return SafeTransport(allow_loopback=allow_loopback)


# --------------------------------------------------------------------------- fetcher

@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str                     # final URL after redirects
    requested_url: str
    redirects: list[str] = field(default_factory=list)
    robots: str = "not_checked"

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    def text(self) -> str:
        charset = "utf-8"
        ctype = self.headers.get("content-type", "")
        if "charset=" in ctype:
            charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


@dataclass
class StreamResult:
    raw: RawResponse
    requested_url: str
    redirects: list[str]
    robots: str


def parse_retry_after(value: str | None, now: float | None = None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    return max(0.0, dt.timestamp() - (time.time() if now is None else now))


class RateLimiter:
    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self.clock = clock
        self.sleep = sleep
        self._next: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str, interval: float) -> None:
        with self._lock:
            now = self.clock()
            ready = self._next.get(host, now)
            delay = max(0.0, ready - now)
            self._next[host] = max(now, ready) + interval
        if delay > 0:
            self.sleep(delay)


HopCheck = Callable[[str], None]   # raise PolicyBlocked to refuse a hop


class Fetcher:
    def __init__(self, settings: Settings, transport: Transport, *, sleep=time.sleep,
                 clock=time.monotonic, allow_loopback: bool = False):
        self.settings = settings
        self.transport = transport
        self.sleep = sleep
        self.allow_loopback = allow_loopback
        self.rate = RateLimiter(clock=clock, sleep=sleep)
        self._robots: dict[str, tuple[urllib.robotparser.RobotFileParser | None, str]] = {}
        self._robots_lock = threading.Lock()
        self.request_count = 0

    # -- robots ----------------------------------------------------------------
    def robots_status(self, url: str) -> str:
        """'allowed', 'disallowed' or 'unavailable' (no robots.txt -> allowed by RFC 9309)."""
        if not self.settings.respect_robots:
            return "not_checked"
        origin = origin_of(url)
        with self._robots_lock:
            cached = self._robots.get(origin)
        if cached is None:
            cached = self._load_robots(origin)
            with self._robots_lock:
                self._robots[origin] = cached
        parser, state = cached
        if state == "unreachable":
            return "disallowed"
        if parser is None:
            return "unavailable"
        return "allowed" if parser.can_fetch(self.settings.user_agent, url) else "disallowed"

    def crawl_delay(self, url: str) -> float:
        cached = self._robots.get(origin_of(url))
        if cached and cached[0] is not None:
            delay = cached[0].crawl_delay(self.settings.user_agent)
            if delay:
                return min(float(delay), 30.0)
        return 0.0

    def _load_robots(self, origin: str):
        robots_url = urljoin(origin, "/robots.txt")
        try:
            resp = self._fetch_follow(robots_url, max_bytes=500_000, check_robots=False)
        except FetchError as exc:
            # RFC 9309: 4xx -> unavailable (crawl allowed); 5xx / unreachable -> disallow all.
            if exc.http_status is not None and 400 <= exc.http_status < 500:
                return (None, "unavailable")
            log.warning("robots.txt unreachable for %s (%s): treating as disallow-all",
                        origin, exc.code)
            return (None, "unreachable")
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(resp.text().splitlines())
        return (parser, "ok")

    def sitemaps_from_robots(self, url: str) -> list[str]:
        self.robots_status(url)
        cached = self._robots.get(origin_of(url))
        if cached and cached[0] is not None:
            return list(cached[0].site_maps() or [])
        return []

    # -- requests --------------------------------------------------------------
    def _headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept-Encoding": "identity",
            "Accept": "*/*",
        }
        if extra:
            headers.update(extra)
        return headers

    def _one_hop(self, url: str, headers: dict[str, str]) -> RawResponse:
        """One URL, bounded retries for transient failures. Returns a non-retryable response."""
        host = host_of(url)
        attempt = 0
        while True:
            attempt += 1
            interval = max(self.settings.request_interval, self.crawl_delay(url))
            self.rate.wait(host, interval)
            self.request_count += 1
            try:
                raw = self.transport.open("GET", url, headers, self.settings.timeout)
            except netsafe.UnsafeURLError as exc:
                raise PolicyBlocked(exc.code, str(exc), url=url, stage="fetch") from exc
            except TransportError as exc:
                if not exc.transient or attempt > self.settings.max_retries:
                    raise FetchError(exc.code, f"{exc} after {attempt} attempt(s)",
                                     error_class="transient" if exc.transient else "permanent",
                                     url=url) from exc
                delay = self.settings.backoff_base * (2 ** (attempt - 1))
                log.info("retry %d/%d for %s after %s (sleep %.1fs)", attempt,
                         self.settings.max_retries, redact_url(url), exc.code, delay)
                self.sleep(delay)
                continue
            if raw.status not in TRANSIENT_STATUSES:
                return raw
            raw.close()
            retry_after = parse_retry_after(raw.headers.get("retry-after"))
            if attempt > self.settings.max_retries:
                raise FetchError(f"http_{raw.status}",
                                 f"HTTP {raw.status} after {attempt} attempt(s)",
                                 error_class="transient", http_status=raw.status, url=url)
            if retry_after is not None and retry_after > self.settings.max_retry_after:
                raise FetchError("retry_after_too_long",
                                 f"HTTP {raw.status} with Retry-After {retry_after:.0f}s exceeds "
                                 f"cap {self.settings.max_retry_after:.0f}s",
                                 error_class="transient", http_status=raw.status, url=url)
            delay = self.settings.backoff_base * (2 ** (attempt - 1))
            if retry_after is not None:
                delay = max(delay, retry_after)
            log.info("retry %d/%d for %s after HTTP %d (sleep %.1fs)", attempt,
                     self.settings.max_retries, redact_url(url), raw.status, delay)
            self.sleep(delay)

    def open(self, url: str, *, check_robots: bool = True, hop_check: HopCheck | None = None,
             headers: dict[str, str] | None = None) -> StreamResult:
        """Follow redirects (bounded) and return the final 2xx response, unread."""
        try:
            current = normalize_url(url)
        except InvalidURL as exc:
            raise PolicyBlocked("invalid_url", str(exc), url=url, stage="fetch") from exc
        requested = current
        visited: list[str] = []
        robots = "not_checked"
        hdrs = self._headers(headers)
        while True:
            try:
                netsafe.check_url(current, self.allow_loopback)
            except netsafe.UnsafeURLError as exc:
                raise PolicyBlocked(exc.code, str(exc), url=current, stage="fetch") from exc
            if hop_check is not None:
                hop_check(current)
            if check_robots:
                robots = self.robots_status(current)
                if robots == "disallowed":
                    raise PolicyBlocked("robots_disallowed",
                                        f"robots.txt disallows {redact_url(current)}",
                                        url=current, stage="robots")
            raw = self._one_hop(current, hdrs)
            if raw.status in REDIRECT_STATUSES:
                location = raw.headers.get("location")
                raw.close()
                if not location:
                    raise FetchError("redirect_without_location", "redirect without Location",
                                     http_status=raw.status, url=current)
                visited.append(current)
                if len(visited) > MAX_REDIRECTS:
                    raise FetchError("too_many_redirects", f"more than {MAX_REDIRECTS} redirects",
                                     http_status=raw.status, url=current)
                try:
                    nxt = normalize_url(location, base=current)
                except InvalidURL as exc:
                    raise PolicyBlocked("invalid_redirect", f"invalid redirect target: {exc}",
                                        url=current, stage="fetch") from exc
                if nxt in visited:
                    raise FetchError("redirect_loop", "redirect loop detected",
                                     http_status=raw.status, url=current)
                current = nxt
                continue
            if not 200 <= raw.status < 300:
                raw.close()
                raise FetchError(f"http_{raw.status}", f"HTTP {raw.status}",
                                 error_class=classify_status(raw.status),
                                 http_status=raw.status, url=current)
            return StreamResult(raw=raw, requested_url=requested, redirects=visited, robots=robots)

    def _fetch_follow(self, url: str, *, max_bytes: int, check_robots: bool = True,
                      hop_check: HopCheck | None = None) -> Response:
        stream = self.open(url, check_robots=check_robots, hop_check=hop_check)
        raw = stream.raw
        try:
            declared = raw.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise FetchError("too_large", f"Content-Length {declared} exceeds {max_bytes}",
                                 http_status=raw.status, url=raw.url)
            chunks, total = [], 0
            for chunk in raw.iter_chunks():
                total += len(chunk)
                if total > max_bytes:
                    raise FetchError("too_large", f"response exceeds {max_bytes} bytes",
                                     http_status=raw.status, url=raw.url)
                chunks.append(chunk)
        except TransportError as exc:
            raise FetchError(exc.code, str(exc), error_class="transient", url=raw.url) from exc
        finally:
            raw.close()
        return Response(raw.status, raw.headers, b"".join(chunks), raw.url, stream.requested_url,
                        stream.redirects, stream.robots)

    def fetch(self, url: str, *, max_bytes: int | None = None, check_robots: bool = True,
              hop_check: HopCheck | None = None) -> Response:
        return self._fetch_follow(url, max_bytes=max_bytes or self.settings.max_page_bytes,
                                  check_robots=check_robots, hop_check=hop_check)
