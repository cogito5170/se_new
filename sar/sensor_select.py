#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sensor-agnostic 선택 정책 (policy update) — 환경에서 **센서를 못 박지 않고** 물리로 고른다.

사람 우선 UAV: 상황(안개·야간·수관·협곡·화재)마다 어느 센서가 사람을 탐지·측위하는 데 가장
정보량이 큰지 다르다. 정책은 하나를 하드코딩하지 않고, **각 modality 의 환경결합 품질 q∈[0,1]**
(sensors_ref 물리 + environment 변수)를 재서 고른다.

  탐지(detection): RGB · Thermal · LiDAR · Audio  — 사람을 '찾는다'
  측위(positioning): GNSS · IMU                   — 어디인지 '안다'

정직(과장방지·NASA-STD-7009B): q 는 우리 환경변수(대표/유도 포함)에 기댄 값이라 domain 한정이다.
'센서를 선택했다'가 '탐지에 성공했다'가 아니다 — 품질 순위일 뿐. 실측 보정 전엔 상대 비교.
"""
from __future__ import annotations
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sensors_ref as SR
import environment as ENV

DETECTION = ("RGB", "Thermal", "LiDAR", "Audio")
POSITIONING = ("GNSS", "IMU")


def _clip01(x):
    return max(0.0, min(1.0, float(x)))


# 정보 풍부도(식별력) 가중 — 물리 탐지력이 비슷해도 modality 가 주는 정보의 질은 다르다:
# RGB=색·형상(식별) > Thermal=열형체 > LiDAR=기하 > Audio=방위만. 맑은 날 RGB 가 앞서는 이유.
INFO_WEIGHT = {"RGB": 1.0, "Thermal": 0.85, "LiDAR": 0.80, "Audio": 0.60}


def quality(modality, env, rng=None):
    """modality 의 환경결합 탐지/측위 품질 q∈[0,1] — sensors_ref 물리 × 정보풍부도.

    탐지 q = INFO_WEIGHT × 물리탐지력(환경에 따라 무너짐). 측위는 **절대(GNSS) > 상대(IMU 표류)**."""
    R = env["range_m"]
    canopy = env["canopy"]
    if modality == "RGB":
        tau = math.exp(-(3.912 / max(env["V"], 1.0)) * R)              # 안개 투과(가시)
        illum = _clip01(math.log10(max(env["lux"], 1e-4)) / 4.0)        # 조도(광자한계)
        cf = 0.05 if canopy else 1.0                                    # 수관 광학 못 뚫음
        return _clip01(tau * illum * cf * (1.0 - env["glare"])) * INFO_WEIGHT["RGB"]
    if modality == "Thermal":
        r = SR.thermal_dn(env["T_target"], env["T_ambient"], 0.98, env["V"], R, rng=rng)
        cf = 0.25 if canopy else 1.0                                    # 침엽 수관은 LWIR 도 대부분 가린다(정직)
        return _clip01(abs(r["dT_apparent_K"]) / 6.0 * cf) * INFO_WEIGHT["Thermal"]   # 열대비/NETD 포화 완화
    if modality == "LiDAR":
        r = SR.lidar_return(R, env["reflectivity"], env["V"], rng=rng)
        cf = 0.1 if canopy else 1.0        # 수관 위를 맞고 사람에 거의 안 닿음(반사율↓만으론 부족 — 폐색)
        return _clip01(r["snr"] / 10.0) * INFO_WEIGHT["LiDAR"] * cf
    if modality == "Audio":
        r = SR.audio_detect((R, 0.0), (0.0, 0.0), source_db=env["source_db"], wind_db=env["wind_db"], rng=rng)
        base = _clip01(r["snr_db"] / 20.0 + 0.3) if r["snr_db"] > -6 else 0.0   # 소리는 안개·수관 통과
        return base * INFO_WEIGHT["Audio"]
    if modality == "GNSS":
        r = SR.gnss_measure(env["gnss_env"], rng=rng)
        return 0.0 if not r["available"] else _clip01(1.0 / (1.0 + r["pos_sigma_m"] / 10.0))
    if modality == "IMU":
        r = SR.imu_sample(0.0, 0.0, env["t"], rng=rng)
        # IMU 는 **상대 추측항법**(절대위치 없음, 표류) — 작동하는 GNSS 보다 항상 낮게(폴백) 상한 0.5
        return _clip01(0.5 / (1.0 + r["pos_sigma_m"] / 15.0))


def select(env, available=None, rng=None):
    """환경에서 탐지·측위 센서를 물리 품질로 고른다. 반환 순위·1순위·근거(sensor-agnostic)."""
    det = [m for m in DETECTION if (available is None or m in available)]
    pos = [m for m in POSITIONING if (available is None or m in available)]
    dq = sorted(((m, quality(m, env, rng)) for m in det), key=lambda z: -z[1])
    pq = sorted(((m, quality(m, env, rng)) for m in pos), key=lambda z: -z[1])
    primary = dq[0][0] if dq and dq[0][1] > 0 else None
    posprimary = pq[0][0] if pq and pq[0][1] > 0 else None
    why = _rationale(env, dq, pq)
    return {"detection_rank": dq, "positioning_rank": pq,
            "primary_detection": primary, "primary_positioning": posprimary, "rationale": why}


def _rationale(env, dq, pq):
    parts = []
    top = dq[0] if dq and dq[0][1] > 0 else (None, 0.0)
    rgb_q = dict(dq).get("RGB", 0.0)
    reason = {
        "RGB": "가시·조도 양호 → RGB 우선(식별력)",
        "Thermal": ("야간/저조도 RGB 무력 → 열대비로 Thermal" if env["lux"] < 1.0
                    else "안개/연기로 RGB 저하 → LWIR τ 우위로 Thermal"),
        "LiDAR": "RGB 저하지만 LiDAR 기하 확보 → LiDAR",
        "Audio": "광학·LiDAR 막힘(수관/짙은안개) → 소리로 Audio",
        None: "탐지 센서 전부 저하 — MRC/재접근 필요",
    }[top[0]]
    parts.append(reason)
    if pq and pq[0][0] == "GNSS":
        parts.append("GNSS 가용 → 절대측위")
    elif pq and pq[0][0] == "IMU":
        parts.append("GNSS 불가(협곡/도심) → IMU 추측항법")
    return " · ".join(parts)


# 정책 결정 규격(사람이 읽는 표)
POLICY_SPEC = [
    ("맑음·주간", "RGB", "GNSS", "가시 τ·조도 높음"),
    ("야간", "Thermal", "GNSS", "조도↓지만 열대비 유지(배경 서늘)"),
    ("옅은 안개/연기", "Thermal", "GNSS", "LWIR τ > 가시 τ"),
    ("짙은 안개(물방울)+원거리", "Audio/근접", "IMU/GNSS", "LWIR 도 먹힘 → 소리·근접"),
    ("수관 아래", "Audio", "GNSS", "광학·LiDAR·근적외 못 뚫음, 소리는 통과"),
    ("도심/협곡", "RGB/Thermal", "IMU", "GNSS multipath·outage → 추측항법"),
    ("화재 근접", "Thermal(단 clutter 주의)", "GNSS", "사람=차가운 대비(−ΔT), RGB 는 glare↓; hot clutter 오경보는 미모델(GAP)"),
]


def spec_md():
    L = ["# Sensor-agnostic 선택 정책 규격 (policy update)", ""]
    L.append("> 센서를 하드코딩하지 않는다. 환경변수(V·lux·온도·풍·수관·gnss_env)로 각 modality 의 물리 "
             "품질 q 를 재서 탐지·측위 센서를 고른다. 'q 최대'가 '탐지 성공'은 아니다(상대 순위) — NASA-STD-7009B domain 한정.")
    L.append("")
    L.append("| 상황 | 1순위 탐지 | 측위 | 물리 근거 |")
    L.append("|---|---|---|---|")
    for s, d, p, w in POLICY_SPEC:
        L.append("| %s | %s | %s | %s |" % (s, d, p, w))
    L.append("")
    L.append("- 탐지: RGB·Thermal·LiDAR·Audio / 측위: GNSS·IMU. `quality()` 가 sensors_ref 물리로 q 를 낸다.")
    L.append("- 정직: q 는 대표/유도 환경변수에 기댄 domain 한정 값. 실측 referent 보정 전엔 상대 비교다.")
    return "\n".join(L) + "\n"


def demo_md():
    """대표 상황들에서 정책이 어느 센서를 고르는지 — 물리로."""
    cases = [
        ("맑음 주간(숲)", ENV.build("정상", V=20000, lux=15000, landcover_class="forest", range_m=120, t=60)),
        ("야간(숲)", ENV.build("야간", V=12000, lux=0.05, landcover_class="forest", range_m=120, t=60)),
        ("옅은 안개", ENV.build("안개", V=300, lux=4000, landcover_class="forest", range_m=120, t=60)),
        ("짙은 안개 원거리", ENV.build("안개", V=40, lux=2000, landcover_class="forest", range_m=180, t=60)),
        ("수관 아래", ENV.build("정상", V=15000, lux=8000, landcover_class="forest", canopy=True, range_m=100, t=60)),
        ("도심(multipath)", ENV.build("정상", V=18000, lux=12000, landcover_class="urban", slope=0.2, range_m=120, t=60)),
        ("산악 협곡(급경사)", ENV.build("정상", V=18000, lux=12000, landcover_class="alpine", slope=0.85, range_m=120, t=90)),
        ("화재 근접", ENV.build("화재", V=200, lux=5000, glare=0.65, landcover_class="grass", range_m=80, t=60)),
    ]
    L = ["# 상황별 센서 선택 (물리로 고른다)", ""]
    L.append("| 상황 | 탐지 순위(q) | 1순위 | 측위 | 근거 |")
    L.append("|---|---|---|---|---|")
    import numpy as np
    for name, env in cases:
        s = select(env, rng=np.random.default_rng(0))
        rank = " ".join("%s%.2f" % (m, q) for m, q in s["detection_rank"])
        L.append("| %s | %s | **%s** | %s | %s |" % (name, rank, s["primary_detection"] or "—",
                 s["primary_positioning"] or "—", s["rationale"]))
    L.append("")
    L.append("- 하드코딩 없음: 같은 `quality()` 로 상황마다 다른 센서가 1순위가 된다(sensor-agnostic).")
    L.append("- 정직: domain 한정(대표/유도 환경변수). 온도·풍·multipath 는 실측 GAP(environment.gaps()).")
    return L, cases


if __name__ == "__main__":
    import argparse
    import datetime
    ap = argparse.ArgumentParser(); ap.add_argument("--spec", action="store_true"); ap.add_argument("--demo", action="store_true")
    a, _ = ap.parse_known_args()
    if a.spec:
        print(spec_md()); raise SystemExit(0)
    L, cases = demo_md()
    md = "\n".join(L) + "\n"
    if a.demo:
        REPO = os.path.dirname(HERE); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
        rel = "public_agent_memory/sensor_select_%s.md" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        # spec + env audit + demo 를 한 보고서로
        open(os.path.join(REPO, rel), "w", encoding="utf-8").write(
            SR.spec_md() + "\n---\n" + ENV.audit_md() + "\n---\n" + spec_md() + "\n---\n" + md)
        print("산출물:", rel)
    print(md)
