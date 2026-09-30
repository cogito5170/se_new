# -*- coding: utf-8 -*-
"""V&V for 3D visibility (handoff section 7) -- visibility is also obtained by two independent methods and cross-checked.

  G  numpy ray visible fraction (opaque trees + terrain) <-> three.js mask render pixel ratio   PASS/FAIL |d|<=0.05 or 미측정
  H  numpy terrain_los <-> sar/camera.py occlusion (is the feature drawn at all?)               PASS/FAIL agreement >= 95%
  I  Johnson TTPF referent: P(N50) = 0.5, monotone increasing                                   PASS/FAIL

Test terrain: a smooth ridge (no noise). On a noisy DEM, three.js triangle interpolation and the bilinear ground
differ by up to metres, so the target (0.15 m above the ground) would be buried under the mesh and the check would
compare something else -- a GAP, stated here.
"""
from __future__ import annotations

import math


def ridge_dem(n: int = 97, mpp: float = 15.0):
    import numpy as np
    y, x = np.mgrid[0:n, 0:n] / float(n - 1)
    return 800.0 + 120.0 * np.exp(-((x - 0.5) / 0.08) ** 2) + 10.0 * y, mpp


def _cases(world):
    """(name, cam, target_xy, yaw, trees). Besides open / fully hidden / ridge, **partial occlusion** cases are chosen by sweeping with numpy.

    The first version had all three tree cases fully hidden (0.0) -- agreement on 0 and 1 alone is trivial.
    So the tree offset is swept to find points with visible fraction ~0.25 / 0.5 / 0.75 (the render is independent, not fitted)."""
    from render3d.visibility import World
    g = lambda x, y: float(world.ground(x, y))
    C = []
    tx, ty = 400.0, 700.0                        # West slope (x=400 m; the ridge is at x=720 m)
    C.append(("개방·거의 수직", (tx + 20, ty + 10, g(tx, ty) + 120), (tx, ty), 20.0, []))
    C.append(("수관 바로 아래·45°", (tx + 110, ty, g(tx, ty) + 110), (tx, ty), 0.0, [(tx, ty, 12.0)]))
    for goal, cam_off, yaw, size in ((0.5, (90, 30, 80), 35.0, 10.0), (0.25, (-70, -60, 60), 70.0, 9.0), (0.75, (60, -80, 140), 10.0, 11.0)):
        cam = (tx + cam_off[0], ty + cam_off[1], g(tx, ty) + cam_off[2])
        ux, uy = cam[0] - tx, cam[1] - ty; n = math.hypot(ux, uy); ux, uy = ux / n, uy / n
        best = None
        for k in range(0, 161):                  # Slide the tree along the camera direction, 0 to 16 m
            d = k * 0.1
            Wd = World(world.dem, world.mpp); Wd.add_tree(tx + ux * d, ty + uy * d, size)
            v = Wd.visible_fraction(cam, (tx, ty), yaw, opaque=True, n=(9, 27))["vis"]
            if best is None or abs(v - goal) < abs(best[0] - goal):
                best = (v, d)
        d = best[1]
        C.append(("부분가림 목표 %.2f" % goal, cam, (tx, ty), yaw, [(tx + ux * d, ty + uy * d, size)]))
    C.append(("능선 뒤 저고도(지형가림)", (1050.0, 700.0, g(1050, 700) + 30), (tx, ty), 0.0, []))
    C.append(("능선 넘어 고고도(보임)", (1050.0, 700.0, g(1050, 700) + 900), (tx, ty), 0.0, []))
    return C


