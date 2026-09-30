#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sensor-agnostic 선택 정책 검사 — 하드코딩 없이 환경으로 센서를 고르는지 붙든다.

핵심: (1) q∈[0,1] 유계, (2) 상황마다 1순위가 다르다(맑음→RGB·야간/안개→Thermal·수관/짙은안개→
Audio), (3) 측위는 협곡서 GNSS→IMU 로 폴백, (4) 같은 quality() 하나로 갈린다(sensor-agnostic).
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sar"))
import sensor_select as SS
import environment as ENV

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def _sel(**kw):
    env = ENV.build(**kw)
    return SS.select(env, rng=np.random.default_rng(0))


def test_quality_bounded():
    env = ENV.build("안개", V=200, lux=3000, landcover_class="forest", range_m=120, t=30)
    for m in SS.DETECTION + SS.POSITIONING:
        q = SS.quality(m, env, rng=np.random.default_rng(0))
        ok(0.0 <= q <= 1.0, "q(%s)∈[0,1] (%.2f)" % (m, q))


def test_clear_day_rgb():
    s = _sel(condition="정상", V=20000, lux=15000, landcover_class="forest", range_m=120, t=60)
    ok(s["primary_detection"] == "RGB", "맑음 주간 → RGB 1순위(식별력)")
    ok(s["primary_positioning"] == "GNSS", "open → GNSS 측위")


def test_night_thermal():
    s = _sel(condition="야간", V=12000, lux=0.05, landcover_class="forest", range_m=120, t=60)
    ok(s["primary_detection"] == "Thermal", "야간 → Thermal 1순위(RGB 무력)")


def test_canopy_audio():
    s = _sel(condition="정상", V=15000, lux=8000, landcover_class="forest", canopy=True, range_m=100, t=60)
    ok(s["primary_detection"] == "Audio", "수관 아래 → Audio 1순위(광학·LiDAR 폐색)")
    # RGB·LiDAR 는 수관서 바닥
    dq = dict(s["detection_rank"])
    ok(dq["RGB"] < 0.15 and dq["LiDAR"] < 0.2, "수관서 RGB·LiDAR q 바닥")


def test_canyon_imu_fallback():
    s = _sel(condition="정상", V=18000, lux=12000, landcover_class="alpine", slope=0.85, range_m=120, t=90)
    ok(s["primary_positioning"] == "IMU", "협곡(GNSS outage) → IMU 추측항법")


def test_sensor_agnostic_varies():
    # 같은 정책이 상황마다 다른 1순위를 내야 한다(하드코딩 아님)
    prims = set()
    for kw in (dict(condition="정상", V=20000, lux=15000, landcover_class="forest", range_m=120, t=60),
               dict(condition="야간", V=12000, lux=0.05, landcover_class="forest", range_m=120, t=60),
               dict(condition="안개", V=40, lux=2000, landcover_class="forest", range_m=180, t=60),
               dict(condition="정상", V=15000, lux=8000, landcover_class="forest", canopy=True, range_m=100, t=60)):
        prims.add(_sel(**kw)["primary_detection"])
    ok(len(prims) >= 3, "상황별 1순위가 갈린다(sensor-agnostic): %s" % prims)


if __name__ == "__main__":
    for fn in (test_quality_bounded, test_clear_day_rgb, test_night_thermal, test_canopy_audio,
               test_canyon_imu_fallback, test_sensor_agnostic_varies):
        print("[%s]" % fn.__name__)
        fn()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\n센서 선택 정책 검사 통과: 하드코딩 없이 환경으로 갈린다")
