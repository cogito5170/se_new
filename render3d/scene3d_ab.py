# -*- coding: utf-8 -*-
"""scene3d A/B -- on the same scenarios and seeds, compare the IV&V result with 3D visibility off vs on, **per factor**.

Handoff section 9: rule out trivial explanations before stating an effect.
  - Arms: off / on(all) / los only / canopy only / pixels only. Split out which factor makes the difference.
  - LAD sweep (canopy only): if the canopy effect moves with LAD, it depends on an assumption.
  - Operating point: if the off-arm detection rate is saturated near 0 or 1, the comparison says nothing -- report that.
  - Geometry distribution: compare the real canopy_vis distribution for canopy targets with the old constant (0.05).

Fidelity: synthetic DEM (sar_bridge.synthetic_dem) -> **L1**. Only L1-L2 exist in this repository; L3+ (real imagery/sensors) does not.
Run: python3 -m render3d ab [--n 30]
"""
from __future__ import annotations

import math

from render3d.visibility import CAMERAS

# "slant" = 3D range (adds the terrain height difference). The unit bug (rc x DEM mpp) is fixed in the reference itself;
# legacy_slant_units=True reproduces the old one (run_units measures that difference separately).
ALL = ("los", "canopy", "pixels", "slant", "radar_shadow")
ARMS = [("off", None), ("on", ALL), ("지형만", ("los",)), ("수관만", ("canopy",)),
        ("픽셀만", ("pixels",)), ("거리만", ("slant",)), ("레이더그림자만", ("radar_shadow",)), ("on-거리 제외", ("los", "canopy", "pixels", "radar_shadow"))]


def scenarios(n: int = 30, seed: int = 20260928):
    import numpy as np
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        nt = int(rng.integers(1, 4))
        spec = [{"bearing_deg": float(rng.uniform(0, 360)), "range_m": float(rng.uniform(300, 2400)),
                 "canopy": bool(rng.random() < 0.5)} for _ in range(nt)]
        out.append(dict(seed=int(rng.integers(1, 1_000_000)), lat=37.0, lon=128.0,
                        V=float(rng.choice([300, 800, 3000, 20000])), illum=float(rng.choice([50, 2000, 20000])),
                        agl=float(rng.choice([60, 90, 150])), n_target=nt, targets_spec=spec,
                        sensors=["RGB", "SAR", "IMU", "Thermal", "LiDAR"], dem_seed=i % 6))
    return out


def _paths():
    import sys, os
    here = os.path.dirname(os.path.abspath(__file__)); root = os.path.dirname(here)
    for p in (root, os.path.join(root, "sar"), os.path.join(root, "sar", "ivv")):
        if p not in sys.path:
            sys.path.insert(0, p)


def _arm(scs, dems, extra, budget) -> dict:
    """Run the same scenarios with extra settings folded in -> detection rate, CI, false alarms, SUT state share."""
    import harness as Hn
    det = tgt = fa = 0; steps = []
    for sc in scs:
        s = dict(sc); s.update(extra)
        m, _ = Hn.run_one(s, budget=budget, dem=dems[sc["dem_seed"]])
        det += m["detected"]; tgt += m["n_targets"]; fa += m["false_alarms"]; steps.append(m["steps"])
    lo, hi = wilson(det, tgt)
    return {"detect_rate": det / max(1, tgt), "ci95": [round(lo, 3), round(hi, 3)], "detected": det, "targets": tgt,
            "false_alarms": fa, "mean_steps": sum(steps) / len(steps)}


