# -*- coding: utf-8 -*-
"""scene3d -- the IV&V reference world computes observations from 3D visibility (contract: render3d/핸드오프_센서스펙_관측계약.md).

What it holds in place (each with the reason it can break):
  - **scene3d off + legacy_slant_units == old code, bit for bit.** The fixture was recorded from the origin/main reference.py
    (6 runs x 50 poses, 6 sensor types, decoys, clutter). The range-unit fix changes the default path on purpose (rc x DEM mpp
    was wrong); the old behaviour is only reproducible with the flag. If this breaks, past numbers can no longer be reproduced.
  - The unit fix: range = grid cells x cell size (PATCH_M/GW), not x DEM pixel size.
  - Radar shadow is decided on a separate random stream -- the main stream does not move (the first version shifted it via p_sar).
  - **scene3d on with no parts == off.** The ablation arms start from the old treatment; if not, you get the fake effect the
    first version produced (los-only dropped the canopy constant).
  - The SUT does not import render3d or visibility (V&V space separation).
  - Cone chord = brute-force integration, vectorised line of sight = loop, Johnson referent, line of sight vs sar/camera occlusion.
  - The A/B report states the fidelity level, the assumptions and the trivial explanations.
Run: python3 tests/test_scene3d.py
"""
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "sar", REPO / "sar" / "ivv"):
    sys.path.insert(0, str(p))

import numpy as np  # noqa: E402

fails = []


def ok(cond, label):
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


import reference as Rf  # noqa: E402  (sar/ivv/reference.py)
from render3d.sar_bridge import synthetic_dem  # noqa: E402
from render3d.visibility import World, TREE, johnson_p  # noqa: E402
from render3d import vv_scene3d as V3, scene3d_ab as AB, discord_cmd as DC  # noqa: E402

# ---- Bit identity
F = json.loads((REPO / "tests/fixtures/reference_obs_scene3d_off.json").read_text(encoding="utf-8"))
diff = 0
for run in F["runs"]:
    R = Rf.Reference(dict(run["scenario"], legacy_slant_units=True), dem=synthetic_dem(96, seed=run["dem_seed"]))
    got = json.loads(json.dumps([R.observe(tuple(p)) for p in F["poses"]]))
    diff += got != run["obs"]
ok(diff == 0, "scene3d 끔 + 옛 단위 == origin/main 참조세계 관측 (6회×50자세, 비트 단위) -- 다름 %d" % diff)
diff = 0
for run in F["runs"][:3]:
    sc = dict(run["scenario"]); sc.update(scene3d=True, scene3d_parts=[], legacy_slant_units=True)
    R = Rf.Reference(sc, dem=synthetic_dem(96, seed=run["dem_seed"]))
    got = json.loads(json.dumps([R.observe(tuple(p)) for p in F["poses"]]))
    diff += got != run["obs"]
ok(diff == 0, "scene3d 켬·요소 없음 == 끔 -- 절제 팔은 옛 처리에서 출발한다 (다름 %d)" % diff)

# ---- Range-unit fix: one grid cell is PATCH_M/GW (not the DEM pixel)
sc0 = dict(F["runs"][0]["scenario"])
Rn = Rf.Reference(sc0, dem=synthetic_dem(96, seed=0)); Rl = Rf.Reference(dict(sc0, legacy_slant_units=True), dem=synthetic_dem(96, seed=0))
ok(abs(Rn.cell_m - Rn.PATCH_M / Rn.GW) < 1e-9 and Rn.cell_m > Rn.mpp, "격자칸 크기 = PATCH_M/GW (%.1f m) > DEM 픽셀 (%.1f m)" % (Rn.cell_m, Rn.mpp))
import math  # noqa: E402
vn, vl = Rn.observe((12.0, 12.0))["rgb"]["vis"], Rl.observe((12.0, 12.0))["rgb"]["vis"]
ok(abs(vn - Rf.ref_transmittance(Rn.V, math.hypot(3 * Rn.cell_m, Rn.AGL))) < 1e-12 and abs(vl - Rf.ref_transmittance(Rl.V, math.hypot(3 * Rl.mpp, Rl.AGL))) < 1e-12,
   "RGB vis 는 3칸 = 3×cell_m 로 잰다 (옛 단위 플래그는 3×mpp)")
ok(vn < vl, "고친 거리 > 옛 거리 -> 투과율이 낮아진다 (%.3f < %.3f)" % (vn, vl))

