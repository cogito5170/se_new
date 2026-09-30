#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#449 Cross-Modal Physical Consistency — 5센서로 닫히는 범위와 안 닫히는 범위를 분리.

**nav 분리(정직):** 탐지율이 nav(belief 추종)에 얽히면 fusion 규칙을 못 가린다. 그래서 시나리오마다
**고정 경로**로 관측 스트림을 한 번 기록하고(심판이 truth 를 알기에 표적·decoy 를 공평히 방문),
같은 스트림에 각 정보집합의 **claim 규칙만** 적용해 채점한다(진짜 replay: 입력 동일, 규칙만 다름).

정보집합(센서 개수 5 고정):
  I0 = spatial(≥1 모달리티)      기준선
  I1s= CMPC strict(≥2, 완화 없음)
  I1c= CMPC conditional(≥2, 가림-강 채널만이면 ≥1 완화)
  I2 = CMPC conditional + liveness(호흡·심박) 요구

시나리오: A 단일모달 clutter · B 부분관측 진짜(수관) · C 전-서명 decoy.
지표: 탐지율(진짜)·오경보(decoy/clutter). eps=2.5셀.
"""
from __future__ import annotations
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
REPO = os.path.dirname(os.path.dirname(HERE))
import selector_train as st
import policies as _pol
import reference as _ref


def _scn(rng, canopy=False, clutter=0.0, persist=1, n_decoy=0, V=18000.0, illum=15000.0):
    return dict(seed=int(rng.integers(1, 10_000_000)), lat=st.TEST_LOC[0], lon=st.TEST_LOC[1],
                V=V, illum=illum, agl=120.0,
                sensors=["RGB", "SAR", "IMU", "Thermal", "LiDAR", "Audio"],
                clutter=clutter, clutter_persist=persist, n_decoy=n_decoy,
                targets_spec=[dict(bearing_deg=float(rng.uniform(0, 360)), range_m=float(rng.uniform(120, 240)),
                                   canopy=canopy)])


def _record(scn, dem, dwell=8):
    """고정 경로로 관측 스트림 기록: 표적 위 dwell 스텝 + 각 decoy 위 dwell + 빈 곳 dwell(clutter 노출).
    nav 와 무관 — 표적·decoy 를 공평히 관측하게 심판이 경로를 짠다. 반환 (stream, truth_targets)."""
    ref = _ref.Reference(scn, dem=dem)
    truth = [(t["gx"], t["gy"]) for t in ref._targets]
    spots = [(t["gx"], t["gy"]) for t in ref._targets] + [(d["gx"], d["gy"]) for d in ref._decoys]
    # 빈 곳(clutter 노출용): 표적은 패치 중심 근처에 몰리므로 중심에서 먼 구석을 쓴다(표적서 ≥4셀).
    spots.append((ref.GW * 0.2, ref.GH * 0.2))
    stream = []
    for (sx, sy) in spots:
        for _ in range(dwell):
            stream.append(ref.observe((sx, sy)))
    return stream, truth


def _score(stream, truth, cmpc_min, require_live, conditional, eps=2.5):
    claims = []
    for obs in stream:
        for (cx, cy, _c) in _pol.cmpc_confirm(obs, cmpc_min, require_live, 2.5, conditional):
            if all((cx - c[0]) ** 2 + (cy - c[1]) ** 2 > eps * eps for c in claims):
                claims.append((cx, cy))
    det = 0
    for (tx, ty) in truth:
        if any(math.hypot(cx - tx, cy - ty) <= eps for (cx, cy) in claims):
            det += 1
    fa = sum(1 for (cx, cy) in claims
             if all(math.hypot(cx - tx, cy - ty) > eps for (tx, ty) in truth))
    dr = 100.0 * det / max(1, len(truth))
    return dr, fa


FW_ORDER = ["rgb", "thermal", "lidar", "sar", "audio"]   # bridge 센서 순서


def _c_step(lib, h, obs):
    ev = [0.0] * 5; xs = [0.0] * 5; ys = [0.0] * 5; pres = [0] * 5; health = [1.0] * 5
    for i, key in enumerate(FW_ORDER):
        dets = obs.get(key, {}).get("detections", [])
        if dets:
            dx, dy, c = max(dets, key=lambda d: d[2]); ev[i] = float(c); xs[i] = float(dx); ys[i] = float(dy); pres[i] = 1
    ld = obs.get("live", {}).get("detections", [])
    lp, lx, ly = (1, float(ld[0][0]), float(ld[0][1])) if ld else (0, 0.0, 0.0)
    import ctypes
    cf = (ctypes.c_float * 5); ci = (ctypes.c_int * 5)
    px = ctypes.c_float(); py = ctypes.c_float(); conf = ctypes.c_int(); tc = ctypes.c_float(); nis = ctypes.c_float()
    lib.fw_bridge_step(h, cf(*ev), cf(*xs), cf(*ys), ci(*pres), cf(*health),
                       ctypes.c_float(1.0), ctypes.c_float(0.0), ctypes.c_int(1), ctypes.c_int(1), ctypes.c_float(0.0),
                       ctypes.c_int(lp), ctypes.c_float(lx), ctypes.c_float(ly),
                       ctypes.byref(px), ctypes.byref(py), ctypes.byref(conf), ctypes.byref(tc), ctypes.byref(nis))
    return conf.value, px.value, py.value


def _score_c(stream, truth, lib, cmpc_min, require_live, eps=2.5):
    """C 이식본(fw/evidence.c)을 고정경로 스트림에 그대로 구동(confirm_n=1). 프로토타입과 수치 비교용."""
    import ctypes
    h = lib.fw_bridge_new()
    lib.fw_bridge_set_confirm(h, 1, ctypes.c_float(0.6))
    lib.fw_bridge_set_cmpc(h, int(cmpc_min), 1 if require_live else 0)
    claims = []
    for obs in stream:
        c, px, py = _c_step(lib, h, obs)
        if c:
            if all((px - a[0]) ** 2 + (py - a[1]) ** 2 > eps * eps for a in claims):
                claims.append((px, py))
    lib.fw_bridge_free(h)
    det = sum(1 for (tx, ty) in truth if any(math.hypot(cx - tx, cy - ty) <= eps for (cx, cy) in claims))
    fa = sum(1 for (cx, cy) in claims if all(math.hypot(cx - tx, cy - ty) > eps for (tx, ty) in truth))
    return 100.0 * det / max(1, len(truth)), fa


_SCEN = [
    ("A 단일모달 clutter",   lambda rng: _scn(rng, clutter=0.25, persist=4), "FA"),
    ("B 부분관측 진짜(수관+짙은안개)", lambda rng: _scn(rng, canopy=True, V=120.0), "det"),
    ("C 전-서명 decoy",      lambda rng: _scn(rng, n_decoy=1),               "FA"),
]


def run(n_ep=20, seed=4949, engine="py", lib=None, dem=None):
    """engine='py': 프로토타입 policies.cmpc_confirm. 'c': fw/evidence.c 이식본(bridge).
    C 는 조건부 CMPC(배포형)만 구현 → 열은 I0 / I1 cond / I2 (strict 은 py 진단용)."""
    if dem is None:
        dem, src = st._dem_for(st.TEST_LOC)
        print("held-out 지리산 DEM=%s%s · #449 Cross-Modal Consistency (nav 분리 고정경로)" % (dem.shape, src))
    if engine == "py":
        cols_def = [("I0 spatial", dict(cmpc_min=1, require_live=False, conditional=True)),
                    ("I1 strict",  dict(cmpc_min=2, require_live=False, conditional=False)),
                    ("I1 cond",    dict(cmpc_min=2, require_live=False, conditional=True)),
                    ("I2 +live",   dict(cmpc_min=2, require_live=True,  conditional=True))]
    else:
        cols_def = [("I0 spatial", dict(cmpc_min=1, require_live=False)),
                    ("I1 cond",    dict(cmpc_min=2, require_live=False)),
                    ("I2 +live",   dict(cmpc_min=2, require_live=True))]
    print("\n### engine=%s (%s)" % (engine, "프로토타입 cmpc_confirm" if engine == "py" else "C 이식본 fw/evidence.c"))
    print("| 시나리오 | 관심 | " + " | ".join(n for n, _ in cols_def) + " |")
    print("|---|---|" + "---|" * len(cols_def))
    for label, scn_fn, focus in _SCEN:
        cols = []
        for _, cfg in cols_def:
            rng = np.random.default_rng(seed); drs = []; fas = []
            for _ in range(n_ep):
                stream, truth = _record(scn_fn(rng), dem)
                if engine == "py":
                    dr, fa = _score(stream, truth, **cfg)
                else:
                    dr, fa = _score_c(stream, truth, lib, cfg["cmpc_min"], cfg["require_live"])
                drs.append(dr); fas.append(fa)
            cols.append("탐%.0f%%/오%.1f" % (float(np.mean(drs)), float(np.mean(fas))))
        print("| %s | %s | %s |" % (label, focus, " | ".join(cols)))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--ep", type=int, default=20)
    ap.add_argument("--engine", choices=["py", "c", "both"], default="both")
    a, _ = ap.parse_known_args()
    dem, src = st._dem_for(st.TEST_LOC)
    print("held-out 지리산 DEM=%s%s · #449 CMPC 관측가능성 (nav 분리 고정경로) · engine=%s" % (dem.shape, src, a.engine))
    if a.engine in ("py", "both"):
        run(n_ep=a.ep, engine="py", dem=dem)
    if a.engine in ("c", "both"):
        import fw_vv
        lib = fw_vv.load_lib()
        run(n_ep=a.ep, engine="c", lib=lib, dem=dem)
    if a.engine == "both":
        print("\n프로토타입(py)과 C 이식본(c)의 I0/I1cond/I2 방향성이 일치하면 규칙 수치 등가(FW-CMPC-001).")
