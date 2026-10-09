import socket

from helpers import raises

from magref.netsafe import UnsafeURLError, check_ip, check_url, resolve_public


def test_blocks_local_private_linklocal_and_metadata():
    for url in ("http://127.0.0.1/", "http://localhost/x", "http://10.1.2.3/", "http://192.168.0.5/",
                "http://172.16.0.1/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/",
                "http://[fd00:ec2::254]/", "http://[::ffff:127.0.0.1]/", "http://2130706433/",
                "http://127.1/", "http://metadata.google.internal/", "http://service.internal/",
                "http://printer.local/", "http://0.0.0.0/", "http://100.64.0.1/"):
        raises(UnsafeURLError, check_url, url)


def test_scheme_credentials_and_ports():
    raises(UnsafeURLError, check_url, "ftp://example.org/x")
    raises(UnsafeURLError, check_url, "https://user:pw@example.org/x")
    raises(UnsafeURLError, check_url, "https://example.org:22/x")
    check_url("https://example.org/x")
    check_url("http://93.184.216.34/x")


def test_allow_loopback_is_only_loopback():
    check_url("http://127.0.0.1:8080/x", allow_loopback=True)
    raises(UnsafeURLError, check_url, "http://10.0.0.1:8080/x", allow_loopback=True)
    raises(UnsafeURLError, check_ip, "169.254.169.254", True)


def test_dns_answers_are_checked_all_of_them():
    def resolver(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", port))]
    err = raises(UnsafeURLError, resolve_public, "rebind.test", 443, False, resolver)
    assert err.code == "private_address"

    def ok(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
    assert resolve_public("good.test", 443, False, ok) == ["93.184.216.34"]


def test_dns_failure_is_reported():
    def fail(host, port, type=None):
        raise socket.gaierror("nope")
    assert raises(UnsafeURLError, resolve_public, "x.test", 80, False, fail).code == "dns_failure"
