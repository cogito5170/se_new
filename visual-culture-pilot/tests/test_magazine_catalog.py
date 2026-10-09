"""Tests for the magazine catalogue (colour measurement, vocabulary gate, build). Local files only."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from PIL import Image
    import catalog_measure as M
    import magazine_catalog as C
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cat-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def img(self, name, colours, size=(120, 120)):
        im = Image.new("RGB", size)
        w = size[0] // len(colours)
        for i, col in enumerate(colours):
            im.paste(col, (i * w, 0, (i + 1) * w if i < len(colours) - 1 else size[0], size[1]))
        p = self.tmp / name
        im.save(p)
        return p


@unittest.skipUnless(HAS_PIL, "Pillow not installed in this interpreter")
class Measure(Base):
    def test_white_is_high_key_achromatic(self):
        m = M.measure(self.img("w.png", [(250, 250, 250)]))
        self.assertEqual((m["key"], m["chroma"], m["scheme"]), ("하이키", "무채색", "무채색 배색"))
        self.assertEqual(m["palette"][0]["hex"][:3], "#FA")

    def test_black_is_low_key(self):
        self.assertEqual(M.measure(self.img("b.png", [(10, 10, 10)]))["key"], "로우키")

    def test_red_is_monochromatic_high_chroma(self):
        m = M.measure(self.img("r.png", [(220, 20, 30)]))
        self.assertEqual((m["scheme"], m["chroma"]), ("모노크로매틱 배색", "고채도"))

    def test_blue_orange_is_complementary_and_contrast_measured(self):
        m = M.measure(self.img("bo.png", [(30, 70, 220), (255, 140, 0)]))
        self.assertEqual(m["scheme"], "보색 배색")
        self.assertEqual(len(m["palette"]), 2)
        self.assertAlmostEqual(sum(p["share"] for p in m["palette"]), 1.0, places=2)

    def test_black_white_split_is_high_contrast(self):
        self.assertEqual(M.measure(self.img("bw.png", [(0, 0, 0), (255, 255, 255)]))["contrast"], "고대비")

    def test_rgb_triad_is_triadic(self):
        self.assertEqual(M.measure(self.img("rgb.png", [(220, 30, 30), (30, 200, 30), (30, 60, 220)]))["scheme"],
                         "트라이어딕 배색")

    def test_red_yellow_blue_is_not_triadic_on_the_hsv_wheel(self):
        # RYB is a painter's triad, but on the RGB/HSV hue circle red and yellow are only ~55 degrees apart.
        self.assertEqual(M.measure(self.img("ryb.png", [(220, 30, 30), (240, 220, 20), (30, 60, 220)]))["scheme"],
                         "다색 배색")


@unittest.skipUnless(HAS_PIL, "Pillow not installed in this interpreter")
class Build(Base):
    def setUp(self):
        super().setUp()
        self.pd = self.tmp / "magazine_pd" / "images"
        self.pd.mkdir(parents=True)
        self.mine = self.tmp / "inbox"
        self.mine.mkdir()
        self.img("magazine_pd/images/met_1.jpg", [(200, 180, 150), (30, 30, 30)])
        self.img("magazine_pd/images/met_2.jpg", [(240, 240, 240)])
        self.img("inbox/vogue_1997_09.jpg", [(20, 20, 20), (200, 20, 40)])
        (self.tmp / "magazine_pd" / "manifests").mkdir()
        (self.tmp / "magazine_pd" / "manifests" / "collection_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
            {"local_file_path": "images/met_1.jpg", "title": "Gazette du Bon Ton", "creation_date_text": "1914",
             "is_public_domain": True, "source_record_url": "https://www.metmuseum.org/art/collection/search/1",
             "attribution_text": "The Metropolitan Museum of Art. Object 1.", "creator": None},
            {"local_file_path": "images/met_2.jpg", "title": "Plate", "is_public_domain": True}]), encoding="utf-8")
        self.ann = self.tmp / "annotations.json"

    def write_ann(self, entries):
        self.ann.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")

    def test_non_vocabulary_term_is_rejected(self):
        self.write_ann([{"file": "met_1.jpg", "layout": ["도시락처럼 나눈 벤토 그리드"], "typography": ["디돈 세리프"],
                         "image": ["패션 플레이트"]}])
        with self.assertRaises(SystemExit) as cm:
            C.build([self.pd], self.ann, self.tmp / "out", True)
        self.assertIn("not in catalog_vocab.py", str(cm.exception))

    def test_public_build_uses_met_metadata_and_four_components(self):
        self.write_ann([{"file": "met_1.jpg", "layout": ["마진 프레임", "중앙 축 정렬"], "typography": ["캡션 타이포그래피"],
                         "image": ["패션 플레이트", "포슈아르"], "annotated_by": "Claude (image review)"}])
        r = C.build([self.pd, self.mine], self.ann, self.tmp / "out", True)
        self.assertEqual((r["complete"], r["waiting"]), (1, 1))
        self.assertEqual([n for n, _ in r["skipped_not_public"]], ["vogue_1997_09.jpg"])
        page = (self.tmp / "out" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Gazette du Bon Ton", page)
        self.assertNotIn("vogue_1997_09", page)
        for comp in ("layout:마진 프레임", "typography:캡션 타이포그래피", "image:포슈아르", "colour:"):
            self.assertIn(comp, page)
        self.assertTrue((self.tmp / "out" / "images" / "met_1.jpg").is_file())
        self.assertIn('src="images/met_1.jpg"', page)

    def test_local_build_includes_own_images_with_rights_label(self):
        self.write_ann([{"file": "vogue_1997_09.jpg", "magazine": "Vogue (US)", "issue": "1997-09", "page_type": "표지",
                         "rights": "licensed_access_personal_reference", "layout": ["풀블리드", "마스트헤드 오버랩"],
                         "typography": ["디돈 세리프", "올캡스"], "image": ["사진", "스튜디오", "클로즈업"]}])
        r = C.build([self.mine], self.ann, self.tmp / "local", False)
        self.assertEqual(r["complete"], 1)
        page = (self.tmp / "local" / "index.html").read_text(encoding="utf-8")
        self.assertIn("재배포 금지", page)
        self.assertIn("공유하지 마세요", page)

    def test_originals_untouched(self):
        before = (self.pd / "met_1.jpg").read_bytes()
        self.write_ann([])
        C.build([self.pd], self.ann, self.tmp / "out", True)
        self.assertEqual((self.pd / "met_1.jpg").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
