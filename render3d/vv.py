# -*- coding: utf-8 -*-
"""render3d V&V -- the same form as sar/ivv/refval.py: measurement, reference, error, verdict, validity domain, GAP.

**Two verdict kinds.**
  PASS/FAIL  claims that must hold (the implementation matches the reference). Every tolerance is written down.
  측정        a measured difference between two models (not an error of either). Reported as a number and a GAP.
  미측정      not measured (no browser, etc.). **Never reported as PASS.**

  A  SAR camera reimplementation (camera.sar_pixel) vs the actual sar/camera.render output   PASS/FAIL, +/-1 px
  B  SAR camera vs three.js pinhole (same position, heading, vertical FOV)                  측정 (px)
  C  Fog: Beer-Lambert vs three.js default FogExp2 (at equal Koschmieder visibility)        측정 (dT)
  D  three.js render: projection error and fog transmittance (browser)                     PASS/FAIL or 미측정
  E  Heightfield: scene vertices vs DEM and the sar/camera bilinear sampler                PASS/FAIL, 0.01 m
  F  Area programme: sum of per-use areas vs footprint (bundled layouts)                   PASS/FAIL, 0.05 m2

Run: python3 -m render3d vv  -> public_agent_memory/render3d/vv_<ts>.md|png
"""
from __future__ import annotations

import math

from render3d import camera as C
from render3d import fog as FOG

W_SAR, H_SAR = 220, 140


class _PinScene:
    """A fake scene for sar/camera.render: grey ground plus features we place. Only the three methods render calls."""

    def __init__(self, feats):
        self.feats = feats

    def ground_rgb(self, wx, wy):
        import numpy as np
        return np.full((len(np.atleast_1d(wx)), 3), 0.5)

    def query(self, cam_xy, radius_m):
        return list(self.feats)

    def rgb_of(self, f):
        return {"color": (1.0, 0.0, 0.0)}


def check_sar_impl() -> dict:
    """A: do features rendered by the real sar/camera.py land at the pixels camera.sar_pixel predicts?"""
    import numpy as np
    from sar.camera import render as sar_render
    dem = np.zeros((220, 220)); mpp = 10.0
    cam = {"x": 1100.0, "y": 1100.0, "z": 50.0, "heading_deg": 30.0, "pitch_deg": -20.0, "fov_deg": 72.0}
    feats = []
    for k, (da, r) in enumerate([(-28, 180.0), (-12, 320.0), (3, 240.0), (17, 420.0), (29, 150.0)]):
        a = math.radians(cam["heading_deg"] + da)
        feats.append({"kind": "building", "size": 12.0, "wx": cam["x"] + r * math.cos(a), "wy": cam["y"] + r * math.sin(a), "z": 0.0})
    worst_u = worst_v = 0.0
    found = 0
    for f in feats:                                 # Render one at a time so a blob cannot be confused with a neighbour
        img = sar_render(dem, mpp, (cam["x"], cam["y"]), cam["z"], cam["heading_deg"], 1e-7,
                         W=W_SAR, H=H_SAR, fov_deg=cam["fov_deg"], pitch_deg=cam["pitch_deg"], scene=_PinScene([f]))
        red = (img[..., 0] > 0.45) & (img[..., 1] < 0.12) & (img[..., 2] < 0.12)
        if not red.any():
            continue
        found += 1
        cols = np.where(red.any(axis=0))[0]; rows = np.where(red.any(axis=1))[0]
        u, v = C.sar_pixel(cam, (f["wx"], f["wy"], f["z"]), W_SAR, H_SAR)
        worst_u = max(worst_u, abs((cols.min() + cols.max()) / 2 - int(u)))
        worst_v = max(worst_v, abs((rows.max() + 1) - int(np.clip(v, 0, H_SAR - 1))))   # sar/camera: img[top:bot], bot=int(vb)
    ok = found == len(feats) and worst_u <= 1.0 and worst_v <= 1.0
    return {"id": "A", "항목": "RGB 카메라(sar/camera.py) 재구현 ↔ sar/camera.py 실제 출력", "측정": "|Δu|≤%.1f px, |Δv|≤%.1f px (피처 %d/%d)" % (worst_u, worst_v, found, len(feats)),
            "기준": "±1 px (int 절단)", "판정": "PASS" if ok else "FAIL", "유효영역": "평지, 건물 피처, 수평 FOV 72°",
            "GAP": "지형 가림(ybuf)은 대조하지 않았다", "_num": {"du": worst_u, "dv": worst_v, "found": found}}