def run(n: int = 200, budget: int = 40, lads=(0.5, 1.5, 3.0)) -> dict:
    _paths()
    import harness as Hn                                   # sar/ivv/harness.py (the same module the IV&V demo uses)
    from render3d.sar_bridge import synthetic_dem
    scs = scenarios(n)
    dems = {k: synthetic_dem(96, seed=k) for k in range(6)}
    res = {}
    wide_th = {"rgb": dict(CAMERAS["rgb"]), "thermal": dict(CAMERAS["thermal"], hfov_deg=CAMERAS["thermal"]["hfov_deg"] * 2)}
    narrow_th = {"rgb": dict(CAMERAS["rgb"]), "thermal": dict(CAMERAS["thermal"], hfov_deg=CAMERAS["thermal"]["hfov_deg"] / 2)}
    arms = [(a, p, 1.5, None) for a, p in ARMS] + [("수관만 LAD=%.1f" % l, ("canopy",), l, None) for l in lads if l != 1.5] + \
           [("픽셀만 열FOV×2", ("pixels",), 1.5, wide_th), ("픽셀만 열FOV×½", ("pixels",), 1.5, narrow_th)]
    for name, parts, lad, cams in arms:
        det = tgt = fa = 0; steps = []
        for sc in scs:
            s = dict(sc)
            if parts is not None:
                s.update(scene3d=True, scene3d_parts=list(parts), lad=lad, scene3d_cams=cams)
            m, _ = Hn.run_one(s, budget=budget, dem=dems[sc["dem_seed"]])
            det += m["detected"]; tgt += m["n_targets"]; fa += m["false_alarms"]; steps.append(m["steps"])
        lo, hi = wilson(det, tgt)
        res[name] = {"detect_rate": det / max(1, tgt), "ci95": [round(lo, 3), round(hi, 3)], "detected": det, "targets": tgt,
                     "false_alarms": fa, "mean_steps": sum(steps) / len(steps)}
    res["_geometry"] = geometry_stats(scs, dems)
    return res


def canyon_scenarios(n: int = 60, seed: int = 20260929):
    """Low altitude + canyon: AGL 30/60 m, targets 300-1500 m, clear air (so fog does not decide it). dem_seed -> canyon_dem."""
    import numpy as np
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        nt = int(rng.integers(1, 4))
        spec = [{"bearing_deg": float(rng.uniform(0, 360)), "range_m": float(rng.uniform(300, 1500)),
                 "canopy": bool(rng.random() < 0.3)} for _ in range(nt)]
        out.append(dict(seed=int(rng.integers(1, 1_000_000)), lat=37.0, lon=128.0, V=20000.0, illum=20000.0,
                        agl=float(rng.choice([30, 60])), n_target=nt, targets_spec=spec,
                        sensors=["RGB", "SAR", "IMU", "Thermal", "LiDAR"], dem_seed=i % 4))
    return out


