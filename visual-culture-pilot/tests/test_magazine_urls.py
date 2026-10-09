"""Tests for magazine_urls.py. All HTTP is mocked; no network."""
import io
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import magazine_urls as U  # noqa: E402

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class Resp:
    def __init__(self, url, body, ctype):
        self._b, self._u = io.BytesIO(body), url
        self.headers = Message()
        self.headers["Content-Type"] = ctype

    def read(self, n=-1):
        return self._b.read(n)

    def geturl(self):
        return self._u

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(routes):
    calls = []

    def op(req, timeout=None):
        calls.append(req.full_url)
        if req.full_url not in routes:
            raise urllib.error.HTTPError(req.full_url, 404, "nf", Message(), io.BytesIO(b""))
        body, ctype = routes[req.full_url]
        return Resp(req.full_url, body, ctype)
    op.calls = calls
    return op


def jpeg():
    b = io.BytesIO()
    Image.new("RGB", (40, 50), (200, 30, 40)).save(b, "JPEG")
    return b.getvalue()


class Parse(unittest.TestCase):
    def test_og_image_preferred_and_resolved(self):
        page = ('<html><head><meta name="twitter:image" content="https://cdn.x/t.jpg">'
                '<meta property="og:image" content="/img/cover.jpg"></head></html>')
        self.assertEqual(U.find_preview_image(page, "https://mag.example/"), "https://mag.example/img/cover.jpg")

    def test_twitter_fallback_and_none(self):
        self.assertEqual(U.find_preview_image('<meta name="twitter:image" content="https://c/t.png">', "https://m/"),
                         "https://c/t.png")
        self.assertIsNone(U.find_preview_image("<html><title>x</title></html>", "https://m/"))
        self.assertIsNone(U.find_preview_image('<meta property="og:image" content="javascript:alert(1)">', "https://m/"))

    def test_keywords_use_vocabulary_only(self):
        U.check_keywords()  # the shipped table is valid
        saved = U.KEYWORDS["vogue"]
        try:
            U.KEYWORDS["vogue"] = (["도시락처럼 나눈 벤토 그리드"], [], [], [])
            with self.assertRaises(SystemExit):
                U.check_keywords()
        finally:
            U.KEYWORDS["vogue"] = saved

    def test_every_magazine_has_keywords_and_https_url_or_none(self):
        for slug, name, _, _, url, _ in U.MAGAZINES:
            self.assertIn(slug, U.KEYWORDS)
            self.assertTrue(url is None or url.startswith("https://"), name)


@unittest.skipUnless(HAS_PIL, "Pillow not installed in this interpreter")
class FetchBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="murl-"))
        self.saved, self.saved_kw = U.MAGAZINES, U.KEYWORDS
        U.KEYWORDS = {k: v for k, v in U.KEYWORDS.items() if k in ("vogue", "purple", "kinfolk", "self-service")}
        U.MAGAZINES = [("vogue", "Vogue", "미국", "글로벌 패션", "https://www.vogue.com", ""),
                       ("purple", "Purple", "프랑스", "패션·아트", "https://purple.fr", ""),
                       ("kinfolk", "Kinfolk", "미국", "라이프스타일", "https://www.kinfolk.com", ""),
                       ("self-service", "Self Service", "프랑스", "패션", None, "")]

    def tearDown(self):
        U.MAGAZINES, U.KEYWORDS = self.saved, self.saved_kw
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fetch_statuses_and_build(self):
        routes = {
            "https://www.vogue.com/robots.txt": (b"User-agent: *\nAllow: /\n", "text/plain"),
            "https://www.vogue.com": (b'<meta property="og:image" content="https://assets.vogue.com/c.jpg">', "text/html"),
            "https://assets.vogue.com/c.jpg": (jpeg(), "image/jpeg"),
            "https://purple.fr/robots.txt": (b"User-agent: *\nDisallow: /\n", "text/plain"),
            "https://www.kinfolk.com": (b"<html>no preview</html>", "text/html"),
        }
        op = opener_for(routes)
        meta = U.fetch(self.tmp, opener=op, sleep=lambda s: None)
        self.assertEqual({k: v["status"] for k, v in meta.items()},
                         {"vogue": "ok", "purple": "robots_disallow", "kinfolk": "no_preview_image",
                          "self-service": "no_official_url"})
        self.assertNotIn("https://purple.fr", op.calls, "robots.txt disallow must stop the page fetch")
        r = U.build(self.tmp, self.tmp / "out.html")
        page = (self.tmp / "out.html").read_text(encoding="utf-8")
        self.assertEqual(r["with_image"], 1)
        self.assertEqual(page.count('src="data:image/jpeg;base64,'), 1)
        self.assertIn("모노크로매틱 배색", page)            # measured colour keyword from the red preview
        self.assertIn('data-tag="타이포그래피:디돈 세리프"', page)
        self.assertIn("사이트가 수집을 허용하지 않음", page)

    def test_non_image_preview_is_an_error(self):
        routes = {"https://www.vogue.com": (b'<meta property="og:image" content="https://x/c.jpg">', "text/html"),
                  "https://x/c.jpg": (b"<html>login</html>", "text/html")}
        meta = U.fetch(self.tmp, opener=opener_for(routes), sleep=lambda s: None, only={"vogue"})
        self.assertEqual(meta["vogue"]["status"], "error")
        self.assertFalse((self.tmp / "images" / "vogue.jpg").exists())


if __name__ == "__main__":
    unittest.main()
