"""Network-safety (SSRF) checks.

Three layers, applied to every hop including redirect targets:

1. `check_url`  -- string level: scheme http/https only, no credentials in the
   URL, no blocked host names (localhost, *.internal, cloud metadata names),
   IP literals must be public, non-standard ports only for allowed loopback.
2. `resolve_public` -- DNS level: every address the name resolves to must be
   public. One private answer rejects the whole name (DNS-rebinding defence).
3. connect time -- `SafeTransport` connects to the exact IP that passed (2) and
   re-checks the socket peer address, so a second DNS answer cannot redirect
   the connection (see magref.http).

`allow_loopback` exists only for tests against a local HTTP server. It permits
127.0.0.0/8 and ::1 -- never private ranges, link-local or metadata addresses.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

BLOCKED_HOSTNAMES = {
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
    "metadata", "metadata.google.internal", "instance-data", "instance-data.ec2.internal",
}
BLOCKED_SUFFIXES = (".localhost", ".internal", ".local", ".localdomain", ".home.arpa")
METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
}
STANDARD_PORTS = {None, 80, 443}


class UnsafeURLError(ValueError):
    """The URL or its resolved address is not allowed (never retried)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def check_ip(ip_text: str, allow_loopback: bool = False) -> None:
    try:
        ip = ipaddress.ip_address(ip_text.split("%", 1)[0])
    except ValueError as exc:
        raise UnsafeURLError("invalid_ip", f"invalid IP address: {ip_text}") from exc
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip in METADATA_IPS:
        raise UnsafeURLError("metadata_address", f"cloud metadata address blocked: {ip}")
    if ip.is_loopback:
        if allow_loopback:
            return
        raise UnsafeURLError("loopback_address", f"loopback address blocked: {ip}")
    if (ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved
            or ip.is_unspecified or not ip.is_global):
        raise UnsafeURLError("private_address", f"non-public address blocked: {ip}")


def _ip_literal(host: str) -> str | None:
    try:
        ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
        return host.strip("[]")
    except ValueError:
        pass
    # Integer / short-dotted IPv4 forms ("2130706433", "127.1") that some resolvers accept.
    try:
        packed = socket.inet_aton(host)
        return socket.inet_ntoa(packed)
    except OSError:
        return None


def check_url(url: str, allow_loopback: bool = False) -> None:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("invalid_url", f"unparseable URL: {exc}") from exc
    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError("scheme_not_allowed", f"scheme not allowed: {parts.scheme or '(none)'}")
    if parts.username or parts.password:
        raise UnsafeURLError("credentials_in_url", "URLs with embedded credentials are refused")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURLError("invalid_url", "URL has no host")
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        raise UnsafeURLError("blocked_hostname", f"host name blocked: {host}")
    literal = _ip_literal(host)
    if literal is not None:
        check_ip(literal, allow_loopback)
        loopback = ipaddress.ip_address(literal.split("%", 1)[0]).is_loopback
    else:
        loopback = False
    if port not in STANDARD_PORTS and not (allow_loopback and loopback):
        raise UnsafeURLError("port_not_allowed", f"non-standard port refused: {port}")


def resolve_public(host: str, port: int, allow_loopback: bool = False,
                   resolver=socket.getaddrinfo) -> list[str]:
    """Resolve `host` and return its addresses; raise if ANY address is not public."""
    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError("dns_failure", f"DNS resolution failed for {host}") from exc
    addresses: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in addresses:
            addresses.append(addr)
    if not addresses:
        raise UnsafeURLError("dns_failure", f"no addresses for {host}")
    for addr in addresses:
        check_ip(addr, allow_loopback)
    return addresses