def check_sar_vs_pinhole(cam=None) -> dict:
    """B: how far apart are the two models on the same camera (for three.js users to know)."""
    cam = cam or {"x": 0.0, "y": 0.0, "z": 90.0, "heading_deg": 0.0, "pitch_deg": -30.0, "fov_deg": 72.0}
    view = C.sar_to_view(cam, W_SAR, H_SAR)
    half = cam["fov_deg"] / 2
    du = dv = 0.0; at = None; centre = None
    for fa in [-0.9, -0.6, -0.3, 0.0, 0.3, 0.6, 0.9]:
        for r in (120.0, 250.0, 500.0, 1000.0):
            a = math.radians(cam["heading_deg"] + fa * half)
            p = (cam["x"] + r * math.cos(a), cam["y"] + r * math.sin(a), 0.0)
            s_ = C.sar_pixel(cam, p, W_SAR, H_SAR); q = C.pinhole_pixel(view, p, W_SAR, H_SAR, "south")
            if s_ is None or q is None:
                continue
            if fa == 0.0 and r == 250.0:
                centre = (s_[0] - q[0], s_[1] - q[1])
            if abs(s_[0] - q[0]) > du:
                du, at = abs(s_[0] - q[0]), (fa, r)
            dv = max(dv, abs(s_[1] - q[1]))
    fh_pin = 2 * math.degrees(math.atan(math.tan(math.radians(view["fov"] / 2)) * W_SAR / H_SAR))
    return {"id": "B", "항목": "RGB 카메라(sar/camera.py) ↔ three.js 핀홀 (같은 위치·방위·세로FOV)",
            "측정": "|Δu|최대 %.1f px (방위 %.0f%%·%.0f m), |Δv|최대 %.1f px; 중심선 Δu=%.2f px; 핀홀 수평FOV %.1f° vs SAR %.1f°"
                    % (du, 100 * at[0] if at else 0, at[1] if at else 0, dv, centre[0] if centre else float("nan"), fh_pin, cam["fov_deg"]),
            "기준": "모델 차이(0이 아니어야 정상)", "판정": "측정", "유효영역": "220×140, pitch −30°",
            "GAP": "SAR 은 열 방위가 각도선형·피치가 전단. three.js 는 직선투영·피치가 회전 -- 같은 화면이 아니다. "
                   "중심선 −0.5 px 는 픽셀중심 규약 차이((W−1)/2 vs W/2)",
            "_num": {"du": du, "dv": dv, "centre_du": centre[0] if centre else None, "fh_pin": fh_pin}}


def check_fog_models(V_m: float = 200.0, half_fov_deg: float = 36.0) -> dict:
    """C: at equal visibility, three.js default fog vs Beer-Lambert (analytic)."""
    c = FOG.compare_models(V_m, half_fov_deg)
    return {"id": "C", "항목": "안개: three.js 기본 FogExp2 ↔ Beer-Lambert (Koschmieder V=%.0f m 일치)" % V_m,
            "측정": "최대 |ΔT|=%.3f (r=%.0f m), FOV 가장자리 깊이편향 ΔT=%+.3f" % (c["max_abs_dT"], c["at_r"], c["edge_depth_bias_dT"]),
            "기준": "β=3.912/V (sar/sensors.py)", "판정": "측정", "유효영역": "0 ≤ r ≤ 2V",
            "GAP": "그대로 쓰면 SAR 과 안개가 다르다 -> render3d 는 셰이더를 Beer-Lambert·광선거리로 덮어쓴다(D 에서 실측)",
            "_num": c}


def _vv_scene(beta: "float | None", model: str = "beer_lambert"):
    from render3d import scene as S
    s = S.new("vv", "north", (600.0, 600.0, 50.0), shell=False)
    s["linear_output"] = True
    s["views"]["vv"] = {"pos": [0.0, 0.0, 10.0], "target": [0.0, 100.0, 10.0], "fov": 50.0}
    planes = []
    # Space the azimuths (>=4 deg) and sizes (0.06 rad ~ 3.4 deg) so no plane hides another. The first version put a 30 m plane at -18 deg
    # and a 400 m plane at -20 deg; the near plane hid the far one and the measurement was wrong (a test design flaw, not the renderer).
    for k, (ang, r) in enumerate([(-18, 30.0), (-8, 60.0), (0, 100.0), (8, 150.0), (16, 220.0), (22, 300.0), (-13, 400.0), (12, 520.0)]):
        a = math.radians(90 - ang)                  # measured from +y (north); + is to the right
        planes.append({"x": r * math.cos(a), "y": r * math.sin(a), "z": 10.0 + (k % 3 - 1) * 0.03 * r, "size": 0.06 * r, "color": [1, 1, 1]})
    s["unlit_planes"] = planes
    if beta is not None:
        s["fog"] = {"beta": beta, "color": [0, 0, 0], "model": model}
    return s