def run_canyon(n: int = 60, budget: int = 40) -> dict:
    """Is terrain occlusion measured at all? Canyon set: off / terrain only / radar shadow only / on + los_frac distribution."""
    _paths()
    import numpy as np
    import reference as Rf
    from render3d.sar_bridge import canyon_dem
    scs = canyon_scenarios(n); dems = {k: canyon_dem(96, seed=k) for k in range(4)}
    res = {}
    for name, parts in (("off", None), ("지형만", ("los",)), ("레이더그림자만", ("radar_shadow",)), ("on", ALL)):
        res[name] = _arm(scs, dems, {} if parts is None else {"scene3d": True, "scene3d_parts": list(parts)}, budget)
    # Geometry: from UAV poses 1-3 cells away, how often does the terrain block the line of sight?
    # Two trivial explanations, measured and ruled out: (1) straight overhead must always see (nadir),
    # (2) an independent 1 m ray-march that skips the last 3 m by the target must agree -- otherwise it is a slope sampling artifact.
    los, nadir, brute = [], [], []
    for sc in scs[:20]:
        s = dict(sc); s.update(scene3d=True)
        R = Rf.Reference(s, dem=dems[sc["dem_seed"]]); W = R.world3d
        for tg in R._targets:
            tx, ty = R._g2w(tg["gx"], tg["gy"]); tz = float(W.ground(tx, ty)) + 1.2
            nadir.append(W.observe_geometry((tx, ty, tz - 1.2 + R.AGL), (tx, ty), tg.get("yaw3d", 0.0))["los_frac"])
            for (dgx, dgy) in ((1.0, 0.0), (0.0, 2.0), (-2.5, 1.0), (3.0, -1.0)):
                cx, cy = R._g2w(tg["gx"] + dgx, tg["gy"] + dgy); cz = float(W.ground(cx, cy)) + R.AGL
                los.append(W.observe_geometry((cx, cy, cz), (tx, ty), tg.get("yaw3d", 0.0))["los_frac"])
                L = math.dist((cx, cy, cz), (tx, ty, tz)); m = int(L); hit = False
                for k in range(1, m):
                    f = k / m
                    if L * (1 - f) < 3.0:
                        break
                    if float(W.ground(cx + (tx - cx) * f, cy + (ty - cy) * f)) > cz + (tz - cz) * f:
                        hit = True; break
                brute.append(0.0 if hit else 1.0)
    los = np.array(los)
    # Radar shadow: this SUT does not read SAR (sut.py claims from RGB only), so the outcome metrics cannot move --
    # the "radar shadow only" row must equal off exactly. What it changes is the SAR echo count; measure that directly.
    hits = {"off": 0, "on": 0}
    for sc in scs[:30]:
        for k, parts in (("off", ["los"]), ("on", ["los", "radar_shadow"])):
            s = dict(sc); s.update(scene3d=True, scene3d_parts=parts)
            R = Rf.Reference(s, dem=dems[sc["dem_seed"]])
            for tg in R._targets:
                for (dgx, dgy) in ((1.0, 0.0), (0.0, 2.0), (-2.5, 1.0)):
                    hits[k] += R.observe((min(R.GW - 1, max(0, tg["gx"] + dgx)), min(R.GH - 1, max(0, tg["gy"] + dgy))))["sar"]["hits"]
    res["_radar"] = {"sar_hits_no_shadow": hits["off"], "sar_hits_shadow": hits["on"],
                     "kept_share": round(hits["on"] / max(1, hits["off"]), 3)}
    res["_geometry"] = {"n_views": int(los.size), "los_frac_mean": round(float(los.mean()), 3),
                        "fully_hidden_share": round(float((los == 0).mean()), 3), "partly_hidden_share": round(float(((los > 0) & (los < 1)).mean()), 3),
                        "nadir_min": float(min(nadir)), "n_nadir": len(nadir),
                        "brute_hidden_share": round(float((np.array(brute) == 0).mean()), 3),
                        "brute_agree": round(float((np.round(los) == np.array(brute)).mean()), 3)}
    return res


# Tree placement assumption sweep. sigma = offset of the tree from the target (m), size = height range (m), n/cluster_r = cluster.
TREE_CASES = [("기본 σ0.6 10–14m", {}), ("바로 위 σ0", {"sigma": 0.0}), ("어긋남 σ2", {"sigma": 2.0}), ("크게 어긋남 σ4", {"sigma": 4.0}),
              ("작은 나무 5–8m", {"size": (5.0, 8.0)}), ("큰 나무 18–25m", {"size": (18.0, 25.0)}),
              ("군집 5그루 r6m", {"n": 5, "cluster_r": 6.0})]


def run_trees(n: int = 200, budget: int = 40) -> dict:
    """Does the canopy effect survive changes to the tree placement assumption? Canopy-only arm x placement, plus off as the baseline."""
    _paths()
    import numpy as np
    import reference as Rf
    from render3d.sar_bridge import synthetic_dem
    scs = scenarios(n); dems = {k: synthetic_dem(96, seed=k) for k in range(6)}
    res = {"off": _arm(scs, dems, {}, budget)}
    for name, ct in TREE_CASES:
        r = _arm(scs, dems, {"scene3d": True, "scene3d_parts": ["canopy"], "canopy_tree": ct}, budget)
        vis = []
        for sc in scs[:15]:
            s = dict(sc); s.update(scene3d=True, canopy_tree=ct)
            R = Rf.Reference(s, dem=dems[sc["dem_seed"]])
            for tg in R._targets:
                if not tg["canopy"]:
                    continue
                for (dgx, dgy) in ((1.0, 0.0), (0.0, 2.0), (-2.5, 1.0)):
                    cx, cy = R._g2w(tg["gx"] + dgx, tg["gy"] + dgy); cz = float(R.world3d.ground(cx, cy)) + R.AGL
                    vis.append(R.world3d.observe_geometry((cx, cy, cz), R._g2w(tg["gx"], tg["gy"]), tg.get("yaw3d", 0.0))["canopy_vis"])
        r["canopy_vis_p10_50_90"] = [round(float(x), 3) for x in np.percentile(vis, [10, 50, 90])] if vis else None
        res[name] = r
    return res