def check_visibility_two_methods(w: int = 600, h: int = 600) -> dict:
    """G: numpy vs three.js mask render."""
    from render3d import headless, html, sar_bridge as B
    from render3d.visibility import World, PERSON
    base = {"id": "G", "항목": "3D 가시비: numpy 광선기하 ↔ three.js 마스크 렌더 (두 독립 방법)", "기준": "|Δ| ≤ 0.05 (불투명 기하)",
            "유효영역": "매끈한 능선 DEM 97², 나무 원뿔+줄기, 누운 사람 0.5×1.7 m"}
    ok, why = headless.available()
    if not ok:
        return dict(base, 측정="—", 판정="미측정", GAP="브라우저 없음: " + why, _num={})
    import tempfile
    from pathlib import Path
    import numpy as np
    from matplotlib.image import imread
    dem, mpp = ridge_dem()
    rows, worst = [], 0.0
    tmp = Path(tempfile.mkdtemp(prefix="r3dG_"))
    for k, (name, cam, txy, yaw, trees) in enumerate(_cases(World(dem, mpp))):
        W_ = World(dem, mpp)
        for (x, y, s) in trees:
            W_.add_tree(x, y, s)
        num = W_.visible_fraction(cam, txy, yaw, opaque=True, n=(9, 27))["vis"]
        feats = [{"kind": "tree", "wx": x, "wy": y, "z": float(W_.ground(x, y)), "size": s} for (x, y, s) in trees]
        sc = B.terrain_scene(dem, mpp, name="vvG", features=feats, max_n=129)
        tz = float(W_.ground(*txy)) + PERSON["h"]
        slant = math.dist(cam, (txy[0], txy[1], tz))
        fov = 2 * math.degrees(math.atan(1.25 * PERSON["l"] / slant))
        sc["views"] = {"g": {"pos": list(cam), "target": [txy[0], txy[1], tz], "fov": fov, "near": max(0.5, 0.2 * slant)}}
        sc["linear_output"] = True
        cnt = {}
        for occ in (False, True):
            sc["mask"] = {"x": txy[0], "y": txy[1], "z": tz, "w": PERSON["w"], "l": PERSON["l"], "yaw_deg": yaw, "occluders": occ}
            hp = html.write(sc, tmp / ("g%d_%d.html" % (k, occ)))
            rr = headless.render(hp, tmp / ("g%d_%d.png" % (k, occ)), view="g", w=w, h=h, timeout_s=120)
            if not rr["ok"]:
                return dict(base, 측정="—", 판정="미측정", GAP="렌더 실패: " + rr["reason"], _num={})
            cnt[occ] = int((imread(str(tmp / ("g%d_%d.png" % (k, occ))))[..., :3].mean(axis=2) > 0.5).sum())
        ren = cnt[True] / max(1, cnt[False])
        worst = max(worst, abs(ren - num))
        rows.append((name, round(num, 3), round(ren, 3), cnt[False]))
    partial = sum(1 for r in rows if 0.1 < r[1] < 0.9)
    ok = worst <= 0.05 and all(r[3] > 500 for r in rows) and partial >= 2     # agreeing on 0 and 1 alone is trivial -- need >=2 partial cases
    return dict(base, 측정="최대 |Δ|=%.3f (%d개 기하, 부분가림 %d개)" % (worst, len(rows), partial), 판정="PASS" if ok else "FAIL",
                GAP="삼각형 메시 ↔ 이중선형 지면 차이는 매끈한 지형에서만 작다(잡음 DEM 은 표적이 메시에 묻힐 수 있다). 잎 틈(투과)은 대조 대상이 아니다(불투명 기하만)",
                _num={"worst": worst, "rows": rows})


def check_los_vs_sar_camera(n: int = 60, seed: int = 4) -> dict:
    """H: numpy terrain_los vs sar/camera.py -- is a feature at the target drawn (not occluded) in the SAR camera?"""
    import numpy as np
    from sar.camera import render as sar_render
    from render3d.visibility import World
    from render3d.vv import _PinScene
    dem, mpp = ridge_dem()
    Wd = World(dem, mpp)
    rng = np.random.default_rng(seed)
    agree = tot = 0
    mism = []
    for _ in range(n * 3):
        tx, ty = rng.uniform(250, 600), rng.uniform(300, 1100)
        cx, cy = rng.uniform(800, 1200), rng.uniform(300, 1100)
        agl = float(rng.choice([15, 30, 60, 120, 250]))
        cz = float(Wd.ground(cx, cy)) + agl
        tz = float(Wd.ground(tx, ty))
        rng_h = math.hypot(tx - cx, ty - cy)
        if rng_h > 1500 or rng_h < 50:
            continue
        hd = math.degrees(math.atan2(ty - cy, tx - cx))
        pitch = math.degrees(math.atan2(tz - cz, rng_h))
        f = {"kind": "building", "size": 12.0, "wx": tx, "wy": ty, "z": tz}
        img = sar_render(dem, mpp, (cx, cy), agl, hd, 1e-7, W=220, H=140, fov_deg=40.0, pitch_deg=float(np.clip(pitch, -60, 10)),
                         zfar=1700.0, zstep=3.0, scene=_PinScene([f]))
        drawn = bool(((img[..., 0] > 0.45) & (img[..., 1] < 0.12) & (img[..., 2] < 0.12)).any())
        los = Wd.terrain_los((cx, cy, cz), (tx, ty, tz + 0.01))
        tot += 1; agree += int(drawn == los)
        if drawn != los:
            mism.append((round(agl), round(rng_h)))
        if tot >= n:
            break
    rate = agree / max(1, tot)
    return {"id": "H", "항목": "지형 가시선: numpy ↔ sar/camera.py 가림", "측정": "일치 %d/%d (%.0f%%)" % (agree, tot, 100 * rate),
            "기준": "≥ 95%", "판정": "PASS" if rate >= 0.95 else "FAIL", "유효영역": "능선 DEM, 고도 15–250 m, 수평 50–1500 m",
            "GAP": "sar/camera 는 피처 밑동 한 점을 지형 실루엣(행진 간격 3 m↑)과 비교 -- 스치는 각도에선 갈릴 수 있다. 불일치 %s" % (mism[:4],),
            "_num": {"rate": rate, "n": tot, "mismatch": mism}}


