#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""폐루프 미션(mission_sim) → render3d 3D 장면(three.js) → 인터랙티브 HTML + webm.

!렌더 와 같은 3D 파이프라인(실 지형 relief·나무·탑재/조감 카메라)에 미션 데이터를 얹는다.
정사영 2D(mission_video)와 달리 실제 지형지물을 3D 로 렌더한다. 실 지명이면 실 DEM(AWS Terrarium).

좌표: 미션은 24×24 격자(칸). render3d 장면은 월드 미터라 ref._g2w 로 변환하고, 고도는 실 DEM 에서
world3d.ground 로 읽는다(UAV 는 +AGL). 정직: L2 대표 렌더 — 관찰 뷰만 truth 를 그리고 SUT 는 센서만.
"""
from __future__ import annotations
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.dirname(HERE), REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RGB_FOV_V = 2 * math.degrees(math.atan(math.tan(math.radians(84.0 / 2)) * 9 / 16))  # ≈58.7° (CAMERAS rgb hfov 84)


def _states(ref, frames, agl, sub=6):
    """결정 프레임(20s 간격) → 보간된 3D anim states. states[i]=[t,x,y,z,heading,policy,vis,sig,cov,vel,agl]."""
    g = ref.world3d.ground
    pts = []
    for fr in frames:
        x, y = ref._g2w(fr["veh"][0], fr["veh"][1])
        pts.append((float(x), float(y), fr))
    out = []
    for i in range(len(pts)):
        x0, y0, fr = pts[i]
        x1, y1, _ = pts[min(i + 1, len(pts) - 1)]
        for s in range(sub):
            a = s / sub
            x = x0 + (x1 - x0) * a; y = y0 + (y1 - y0) * a
            t = (i + a) * 20.0
            hx, hy = (x1 - x0), (y1 - y0)
            heading = math.degrees(math.atan2(hy, hx)) if (abs(hx) + abs(hy)) > 1e-6 else (out[-1][4] if out else 0.0)
            vel = math.hypot(x1 - x0, y1 - y0) / 20.0
            z = float(g(x, y)) + agl
            out.append([round(t, 1), round(x, 1), round(y, 1), round(z, 1), round(heading, 1),
                        fr["act"], round(fr["rgb_vis"], 3), round(fr["imu_sigma"], 2),
                        round(fr["coverage"], 1), round(vel, 2), round(agl, 1)])
    return out


def _decisions(frames):
    out = []
    for i, fr in enumerate(frames):
        b = fr["belief"]
        rule = ("fw C executive: 행동=%s · target_conf=%.2f · %s · NIS=%.1f · 배터리 %d%%"
                % (fr["act"], b[3], ("확인됨(liveness)" if b[2] else "미확인"), b[4], round(fr["battery"] * 100)))
        obs = ("관측: RGB vis %.2f · RGB탐지 %d · 열 %d · live %d · IMU %s"
               % (fr["rgb_vis"], len(fr["sensors"].get("rgb", [])), len(fr["sensors"].get("thermal", [])),
                  len(fr["live"]), "OK" if fr["imu_ok"] else "상실"))
        out.append([round(i * 20.0, 1), fr["act"], rule, obs])
    return out


def _terrain_colors(hf):
    """고도 밴드(계곡 초록→능선 갈색→정상 회백) + NW 조명 hillshade 로 실 지형처럼 음영을 준다.
    위성 사진 텍스처가 아니라 **실 고도**에서 색·음영을 낸다(Google Earth 지형 음영과 같은 종류)."""
    import numpy as np
    Z = np.array(hf["z"], dtype=float)                  # z[j][i]
    xs = np.array(hf["xs"], dtype=float); ys = np.array(hf["ys"], dtype=float)
    zmin, zmax = hf["zmin"], hf["zmax"]
    e = (Z - zmin) / (max(1e-6, zmax - zmin))
    # 고도 밴드 색(계곡→숲→능선→정상)
    stops = [(0.0, (0.33, 0.50, 0.28)), (0.35, (0.24, 0.42, 0.21)),
             (0.65, (0.45, 0.40, 0.30)), (0.85, (0.60, 0.56, 0.48)), (1.0, (0.82, 0.82, 0.80))]
    base = np.zeros(Z.shape + (3,))
    for k in range(len(stops) - 1):
        lo, clo = stops[k]; hi, chi = stops[k + 1]
        msk = (e >= lo) & (e <= hi + 1e-9)
        f = ((e[msk] - lo) / max(1e-6, hi - lo))[:, None]
        base[msk] = np.array(clo) * (1 - f) + np.array(chi) * f
    # hillshade: NW 광원
    dzdx = np.gradient(Z, xs, axis=1); dzdy = np.gradient(Z, ys, axis=0)
    nx, ny, nz = -dzdx, -dzdy, np.ones_like(Z)
    nrm = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-9
    lx, ly, lz = -0.5, -0.5, 0.7                          # 북서 상공
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    shade = (nx * lx + ny * ly + nz * lz) / (nrm * ln)
    shade = np.clip(0.65 + 0.55 * shade, 0.45, 1.2)[:, :, None]
    col = np.clip(base * shade, 0, 1)
    return [[[round(float(col[j, i, c]), 3) for c in range(3)] for i in range(Z.shape[1])] for j in range(Z.shape[0])]


def build_scene(ref, dem, data, name="임무 3D", speed=30.0, tree_cap=500):
    """mission_sim (data) + ref + dem → render3d 장면(anim 포함). html.write 로 쓰면 3D HTML."""
    from render3d import sar_bridge as B
    mpp = float(ref.mpp)
    agl = float(data["scenario"].get("agl", 90.0))
    V = data["scenario"].get("V")
    fid = data["scenario"].get("fidelity", "")
    sc = B.terrain_scene(dem, mpp, name=name, V_m=(V if V and V < 6000 else None), fidelity=fid)
    if "colors" not in sc.get("heightfield", {}):       # 실 지형 색·음영(위성 텍스처 아님 — 고도 기반)
        sc["heightfield"]["colors"] = _terrain_colors(sc["heightfield"])
    g = ref.world3d.ground

    # 나무(숲) — world3d 에서. 많으면 균등 솎아 성능 유지.
    trees = list(getattr(ref.world3d, "trees", []))
    if len(trees) > tree_cap:
        step = len(trees) / tree_cap
        trees = [trees[int(k * step)] for k in range(tree_cap)]
    for (tx, ty, tz, tsz) in trees:
        sc["props"].append({"kind": "tree", "x": float(tx), "y": float(ty), "z": float(tz), "size": float(tsz)})

    # 표적: 사람 마커(최종 확인=초록, 미탐 수관=회색). decoy: 바위.
    for i, (gx, gy) in enumerate(data["targets"]):
        x, y = ref._g2w(gx, gy)
        col = [0.20, 0.85, 0.45] if data["found"][i] else ([0.55, 0.58, 0.62] if data["canopy"][i] else [0.80, 0.80, 0.85])
        sc["props"].append({"kind": "person", "x": float(x), "y": float(y), "z": float(g(x, y)),
                            "size": 1.6, "yaw_deg": 0.0, "color": col})
    for (gx, gy) in data["decoys"]:
        x, y = ref._g2w(gx, gy)
        sc["props"].append({"kind": "rock", "x": float(x), "y": float(y), "z": float(g(x, y)),
                            "size": 4.0, "color": [0.85, 0.60, 0.20]})

    truth = []
    for (gx, gy) in data["targets"]:
        x, y = ref._g2w(gx, gy)
        truth.append([round(float(x), 1), round(float(y), 1), round(float(g(x, y)), 1)])

    sc["anim"] = {"states": _states(ref, data["frames"], agl), "reports": [], "events": [],
                  "decisions": _decisions(data["frames"]), "speed": speed,
                  "state_hz": 10, "report_hz": 1, "decision_s": 20.0,
                  "rgb_fov_v": RGB_FOV_V, "rgb_pitch_deg": -30.0, "truth": truth}
    if sc.get("fog"):
        sc["fog"]["views"] = ["onboard"]
    return sc


def render(ref, dem, data, stem, name="임무 3D", speed=30.0, webm=True):
    """장면 → HTML(+webm). stem 은 확장자 없는 경로. 산출물 경로 리스트 반환."""
    from render3d import html as H, headless
    sc = build_scene(ref, dem, data, name=name, speed=speed)
    hp = stem + ".html"
    H.write(sc, hp)
    outs = [hp]
    if webm:
        r = headless.record(hp, stem + ".webm", cam="tour", speed=speed)
        if r.get("ok"):
            outs.append(stem + ".webm")
        else:
            print("webm 못 만듦:", r.get("reason"))
    return outs, sc


if __name__ == "__main__":
    import argparse
    import nl_scenario as _nl
    import mission_sim as _ms
    ap = argparse.ArgumentParser()
    ap.add_argument("--nl", default=None)
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--battery", type=int, default=200)
    ap.add_argument("--speed", type=float, default=30.0)
    ap.add_argument("--stem", default=os.path.join(REPO, "public_agent_memory", "mission", "mission3d"))
    ap.add_argument("--no-webm", action="store_true")
    a, _ = ap.parse_known_args()
    text = a.nl or "강원도 산맥에서 RGB·열화상·IMU 로 실종 다섯명 탐색, 바위·동물·식생 오인(FP)과 수관 은폐 놓침(FN) 포함"
    scn = _nl.parse(text, seed=a.seed)
    os.makedirs(os.path.dirname(a.stem), exist_ok=True)
    data, ref, dem = _ms.run(scn, battery_life_steps=a.battery, real_dem=True, return_ref=True)
    outs, _ = render(ref, dem, data, a.stem, name="임무 3D · %s" % (scn.get("place") or "합성 지형"),
                     speed=a.speed, webm=not a.no_webm)
    for p in outs:
        print("산출물:", os.path.relpath(p, REPO))
    print("=== 보고 ===")
    print("장소: %s · %s" % (scn.get("place") or "합성", data["scenario"]["fidelity"]))
    print(_ms.summary_line(data))
