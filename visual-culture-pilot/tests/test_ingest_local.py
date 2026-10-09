"""Tests for ingest_local.py. Local files only; no network.

    python3 -m unittest discover -s tests -v
"""
import contextlib
import csv
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ingest_local as g  # noqa: E402

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

needs_pil = unittest.skipUnless(HAS_PIL, "Pillow not installed in this interpreter")
PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << >>\n%%EOF\n"


def jpeg(size=(30, 20), color=(120, 40, 40)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ingest-test-"))
        self.inbox = self.tmp / "inbox"
        self.archive = self.tmp / "magazine_archive"
        self.inbox.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, name, data):
        (self.inbox / name).write_bytes(data)

    def write_csv(self, rows):
        with open(self.inbox / g.CSV_NAME, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=g.CSV_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow(r)

    def row(self, filename, **kw):
        r = {"filename": filename, "magazine": "Vogue", "edition": "US", "issue_date": "1997-09",
             "page": "112", "page_type": "editorial", "rights_status": "licensed_access_personal_reference",
             "source_url": "https://www.proquest.com/docview/123", "notes": ""}
        r.update(kw)
        return r

    def ingest(self):
        return g.cmd_ingest(self.inbox, self.archive)

    def manifest(self):
        return g.read_manifest(g.manifest_path(self.archive))


class Init(Base):
    def test_rows_added_for_new_files_only(self):
        self.put("a.pdf", PDF)
        self.put(".DS_Store", b"x")
        self.put("notes.txt", b"x")
        r = g.cmd_init(self.inbox, self.archive)
        self.assertEqual(r["new_rows"], ["a.pdf"])
        rows = g.read_rows(self.inbox / g.CSV_NAME)
        self.assertEqual([x["filename"] for x in rows], ["a.pdf"])
        self.assertEqual(list(rows[0]), list(g.CSV_FIELDS))

    def test_existing_edits_preserved_and_ingested_files_skipped(self):
        self.put("a.pdf", PDF)
        self.write_csv([self.row("a.pdf", notes="내 메모")])
        self.ingest()
        self.put("b.pdf", PDF + b"% b\n")
        r = g.cmd_init(self.inbox, self.archive)
        self.assertEqual(r["new_rows"], ["b.pdf"])
        rows = g.read_rows(self.inbox / g.CSV_NAME)
        self.assertEqual(rows[0]["notes"], "내 메모")
        self.assertEqual(rows[0]["magazine"], "Vogue")
        # a renamed copy of an ingested file is recognised by hash
        self.put("a_copy.pdf", PDF)
        self.assertNotIn("a_copy.pdf", g.cmd_init(self.inbox, self.archive)["new_rows"])

    def test_bom_csv_from_excel_is_read(self):
        self.put("a.pdf", PDF)
        text = ",".join(g.CSV_FIELDS) + "\r\n" + "a.pdf,Elle,,2001,,cover,,own_scan_personal_reference,\r\n"
        (self.inbox / g.CSV_NAME).write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
        self.assertEqual(len(self.ingest()["ingested"]), 1)
        self.assertEqual(self.manifest()[0]["magazine"], "Elle")


class Rows(Base):
    def test_incomplete_rows_are_skipped_not_guessed(self):
        self.put("a.pdf", PDF)
        self.write_csv([self.row("a.pdf", magazine=""), self.row("a.pdf", rights_status="")])
        r = self.ingest()
        self.assertEqual(len(r["incomplete"]), 2)
        self.assertEqual(self.manifest(), [])

    def test_invalid_values_rejected(self):
        self.put("a.pdf", PDF)
        bad = [self.row("a.pdf", rights_status="cc0"), self.row("a.pdf", page_type="spread"),
               self.row("a.pdf", issue_date="Sept 1997"), self.row("a.pdf", issue_date="1997-13"),
               self.row("a.pdf", source_url="javascript:alert(1)"), self.row("../etc/passwd")]
        self.write_csv(bad)
        r = self.ingest()
        self.assertEqual(len(r["rejected"]), len(bad), r)
        self.assertEqual(self.manifest(), [])

    def test_missing_file(self):
        self.write_csv([self.row("nope.pdf")])
        self.assertEqual(self.ingest()["rejected"][0]["reason"], "file not found in inbox/")


class Files(Base):
    def test_pdf_ingested_with_structural_check_only(self):
        self.put("vogue p112.pdf", PDF)
        self.write_csv([self.row("vogue p112.pdf")])
        r = self.ingest()
        self.assertEqual(len(r["ingested"]), 1, r)
        rec = self.manifest()[0]
        self.assertEqual(rec["file_type"], "pdf")
        self.assertEqual(rec["validation_status"], "pdf_header_and_eof_ok")
        self.assertIn("not parsed", rec["validation_note"])
        self.assertEqual(rec["source_platform"], "proquest")
        self.assertTrue(rec["local_file_path"].startswith("files/mag_") and rec["local_file_path"].endswith(".pdf"))
        self.assertEqual((self.archive / rec["local_file_path"]).read_bytes(), PDF)
        self.assertEqual((self.inbox / "vogue p112.pdf").read_bytes(), PDF, "inbox file untouched")

    def test_html_named_pdf_rejected(self):
        self.put("page.pdf", b"<!DOCTYPE html><html>login required</html>")
        self.write_csv([self.row("page.pdf")])
        self.assertIn("neither PDF", self.ingest()["rejected"][0]["reason"])

    def test_truncated_pdf_rejected(self):
        self.put("t.pdf", PDF[:-8])
        self.write_csv([self.row("t.pdf")])
        self.assertIn("%%EOF", self.ingest()["rejected"][0]["reason"])

    def test_empty_file_rejected(self):
        self.put("e.jpg", b"")
        self.write_csv([self.row("e.jpg")])
        self.assertEqual(self.ingest()["rejected"][0]["reason"], "empty file")

    @needs_pil
    def test_image_ingested_with_full_decode(self):
        self.put("pin.png.jpg", jpeg())
        self.write_csv([self.row("pin.png.jpg", rights_status="third_party_unverified",
                                 source_url="https://www.pinterest.com/pin/1/")])
        self.assertEqual(len(self.ingest()["ingested"]), 1)
        rec = self.manifest()[0]
        self.assertEqual((rec["file_type"], rec["image_format"], rec["validation_status"]), ("image", "JPEG", "valid"))
        self.assertEqual(rec["source_platform"], "pinterest")
        self.assertIn("not verified", rec["rights_note"])

    @needs_pil
    def test_truncated_image_rejected(self):
        data = jpeg(size=(80, 80))
        self.put("cut.jpg", data[: len(data) // 2])
        self.write_csv([self.row("cut.jpg")])
        self.assertEqual(len(self.ingest()["rejected"]), 1)

    def test_duplicates_and_reingest(self):
        self.put("a.pdf", PDF)
        self.put("a again.pdf", PDF)
        self.write_csv([self.row("a.pdf"), self.row("a again.pdf")])
        r = self.ingest()
        self.assertEqual((len(r["ingested"]), len(r["duplicate"])), (1, 1))
        self.assertEqual(r["duplicate"][0]["kept_file"], "a.pdf")
        r2 = self.ingest()
        self.assertEqual((len(r2["ingested"]), len(r2["duplicate"])), (0, 2))
        self.assertEqual(len(self.manifest()), 1)

    def test_user_fields_kept_separate_from_pipeline_fields(self):
        self.put("a.pdf", PDF)
        self.write_csv([self.row("a.pdf", notes="좋은 레이아웃")])
        self.ingest()
        rec = self.manifest()[0]
        self.assertEqual(rec["notes"], "좋은 레이아웃")
        self.assertEqual(rec["field_provenance"]["magazine"], "user_csv")
        self.assertTrue(rec["field_provenance"]["sha256"].startswith("pipeline"))
        self.assertNotIn("context_claims", rec)


class Validate(Base):
    def setUp(self):
        super().setUp()
        self.put("a.pdf", PDF)
        self.write_csv([self.row("a.pdf")])
        self.ingest()
        self.rec = self.manifest()[0]
        self.path = self.archive / self.rec["local_file_path"]

    def codes(self):
        return {e["code"] for e in g.cmd_validate(self.archive)["errors"]}

    def test_clean(self):
        r = g.cmd_validate(self.archive)
        self.assertEqual((r["status"], r["records"]), ("valid", 1))

    def test_missing_file(self):
        self.path.unlink()
        self.assertIn("file_missing", self.codes())

    def test_hash_mismatch(self):
        self.path.write_bytes(PDF + b"% changed\n")
        self.assertIn("sha256_mismatch", self.codes())

    def test_orphan(self):
        (self.archive / "files" / "stray.pdf").write_bytes(PDF)
        self.assertIn("orphan_file", self.codes())

    def test_no_manifest_is_not_success(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(g.main(["validate", "--archive-dir", str(self.tmp / "empty")]), 3)


class Gallery(Base):
    def test_gallery_escapes_user_text(self):
        self.put("a.pdf", PDF)
        self.write_csv([self.row("a.pdf", magazine="<script>x</script>", notes='"><img src=x>')])
        self.ingest()
        page = g.cmd_gallery(self.archive).read_text(encoding="utf-8")
        self.assertNotIn("<script>x</script>", page)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", page)
        self.assertNotIn('"><img src=x>', page)
        self.assertIn("do not redistribute", page.lower())


if __name__ == "__main__":
    unittest.main()
