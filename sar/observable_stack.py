#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""관측 스택 × decoy 분류 × 환경 → 증분 구별가능성 D_k(E) 와 최소 관측집합 Z_min(E) 실측.

사용자 재정식화(2026-09):
  "liveness 는 단일 센서가 아니라, 현재 관측모델에 없는 식별 정보를 어떤 **최소 물리 observable
   집합**이 제공해야 하는가(환경 의존 Z_min(E))" 이다. motion≠liveness, thermal≠liveness.

이 모듈은 **참조세계(심판) 쪽** 분석이다 — 숨은 truth 인 소스(사람/식생/바위/동물/열원/이동체)가
각 관측 변수에 무엇을 내는지 물리로 모델링하고, 사람(H_T) 대 각 decoy(H_D)의 구별가능성(AUC,
Mann–Whitney)을 환경 E 별로 잰다. SUT 에는 아무것도 주지 않는다(V&V 공간 분리).

관측 스택:
  thermal_contrast  (L0)  — sensors_ref.thermal_dn 의 겉보기 ΔT (실제 센서 물리)
  motion_speed      (L1)  — 평균 속력
  motion_periodicity(L1)  — 속력 스펙트럼의 바람대역 에너지비(식생 흔들림 vs 사람)
  motion_directedness(L1) — |순변위|/경로길이 (직진 vs 진동)
  microdoppler(z)   (L1)  — liveness_ref 심폐 대역에너지 (live vs non-live)

정직(과장방지):
  - 사람은 정지(호흡만)와 보행 두 경우로 나눠 잰다. 재난 표적은 정지가 흔하고 그때 motion 이 무력하다.
  - 동물은 live 라 microdoppler 로 못 가른다(사람 대 동물은 gait/articulation 필요 — 이 스택 밖).
  - 모두 대표 물리 L2 이며 현장 validation 아님. 파라미터는 문헌 대표값 [출처:조각].
