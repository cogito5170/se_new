#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reference 의 clutter(헛 탐지) 항 검사(네트워크 불필요, 합성 DEM).

clutter=0 이면 스퍼리어스 탐지가 없어야(기존 동작 불변), clutter>0 이면 표적에서 먼 곳에
헛 탐지가 생겨야 한다. 이게 있어야 '오탐 거부'를 진짜로 잴 수 있다(clutter 없으면 FA=0 은
공짜였다 — PR #442 의 정정)."""
from __future__ import annotations
import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "sar", "ivv")); sys.path.insert(0, os.path.join(REPO, "sar"))
import reference as _ref

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def _dem():
    return np.full((48, 48), 700.0)


def _far_detections(clutter, steps=30):
    """드론을 표적에서 멀리 두고(실 탐지 불가) 관측 — 나오는 탐지는 전부 clutter 여야."""
    scn = dict(seed=7, lat=37.0, lon=128.9, V=18000.0, illum=15000.0, agl=120.0,
               sensors=["RGB", "SAR", "IMU", "Thermal", "LiDAR", "Audio"], clutter=clutter,
               targets_spec=[dict(bearing_deg=45.0, range_m=240.0, canopy=False)])
    ref = _ref.Reference(scn, dem=_dem())
    tgt = ref._targets[0]
    pose = (tgt["gx"] + 12.0, tgt["gy"] + 12.0)   # 표적서 멀리(실 탐지 rc>3.2 불가)
    pose = (float(np.clip(pose[0], 0, ref.GW - 1)), float(np.clip(pose[1], 0, ref.GH - 1)))
    n = 0
    for _ in range(steps):
        obs = ref.observe(pose)
        for key in ("rgb", "sar", "thermal", "lidar", "audio"):
            for (dx, dy, *_r) in obs.get(key, {}).get("detections", []):
                if all(math.hypot(dx - t["gx"], dy - t["gy"]) > 4.0 for t in ref._targets):
                    n += 1
    return n


def _consec_move(persist, steps=16):
    """RGB 만 켜고 clutter=1.0·지정 persist 로 관측 — 연속 스텝 헛탐지 간 이동거리들의 중앙값.
    persist>1 이면 지속 구간엔 이동이 작다(같은 위치+잡음), transient(1)는 매번 새 위치라 크다."""
    scn = dict(seed=3, lat=37.0, lon=128.9, V=18000.0, illum=15000.0, agl=120.0,
               sensors=["RGB", "IMU"], clutter=1.0, clutter_persist=persist,
               targets_spec=[dict(bearing_deg=45.0, range_m=240.0, canopy=False)])
    ref = _ref.Reference(scn, dem=_dem())
    tgt = ref._targets[0]
    pose = (float(np.clip(tgt["gx"] + 12.0, 0, ref.GW - 1)), float(np.clip(tgt["gy"] + 12.0, 0, ref.GH - 1)))
    pts = []
    for _ in range(steps):
        d = ref.observe(pose).get("rgb", {}).get("detections", [])
        pts.append((d[0][0], d[0][1]) if d else None)
    moves = [math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
             for i in range(1, len(pts)) if pts[i] and pts[i - 1]]
    moves.sort()
    return (moves[len(moves) // 2] if moves else 0.0), len(moves)


def test_clutter():
    n0 = _far_detections(0.0)
    ok(n0 == 0, "clutter=0 → 스퍼리어스 탐지 없음(기존 동작 불변) [%d]" % n0)
    nh = _far_detections(0.8)
    ok(nh > 10, "clutter=0.8 → 표적서 먼 헛 탐지 다수 생성 [%d]" % nh)
    # 지속성(worst case F): persist=6 은 연속 스텝 이동이 작고(같은 위치), persist=1 은 크다.
    m6, n6 = _consec_move(6)
    m1, n1 = _consec_move(1)
    ok(n6 >= 4 and m6 < 1.0, "persist=6 → 연속 헛탐지 이동 작음(중앙값 %.2f셀 < 1.0, 같은 위치)" % m6)
    ok(m6 < m1, "persist=6 이동(%.2f) < persist=1 transient 이동(%.2f) — 지속성 실재" % (m6, m1))


def _target_track(motion, steps=10):
    scn = dict(seed=5, lat=37.0, lon=128.9, V=18000.0, illum=15000.0, agl=120.0,
               sensors=["RGB", "IMU"], target_motion=motion, target_speed=0.4,
               targets_spec=[dict(bearing_deg=30.0, range_m=180.0, canopy=False)])
    ref = _ref.Reference(scn, dem=_dem())
    for _ in range(steps):
        ref.observe((10.0, 10.0))
    return ref._traj


def test_target_motion():
    tr_s = _target_track("static")
    moved_s = math.hypot(tr_s[-1][0][0] - tr_s[0][0][0], tr_s[-1][0][1] - tr_s[0][0][1])
    ok(moved_s < 0.01, "static → 표적 안 움직임(이동 %.3f셀)" % moved_s)
    tr_c = _target_track("const")
    moved_c = math.hypot(tr_c[-1][0][0] - tr_c[0][0][0], tr_c[-1][0][1] - tr_c[0][0][1])
    ok(moved_c > 1.0, "const → 표적 등속 이동(이동 %.2f셀)" % moved_c)
    ok(len(tr_c) == 10, "궤적이 스텝마다 기록됨(운동 표적 시각 맞춤 채점용)")


if __name__ == "__main__":
    test_clutter()
    test_target_motion()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nreference clutter 검사 통과(0=없음 · >0=표적서 먼 헛 탐지)")