def _component(mask, r0: int, c0: int):
    """4-connected component of mask containing (r0, c0) -> (rows, cols) arrays. None if that pixel is empty. No scipy needed."""
    import numpy as np
    H, W = mask.shape
    if not (0 <= r0 < H and 0 <= c0 < W) or not mask[r0, c0]:
        return None
    seen = np.zeros_like(mask, dtype=bool); seen[r0, c0] = True
    st, rr, cc = [(r0, c0)], [], []
    while st:
        r, c = st.pop(); rr.append(r); cc.append(c)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = r + dr, c + dc
            if 0 <= a < H and 0 <= b < W and mask[a, b] and not seen[a, b]:
                seen[a, b] = True; st.append((a, b))
    return np.array(rr), np.array(cc)


def check_browser(beta: float = 0.004, w: int = 800, h: int = 500) -> dict:
    """D: do three.js renders land at the pinhole prediction, and does the pixel transmittance match exp(-beta r)?"""
    from render3d import headless, html
    ok, why = headless.available()
    base = {"id": "D", "항목": "three.js 실렌더: 투영 오차 · 안개 투과율(Beer-Lambert 덮어쓰기)", "기준": "투영 ±1.5 px · |ΔT|≤0.02",
            "유효영역": "선형출력, 무조명 평면, r=30–520 m", "GAP": ""}
    if not ok:
        return dict(base, 측정="—", 판정="미측정", GAP="브라우저 없음: " + why, _num={})
    import tempfile
    from pathlib import Path
    import numpy as np
    tmp = Path(tempfile.mkdtemp(prefix="r3dvv_"))
    imgs = {}
    for key, b, model in (("clear", None, "beer_lambert"), ("bl", beta, "beer_lambert"), ("t3", beta, "three_default")):
        s = _vv_scene(b, model)
        hp = html.write(s, tmp / (key + ".html"))
        rr = headless.render(hp, tmp / (key + ".png"), view="vv", w=w, h=h, timeout_s=120)
        if not rr["ok"]:
            return dict(base, 측정="—", 판정="미측정", GAP="렌더 실패: " + rr["reason"], _num={})
        from matplotlib.image import imread
        imgs[key] = imread(str(tmp / (key + ".png")))[..., :3]
    s = _vv_scene(None)
    v = s["views"]["vv"]; P = v["pos"]
    perr, dT_bl, dT_t3, rows = 0.0, 0.0, 0.0, []
    lum = imgs["clear"].mean(axis=2)
    for q in s["unlit_planes"]:
        u, vv_ = C.pinhole_pixel(v, (q["x"], q["y"], q["z"]), w, h, "north")
        # Use only the blob connected to the predicted pixel -- the first version used every bright pixel in the window and
        # mixed in a neighbouring plane (3.8-5.3 px 'error'; the renderer was not wrong).
        x0, x1 = int(max(0, u - 40)), int(min(w, u + 41)); y0, y1 = int(max(0, vv_ - 40)), int(min(h, vv_ + 41))
        comp = _component(lum[y0:y1, x0:x1] > 0.5, int(vv_) - y0, int(u) - x0)
        if comp is None:
            perr = float("inf"); continue
        yy, xx = comp
        cu, cv = x0 + xx.mean() + 0.5, y0 + yy.mean() + 0.5          # pixel centre = +0.5
        perr = max(perr, math.hypot(cu - u, cv - vv_))
        r = math.dist(P, (q["x"], q["y"], q["z"]))
        iu, iv = int(round(cu - 0.5)), int(round(cv - 0.5))
        t_bl = float(imgs["bl"][iv - 1:iv + 2, iu - 1:iu + 2].mean()); t_t3 = float(imgs["t3"][iv - 1:iv + 2, iu - 1:iu + 2].mean())
        ref = FOG.T_beer_lambert(beta, r)
        dT_bl = max(dT_bl, abs(t_bl - ref)); dT_t3 = max(dT_t3, abs(t_t3 - ref))
        rows.append((r, ref, t_bl, t_t3))
    ok = perr <= 1.5 and dT_bl <= 0.02
    return dict(base, 측정="투영 최대 %.2f px · |ΔT| 덮어쓴 안개 %.3f / 기본 FogExp2 %.3f (β=%.3f)" % (perr, dT_bl, dT_t3, beta),
                판정="PASS" if ok else "FAIL",
                GAP="8비트 양자화(±0.004). 기본 FogExp2 값은 ρ=β 그대로라 '같은 V' 비교가 아니다(C 참조)",
                _num={"proj_px": perr, "dT_bl": dT_bl, "dT_t3": dT_t3, "rows": rows})


