#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""liveness reference model — 관측가능성 경계가 요구한 물리 변수 z 를 실제 물리로 둔다.

#449(cmpc_vv)가 실험으로 보인 것: 전-서명 decoy 는 5채널 관측공간 I={RGB,LWIR,LiDAR,SAR,Audio}
에서 실표적 가설 H_T 와 **관측적으로 동치인 영역**을 갖는다(P(I|H_T)≈P(I|H_D)). 그 영역을 가르려면
**새 관측 변수 z** 가 필요하고, z 는 P(I,z|H_T) ≠ P(I,z|H_D) 를 만드는 것이라야 한다.

이 모듈은 후보 z 들을 **물리로 모델링**하고, 각 z 가 H_T(살아있는 사람) 대 H_D(decoy)를 얼마나
가르는지 D_KL(P(z|H_T) ‖ P(z|H_D)) 와 ROC-AUC 로 잰다 — "어느 liveness 센서를 달까"를
**"두 가설을 가장 잘 가르는 최소 물리 변수는 무엇인가"** 로 바꾼다.

주 물리 변수(FINDER/JPL·DHS 계열, 전문 미열람 [출처:조각]):
  심폐 미세운동(호흡+심박)을 **RF 마이크로도플러 위상**으로 본다.
  가슴벽 변위     x(t) = A_r sin(2π f_r t) + A_h sin(2π f_h t)
  RF 위상         φ(t) = (4π/λ) x(t)                       (λ=반송파 파장)
  기저대역        s(t) = exp(j φ(t)) + n(t),  n ~ CN(0, σ²)
  탐지 통계       위상복조 신호의 [f_lo, f_hi] Hz 대역 에너지(호흡·심박 대역)

문헌 대표값 [출처:조각] (현장 validation 아님):
  호흡  f_r ≈ 0.2–0.34 Hz(12–20 회/분), 진폭 A_r ≈ 1–12 mm (가슴벽)
  심박  f_h ≈ 1.0–1.7 Hz(60–100 bpm),   진폭 A_h ≈ 0.2–0.5 mm
  decoy H_D: 심폐 주기 운동 없음(구조 진동·잡음만) → 대역 에너지가 잡음 바닥.

