#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""센서 reference model + 환경정합 검사 — 물리 sanity 와 '우리 환경변수에 fit' 을 붙든다.

핵심: (1) 각 모델이 물리적으로 옳은 방향으로 반응(열대비·LWIR>가시 τ·LiDAR 안개감쇠·IMU 표류·
GNSS 협곡 outage·Audio 거리감쇠), (2) environment.build 가 부족분(온도·풍·gnss_env)을 채우고
gaps() 로 정직히 남긴다, (3) 파라미터가 우리 환경변수(condition·V·land-cover)에서 온다.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sar"))
import sensors_ref as SR
import environment as ENV

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def test_thermal_physics():
    rng = np.random.default_rng(0)
    # 야간(배경 서늘) 근거리: 사람 열대비 커서 탐지
    near = SR.thermal_dn(305.0, 283.0, 0.98, 20000.0, 30.0, rng=rng)
    ok(near["detectable"], "야간 근거리 사람 열대비 탐지")
    ok(near["tau_lwir"] > near["tau_visible"], "LWIR τ > 가시 τ(같은 안개서 열화상 유리)")
    # 짙은 안개 원거리: LWIR 도 먹혀 탐지 실패(면역 아님 — 정직)
    far_fog = SR.thermal_dn(305.0, 283.0, 0.98, 40.0, 180.0, rng=rng)
    ok(not far_fog["detectable"], "짙은 안개 180m 는 LWIR 도 실패(면역 아님)")


def test_lidar_physics():
    rng = np.random.default_rng(1)
    clear = SR.lidar_return(120.0, 0.3, 20000.0, rng=rng)
    fog = SR.lidar_return(120.0, 0.3, 40.0, rng=rng)
    ok(clear["detectable"], "맑은 날 120m LiDAR 탐지")
    ok(clear["snr"] > fog["snr"], "안개서 LiDAR SNR 급감(왕복 2β)")


def test_imu_drift_grows():
    a = SR.imu_sample(0.1, 0.01, 5.0)
    b = SR.imu_sample(0.1, 0.01, 120.0)
    ok(b["pos_sigma_m"] > a["pos_sigma_m"], "IMU 위치불확실 시간에 따라 성장(표류)")


def test_gnss_canyon_outage():
    op = SR.gnss_measure("open"); ca = SR.gnss_measure("canyon")
    ok(op["available"] and not ca["available"], "open 가용·canyon outage(<4위성)")
    ur = SR.gnss_measure("urban")
    ok(ur["available"] and ur["pos_sigma_m"] > op["pos_sigma_m"], "urban multipath 로 σ↑(가용은 함)")


def test_audio_distance():
    near = SR.audio_detect((30.0, 0.0), (0.0, 0.0), source_db=85.0, wind_db=35.0)
    far = SR.audio_detect((400.0, 0.0), (0.0, 0.0), source_db=85.0, wind_db=35.0)
    ok(near["snr_db"] > far["snr_db"], "가까울수록 음향 SNR↑")
    ok(near["detectable"], "30m 외침 탐지")


def test_rgb_fog_darkness():
    rng = np.random.default_rng(2)
    bright = SR.rgb_raw(np.full((4, 4), 0.8), env={"V": 20000, "illum": 15000, "range_m": 30}, rng=rng)
    dark = SR.rgb_raw(np.full((4, 4), 0.8), env={"V": 20000, "illum": 0.05, "range_m": 30}, rng=rng)
    ok(bright["snr"] > 0, "밝은 장면 RGB SNR>0")
    ok(int(np.mean(bright["DN"])) >= int(np.mean(dark["DN"])), "저조도면 DN↓")


def test_environment_fit_and_gaps():
    e = ENV.build("야간", V=12000, lux=0.05, landcover_class="forest", canopy=True, range_m=120, t=60)
    for k in ("T_ambient", "T_target", "wind_db", "gnss_env", "emissivity", "reflectivity"):
        ok(k in e, "env 에 %s 채워짐(부족분 보강)" % k)
    ok(e["gnss_env"] == "open", "숲 완경사 → gnss_env=open")
    ok(ENV.gnss_env_from("urban") == "urban" and ENV.gnss_env_from("alpine") == "canyon", "gnss_env 유도(도시/고산)")
    ok(len(ENV.gaps()) >= 3, "남은 GAP 을 정직히 나열(%d개)" % len(ENV.gaps()))
    # adapter 가 sensors_ref kwargs 로 매핑되는지
    ok(set(ENV.thermal_env(e)) >= {"T_scene", "T_ambient", "emissivity", "V", "range_m"}, "thermal adapter 키")
    ok(set(ENV.audio_env(e)) >= {"source_db", "wind_db"}, "audio adapter 키")


def test_thermal_contrast_sign_flips():
    # 물리 진실: 서늘 배경(293K)선 사람이 더 뜨겁고(+ΔT), 화재 배경(320K)선 사람이 더 차갑다(−ΔT).
    # (화재서 thermal 이 불리한 진짜 이유는 |ΔT|↓ 가 아니라 hot clutter 오경보 — 이 모델은 clutter 미포함.)
    cool = SR.thermal_dn(305.0, 293.0, 0.98, 20000.0, 50.0)["dT_apparent_K"]
    hot = SR.thermal_dn(305.0, 320.0, 0.98, 20000.0, 50.0)["dT_apparent_K"]
    ok(cool > 0 and hot < 0, "열대비 부호 반전: 서늘 배경 +ΔT, 화재 배경 −ΔT")
    ok(abs(cool) > 3 * 0.05 and abs(hot) > 3 * 0.05, "두 경우 다 |ΔT|>3·NETD(탐지 가능) — 크기는 남는다")


if __name__ == "__main__":
    for fn in (test_thermal_physics, test_lidar_physics, test_imu_drift_grows, test_gnss_canyon_outage,
               test_audio_distance, test_rgb_fog_darkness, test_environment_fit_and_gaps,
               test_thermal_contrast_sign_flips):
        print("[%s]" % fn.__name__)
        fn()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\n센서 reference + 환경정합 검사 통과: 물리 방향·환경 fit·GAP 정직")