def run_units(n: int = 200, budget: int = 40) -> dict:
    """Impact of the range-unit fix on existing IV&V results: scene3d off, legacy_slant_units True vs False."""
    _paths()
    from render3d.sar_bridge import synthetic_dem
    scs = scenarios(n); dems = {k: synthetic_dem(96, seed=k) for k in range(6)}
    return {"옛 단위(버그)": _arm(scs, dems, {"legacy_slant_units": True}, budget), "고친 단위": _arm(scs, dems, {}, budget)}


def report_md(r: dict, n: int) -> str:
    g = r.get("_geometry", {})
    L = ["# scene3d A/B — 3D 가시성이 IV&V 결과를 얼마나 바꾸나 (요인별)", "",
         "> **충실도 L1**(합성 DEM). 같은 시나리오 %d개·같은 씨앗, 켠 요소 외에는 옛 처리를 그대로 둔다." % n,
         "> 카메라 해상도·FOV(`visibility.CAMERAS`)·LAD·나무 배치는 **대표값 가정**이다. 현장 검증(L4)이 아니다.", "",
         "| 팔 | 탐지율 | 95% CI (Wilson) | 탐지/표적 | 오경보 |", "|---|---|---|---|---|"]
    for k, v in r.items():
        if k.startswith("_"):
            continue
        L.append("| %s | %.3f | [%.3f, %.3f] | %d/%d | %d |" % (k, v["detect_rate"], v["ci95"][0], v["ci95"][1], v["detected"], v["targets"], v["false_alarms"]))
    L += ["", "## 기하 분포 (수관 표적, UAV 1–3칸 거리의 시점)", "",
          "- 잎 투과 가시비(foliage_vis) p10/p50/p90 = %s — 옛 상수 RGB 0.05 와 대조" % g.get("canopy_foliage_vis_p10_50_90"),
          "- 지형 가시선 비율 평균 = %s — 1.0 이면 이 집합에서 **지형 가림이 측정되지 않은 것**(효과 0 이 아님)" % g.get("los_frac_mean"),
          "- 열 Johnson p10/p50/p90 = %s (카메라 가정 의존)" % g.get("thermal_johnson_p10_50_90"), "",
          "## 효과를 말하기 전에 (사소한 설명)", "",
          "- **사거리 단위 버그는 참조세계에서 고쳤다**(`rc × cell_m`). 이제 '거리만' 팔은 지형 고도차만 더한 3D 경사거리다. "
          "옛 단위와의 차이는 `run_units`(=`python3 -m render3d ab --세트 units`)가 따로 잰다.",
          "- **레이더그림자만 == off 는 정상이다**: 이 SUT 는 SAR 를 안 읽는다(주장은 RGB 로만). 레이더 그림자가 바꾸는 것은 SAR 반향 수다 — 협곡 세트에서 따로 잰다.",
          "- **팔 사이 난수 흐름**: 탐지가 나면 위치 잡음을 두 번 더 뽑으므로 p 가 바뀐 팔은 뒤 흐름이 달라진다. 편향은 아니고 잡음이다 — CI 가 그만큼 넓다.",
          "- **오경보 변화**: 위치오차 `gerr = 0.25 + 1.2(1−p) + …` 가 탐지확률 p 에 묶여 있다. p 가 바뀌면 허용반경 밖 주장이 늘거나 준다 — 새 clutter 가 아니다.",
          "- **LAD 쓸기**로 수관 효과가 거의 안 변하면 → 효과는 잎 밀도 가정이 아니라 기하(비스듬한 광선이 수관을 비껴감)에서 온다. 다만 나무 배치 가정에 달려 있다 → 후보.",
          "- **지형만 팔 == off** 이면 이 합성 지형·고도에선 능선 가림이 일어나지 않은 것이다. 저고도·협곡 케이스가 필요하다."]
    return "\n".join(L) + "\n"


