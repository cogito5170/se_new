# -*- coding: utf-8 -*-
"""render3d in a real browser -- the three.js render lands at the pinhole prediction, and the fog pixels match Beer-Lambert (vv D).

Without a browser (no playwright, chromium will not start, three.js will not load), print **'건너뜀'** and exit 0.
That is not a pass -- the reason is printed as it is. (Environments where the CDN is blocked: set SE_THREE_DIR to a local three package.)
Run: python3 tests/test_render3d_browser.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from render3d import headless, vv  # noqa: E402

ok_, why = headless.available()
if not ok_:
    print("건너뜀(통과 아님): " + why)
    sys.exit(0)
r = vv.check_browser()
if r["판정"] == "미측정":
    print("건너뜀(통과 아님): " + r["GAP"])
    sys.exit(0)
print("D:", r["판정"], r["측정"])
n = r["_num"]
fails = []
if not n["proj_px"] <= 1.5:
    fails.append("투영 오차 %.2f px > 1.5" % n["proj_px"])
if not n["dT_bl"] <= 0.02:
    fails.append("Beer-Lambert 덮어쓴 안개 |ΔT| %.3f > 0.02" % n["dT_bl"])
if not n["dT_t3"] > 0.05:
    fails.append("기본 FogExp2 와의 차이가 안 보인다(%.3f) -- 덮어쓰기가 실제로 걸렸는지 대조가 무의미" % n["dT_t3"])
# G: 3D visibility -- numpy rays vs three.js mask render (two independent methods). >=2 partial-occlusion cases required.
from render3d import vv_scene3d as V3  # noqa: E402
g = V3.check_visibility_two_methods()
print("G:", g["판정"], g["측정"])
if g["판정"] == "FAIL":
    fails.append("G 가시비 대조 실패: " + g["측정"])
# Mission animation: the page plays to the end in a real browser and records a video (headless.record)
import tempfile  # noqa: E402
from render3d import mission_anim as MA, sar_bridge as B, html as HT  # noqa: E402
sc_, _ = MA.build(dict(MA.default_spec(V=6000.0), budget_min=1), B.synthetic_dem(96, seed=2), speed=20)
with tempfile.TemporaryDirectory() as t:
    hp = Path(t) / "m.html"; HT.write(sc_, hp)
    rv = headless.record(hp, Path(t) / "m.webm", w=960, h=540, speed=20, timeout_s=180)
    print("영상:", rv)
    if not rv["ok"] or (Path(t) / "m.webm").stat().st_size < 10_000:
        fails.append("임무 영상 녹화 실패: %s" % rv.get("reason"))
if fails:
    print("FAIL: " + "; ".join(fails)); sys.exit(1)
print("render3d 브라우저: 투영·안개·3D 가시비·임무 영상 -- 통과")