# ---- Radar shadow: separate random stream
from render3d.sar_bridge import canyon_dem  # noqa: E402
scs_c = AB.canyon_scenarios(12)
same_other = True; h_off = h_on = 0
for scx in scs_c:
    a_ = dict(scx, scene3d=True, scene3d_parts=["los"]); b_ = dict(scx, scene3d=True, scene3d_parts=["los", "radar_shadow"])
    Ra, Rb = Rf.Reference(a_, dem=canyon_dem(96, seed=scx["dem_seed"])), Rf.Reference(b_, dem=canyon_dem(96, seed=scx["dem_seed"]))
    for tg in Ra._targets:
        for d_ in ((1.0, 0.0), (0.0, 2.0), (-2.5, 1.0)):
            p_ = (min(Ra.GW - 1, max(0, tg["gx"] + d_[0])), min(Ra.GH - 1, max(0, tg["gy"] + d_[1])))
            oa, ob = Ra.observe(p_), Rb.observe(p_)
            same_other &= all(json.dumps(oa[k]) == json.dumps(ob[k]) for k in oa if k != "sar")
            h_off += oa["sar"]["hits"]; h_on += ob["sar"]["hits"]
ok(same_other, "레이더 그림자를 켜도 SAR 외 관측은 비트 동일 -- 주 난수 흐름을 안 건드린다")
ok(h_on < h_off, "협곡에서 레이더 그림자가 SAR 반향을 줄인다 (%d -> %d)" % (h_off, h_on))
rr = V3.check_radar_shadow()
ok(rr["판정"] == "PASS", "R: 레이더 그림자 길이 == L=H·d/(Z−H) (%s)" % rr["측정"])

# ---- Reference world with 3D on
sc = dict(F["runs"][0]["scenario"]); sc.update(scene3d=True, targets_spec=[{"bearing_deg": 90, "range_m": 400, "canopy": True}], n_target=1)
Ron = Rf.Reference(sc, dem=synthetic_dem(96, seed=0))
sc_off = dict(sc); sc_off["scene3d"] = False
Roff = Rf.Reference(sc_off, dem=synthetic_dem(96, seed=0))
ok([(t["gx"], t["gy"]) for t in Ron._targets] == [(t["gx"], t["gy"]) for t in Roff._targets], "켜도 표적 위치(주 난수 흐름)가 같다 -- 3D 는 별도 난수를 쓴다")
x, y = Ron._g2w(Ron._targets[0]["gx"], Ron._targets[0]["gy"])
near = [t for t in Ron.world3d.trees if abs(t[0] - x) < 3 and abs(t[1] - y) < 3 and t[3] >= 10]
ok(len(near) >= 1, "canopy 깃발 표적 위에 실제 나무가 있다 (기하로 바뀜)")
o1, o0 = Ron.observe((12.0, 12.0)), Roff.observe((12.0, 12.0))
ok(set(o1) == set(o0) and all(set(o1[k]) == set(o0[k]) for k in o0 if isinstance(o0[k], dict)), "관측 스키마가 끔과 같다 (계약 §1)")
ok(Ron.fidelity.startswith("주어진 DEM") and Rf.Reference(dict(sc, fidelity="L1 합성"), dem=synthetic_dem(96, seed=0)).fidelity == "L1 합성",
   "충실도 표기(주어진 DEM 은 출처 미상, 지정하면 그 값)")

# ---- SUT separation (AST)
for f in ("sut.py", "policies.py"):
    src = (REPO / "sar/ivv" / f).read_text(encoding="utf-8")
    mods = {n.names[0].name if isinstance(n, ast.Import) else (n.module or "") for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom))}
    ok(not any("render3d" in m or "visibility" in m for m in mods), "SUT(%s) 는 render3d·visibility 를 임포트하지 않는다" % f)