정직: 이것은 **대표 물리 L2 reference** 이지 실 센서 검증이 아니다. z 의 최소성(더 작은 관측으로도
충분한가)과 실 하드웨어 실현성은 미해결 — 논문 §minimal-observable 의 open problem 으로 남긴다.
"""
from __future__ import annotations
import math
import numpy as np

C_LIGHT = 299_792_458.0


def chest_displacement(t, f_r, A_r, f_h, A_h, phase_r=0.0, phase_h=0.0):
    """가슴벽 변위 x(t) [m] = 호흡 + 심박 (미터 단위). A_* 는 미터로 받는다."""
    return A_r * np.sin(2 * math.pi * f_r * t + phase_r) + A_h * np.sin(2 * math.pi * f_h * t + phase_h)


def microdoppler_baseband(t, x, fc_hz, snr_db, rng):
    """RF 마이크로도플러 기저대역 s(t)=exp(jφ)+n, φ=(4π/λ)x. 반환 복소 신호."""
    lam = C_LIGHT / fc_hz
    phi = (4.0 * math.pi / lam) * x
    s = np.exp(1j * phi)
    # 잡음: 목표 SNR(신호 전력 1) 에 맞춰 CN(0,σ²)
    sigma = math.sqrt(10 ** (-snr_db / 10.0))
    n = (rng.standard_normal(len(t)) + 1j * rng.standard_normal(len(t))) * (sigma / math.sqrt(2.0))
    return s + n


def band_energy_stat(s, fs, f_lo=0.15, f_hi=2.0):
    """탐지 통계: 위상복조 신호의 [f_lo,f_hi] Hz 대역 에너지 비(생체징후 대역/전대역).
    decoy 는 이 대역에 주기 성분이 없어 값이 낮다."""
    phi = np.unwrap(np.angle(s))
    phi = phi - phi.mean()
    n = len(phi)
    P = np.abs(np.fft.rfft(phi)) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    band = (freqs >= f_lo) & (freqs <= f_hi)
    tot = P.sum() + 1e-30
    return float(P[band].sum() / tot)


def _episode_stat(alive, rng, T=20.0, fs=20.0, fc_hz=3.0e9, snr_db=6.0):
    """한 에피소드의 탐지 통계. alive=True → 심폐 미세운동, False → decoy(운동 없음)."""
    t = np.arange(0, T, 1.0 / fs)
    if alive:
        f_r = rng.uniform(0.2, 0.34); A_r = rng.uniform(1e-3, 8e-3)      # 호흡 1–8 mm
        f_h = rng.uniform(1.0, 1.7);  A_h = rng.uniform(0.2e-3, 0.5e-3)  # 심박 0.2–0.5 mm
        x = chest_displacement(t, f_r, A_r, f_h, A_h,
                               rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi))
    else:
        # decoy: 심폐 주기 없음. 미세 구조진동(광대역·작음)만 — 생체징후 대역에 주기 피크 없음.
        x = 1e-4 * rng.standard_normal(len(t))
    s = microdoppler_baseband(t, x, fc_hz, snr_db, rng)
    return band_energy_stat(s, fs)


def _kl_gauss(m1, s1, m2, s2):
    """1차원 가우스 근사 D_KL(N1 ‖ N2) [nats]. 통계 분포를 가우스로 근사(대칭성 위해 양방향 평균도 낸다)."""
    s1 = max(s1, 1e-9); s2 = max(s2, 1e-9)
    return math.log(s2 / s1) + (s1 * s1 + (m1 - m2) ** 2) / (2 * s2 * s2) - 0.5


def _auc(pos, neg):
    """ROC-AUC(Mann–Whitney U). pos=H_T 통계, neg=H_D 통계."""
    pos = np.asarray(pos); neg = np.asarray(neg)
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order), float); ranks[order] = np.arange(1, len(order) + 1)
    r_pos = ranks[:len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def separability(n_ep=400, seed=7009, snr_db=6.0, **kw):
    """H_T(alive) 대 H_D(decoy) 의 z=마이크로도플러 대역에너지 분리도.
    반환 D_KL(양방향 평균), AUC, 두 분포의 mean/sd, n. (측정: 재현·독립대조용)."""
    rng = np.random.default_rng(seed)
    zt = np.array([_episode_stat(True, rng, snr_db=snr_db, **kw) for _ in range(n_ep)])
    zd = np.array([_episode_stat(False, rng, snr_db=snr_db, **kw) for _ in range(n_ep)])
    mt, st = zt.mean(), zt.std(ddof=1); md, sd = zd.mean(), zd.std(ddof=1)
    kl = 0.5 * (_kl_gauss(mt, st, md, sd) + _kl_gauss(md, sd, mt, st))  # 대칭 KL(Jeffreys)
    return dict(D_KL_sym=kl, AUC=_auc(zt, zd), n=n_ep, snr_db=snr_db,
                HT_mean=float(mt), HT_sd=float(st), HD_mean=float(md), HD_sd=float(sd))


# 후보 관측 변수 z 와 판별 기준(비접촉·가림투과·국소화·전력 유한). computed=D_KL/AUC 로 잰 것.
CANDIDATES = [
    # (기호, 이름, 물리, 비접촉, 가림투과, 국소화(방위/거리), 판정)
    ("z1", "호흡 주기", "가슴벽 저주파 변위 f_r≈0.2–0.34Hz", "예", "부분", "약함",
     "긴 dwell 필요·몸 움직임에 가림. 마이크로도플러의 한 성분."),
    ("z2", "심박 미세운동", "심장 박동 변위 f_h≈1–1.7Hz, 0.2–0.5mm", "예", "부분", "약함",
     "진폭 매우 작음·민감 위상 필요. 마이크로도플러의 한 성분."),
    ("z3", "CO2 농도", "호기 CO2 확산", "예", "약함", "없음(방위 불가)",
     "확산·바람 의존, 국소화 불가 → 표적 위치 결정 못 함."),
    ("z4", "미세 진동(접촉/지진)", "지반·구조 결합 진동", "아니오", "해당없음", "중간",
     "접촉/결합 필요 → 공중 UAV 에 부적합."),
    ("z5", "RF 마이크로도플러", "심폐 미세운동 위상 φ=(4π/λ)x", "예", "강함(잔해·수관)", "강함(레이더)",
     "★ 비접촉·가림투과·국소화 모두 충족. z1·z2 를 한 관측으로 포섭. FINDER 계열."),
]


def report(n_ep=400):
    r = separability(n_ep=n_ep)
    print("# liveness 물리 변수 z — H_T(사람) 대 H_D(decoy) 분리도 (RF 마이크로도플러)")
    print("D_KL_sym=%.2f nats · ROC-AUC=%.3f · n=%d (SNR=%.0f dB)" % (r["D_KL_sym"], r["AUC"], r["n"], r["snr_db"]))
    print("  H_T 대역에너지 mean=%.3f sd=%.3f · H_D mean=%.3f sd=%.3f" % (r["HT_mean"], r["HT_sd"], r["HD_mean"], r["HD_sd"]))
    print("\n# 후보 z 판별표 (비접촉·가림투과·국소화)")
    print("| z | 이름 | 물리 | 비접촉 | 가림투과 | 국소화 | 판정 |")
    print("|---|---|---|---|---|---|---|")
    for row in CANDIDATES:
        print("| " + " | ".join(row) + " |")
    # SNR 민감도(동작점 성함 확인 — 사소한 설명 죽이기: 아주 높은 SNR 이라 나온 게 아님)
    print("\n# SNR 민감도 (동작점)")
    for snr in (0.0, 3.0, 6.0, 12.0):
        rr = separability(n_ep=n_ep, snr_db=snr)
        print("  SNR=%2.0f dB: AUC=%.3f  D_KL_sym=%.2f" % (snr, rr["AUC"], rr["D_KL_sym"]))
    return r


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--ep", type=int, default=400)
    a, _ = ap.parse_known_args()
    report(n_ep=a.ep)