"""
from __future__ import annotations
import math
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import sensors_ref as _sr
import liveness_ref as _lv

FS = 5.0          # 관측 표본율(Hz)
T = 20.0          # dwell(s)
NSTEP = int(FS * T)

# 소스 정의: (온도K, 운동유형, live?)  운동유형: static·breath·walk·oscillate·directed·straight
SOURCES = {
    "human_static": dict(temp=305.0, motion="static", live=True),
    "human_walk":   dict(temp=305.0, motion="walk", live=True),
    "vegetation":   dict(temp=None,  motion="oscillate", live=False),   # temp=ambient
    "rock":         dict(temp="rock", motion="static", live=False),     # 햇빛 데움(주간)
    "heat_source":  dict(temp=330.0, motion="static", live=False),      # 엔진·불씨
    "animal":       dict(temp=305.0, motion="directed", live=True),     # 포유류(live!)
    "moving_object":dict(temp=300.0, motion="straight", live=False),    # 차량 등
}
TARGETS = ["human_static", "human_walk"]
DECOYS = ["vegetation", "rock", "heat_source", "animal", "moving_object"]

# 환경 E: (T_amb, 시정 V[m], 조도 illum[lux], 바람진폭 wind_amp[m], microD SNR[dB])
ENVIRON = {
    "day-calm":   dict(T_amb=293.0, V=18000.0, illum=15000.0, wind=0.05, md_snr=6.0),
    "day-breeze": dict(T_amb=293.0, V=18000.0, illum=15000.0, wind=0.33, md_snr=6.0),  # veg speed≈walk
    "day-wind":   dict(T_amb=293.0, V=18000.0, illum=15000.0, wind=0.9,  md_snr=6.0),
    "night-calm": dict(T_amb=283.0, V=8000.0,  illum=0.5,     wind=0.05, md_snr=6.0),
}
AUC_SEP = 0.90    # |AUC-0.5|>=0.4 → 그 관측이 이 decoy 를 가른다(보수적: 단일 관측 기준)


def _temp_of(src, E):
    t = SOURCES[src]["temp"]
    if t is None:
        return E["T_amb"]                          # 식생=주변온
    if t == "rock":
        return E["T_amb"] + (27.0 if E["illum"] > 100 else 3.0)   # 주간 햇빛 데움, 야간 미미
    return float(t)


def _motion_track(kind, E, rng):
    """위치 시계열 (NSTEP,2). 바람은 식생 진동 진폭을 키운다."""
    p = np.zeros((NSTEP, 2)); dt = 1.0 / FS
    if kind in ("static",):
        return p + rng.normal(0, 0.02, (NSTEP, 2))
    if kind == "oscillate":                        # 식생: 바람 구동 진동(순변위≈0)
        A = E["wind"]; f = rng.uniform(0.2, 0.8); ph = rng.uniform(0, 2*math.pi)
        t = np.arange(NSTEP) * dt
        p[:, 0] = A * np.sin(2*math.pi*f*t + ph); p[:, 1] = 0.6*A*np.sin(2*math.pi*f*t + ph + 1.0)
        return p + rng.normal(0, 0.02, (NSTEP, 2))
    # 방향성 운동: walk 1.0 / directed 1.5 / straight 2.0 m/s, 회전잡음 차등
    v0 = {"walk": 1.0, "directed": 1.5, "straight": 2.0}[kind]
    turn = {"walk": 0.15, "directed": 0.35, "straight": 0.03}[kind]
    hdg = rng.uniform(0, 2*math.pi); pos = np.zeros(2)
    for i in range(NSTEP):
        hdg += rng.normal(0, turn); v = max(0.0, rng.normal(v0, 0.2))
        pos = pos + v*dt*np.array([math.cos(hdg), math.sin(hdg)])
        p[i] = pos
    return p + rng.normal(0, 0.02, (NSTEP, 2))


def _obs_stats(src, E, rng):
    """한 에피소드의 관측 통계 dict."""
    S = SOURCES[src]
    # thermal: 겉보기 ΔT 크기(실 센서 물리)
    slant = 210.0
    th = _sr.thermal_dn(_temp_of(src, E), E["T_amb"], 0.95, E["V"], slant, rng=rng)
    thermal = abs(th["dT_apparent_K"])
    # motion
    trk = _motion_track(S["motion"], E, rng)
    d = np.diff(trk, axis=0); step = np.hypot(d[:, 0], d[:, 1])
    speed = float(step.mean() * FS)
    path = float(step.sum()) + 1e-9
    net = float(np.hypot(*(trk[-1] - trk[0])))
    directed = net / path
    sp = step - step.mean()
    P = np.abs(np.fft.rfft(sp))**2; fr = np.fft.rfftfreq(len(sp), 1.0/FS)
    band = (fr >= 0.15) & (fr <= 1.0)
    period = float(P[band].sum() / (P.sum() + 1e-30))
    # microdoppler(z): live 면 심폐 신호
    md = _lv._episode_stat(S["live"], rng, T=T, fs=20.0, snr_db=E["md_snr"])
    return dict(thermal=thermal, motion_speed=speed, motion_periodicity=period,
                motion_directedness=directed, microdoppler=md)


OBS = ["thermal", "motion_speed", "motion_periodicity", "motion_directedness", "microdoppler"]


def _auc(a, b):
    a = np.asarray(a); b = np.asarray(b)
    order = np.argsort(np.concatenate([a, b]))
    ranks = np.empty(len(order)); ranks[order] = np.arange(1, len(order)+1)
    r = ranks[:len(a)].sum()
    return float((r - len(a)*(len(a)+1)/2.0) / (len(a)*len(b)))


def measure(n=300, seed=909):
    rng = np.random.default_rng(seed)
    # 소스별·환경별 통계 표본
    samp = {E: {s: {o: [] for o in OBS} for s in SOURCES} for E in ENVIRON}
    for Ename, E in ENVIRON.items():
        for s in SOURCES:
            for _ in range(n):
                st = _obs_stats(s, E, rng)
                for o in OBS:
                    samp[Ename][s][o].append(st[o])
    return samp


def report(n=300):
    samp = measure(n=n)
    print("# 관측 스택 × decoy × 환경 — 사람(H_T) 대 decoy(H_D) 구별가능성 |AUC|  (n=%d/셀)" % n)
    print("# 가름 기준: |AUC-0.5|>=0.40 (AUC>=0.90 또는 <=0.10).  ★=가름")
    for tgt in TARGETS:
        print("\n================ H_T = %s ================" % tgt)
        for Ename in ENVIRON:
            print("\n## E = %s" % Ename)
            print("| decoy | " + " | ".join(OBS) + " | Z_min(이 decoy 가르는 최소집합) |")
            print("|---|" + "---|"*len(OBS) + "---|")
            for d in DECOYS:
                cells = []; covering = []
                for o in OBS:
                    auc = _auc(samp[Ename][tgt][o], samp[Ename][d][o])
                    sep = abs(auc - 0.5) >= 0.40
                    cells.append(("★%.2f" % auc) if sep else ("%.2f" % auc))
                    if sep:
                        covering.append(o)
                zmin = ", ".join(covering) if covering else "**없음(이 스택으론 못 가름)**"
                print("| %s | %s | %s |" % (d, " | ".join(cells), zmin))
            # 환경별 Z_min: 모든 decoy 를 덮는 최소 관측집합(집합덮개, 단일관측 커버 기준)
            cover = {}
            for d in DECOYS:
                cover[d] = set(o for o in OBS if abs(_auc(samp[Ename][tgt][o], samp[Ename][d][o]) - 0.5) >= 0.40)
            uncovered = [d for d in DECOYS if not cover[d]]
            chosen = _set_cover({d: cover[d] for d in DECOYS if cover[d]})
            print("  → Z_min(%s | %s) = {%s}%s" % (
                Ename, tgt, ", ".join(chosen) if chosen else "—",
                ("  · 못 덮는 decoy: " + ", ".join(uncovered)) if uncovered else ""))


def _set_cover(cover):
    """greedy set cover: decoy 를 가장 많이 덮는 관측부터."""
    need = set(cover); chosen = []
    obs_to_decoys = {}
    for d, os_ in cover.items():
        for o in os_:
            obs_to_decoys.setdefault(o, set()).add(d)
    remaining = set(need)
    while remaining and obs_to_decoys:
        best = max(obs_to_decoys, key=lambda o: len(obs_to_decoys[o] & remaining))
        gain = obs_to_decoys[best] & remaining
        if not gain:
            break
        chosen.append(best); remaining -= gain; del obs_to_decoys[best]
    return chosen


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=300)
    a, _ = ap.parse_known_args()
    report(n=a.n)