def knife_ridge_dem(n: int = 201, mpp: float = 5.0, x_ridge_px: int = 80, H: float = 40.0):
    """Flat ground (z=0) + a triangular knife-edge ridge (height H at column x_ridge_px, slopes 1:1 on both sides, crossing the whole y range).
    Along x the bilinear DEM is exactly piecewise linear -> an analytic referent applies."""
    import numpy as np
    x = np.arange(n) * mpp
    xr = x_ridge_px * mpp
    prof = np.clip(H - np.abs(x - xr), 0, None)
    return np.tile(prof, (n, 1)), mpp, xr


def check_radar_shadow() -> dict:
    """R: radar shadow length from line of sight vs the analytic referent L = H*d/(Z-H) (similar triangles, knife ridge on flat ground)."""
    from render3d.visibility import World
    dem, mpp, xr = knife_ridge_dem()
    Wd = World(dem, mpp)
    H = float(dem.max()); y = 500.0
    rows, worst = [], 0.0
    # Premise: the grazing line (slope (Z-H)/d) must be shallower than the back slope (1:1) -- otherwise the back slope is visible and the
    # formula (vertical-wall assumption) does not apply. The first version included (d=150, Z=250), which breaks the premise, and a case whose shadow end fell outside the DEM.
    for d, Z in ((200.0, 60.0), (300.0, 120.0), (400.0, 200.0), (100.0, 60.0)):
        assert (Z - H) / d < 1.0 and xr + H * d / (Z - H) < (dem.shape[1] - 2) * mpp
        cam = (xr - d, y, Z)
        L_ref = H * d / (Z - H)
        # Behind the ridge: the first visible ground point after the far foot of the slope (xr+H), 0.25 m steps
        x = xr + 0.25; last_hidden = None
        while x < xr + L_ref * 2 + 60 and x < (dem.shape[1] - 2) * mpp:
            if not Wd.terrain_los(cam, (x, y, float(Wd.ground(x, y)) + 0.01), step=0.25):
                last_hidden = x
            x += 0.25
        L_meas = (last_hidden - xr) if last_hidden is not None else 0.0
        err = abs(L_meas - L_ref)
        worst = max(worst, err / max(L_ref, 1e-9))
        rows.append((d, Z, round(L_ref, 2), round(L_meas, 2)))
    ok = worst <= 0.02
    return {"id": "R", "항목": "레이더 그림자 길이: 가시선 ↔ 해석식 L=H·d/(Z−H)", "측정": "최대 상대오차 %.2f%% (%d 기하)" % (100 * worst, len(rows)),
            "기준": "≤ 2% (0.25 m 표본)", "판정": "PASS" if ok else "FAIL", "유효영역": "칼날 능선·평지·단일 반사, 레이더 = UAV 위치",
            "GAP": "layover·다중경로·회절·측면관측 기하(입사각별 반사세기)는 모델에 없다 -- 그림자(가림)만", "_num": {"rows": rows, "worst": worst}}


def check_johnson() -> dict:
    """I: TTPF referent."""
    from render3d.visibility import johnson_p
    p50 = johnson_p(1.0)
    mono = all(johnson_p(a) < johnson_p(b) for a, b in zip([0.2, 0.5, 1, 2, 4], [0.5, 1, 2, 4, 8]))
    ok = abs(p50 - 0.5) < 1e-12 and mono and johnson_p(0) == 0.0
    return {"id": "I", "항목": "Johnson TTPF (탐지 N50=1 사이클 ≈ 2 px)", "측정": "P(N50)=%.3f · 단조증가 %s · P(4N50)=%.3f" % (p50, "예" if mono else "아니오", johnson_p(4.0)),
            "기준": "P(N50)=0.5", "판정": "PASS" if ok else "FAIL", "유효영역": "경험식(Johnson 1958 / TTPF)",
            "GAP": "현대 FPA·자동 탐지기에는 한계가 알려져 있다. 카메라 해상도·FOV 는 대표값 가정(visibility.CAMERAS)", "_num": {"p50": p50}}
