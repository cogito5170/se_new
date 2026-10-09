"""URL normalization and stable identifiers.

Normalization rules (documented in README):
  * scheme and host lower-cased; IDN hosts converted to punycode
  * default ports (:80 for http, :443 for https) removed
  * fragment removed
  * dot segments resolved; empty path becomes "/"
  * percent-encoding normalized (unreserved characters decoded, hex upper-cased)
  * tracking parameters removed (utm_*, fbclid, gclid, ...), remaining query
    parameters sorted by key (stable order)
  * trailing slashes are NOT removed ("/a" and "/a/" can be different pages);
    canonical links resolve those cases.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "mc_cid", "mc_eid", "_ga", "_gl",
    "igshid", "ref_src", "spm", "cmpid", "ocid",
}
TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "hsa_")
SECRET_PARAM_RE = re.compile(r"(key|token|secret|sig|signature|password|passwd|auth|session|sid)", re.I)

_UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"


class InvalidURL(ValueError):
    pass


def _normalize_component(text: str, safe: str) -> str:
    # Decode then re-encode: normalizes case of %xx and decodes unreserved chars.
    return quote(unquote(text), safe=safe + _UNRESERVED)


def normalize_url(url: str, base: str | None = None) -> str:
    if url is None:
        raise InvalidURL("empty URL")
    url = url.strip()
    if not url:
        raise InvalidURL("empty URL")
    if base:
        url = urljoin(base, url)
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidURL(f"unsupported scheme: {scheme or '(none)'}")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise InvalidURL("missing host")
    try:
        host = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise InvalidURL(f"invalid host: {host}") from exc
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidURL("invalid port") from exc
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = parts.path or "/"
    trailing = path.endswith("/")
    path = posixpath.normpath(path)
    if path in (".", "//"):
        path = "/"
    if path.startswith("//"):
        path = "/" + path.lstrip("/")
    if trailing and not path.endswith("/"):
        path += "/"
    path = _normalize_component(path, safe="/:@!$&'()*+,;=")
    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)
    ]
    query_pairs.sort(key=lambda kv: (kv[0], kv[1]))
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def try_normalize(url: str | None, base: str | None = None) -> str | None:
    if not url:
        return None
    try:
        return normalize_url(url, base)
    except InvalidURL:
        return None


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def same_site(url: str, base_url: str) -> bool:
    """Exact-host match (www.<host> is treated as the same host)."""
    a, b = host_of(url), host_of(base_url)
    strip = lambda h: h[4:] if h.startswith("www.") else h  # noqa: E731
    return strip(a) == strip(b)


def reference_id(identity_url: str) -> str:
    """Stable ID derived from the normalized identity URL."""
    digest = hashlib.sha256(identity_url.encode("utf-8")).hexdigest()
    return "mr_" + digest[:20]


def redact_url(url: str) -> str:
    """Hide values of query parameters that look like credentials (for logs)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable-url>"
    if not parts.query:
        return url
    pairs = [
        (k, "REDACTED" if SECRET_PARAM_RE.search(k) else v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), ""))