def check_heightfield() -> dict:
    """E: do the scene heightfield vertices sit exactly on the DEM grid (the same sampler sar/camera.py uses)?"""
    import numpy as np
    from sar.camera import _terrain_sampler
    from render3d import sar_bridge as B
    dem = B.synthetic_dem(97, seed=3); mpp = 15.0
    s = B.terrain_scene(dem, mpp, max_n=33)
    hf = s["heightfield"]; Z = np.asarray(hf["z"]); xs = np.asarray(hf["xs"]); ys = np.asarray(hf["ys"])
    X, Y = np.meshgrid(xs, ys)
    ref = _terrain_sampler(dem, mpp)(X.ravel(), Y.ravel()).reshape(Z.shape)
    # sar/camera._terrain_sampler clips the last cell to DW-1.001 (px) -> only the edge vertices shift by slope*0.001 px. Compare interior strictly, the edge as a GAP.
    err = float(np.abs(ref - Z)[:-1, :-1].max())
    edge = float(np.abs(ref - Z).max())
    # Midpoints (triangle linear vs bilinear) -- a GAP, not a verdict.
    mx = (X[:-1, :-1] + X[1:, 1:]) / 2; my = (Y[:-1, :-1] + Y[1:, 1:]) / 2
    mid_ref = _terrain_sampler(dem, mpp)(mx.ravel(), my.ravel())
    mid_tri = ((Z[:-1, :-1] + Z[1:, 1:]) / 2).ravel()
    gap = float(np.abs(mid_ref - mid_tri).max())
    return {"id": "E", "항목": "하이트필드 정점 ↔ DEM·sar/camera 이중선형 샘플러", "측정": "내부 정점 최대 |Δz|=%.4f m" % err,
            "기준": "≤0.01 m (소수 2자리 반올림)", "판정": "PASS" if err <= 0.01 else "FAIL", "유효영역": "합성 DEM 97², 부분표본 33²",
            "GAP": "정점 사이는 삼각형 보간 vs 이중선형: 최대 %.1f m (부분표본 간격 %.0f m). 끝 행·열은 sar 샘플러의 −0.001px 절단으로 %.3f m"
                   % (gap, (xs[1] - xs[0]), edge),
            "_num": {"vertex_err": err, "mid_gap": gap, "edge_err": edge}}


def check_area() -> dict:
    """F: in the bundled layouts, does the area programme (each cell counted for one use only) sum to the footprint?"""
    from render3d import layout as LY
    worst, n = 0.0, 0
    for k, L in LY.examples().items():
        s = LY.to_scene(L)
        a = LY.area_program(s); tot = sum(a.values()); W, D, _ = s["bounds"]
        worst = max(worst, abs(tot - W * D)); n += 1
    return {"id": "F", "항목": "면적 프로그램 합 ↔ 외곽 면적 (예제 %d개 층)" % n, "측정": "최대 |Δ|=%.3f m²" % worst,
            "기준": "≤0.05 m² (0.1 m 격자)", "판정": "PASS" if worst <= 0.05 else "FAIL", "유효영역": "직사각 외곽",
            "GAP": "구역이 겹치면 우선순위로 한 번만 센다(체험 < 판매 < 결제 < 코어)", "_num": {"worst": worst}}


def run_all(browser: bool = True) -> "list[dict]":
    rows = []
    from render3d import vv_scene3d as V3
    for f in (check_sar_impl, check_sar_vs_pinhole, check_fog_models, check_heightfield, check_area, V3.check_los_vs_sar_camera, V3.check_johnson, V3.check_radar_shadow):
        try:
            rows.append(f())
        except Exception as e:                      # noqa: BLE001 -- say it could not be measured; never PASS
            rows.append({"id": f.__name__, "항목": f.__doc__.split(":")[0], "측정": "—", "기준": "—", "판정": "FAIL",
                         "유효영역": "—", "GAP": "%s: %s" % (type(e).__name__, e), "_num": {}})
    if not browser:
        rows.append({"id": "G", "항목": "3D 가시비 두 방법 대조", "측정": "—", "기준": "—", "판정": "미측정", "유효영역": "—",
                     "GAP": "브라우저를 안 씀", "_num": {}})
    if browser:
        try:
            rows.append(V3.check_visibility_two_methods())
        except Exception as e:                      # noqa: BLE001
            rows.append({"id": "G", "항목": "3D 가시비 두 방법 대조", "측정": "—", "기준": "—", "판정": "미측정", "유효영역": "—",
                         "GAP": "%s: %s" % (type(e).__name__, e), "_num": {}})
        try:
            rows.insert(3, check_browser())
        except Exception as e:                      # noqa: BLE001
            rows.insert(3, {"id": "D", "항목": "three.js 실렌더", "측정": "—", "기준": "—", "판정": "미측정", "유효영역": "—",
                            "GAP": "%s: %s" % (type(e).__name__, e), "_num": {}})
    return rows