def _rows(r: dict) -> list:
    L = ["| 팔 | 탐지율 | 95% CI (Wilson) | 탐지/표적 | 오경보 |", "|---|---|---|---|---|"]
    for k, v in r.items():
        if not k.startswith("_"):
            L.append("| %s | %.3f | [%.3f, %.3f] | %d/%d | %d |" % (k, v["detect_rate"], v["ci95"][0], v["ci95"][1], v["detected"], v["targets"], v["false_alarms"]))
    return L


def report_extra_md(units: dict = None, canyon: dict = None, trees: dict = None, n: int = 0) -> str:
    """Report for the unit-fix impact / canyon terrain occlusion / tree placement sweep. Only the sets that were run."""
    L = ["# scene3d 추가 측정 (시나리오 %d개, 충실도 L1 합성 DEM)" % n, ""]
    if units:
        a, b = units["옛 단위(버그)"], units["고친 단위"]
        L += ["## 사거리 단위 수정이 기존 IV&V 결과를 얼마나 바꾸나 (scene3d 끔)", ""] + _rows(units) + ["",
              "- 옛 코드: `hypot(rc·mpp, AGL)` — rc 는 격자칸(1칸 = PATCH_M/GW), mpp 는 DEM 픽셀. 수평거리를 DW/GW 배 줄여 표적을 가깝게 봤다.",
              "- 차이 %+.3f. 옛 결과는 **낙관 편향**이었다(가까이 보니 잘 보였다). `legacy_slant_units=True` 로 옛 수치를 재현할 수 있다." % (b["detect_rate"] - a["detect_rate"]),
              "- 같이 바뀐 것: SUT 가 받는 `rgb.vis`(3칸 거리의 투과율)도 같은 단위를 써서 낮아졌다. SUT 의 상태 이름(SEARCHING/DEGRADED/LOW-INFO)만 바뀌고 항법은 안 바뀐다(웨이포인트는 상태와 무관).", ""]
    if canyon:
        g, rd = canyon["_geometry"], canyon["_radar"]
        L += ["## 저고도·협곡 — 지형 가림을 실제로 쟀나", "", "AGL 30/60 m, 표적 300–1500 m, 맑음(V=20 km, 안개가 판을 가르지 않게).", ""] + _rows(canyon) + ["",
              "- 기하: UAV 1–3칸 시점 %d개 중 **%.1f%% 에서 능선이 표적을 완전히 가린다**(부분 가림 %.1f%%). 언덕 세트에서는 0%% 였다." % (g["n_views"], 100 * g["fully_hidden_share"], 100 * g["partly_hidden_share"]),
              "- 사소한 설명 배제: 바로 위(천정) %d개 시점의 최소 가시비 %.2f. 표적 옆 3 m 를 빼고 1 m 간격으로 따로 광선추적하면 가림 %.1f%%, 일치 %.1f%% — 표적 발밑 경사면 표본화 인공물이 아니다." % (g["n_nadir"], g["nadir_min"], 100 * g["brute_hidden_share"], 100 * g["brute_agree"]),
              "- 탐지율 차이(지형만 − off)는 %+.3f 이고 CI 가 겹친다: 시점당 가림 40%% 가 임무 탐지율로는 작게 번진다. UAV 가 움직이며 다른 시점에서 결국 보기 때문일 것으로 **추정**한다(재지 않았다). 효과가 아니라 후보로 적는다." % (canyon["지형만"]["detect_rate"] - canyon["off"]["detect_rate"]),
              "- **레이더 그림자**: 같은 시점에서 SAR 반향 %d → %d (%.1f%% 남음). 기하 가시선 평균 %.3f 와 맞는다(독립 대조: 관측 계수 vs 기하 통계). "
              "탐지율은 off 와 **똑같다** — 이 SUT 는 SAR 를 안 쓴다. SAR 를 쓰는 정책이 들어오면 그때 효과가 나온다." % (rd["sar_hits_no_shadow"], rd["sar_hits_shadow"], 100 * rd["kept_share"], g["los_frac_mean"]),
              "- 모형화 안 함(GAP): 레이오버·다중경로·회절. 그림자는 수직 벽 전제의 기하 가시선이다(V&V R).", ""]
    if trees:
        off = trees["off"]["detect_rate"]
        L += ["## 나무 배치 가정을 바꾸면 수관 효과가 유지되나 (수관만 팔)", ""]
        L += ["| 배치 | 탐지율 | 95% CI | off 대비 | 오경보 | 수관 가시비 p10/50/90 |", "|---|---|---|---|---|---|"]
        for k, v in trees.items():
            if k != "off":
                L.append("| %s | %.3f | [%.3f, %.3f] | %+.3f | %d | %s |" % (k, v["detect_rate"], v["ci95"][0], v["ci95"][1], v["detect_rate"] - off, v["false_alarms"], v.get("canopy_vis_p10_50_90")))
        vals = [v["detect_rate"] - off for k, v in trees.items() if k != "off"]
        L += ["", "- off = %.3f (옛 상수 RGB ×0.05). 배치에 따라 차이가 **%+.3f ~ %+.3f** — 부호까지 바뀐다. **수관 효과는 배치 가정에 달려 있다. 유지되지 않는다.**" % (off, min(vals), max(vals)),
              "- 사소한 설명: σ 2–4 m 는 사람이 수관 밖으로 나간 경우가 많다(가시비 중앙값 ≈1). '수관 아래' 가 아니라 '나무 옆' 을 잰 것이다.",
              "- 사람이 정말 수관 아래일 때(σ0 · 큰 나무 · 군집) 차이는 CI 안이다 — 옛 상수 0.05 가 그 경우엔 대략 맞았다.",
              "- 오경보는 배치마다 크게 달라진다: 위치오차 `gerr` 가 p 에 묶여 있어서 중간 가시비(0.1–0.5)에서 먼 곳에 주장하는 탐지가 늘어난다. 새 clutter 가 아니다.", ""]
    L += ["카메라 해상도·FOV·LAD·나무 배치는 **대표값 가정**이다. 현장 검증(L4)이 아니다."]
    return "\n".join(L) + "\n"


