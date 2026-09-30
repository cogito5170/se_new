#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""폐루프 데모 — 실제 C 결정 executive(fw/, libfw.so)가 참조세계(sar) 안에서 UAV 를 제어.

배선: reference.observe(참 물리 센서) → fw_bridge_step(진짜 C 코드로 결정) → 행동(Action enum) →
그 행동으로 UAV 항법 → 다시 관측. 세계상태(배터리·충돌·IMU·센서건강)를 임무처럼 대본으로 넣어
정책의 모든 층(탐색·접근·확인·decoy 기각·FDIR·안전귀환)이 실제로 발화하게 한다.

산출: 스텝별 상태 JSON(veh·belief·action·센서·배터리·모드 + truth 오버레이) → HTML 애니메이션용.
정직: nav 는 C 행동으로 구동하되 waypoint 세부는 공통 골격. 대표 물리 L2, 현장 validation 아님.
"""
from __future__ import annotations
import ctypes, json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import selector_train as st
import reference as _ref
import fw_vv

ACT = ["NONE", "SEARCH", "APPROACH", "INSPECT", "RETURN", "AVOID", "RELOCALIZE", "EMERGENCY", "ABSTAIN"]
SENS = ["RGB", "THERMAL", "LIDAR", "SAR", "AUDIO"]


def build(seed=7, scene3d=False):
    dem, src = st._dem_for(st.TEST_LOC)
    if scene3d:
        # 3D: 노출 사면의 수관 아래 생존자(부분 가시선 ~0.7) + 다른 곳 decoy. 고도 살짝 높여 능선 너머 확보.
        agl, tgt, dec = 150.0, dict(bearing_deg=256.0, range_m=1031.0, canopy=False), dict(bearing_deg=135.0, range_m=1414.0, canopy=False)
    else:
        agl, tgt, dec = 120.0, dict(bearing_deg=45.0, range_m=2000.0, canopy=False), dict(bearing_deg=300.0, range_m=1800.0, canopy=False)
    scn = dict(seed=seed, lat=st.TEST_LOC[0], lon=st.TEST_LOC[1], V=2000.0, illum=12000.0, agl=agl,
               sensors=["RGB", "SAR", "IMU", "Thermal", "LiDAR", "Audio"], clutter=0.12, clutter_persist=2,
               scene3d=scene3d,   # 켜면 render3d 로 지형 가시선·수관·픽셀수 반영(참조세계 안, SUT 분리)
               targets_spec=[tgt], decoys_spec=[dec])
    ref = _ref.Reference(scn, dem=dem)
    return ref, dem, src


def nav(veh, act, belief, home, obstacle, cover, GW, GH):
    """C 행동으로 UAV 를 움직인다. 반환 새 veh."""
    x, y = veh; step = 1.4
    if act in ("RETURN", "EMERGENCY"):
        tx, ty = home
    elif act == "AVOID":                                   # 장애물 반대로
        dx, dy = x - obstacle[0], y - obstacle[1]; n = math.hypot(dx, dy) + 1e-6
        tx, ty = x + step*dx/n, y + step*dy/n
    elif act == "INSPECT":
        return [x, y]                                      # 확인 표적 정밀관측: 제자리 loiter(연속 확인)
    elif act == "APPROACH" and belief[2]:                  # 확인된 표적으로 접근
        tx, ty = belief[0], belief[1]
    elif act in ("RELOCALIZE", "NONE"):
        return [x, y]                                      # 정지(호버)
    else:                                                  # SEARCH: 가장 안 덮은 칸으로
        uncov = np.argwhere(cover < 0.5)
        if len(uncov):
            d = np.hypot(uncov[:, 1]-x, uncov[:, 0]-y); j = uncov[np.argmin(d + 0.001*np.random.rand(len(uncov)))]
            tx, ty = float(j[1]), float(j[0])
        else:
            tx, ty = home
    dx, dy = tx - x, ty - y; n = math.hypot(dx, dy)
    if n > step:
        dx, dy = dx*step/n, dy*step/n
    return [float(np.clip(x+dx, 0, GW-1)), float(np.clip(y+dy, 0, GH-1))]


def run(steps=200, seed=7, out=None, scene3d=False):
    np.random.seed(seed)               # nav 의 탐색 타이브레이크 결정화(재현성)
    lib = fw_vv.load_lib()
    ref, dem, src = build(seed, scene3d=scene3d)
    GW, GH = ref.GW, ref.GH
    h = lib.fw_bridge_new()
    lib.fw_bridge_set_confirm(h, 2, ctypes.c_float(0.6))     # 연속 2스텝 확인
    lib.fw_bridge_set_nisgate(h, ctypes.c_float(24.0))       # 운동 일관성 게이트
    lib.fw_bridge_set_cmpc(h, 2, 1)                          # CMPC≥2 + liveness 요구(decoy 기각)

    veh = [3.0, 3.0]; home = [3.0, 3.0]
    obstacle = [GW*0.5, GH*0.35]
    cover = np.zeros((GH, GW))
    cf = (ctypes.c_float*5); ci = (ctypes.c_int*5)
    frames = []
    for t in range(steps):
        obs = ref.observe(veh)
        ev = [0.0]*5; xs = [0.0]*5; ys = [0.0]*5; pres = [0]*5; health = [1.0]*5
        for i, key in enumerate([s.lower() for s in SENS]):
            dets = obs.get(key, {}).get("detections", [])
            if dets:
                dx, dy, c = max(dets, key=lambda d: d[2]); ev[i] = float(c); xs[i] = float(dx); ys[i] = float(dy); pres[i] = 1
        # ── 대본 세계상태: 정책 각 층을 발화시킨다 ──
        battery = max(0.0, 1.0 - 0.0052*t)                  # 서서히 소모 → RETURN(0.25)·EMERGENCY(0.10)
        if 78 <= t < 100:                                    # LiDAR 고장 창(FDIR 격리)
            health[2] = 0.05
        imu_ok = 0 if 112 <= t < 128 else 1                  # IMU 상실 창 → RELOCALIZE
        gps_ok = 0 if 112 <= t < 128 else 1
        dobs = math.hypot(veh[0]-obstacle[0], veh[1]-obstacle[1])
        collision = max(0.0, 1.0 - dobs/2.5) if t < 70 else 0.0   # 접근 초기 장애물 → AVOID
        ld = obs.get("live", {}).get("detections", [])
        lp, lx, ly = (1, float(ld[0][0]), float(ld[0][1])) if ld else (0, 0.0, 0.0)
        pos_err = 0.0 if imu_ok else 5.0
        px = ctypes.c_float(); py = ctypes.c_float(); conf = ctypes.c_int(); tc = ctypes.c_float(); nis = ctypes.c_float()
        a = lib.fw_bridge_step(h, cf(*ev), cf(*xs), cf(*ys), ci(*pres), cf(*health),
                               ctypes.c_float(battery), ctypes.c_float(collision),
                               ctypes.c_int(imu_ok), ctypes.c_int(gps_ok), ctypes.c_float(pos_err),
                               ctypes.c_int(lp), ctypes.c_float(lx), ctypes.c_float(ly),
                               ctypes.byref(px), ctypes.byref(py), ctypes.byref(conf), ctypes.byref(tc), ctypes.byref(nis))
        belief = [px.value, py.value, int(conf.value)]
        act = ACT[a] if 0 <= a < len(ACT) else "NONE"
        # 3D: 현재 UAV 에서 표적으로의 지형 가시선·수관 개방도 (main scene3d World.observe_geometry)
        los = 1; copen = 1.0
        if scene3d and getattr(ref, "scene3d", False) and ref._targets:
            tg0 = ref._targets[0]
            cx3, cy3 = ref._g2w(veh[0], veh[1]); cz3 = float(ref.world3d.ground(cx3, cy3)) + ref.AGL
            geo = ref.world3d.observe_geometry((cx3, cy3, cz3), ref._g2w(tg0["gx"], tg0["gy"]),
                                               tg0.get("yaw3d", 0.0), cams=ref.cams3d)
            los = 1 if geo["terrain_los"] else 0
            copen = round(float(geo["foliage_vis"]), 2)
        # 커버리지 갱신(반경 3칸)
        gy, gx = np.ogrid[0:GH, 0:GW]
        cover[((gx-veh[0])**2 + (gy-veh[1])**2) <= 9] = 1.0
        frames.append(dict(t=t, veh=[round(veh[0],2), round(veh[1],2)],
                           belief=[round(px.value,2), round(py.value,2), int(conf.value), round(tc.value,3), round(nis.value,2)],
                           act=act, present=[int(p) for p in pres], health=[round(x,2) for x in health],
                           battery=round(battery,3), collision=round(collision,2), imu=imu_ok, los=los, copen=copen,
                           coverage=round(float(cover.mean())*100,1)))
        veh = nav(veh, act, belief, home, obstacle, cover, GW, GH)
    lib.fw_bridge_free(h)

    tr = ref.truth()
    ds = 64
    demq = dem[::max(1, dem.shape[0]//ds), ::max(1, dem.shape[1]//ds)]
    demn = ((demq - demq.min())/(np.ptp(demq)+1e-9)).round(3).tolist()
    trees = [[round(tt[0],2), round(tt[1],2), round(tt[2],2)] for tt in getattr(ref, "_trees", [])]
    data = dict(GW=GW, GH=GH, src=src, steps=steps, dem=demn, scene3d=bool(scene3d),
                targets=[[round(t2[0],2), round(t2[1],2)] for t2 in tr["targets"]],
                canopy=tr["canopy"], trees=trees,
                decoys=[[round(d["gx"],2), round(d["gy"],2)] for d in ref._decoys],
                obstacle=[round(obstacle[0],2), round(obstacle[1],2)], home=home, frames=frames)
    out = out or os.path.join(HERE, "demo_run.json")
    with open(out, "w") as f:
        json.dump(data, f)
    # 요약(정직 보고용)
    acts = {}
    for fr in frames:
        acts[fr["act"]] = acts.get(fr["act"], 0) + 1
    confirmed = sum(1 for fr in frames if fr["belief"][2])
    print("DEM=%s%s GW=%d GH=%d steps=%d" % (dem.shape, src, GW, GH, steps))
    print("targets(canopy)=%s decoys=%s" % (data["targets"], data["decoys"]))
    print("action histogram:", acts)
    print("confirmed steps:", confirmed, "/", steps, "· final coverage:", frames[-1]["coverage"], "%")
    print("wrote", out)
    return data


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--steps", type=int, default=200); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scene3d", action="store_true", help="render3d 지형가시선·수관·픽셀수 반영")
    a, _ = ap.parse_known_args()
    run(steps=a.steps, seed=a.seed, scene3d=a.scene3d, out=(None if not a.scene3d else __import__("os").path.join(HERE, "demo_run_3d.json")))