def report(rows, md_path, png_path) -> None:
    from pathlib import Path
    L = ["# render3d V&V — 실사 렌더 ↔ RGB 카메라(sar/camera.py) 물리 대조", "",
         "> 형식은 `sar/ivv/refval.py` 와 같다. **PASS/FAIL** 은 구현이 참조와 일치해야 하는 주장, **측정** 은 두 모델의 차이, "
         "**미측정** 은 못 잰 것이다(PASS 로 세지 않는다).", "",
         "| # | 항목 | 측정 | 기준 | 판정 | 유효영역 | GAP |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | **%s** | %s | %s |" % (r["id"], r["항목"], r["측정"], r["기준"], r["판정"], r["유효영역"], r["GAP"]))
    L += ["", "![vv](%s)" % Path(png_path).name]
    Path(md_path).write_text("\n".join(L) + "\n", encoding="utf-8")
    from render3d.plan import _mpl
    plt = _mpl()
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8), dpi=140)
    V = 200.0; beta = FOG.beta_from_visibility(V); rho = FOG.rho_matching_visibility(V)
    rs = [2 * V * k / 200 for k in range(201)]
    ax[0].plot(rs, [FOG.T_beer_lambert(beta, r) for r in rs], lw=2, label="Beer-Lambert exp(−βr) (SAR)")
    ax[0].plot(rs, [FOG.T_three_default(rho, r) for r in rs], lw=2, ls="--", label="three.js FogExp2 (같은 V)")
    ax[0].axvline(V, color="#888", lw=0.8); ax[0].text(V, 0.9, " V=3.912/β", fontsize=8)
    d = next((r for r in rows if r["id"] == "D"), None)
    if d and d.get("_num", {}).get("rows"):
        b = 0.004
        R = d["_num"]["rows"]
        # T depends only on beta*r, so the measured beta=0.004 points are rescaled to this curve's beta (r' = r * 0.004/beta)
        ax[0].scatter([x[0] * b / beta for x in R], [x[2] for x in R], marker="o", c="#1E8449", zorder=5,
                      label="실측: 덮어쓴 three.js (βr 같게 환산)")
    ax[0].set_xlabel("거리 r (m)"); ax[0].set_ylabel("투과율 T"); ax[0].legend(fontsize=7); ax[0].grid(alpha=.3)
    ax[0].set_title("C/D 안개 모델", fontsize=9)
    cam = {"x": 0.0, "y": 0.0, "z": 90.0, "heading_deg": 0.0, "pitch_deg": -30.0, "fov_deg": 72.0}
    view = C.sar_to_view(cam, W_SAR, H_SAR)
    fr = [k / 20 - 1 for k in range(41)]
    for r_, col in ((150.0, "#B03A2E"), (600.0, "#2E86C1")):
        dus = []
        for f in fr:
            a = math.radians(f * 36 * 0.98)
            p = (r_ * math.cos(a), r_ * math.sin(a), 0.0)
            s_ = C.sar_pixel(cam, p, W_SAR, H_SAR); q = C.pinhole_pixel(view, p, W_SAR, H_SAR, "south")
            dus.append((s_[0] - q[0]) if (s_ and q) else float("nan"))
        ax[1].plot([f * 36 for f in fr], dus, lw=2, color=col, label="지면점 r=%.0f m" % r_)
    ax[1].axhline(0, color="#888", lw=0.8)
    ax[1].set_xlabel("방위 오프셋 (°)"); ax[1].set_ylabel("Δu = SAR − 핀홀 (px)"); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3)
    ax[1].set_title("B 투영 모델 차이 (220×140, FOV 72°)", fontsize=9)
    fig.tight_layout(); fig.savefig(png_path, facecolor="white"); plt.close(fig)
