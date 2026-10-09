"""Unit tests for the pilot. Every HTTP exchange is mocked; no test touches the network.

    python3 -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import logging
import shutil
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import collector as c  # noqa: E402
import validate_collection as v  # noqa: E402

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

needs_pil = unittest.skipUnless(HAS_PIL, "Pillow not installed in this interpreter")
QUIET = logging.getLogger("collector-tests")
QUIET.addHandler(logging.NullHandler())
QUIET.propagate = False

API = "https://collectionapi.metmuseum.org/public/collection/v1"
IMG = "https://images.metmuseum.org/CRDImages/test/original/{}.jpg"


# --------------------------------------------------------------------------- fakes

class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


class FakeResponse:
    def __init__(self, url, body=b"", status=200, headers=None):
        self._buf = io.BytesIO(body)
        self.status = status
        self._url = url
        msg = Message()
        for k, val in (headers or {}).items():
            msg[k] = val
        self.headers = msg

    def read(self, n=-1):
        return self._buf.read(n)

    def getcode(self):
        return self.status

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """Maps URL -> list of outcomes, consumed in order (the last one repeats).
    An outcome is (status, headers, body) or an Exception instance to raise."""

    def __init__(self, routes):
        self.routes = {k: list(vv) if isinstance(vv, list) else [vv] for k, vv in routes.items()}
        self.calls = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append(url)
        if url not in self.routes:
            raise urllib.error.HTTPError(url, 404, "Not Found", Message(), io.BytesIO(b""))
        queue = self.routes[url]
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, Exception):
            raise outcome
        status, headers, body = outcome
        if status != 200:
            hdrs = Message()
            for k, val in headers.items():
                hdrs[k] = val
            raise urllib.error.HTTPError(url, status, "err", hdrs, io.BytesIO(body))
        return FakeResponse(url, body, status, headers)


def http_error(code, headers=None):
    return (code, headers or {}, b"")


def json_ok(obj):
    return (200, {"Content-Type": "application/json"}, json.dumps(obj).encode())


def image_bytes(fmt="JPEG", size=(16, 12), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def img_ok(body, ctype="image/jpeg", length=True):
    h = {"Content-Type": ctype}
    if length:
        h["Content-Length"] = str(len(body))
    return (200, h, body)


def met_object(oid, pd=True, image=True, **extra):
    obj = {"objectID": oid, "isPublicDomain": pd, "primaryImage": IMG.format(oid) if image else "",
           "title": f"Title {oid}", "artistDisplayName": "", "objectDate": "1893", "country": "",
           "region": "", "classification": "Prints", "medium": "Lithograph",
           "objectURL": f"https://www.metmuseum.org/art/collection/search/{oid}", "creditLine": "Gift, 1950"}
    obj.update(extra)
    return obj


def make_client(routes, clock=None):
    clock = clock or FakeClock()
    opener = FakeOpener(routes)
    client = c.HttpClient(opener=opener, min_interval=0.5, sleep=clock.sleep, clock=clock.clock, log=QUIET)
    return client, opener, clock


class TmpDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vca-test-"))
        self.archive = self.tmp / "visual_culture_archive"
        for sub in ("images", "metadata", "manifests", "logs", "reports"):
            (self.archive / sub).mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# --------------------------------------------------------------------------- metadata

class MetadataParsing(unittest.TestCase):
    def test_missing_optional_fields_become_null(self):
        obj = {"objectID": 7, "isPublicDomain": True, "primaryImage": IMG.format(7)}
        rec = c.build_record(obj, local_file_path="images/met_7.jpg", sha256="ab" * 32, file_size_bytes=10,
                             image_info={"format": "JPEG", "width": 1, "height": 1}, collected_at="2026-01-01T00:00:00Z",
                             snapshot_path="metadata/x.json", snapshot_sha256="cd" * 32, search_term="seed",
                             search_endpoint="seed")
        for f in c.REQUIRED_FIELDS:
            self.assertIn(f, rec)
        for f in ("title", "creator", "creation_year", "publication_year", "country_or_region", "genre",
                  "medium", "source_record_url"):
            self.assertIsNone(rec[f], f)
            self.assertIn(f, rec["metadata_confidence"]["missing_fields"])
        self.assertEqual(rec["field_provenance"]["country_or_region"], "not_provided_by_source")
        self.assertNotIn("None", rec["attribution_text"])

    def test_empty_strings_are_null_not_invented(self):
        obj = met_object(9, artistDisplayName="  ", country="", region="")
        rec = self._rec(obj)
        self.assertIsNone(rec["creator"])
        self.assertIsNone(rec["country_or_region"])

    def test_region_used_only_when_country_absent(self):
        self.assertEqual(self._rec(met_object(1, country="France", region="Normandy"))["country_or_region"], "France")
        rec = self._rec(met_object(2, country="", region="Normandy"))
        self.assertEqual(rec["country_or_region"], "Normandy")
        self.assertEqual(rec["field_provenance"]["country_or_region"], "api:region")

    def test_creation_year_only_from_bare_year(self):
        self.assertEqual(c.parse_bare_year("1893"), 1893)
        for text in ("ca. 1890", "1890-95", "19th century", "", None, "1893 or later"):
            self.assertIsNone(c.parse_bare_year(text), text)
        rec = self._rec(met_object(3, objectDate="ca. 1890"))
        self.assertIsNone(rec["creation_year"])
        self.assertEqual(rec["creation_date_text"], "ca. 1890")
        self.assertIsNone(rec["publication_year"])  # never filled from creation dates

    def test_rights_flag_distinguished_from_general_license(self):
        rec = self._rec(met_object(4))
        self.assertIs(rec["is_public_domain"], True)
        self.assertEqual(rec["rights_evidence"]["api_field"], "isPublicDomain")
        self.assertEqual(rec["rights_evidence"]["license_basis"], "general_policy_statement")
        self.assertEqual(rec["license_evidence_url"],
                         "https://www.metmuseum.org/about-the-met/policies-and-documents/open-access")

    @staticmethod
    def _rec(obj):
        return c.build_record(obj, local_file_path="images/x.jpg", sha256="0" * 64, file_size_bytes=1,
                              image_info={}, collected_at="t", snapshot_path="m", snapshot_sha256="s",
                              search_term="t", search_endpoint="v1/search")


class SourceVersusInterpretation(TmpDirCase):
    def test_record_carries_no_generated_interpretation(self):
        obj = met_object(5, artistDisplayName="Jules Chéret", country="France")
        rec = MetadataParsing._rec(obj)
        self.assertEqual(rec["context_claims"], [])
        self.assertEqual(rec["title"], obj["title"])
        self.assertEqual(rec["creator"], obj["artistDisplayName"])
        self.assertEqual(rec["genre"], obj["classification"])
        self.assertEqual(rec["medium"], obj["medium"])
        for f in c.SOURCE_DESCRIPTIVE_FIELDS:
            if rec[f] is not None:
                self.assertTrue(rec["field_provenance"][f].startswith("api:"), f)

    def test_validator_rejects_uncited_claim_and_non_source_descriptive_value(self):
        rec = MetadataParsing._rec(met_object(6))
        rec["context_claims"] = [{"claim": "An early Art Nouveau poster"}]   # no source_citation
        rec["field_provenance"]["genre"] = "model_inferred"
        issues = []
        v.check_record(rec, 1, self.archive.resolve(), issues)
        codes = {i["code"] for i in issues}
        self.assertIn("uncited_context_claim", codes)
        self.assertIn("descriptive_field_not_from_source", codes)


# --------------------------------------------------------------------------- eligibility

class Eligibility(unittest.TestCase):
    def test_public_domain_flag(self):
        self.assertEqual(c.check_eligibility(met_object(1))[:2], (True, None))
        self.assertEqual(c.check_eligibility(met_object(1, pd=False))[1], "rights_not_public_domain")
        for flag in (None, "true", 1, "yes"):
            obj = met_object(1, pd=flag)
            self.assertEqual(c.check_eligibility(obj)[1], "rights_uncertain", flag)
        obj = met_object(1)
        del obj["isPublicDomain"]
        self.assertEqual(c.check_eligibility(obj)[1], "rights_uncertain")

    def test_rights_checked_before_image(self):
        self.assertEqual(c.check_eligibility(met_object(1, pd=False, image=False))[1], "rights_not_public_domain")

    def test_empty_or_missing_image_url(self):
        for url in ("", "   ", None):
            self.assertEqual(c.check_eligibility(met_object(1, primaryImage=url))[1], "image_url_missing")
        obj = met_object(1)
        del obj["primaryImage"]
        self.assertEqual(c.check_eligibility(obj)[1], "image_url_missing")

    def test_unofficial_image_host(self):
        for url in ("http://images.metmuseum.org/x.jpg", "https://example.org/x.jpg",
                    "https://images.metmuseum.org.evil.test/x.jpg"):
            self.assertEqual(c.check_eligibility(met_object(1, primaryImage=url))[1], "image_url_not_official", url)

    def test_bad_schema(self):
        self.assertEqual(c.check_eligibility({"message": "Not a valid object"})[1], "unexpected_schema")
        self.assertEqual(c.check_eligibility([])[1], "unexpected_schema")


# --------------------------------------------------------------------------- HTTP

class Http(unittest.TestCase):
    def test_interval_below_floor_rejected(self):
        with self.assertRaises(ValueError):
            c.HttpClient(opener=FakeOpener({}), min_interval=0.4)

    def test_requests_are_spaced(self):
        url = f"{API}/objects/1"
        client, _, clock = make_client({url: json_ok(met_object(1))})
        client.get_json(url)
        client.get_json(url)
        self.assertTrue(clock.sleeps and abs(clock.sleeps[0] - 0.5) < 1e-9, clock.sleeps)

    def test_404_not_retried(self):
        url = f"{API}/objects/2"
        client, opener, _ = make_client({url: http_error(404)})
        with self.assertRaises(c.FetchError) as cm:
            client.get_json(url)
        self.assertEqual(cm.exception.category, "not_found")
        self.assertEqual(len(opener.calls), 1)

    def test_503_honours_retry_after_then_succeeds(self):
        url = f"{API}/objects/3"
        client, opener, clock = make_client({url: [http_error(503, {"Retry-After": "2"}), json_ok(met_object(3))]})
        data, _ = client.get_json(url)
        self.assertEqual(data["objectID"], 3)
        self.assertEqual(len(opener.calls), 2)
        self.assertIn(2.0, clock.sleeps)

    def test_persistent_5xx_gives_up(self):
        url = f"{API}/objects/4"
        client, opener, _ = make_client({url: http_error(500)})
        with self.assertRaises(c.FetchError) as cm:
            client.get_json(url)
        self.assertEqual(cm.exception.category, "server_error")
        self.assertEqual(len(opener.calls), client.max_retries + 1)

    def test_long_retry_after_is_not_waited_out(self):
        url = f"{API}/objects/5"
        client, opener, clock = make_client({url: http_error(429, {"Retry-After": "3600"})})
        with self.assertRaises(c.FetchError) as cm:
            client.get_json(url)
        self.assertEqual(cm.exception.category, "rate_limited")
        self.assertEqual(len(opener.calls), 1)
        self.assertNotIn(3600.0, clock.sleeps)

    def test_proxy_denial_not_retried(self):
        url = f"{API}/objects/6"
        client, opener, _ = make_client({url: urllib.error.URLError("Tunnel connection failed: 403 Forbidden")})
        with self.assertRaises(c.FetchError) as cm:
            client.get_json(url)
        self.assertEqual(cm.exception.category, "network_blocked")
        self.assertEqual(len(opener.calls), 1)

    def test_invalid_json(self):
        url = f"{API}/objects/7"
        client, _, _ = make_client({url: (200, {"Content-Type": "text/html"}, b"<html>oops</html>")})
        with self.assertRaises(c.FetchError) as cm:
            client.get_json(url)
        self.assertEqual(cm.exception.category, "invalid_json")

    def test_hosts_outside_allowlist_never_requested(self):
        client, opener, _ = make_client({})
        with self.assertRaises(c.FetchError) as cm:
            client.download("https://example.org/a.jpg", io.BytesIO(), 1000)
        self.assertEqual(cm.exception.category, "host_not_allowed")
        with self.assertRaises(c.FetchError):
            client.get_json("https://images.metmuseum.org/not-the-api")
        self.assertEqual(opener.calls, [])

    def test_redirect_to_unapproved_host_refused(self):
        handler = c._ApprovedHostRedirects()
        req = c.urllib.request.Request(IMG.format(1))
        with self.assertRaises(c.FetchError) as cm:
            handler.redirect_request(req, None, 302, "Found", {}, "https://cdn.example.net/1.jpg")
        self.assertEqual(cm.exception.category, "host_not_allowed")
        ok = handler.redirect_request(req, None, 302, "Found", {}, "https://images.metmuseum.org/other.jpg")
        self.assertEqual(ok.full_url, "https://images.metmuseum.org/other.jpg")

    def test_search_response_parsing(self):
        self.assertEqual(c.parse_search_response({"total": 0, "objectIDs": None}), [])
        self.assertEqual(c.parse_search_response({"total": 2, "objectIDs": [5, 3]}), [5, 3])
        for bad in ({"total": 1}, {"objectIDs": ["5"]}, [1, 2]):
            with self.assertRaises(c.FetchError):
                c.parse_search_response(bad)


# --------------------------------------------------------------------------- downloads

class Downloads(TmpDirCase):
    def _download(self, outcome, oid=1, known=None, max_bytes=c.MAX_IMAGE_BYTES):
        url = IMG.format(oid)
        client, _, _ = make_client({url: outcome})
        return c.download_image(client, url, self.archive / "images", oid, known if known is not None else {}, max_bytes)

    def _assert_fails(self, category, outcome, **kw):
        with self.assertRaises(c.FetchError) as cm:
            self._download(outcome, **kw)
        self.assertEqual(cm.exception.category, category, cm.exception.detail)
        self.assertEqual(list((self.archive / "images").iterdir()), [], "nothing may be left behind")

    def test_http_error_on_image(self):
        self._assert_fails("not_found", http_error(404))

    def test_html_error_page_instead_of_image(self):
        self._assert_fails("not_an_image", img_ok(b"<!DOCTYPE html><html>Error</html>", ctype="text/html"))

    def test_html_body_with_image_content_type(self):
        self._assert_fails("not_an_image", img_ok(b"  <html><body>Error</body></html>", ctype="image/jpeg"))

    def test_empty_file(self):
        self._assert_fails("empty_file", img_ok(b""))

    def test_too_large(self):
        self._assert_fails("too_large", img_ok(b"\xff\xd8" + b"0" * 100), max_bytes=50)

    @needs_pil
    def test_truncated_image(self):
        body = image_bytes(size=(64, 64))
        self._assert_fails("invalid_image", img_ok(body[: len(body) // 2], length=False))

    @needs_pil
    def test_content_length_mismatch_is_truncation(self):
        body = image_bytes()
        self._assert_fails("invalid_image", (200, {"Content-Type": "image/jpeg",
                                                   "Content-Length": str(len(body) + 100)}, body))

    @needs_pil
    def test_garbage_bytes(self):
        self._assert_fails("invalid_image", img_ok(b"\x00\x01not an image" * 10))

    @needs_pil
    def test_valid_image_saved_atomically_with_hash(self):
        body = image_bytes("PNG")
        got = self._download(img_ok(body, ctype="image/png"), oid=436121)
        self.assertEqual(got["path"].name, "met_436121.png")
        self.assertEqual(got["path"].read_bytes(), body)
        self.assertEqual(got["sha256"], c.hashlib.sha256(body).hexdigest())
        self.assertEqual([p.name for p in (self.archive / "images").iterdir()], ["met_436121.png"])

    @needs_pil
    def test_duplicate_sha256_rejected(self):
        body = image_bytes()
        first = self._download(img_ok(body), oid=1)
        known = {first["sha256"]: "met:1"}
        with self.assertRaises(c.FetchError) as cm:
            self._download(img_ok(body), oid=2, known=known)
        self.assertEqual(cm.exception.category, "duplicate_hash")
        self.assertEqual(sorted(p.name for p in (self.archive / "images").iterdir()), ["met_1.jpg"])


class FileSafety(TmpDirCase):
    def test_safe_filename(self):
        self.assertEqual(c.safe_image_filename(436121, "JPEG"), "met_436121.jpg")
        self.assertEqual(c.safe_image_filename(5, "PNG"), "met_5.png")
        for bad_id in ("436121", "../etc/passwd", -1, 0, True, 1.5, None):
            with self.assertRaises(ValueError, msg=repr(bad_id)):
                c.safe_image_filename(bad_id, "JPEG")
        with self.assertRaises(ValueError):
            c.safe_image_filename(1, "PDF")

    def test_existing_file_never_overwritten(self):
        images = self.archive / "images"
        final = images / "met_1.jpg"
        final.write_bytes(b"user's own file")
        tmp = images / ".tmp-x.part"
        tmp.write_bytes(b"new bytes")
        with self.assertRaises(c.FetchError) as cm:
            c.place_without_overwrite(tmp, final)
        self.assertEqual(cm.exception.category, "existing_file_conflict")
        self.assertEqual(final.read_bytes(), b"user's own file")

    @needs_pil
    def test_collector_skips_record_whose_file_already_exists(self):
        images = self.archive / "images"
        (images / "met_11.jpg").write_bytes(b"pre-existing")
        routes = {f"{API}/objects/11": json_ok(met_object(11)), IMG.format(11): img_ok(image_bytes())}
        client, opener, _ = make_client(routes)
        col = c.Collector(self.archive, client, terms=[], seed_objects=[11], log=QUIET)
        stats = col.run()
        self.assertEqual((images / "met_11.jpg").read_bytes(), b"pre-existing")
        self.assertEqual(stats.downloaded, 0)
        self.assertEqual([f["category"] for f in stats.failures], ["existing_file_conflict"])
        self.assertNotIn(IMG.format(11), opener.calls)


class Signature(TmpDirCase):
    """Standard-library magic-byte check. Runs without Pillow; preliminary only."""

    def _sig(self, data):
        p = self.tmp / "f.bin"
        p.write_bytes(data)
        return c.signature_check(p)

    def test_jpeg_with_and_without_end_marker(self):
        self.assertEqual(self._sig(b"\xff\xd8\xff\xe0" + b"x" * 40 + b"\xff\xd9"),
                         {**self._sig(b"\xff\xd8\xff\xe0" + b"x" * 40 + b"\xff\xd9"), "signature_format": "JPEG",
                          "end_marker_ok": True})
        truncated = self._sig(b"\xff\xd8\xff\xe0" + b"x" * 40)
        self.assertEqual((truncated["signature_format"], truncated["end_marker_ok"]), ("JPEG", False))

    def test_png_gif_and_html(self):
        png = self._sig(b"\x89PNG\r\n\x1a\n" + b"x" * 30 + b"\x00\x00\x00\x00IEND\xaeB`\x82")
        self.assertEqual((png["signature_format"], png["end_marker_ok"]), ("PNG", True))
        self.assertEqual(self._sig(b"GIF89a" + b"x" * 20 + b";")["signature_format"], "GIF")
        self.assertIsNone(self._sig(b"<!DOCTYPE html><html></html>")["signature_format"])
        self.assertIn("not equivalent", self._sig(b"x")["note"])


# --------------------------------------------------------------------------- validator

@needs_pil
class Validator(TmpDirCase):
    def _collect(self, oids=(1,)):
        routes = {}
        for i, oid in enumerate(oids):
            routes[f"{API}/objects/{oid}"] = json_ok(met_object(oid, title=f"T{oid}"))
            routes[IMG.format(oid)] = img_ok(image_bytes(size=(10 + i, 10)))
        client, _, _ = make_client(routes)
        c.Collector(self.archive, client, terms=[], seed_objects=list(oids), log=QUIET).run()
        return self.archive / "manifests" / "collection_manifest.jsonl"

    def _codes(self):
        return {e["code"] for e in v.validate(self.archive)["errors"]}

    def test_clean_collection_is_valid(self):
        self._collect((1, 2))
        result = v.validate(self.archive)
        self.assertEqual(result["status"], "valid", result["errors"])
        self.assertEqual(result["records"], 2)

    def test_missing_local_file(self):
        self._collect()
        (self.archive / "images" / "met_1.jpg").unlink()
        self.assertIn("local_file_missing", self._codes())

    def test_hash_mismatch(self):
        self._collect()
        p = self.archive / "images" / "met_1.jpg"
        Image.new("RGB", (16, 12), (1, 2, 3)).save(p, format="JPEG")
        codes = self._codes()
        self.assertIn("sha256_mismatch", codes)

    def test_invalid_jsonl_line(self):
        manifest = self._collect()
        with open(manifest, "a") as fh:
            fh.write("{not json\n")
        self.assertIn("invalid_jsonl", self._codes())

    def test_duplicate_hash_across_records(self):
        manifest = self._collect((1, 2))
        recs = [json.loads(line) for line in manifest.read_text().splitlines()]
        img1 = self.archive / recs[0]["local_file_path"]
        img2 = self.archive / recs[1]["local_file_path"]
        img2.write_bytes(img1.read_bytes())
        recs[1]["sha256"], recs[1]["file_size_bytes"] = recs[0]["sha256"], recs[0]["file_size_bytes"]
        manifest.write_text("".join(json.dumps(r) + "\n" for r in recs))
        self.assertIn("duplicate_sha256", self._codes())

    def test_orphan_image_reported(self):
        self._collect()
        (self.archive / "images" / "met_999.jpg").write_bytes(image_bytes())
        self.assertIn("orphan_image", self._codes())

    def test_path_escape_rejected(self):
        manifest = self._collect()
        rec = json.loads(manifest.read_text())
        rec["local_file_path"] = "../../etc/hosts"
        manifest.write_text(json.dumps(rec) + "\n")
        self.assertIn("local_file_outside_archive", self._codes())

    def test_signature_mismatch(self):
        self._collect()
        p = self.archive / "images" / "met_1.jpg"
        p.write_bytes(image_bytes("PNG"))   # PNG bytes under a .jpg name
        self.assertIn("signature_mismatch", self._codes())

    def test_no_decoder_means_no_pass(self):
        self._collect()
        saved = v.Image
        try:
            v.Image = None
            result = v.validate(self.archive)
        finally:
            v.Image = saved
        self.assertEqual(result["status"], "invalid")
        self.assertIn("image_decode_not_run", {e["code"] for e in result["errors"]})
        self.assertEqual(result["valid_images"], 0)

    def test_empty_manifest_is_not_success(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = v.main(["--archive-dir", str(self.archive), "--report", str(self.tmp / "r.json")])
        self.assertEqual(code, 3)


# --------------------------------------------------------------------------- end to end (mocked)

@needs_pil
class MockedRun(TmpDirCase):
    def routes(self):
        r = {
            f"{API}/objects/436121": json_ok(met_object(436121, classification="Paintings")),
            IMG.format(436121): img_ok(image_bytes(size=(20, 10))),
            f"{API}/search?q=poster&hasImages=true": json_ok({"total": 6, "objectIDs": [436121, 10, 11, 12, 13, 14]}),
            f"{API}/objects/10": json_ok(met_object(10, pd=False)),
            f"{API}/objects/11": json_ok(met_object(11, image=False)),
            f"{API}/objects/12": json_ok(met_object(12, title="Poster A")),
            IMG.format(12): img_ok(image_bytes(size=(30, 10))),
            f"{API}/objects/13": json_ok(met_object(13, title="Poster B")),
            IMG.format(13): (200, {"Content-Type": "text/html"}, b"<html>busy</html>"),
            f"{API}/objects/14": json_ok(met_object(14, title="Poster C")),
            IMG.format(14): img_ok(image_bytes(size=(30, 10))),   # same bytes as 12
        }
        return r

    def test_counts_manifest_and_validation(self):
        client, opener, _ = make_client(self.routes())
        stats = c.Collector(self.archive, client, terms=["poster"], log=QUIET).run()
        self.assertEqual(stats.records_inspected, 6)
        self.assertEqual(stats.excluded, {"rights_not_public_domain": 1, "image_url_missing": 1})
        self.assertEqual(stats.eligible, 4)
        self.assertEqual(stats.downloads_attempted, 4)
        self.assertEqual(stats.transfers_completed, 4)
        self.assertEqual(stats.file_validation_passed, 3)   # 436121, 12, and 14 (valid but duplicate)
        self.assertEqual(stats.duplicates, 1)
        self.assertEqual(stats.downloaded, 2)
        self.assertEqual(sorted(f["category"] for f in stats.failures), ["duplicate_hash", "not_an_image"])
        self.assertEqual(stats.new_records, ["met:436121", "met:12"])
        self.assertEqual(opener.calls[0], f"{API}/objects/436121", "seed object must come first")
        result = v.validate(self.archive)
        self.assertEqual(result["status"], "valid", result["errors"])
        self.assertEqual(result["records"], 2)

    def test_rerun_is_idempotent_and_replay_is_deterministic(self):
        client, _, _ = make_client(self.routes())
        first = c.Collector(self.archive, client, terms=["poster"], log=QUIET).run()
        manifest = (self.archive / "manifests" / "collection_manifest.jsonl").read_text()
        client2, _, _ = make_client(self.routes())
        second = c.Collector(self.archive, client2, terms=["poster"], log=QUIET).run()
        self.assertEqual(second.downloaded, 0)
        self.assertEqual(second.already_in_manifest, 2)
        self.assertEqual((self.archive / "manifests" / "collection_manifest.jsonl").read_text(), manifest)
        # Replay from saved snapshots: same decisions, no network at all.
        client3, opener3, _ = make_client({})
        replay = c.Collector(self.archive, client3, terms=["poster"], log=QUIET, replay_run=first.snapshot_run_id,
                             plan_only=True).run()
        self.assertEqual(opener3.calls, [])
        self.assertEqual([d[:2] for d in replay.decisions], [d[:2] for d in first.decisions])

    def test_max_images_bound(self):
        r = {f"{API}/search?q=print&hasImages=true": json_ok({"total": 15, "objectIDs": list(range(100, 115))})}
        for i, oid in enumerate(range(100, 115)):
            r[f"{API}/objects/{oid}"] = json_ok(met_object(oid, title=f"P{oid}", classification=f"C{oid}"))
            r[IMG.format(oid)] = img_ok(image_bytes(size=(8 + i, 8)))   # distinct sizes -> distinct bytes
        client, opener, _ = make_client(r)
        stats = c.Collector(self.archive, client, terms=["print"], seed_objects=[], per_term=20, log=QUIET).run()
        self.assertEqual(stats.downloaded, 10)
        self.assertEqual(stats.duplicates, 0)
        # Stops as soon as the 10th image is saved: no 11th download, no further object lookups.
        self.assertEqual(sum(1 for u in opener.calls if u.startswith("https://images.")), 10)
        self.assertNotIn(f"{API}/objects/110", opener.calls)
        self.assertEqual(len(list((self.archive / "images").iterdir())), 10)
        with self.assertRaises(ValueError):
            c.Collector(self.archive, client, max_images=11, log=QUIET)

    def test_plan_is_deterministic_round_robin(self):
        res = {"a": [1, 2, 3], "b": [2, 4], "c": []}
        self.assertEqual(c.plan_candidates(res, ["a", "b", "c"], 3), [("a", 1), ("b", 2), ("b", 4), ("a", 3)])
        self.assertEqual(c.plan_candidates(res, ["a", "b", "c"], 3), c.plan_candidates(dict(res), ["a", "b", "c"], 3))


if __name__ == "__main__":
    unittest.main()
