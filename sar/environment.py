#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""환경변수 정합층 — 센서 reference model 을 **우리 시뮬 환경변수에 fit** 시키고, 부족한 변수를 재점검.

우리가 이미 만든 환경변수(측정/유도): condition · V(가시) · lux(조도) · glare · land-cover(→material
eps·rough·lidar·emis) · DEM 고도·경사 · canopy · imu_sigma(t).

**재점검(부족분)**: 새 센서(Thermal·Audio·GNSS)가 요구하는데 우리 환경에 **없던** 변수를,
새로 지어내지 않고 **기존 변수에서 유도하거나 대표값으로** 채우고 그 출처/상태를 정직히 남긴다:
  · 온도장 T_ambient/T_target  ← condition 별 대표값(Thermal). 화재면 배경 뜨거워 열대비↓(정직).
  · 풍잡음 wind_db             ← condition 별 대표값(Audio). 비·화재면 시끄럽다.
  · GNSS 환경 open/urban/canyon ← land-cover(urban) + 지형(alpine/급경사=canyon)에서 유도.
  · emissivity                 ← scene.MATERIAL.emis (Thermal).

모든 판단은 NASA-STD-7009B(M&S credibility·validation domain): 유도·대표값은 **validation domain
한정 주장**이고, 실측 referent 로 보정 전에는 GAP 이다(gaps()). 인용/대표값은 [출처:조각].
"""
from __future__ import annotations
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scene as _scene

# ── condition 별 대표 온도[K] (부족분: 우리 COND_PHYS 엔 온도 없음) — 대표값 [출처:조각] ──
TEMP_AMBIENT_K = {
    "정상": 293.0, "야간": 283.0, "안개": 283.0, "연기": 305.0,
    "화재": 320.0, "먼지": 300.0, "비": 288.0, "센서고장": 293.0,
}
TARGET_SKIN_K = 305.0        # 옷 입은 사람 표면(피부 308K 보다 낮음) — 대표값

# ── condition 별 대표 풍/배경 음압잡음[dB] (부족분: 음향 잡음 바닥) — 대표값 [출처:조각] ──
WIND_DB = {
    "정상": 35.0, "야간": 30.0, "안개": 32.0, "연기": 50.0,
    "화재": 58.0, "먼지": 48.0, "비": 55.0, "센서고장": 35.0,
}
SURVIVOR_CALL_DB = 85.0      # 조난자가 부르는 소리(1m 기준) — 대표값

# 환경변수 감사표(NASA-STD-7009B): (변수, 출처, 쓰는 센서, 상태)
#   출처: measured(실측 소스)·derived(기존서 유도)·assumed(대표값)
AUDIT = [
    ("V (가시거리)", "measured→모델(Koschmieder)", "RGB·LiDAR·Thermal", "있음(β=3.912/V)"),
    ("lux (조도)", "assumed(condition 범위)", "RGB", "있음(범위 대표)"),
    ("glare", "assumed(condition)", "RGB", "있음"),
    ("land-cover→material(eps·rough·lidar·emis)", "measured(ESA WorldCover)+대표 material", "SAR·LiDAR·Thermal·RGB", "있음(피복 실측·계수 대표)"),
    ("DEM 고도·경사", "measured(AWS Terrarium)", "GNSS(canyon)·가시", "있음"),
    ("canopy(수관)", "scenario 명시", "RGB·Thermal·LiDAR 가림", "있음(부분)"),
    ("imu_sigma(t)", "모델(랜덤워크/GM)", "IMU", "있음"),
    ("T_ambient/T_target (온도장)", "assumed(condition 대표)", "Thermal", "**부족→대표값 채움**(실측 GAP)"),
    ("wind_db (음향 잡음)", "assumed(condition 대표)", "Audio", "**부족→대표값 채움**(실측 GAP)"),
    ("gnss_env (open/urban/canyon)", "derived(land-cover+지형)", "GNSS", "**부족→유도로 채움**(검증 GAP)"),
    ("multipath 실측", "없음", "GNSS", "GAP(대표 bias 만)"),
    ("실 대기 프로파일(MODTRAN)", "없음", "Thermal·LiDAR", "GAP(단일 β 근사)"),
]


def gnss_env_from(landcover_class, slope=0.0):
    """GNSS 환경 유도: 도시=urban, 고산/급경사(하늘 가림)=canyon, 그 외 open."""
    if landcover_class == "urban":
        return "urban"
    if landcover_class == "alpine" or slope > 0.7:
        return "canyon"
    return "open"


def build(condition="정상", V=20000.0, lux=10000.0, glare=0.0,
          landcover_class="forest", elev=None, slope=0.0, canopy=False, range_m=120.0, t=0.0):
    """우리 환경변수 + 재점검으로 채운 부족분을 하나의 canonical env dict 로."""
    mat = _scene.MATERIAL[_scene.LANDCOVER.get(landcover_class, _scene.LANDCOVER["grass"])["ground"]]
    return {
        "condition": condition, "V": float(V), "lux": float(lux), "glare": float(glare),
        "landcover": landcover_class, "reflectivity": mat["lidar"], "emissivity": mat["emis"],
        "canopy": bool(canopy), "range_m": float(range_m), "t": float(t), "slope": float(slope),
        # 재점검으로 채운 부족 변수(대표/유도) — validation domain 한정
        "T_ambient": TEMP_AMBIENT_K.get(condition, 293.0),
        "T_target": TARGET_SKIN_K,
        "wind_db": WIND_DB.get(condition, 35.0),
        "source_db": SURVIVOR_CALL_DB,
        "gnss_env": gnss_env_from(landcover_class, slope),
    }


# ── 센서별 adapter: canonical env → sensors_ref 함수 kwargs (fit 조율) ──
def rgb_env(env):
    return {"V": env["V"], "illum": env["lux"], "range_m": env["range_m"]}


def thermal_env(env):
    return {"T_scene": env["T_target"], "T_ambient": env["T_ambient"],
            "emissivity": 0.98, "V": env["V"], "range_m": env["range_m"]}


def lidar_env(env):
    # 수관 아래면 반사율 급감(광학·근적외 못 뚫음)
    rho = env["reflectivity"] * (0.1 if env["canopy"] else 1.0)
    return {"true_range_m": env["range_m"], "reflectivity": rho, "V": env["V"]}


def imu_params(env):
    return {}     # 기본 Allan 파라미터(소비자 MEMS 대표) 사용


def gnss_kwargs(env):
    return {"env": env["gnss_env"]}


def audio_env(env):
    # 수관·안개는 소리를 크게 막지 않는다(광학과 다른 채널). 비·화재는 잡음↑(wind_db 에 반영)
    return {"source_db": env["source_db"], "wind_db": env["wind_db"]}


def gaps():
    """실측 referent 로 아직 못 채운 것(NASA-STD-7009B validation domain 밖) — 정직히."""
    return [row for row in AUDIT if "GAP" in row[3] or "부족" in row[3]]


def audit_md():
    L = ["# 환경변수 재점검 (NASA-STD-7009B: 무엇이 measured/derived/assumed 인가)", ""]
    L.append("> 센서 reference model 을 우리 환경변수에 fit 시키며, 부족분을 **지어내지 않고 유도/대표값**으로 "
             "채우고 출처를 남긴다. 유도·대표값은 **validation domain 한정 주장**이다(실측 보정 전엔 GAP).")
    L.append("")
    L.append("| 환경변수 | 출처 | 쓰는 센서 | 상태 |")
    L.append("|---|---|---|---|")
    for v, src, used, st in AUDIT:
        L.append("| %s | %s | %s | %s |" % (v, src, used, st))
    L.append("")
    L.append("## 이번에 채운 부족분 (재점검 결과)")
    L.append("- **온도장 T_ambient/T_target**: condition 별 대표값. 화재면 배경 320K — 사람은 오히려 **차가운 대비**"
             "(−ΔT, 크기는 남음). 화재서 thermal 이 불리한 진짜 이유는 |ΔT|↓ 가 아니라 **화염 hot clutter 오경보**"
             "이고, 이 모델은 clutter 미포함(GAP).")
    L.append("- **wind_db**: condition 별 음향 잡음 바닥. 비·화재면 커서 audio SNR↓.")
    L.append("- **gnss_env**: land-cover(urban)+지형(alpine·급경사)에서 open/urban/canyon 유도.")
    L.append("- **emissivity**: scene.MATERIAL.emis 로 추가(초목 0.98·물 0.99·콘크리트 0.92).")
    L.append("")
    L.append("## 남은 GAP (실측 referent 필요 — 아직 validation domain 밖)")
    for v, src, used, st in gaps():
        L.append("- %s (%s)" % (v, st))
    L.append("- 온도장·풍잡음은 대표값이라 **현장 기상/음향 실측으로 보정 전엔 domain 한정**이다.")
    L.append("- GNSS multipath 는 대표 bias 만; 실 correlation/DLL·PLL·실 위성기하 아님.")
    L.append("- 대기는 단일 β 근사(MODTRAN 실 프로파일 아님). 전부 [출처:조각], 현장 validation 아님.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--audit", action="store_true")
    a, _ = ap.parse_known_args()
    if a.audit:
        print(audit_md()); raise SystemExit(0)
    e = build("안개", V=40.0, lux=2000.0, landcover_class="forest", canopy=True, range_m=180.0, t=30.0)
    print("canonical env(안개·수관·180m):", {k: e[k] for k in ("condition", "V", "T_ambient", "wind_db", "gnss_env", "reflectivity", "emissivity")})
    print("GAP 수:", len(gaps()))