# ---- Geometry
rng = np.random.default_rng(1)
tree = (0.0, 0.0, 0.0, 10.0); s = 10.0
r, h = TREE["cone_r"] * s, TREE["cone_h"] * s; zb = (TREE["cone_c"] - TREE["cone_h"] / 2) * s; za = zb + h
P = np.column_stack([rng.uniform(-6, 6, 800), rng.uniform(-6, 6, 800), rng.uniform(-1, 14, 800)])
Q = np.column_stack([rng.uniform(-40, 40, 800), rng.uniform(-40, 40, 800), rng.uniform(-5, 120, 800)])
D = Q - P
an = World._cone_chord(P, D, tree)
ts = (np.arange(3000) + 0.5) / 3000
pts = P[:, None, :] + ts[None, :, None] * D[:, None, :]
w = za - pts[..., 2]
bf = (((pts[..., 0] ** 2 + pts[..., 1] ** 2) <= (r / h) ** 2 * w * w) & (w >= 0) & (w <= h)).mean(axis=1) * np.linalg.norm(D, axis=1)
ok(np.abs(an - bf).max() < 0.06 and (bf > 0).sum() > 50, "원뿔 현 길이(해석) == 무차별 적분 (최대 %.3f m, A<0 경우 포함)" % np.abs(an - bf).max())
dem, mpp = V3.ridge_dem()
Wd = World(dem, mpp)
Pt = Wd.target_samples((400.0, 700.0))
cam = (1050.0, 700.0, float(Wd.ground(1050, 700)) + 30)
ok((Wd.terrain_los_many(cam, Pt) == np.array([Wd.terrain_los(cam, tuple(p)) for p in Pt])).all(), "벡터 가시선 == 반복 가시선")
ok(V3.check_johnson()["판정"] == "PASS" and johnson_p(1.0) == 0.5, "I: Johnson P(N50)=0.5")
h_ = V3.check_los_vs_sar_camera(n=30)
ok(h_["판정"] == "PASS", "H: 지형 가시선 == sar/camera.py 가림 (%s) -- 능선 뒤 피처가 그려지던 버그의 회귀 방지" % h_["측정"])

# ---- A/B report
r = AB.run(n=4, budget=12)
md = AB.report_md(r, 4)
ok(all(k in r for k in ("off", "on", "지형만", "수관만", "픽셀만", "거리만", "레이더그림자만")), "A/B 팔: 끔·켬·지형·수관·픽셀·거리·레이더그림자")
ok(r["레이더그림자만"] == r["off"], "레이더그림자만 == off (이 SUT 는 SAR 를 안 읽는다 -- 다르면 난수 흐름이 샌 것)")
ok("충실도 L1" in md and "대표값 가정" in md and "사거리 단위" in md and "gerr" in md and "SAR 를 안 읽는다" in md, "A/B 보고서가 충실도·가정·사소한 설명을 적는다")
rc_ = AB.run_canyon(n=12, budget=12); g_ = rc_["_geometry"]
ok(g_["fully_hidden_share"] > 0.1, "협곡: 지형 가림이 실제로 일어난다 (완전 가림 %.1f%%)" % (100 * g_["fully_hidden_share"]))
ok(g_["nadir_min"] == 1.0 and g_["brute_agree"] >= 0.9, "협곡 가림은 인공물이 아니다: 천정 늘 보임 · 별도 광선추적 일치 %.1f%%" % (100 * g_["brute_agree"]))
ok(rc_["레이더그림자만"] == rc_["off"] and rc_["_radar"]["sar_hits_shadow"] < rc_["_radar"]["sar_hits_no_shadow"], "협곡: 레이더 그림자는 SAR 반향만 줄인다")
rt_ = AB.run_trees(n=6, budget=12)
ok(rt_["바로 위 σ0"]["canopy_vis_p10_50_90"][1] < rt_["크게 어긋남 σ4"]["canopy_vis_p10_50_90"][1], "나무 배치 쓸기: 바로 위 < 크게 어긋남 (배치 가정이 실제로 기하를 바꾼다)")
ru_ = AB.run_units(n=6, budget=12)
md2 = AB.report_extra_md(units=ru_, canyon=rc_, trees=rt_, n=6)
ok("낙관 편향" in md2 and "추정" in md2 and "유지되지 않는다" in md2 and "GAP" in md2, "추가 보고서: 단위 영향 · 협곡(추정 표시) · 배치 · GAP")
got = []
DC.run("!렌더 3d비교", runner=lambda argv, log, what: (got.append(argv), "ack")[1])
ok(got and got[0][-1] == "ab", "!렌더 3d비교 → python3 -m render3d ab")
ok((REPO / "render3d/핸드오프_센서스펙_관측계약.md").is_file(), "핸드오프 계약 문서")

if fails:
    print("\nFAIL %d" % len(fails)); sys.exit(1)
print("\nscene3d: 끔 비트동일 · 절제 기준 · SUT 분리 · 기하 · 가시선↔sar카메라 · A/B 보고 -- 통과")