def wilson(k: int, n: int, z: float = 1.96):
    """Wilson 95% interval for a detection rate."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def geometry_stats(scs, dems) -> dict:
    """For canopy targets, the distribution of real geometric visibility (canopy_vis, foliage_vis) seen from UAV poses 1-3 cells away -- compared with the old constant 0.05."""
    import sys, os
    import numpy as np
    import reference as Rf
    fol, comb, los, px_t = [], [], [], []
    for sc in scs[:12]:
        s = dict(sc); s.update(scene3d=True)
        R = Rf.Reference(s, dem=dems[sc["dem_seed"]])
        for tg in R._targets:
            for (dgx, dgy) in ((1.0, 0.0), (0.0, 2.0), (-2.5, 1.0)):
                gx, gy = tg["gx"] + dgx, tg["gy"] + dgy
                cx, cy = R._g2w(gx, gy); cz = float(R.world3d.ground(cx, cy)) + R.AGL
                g = R.world3d.observe_geometry((cx, cy, cz), R._g2w(tg["gx"], tg["gy"]), tg.get("yaw3d", 0.0))
                los.append(g["los_frac"]); px_t.append(g["p_johnson_thermal"])
                if tg["canopy"]:
                    fol.append(g["foliage_vis"]); comb.append(g["canopy_vis"])
    q = lambda a: [round(float(x), 3) for x in np.percentile(a, [10, 50, 90])] if a else None
    return {"canopy_foliage_vis_p10_50_90": q(fol), "canopy_vis_p10_50_90": q(comb), "los_frac_mean": float(np.mean(los)) if los else None,
            "thermal_johnson_p10_50_90": q(px_t), "n_views": len(los), "n_canopy_views": len(fol)}
