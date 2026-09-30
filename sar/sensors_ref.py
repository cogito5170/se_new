#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""물리기반 센서 reference model (radar 제외 — radar.py 가 소유) — 'truth+gaussian' 이 아니다.

각 센서의 **생성 물리 + 신호처리 chain**을 핵심 방정식 수준으로 둔다(사용자가 든 참고 모델의
core 만; **전체 시뮬레이터(ISETCam·DIRSIG 등) 재현이 아님** — Level-2 reference).

  RGB     ISETCam 계열 : radiance→photon→shot/read/PRNU→ADC→DN
  Thermal DIRSIG+MODTRAN: Planck→emissivity→대기(τ·L+L_path)→detector→DN  (왜 안개서 살아남나 물리로)
  LiDAR   DIRSIG waveform: pulse*target impulse→photon→peak→TOF→range
  IMU     IEEE Allan var : scale/misalign→bias(Gauss-Markov)→white→sampled
  GNSS    ESA 계열       : pseudorange(DOP·UERE·multipath·outage)→position
  Audio   Image Source   : Σ α_i/r_i δ(t-r_i/c)→mic→SNR/TDOA (소리는 안개·수관·야간 통과)

정직(과장방지): 파라미터는 문헌 대표값 [출처:조각]. **현장 validation 아님.** 각 모델은
정의된 fidelity 의 core 이지 상용 시뮬레이터가 아니다. reference world(다른 formulation) 소속.
"""
from __future__ import annotations
import math
import numpy as np

H_PLANCK = 6.62607015e-34
C_LIGHT = 299_792_458.0
K_B = 1.380649e-23


# ─────────────────────────────── RGB (ISETCam core) ───────────────────────────────
def rgb_raw(radiance, params=None, env=None, rng=None):
    """장면 radiance(상대,≥0) → 광자적분→shot/read/PRNU/dark→ADC→DN. 반환 DN·SNR·포화.

    핵심: N_e = radiance·gain_e (광자수), shot=Poisson, read~N(0,σ_r), PRNU 곱성, dark 가산.
    env: fog(투과 τ_vis)·illum(lux) 로 도달 radiance 를 줄인다. [출처:조각]"""
    p = dict(full_well=10000.0, read_e=2.0, prnu=0.01, dark_e=5.0, bits=10, gain_e=8000.0)
    if params:
        p.update(params)
    rng = rng or np.random.default_rng()
    L = np.asarray(radiance, dtype=float)
    if env:
        tau = math.exp(-(3.912 / max(env.get("V", 1e9), 1.0)) * env.get("range_m", 30.0))  # 안개 투과(가시)
        L = L * tau * min(1.0, env.get("illum", 20000.0) / 10000.0)                          # 저조도면 광자↓
    Ne = np.clip(L * p["gain_e"], 0, None)
    Ne = rng.poisson(np.clip(Ne, 0, p["full_well"])).astype(float)     # shot noise
    Ne = Ne * (1.0 + p["prnu"] * rng.standard_normal(Ne.shape))        # PRNU(곱성)
    Ne = Ne + rng.normal(0, p["dark_e"], Ne.shape) + rng.normal(0, p["read_e"], Ne.shape)  # dark+read
    sat = Ne >= p["full_well"]
    dn = np.clip(Ne / p["full_well"] * (2 ** p["bits"] - 1), 0, 2 ** p["bits"] - 1).astype(int)
    signal = float(np.mean(np.clip(radiance, 0, None)) * p["gain_e"])
    snr = signal / math.sqrt(signal + p["read_e"] ** 2 + p["dark_e"] ** 2 + 1e-9) if signal > 0 else 0.0
    return {"DN": dn, "snr": float(snr), "saturated": bool(np.any(sat)), "bits": p["bits"]}


# ─────────────────────────────── Thermal LWIR (Planck+MODTRAN core) ───────────────────────────────
def planck_band_radiance(T, lo_um=8.0, hi_um=14.0, n=24):
    """흑체 대역 복사휘도 ∫ L_λ dλ [W/m²/sr], L_λ=2hc²/λ⁵/(exp(hc/λkT)-1). LWIR 8–14µm."""
    lam = np.linspace(lo_um, hi_um, n) * 1e-6
    Ll = 2 * H_PLANCK * C_LIGHT ** 2 / lam ** 5 / (np.exp(H_PLANCK * C_LIGHT / (lam * K_B * T)) - 1.0)
    return float(np.trapezoid(Ll, lam)) if hasattr(np, "trapezoid") else float(np.trapz(Ll, lam))


def lwir_extinction(V, wavelength_um=10.0):
    """LWIR 소광계수 — 가시(Koschmieder 3.912/V)보다 **작다**(연기·박무·야간에 유리).
    단 물방울 안개(droplet~10µm≈λ)는 LWIR 도 크게 먹는다 → 짙은 안개선 면역 아님(정직). [출처:조각]"""
    beta_vis = 3.912 / max(V, 1.0)
    # 대표 비율: 시정 좋을수록(박무·연기) LWIR 훨씬 유리(k≈0.15), 짙은 안개(V작음)면 k→~0.8
    k = 0.15 + 0.65 * math.exp(-V / 150.0)
    return beta_vis * k


def thermal_dn(T_scene, T_ambient=288.0, emissivity=0.95, V=20000.0, range_m=100.0,
               params=None, rng=None):
    """온도장 → Planck → emissivity → 대기(τ·L+L_path) → detector → DN + 겉보기 ΔT + NETD.

    L_sensor = τ·(ε·L_bb(T) + (1-ε)·L_bb(T_amb)) + (1-τ)·L_bb(T_amb)(경로복사≈주변).
    핵심 결과: 사람(체온~308K) 대 배경(T_amb) 의 **열대비 ΔL** 가 안개서도 남는다 —
    LWIR τ 가 가시보다 크기 때문(lwir_extinction). [출처:조각]"""
    p = dict(netd_K=0.05, bits=14, span_K=40.0)
    if params:
        p.update(params)
    rng = rng or np.random.default_rng()
    beta = lwir_extinction(V); tau = math.exp(-beta * range_m)
    L_obj = emissivity * planck_band_radiance(T_scene) + (1 - emissivity) * planck_band_radiance(T_ambient)
    L_path = planck_band_radiance(T_ambient)
    L_sensor = tau * L_obj + (1 - tau) * L_path
    L_bg = tau * planck_band_radiance(T_ambient) + (1 - tau) * L_path
    # 겉보기 온도차(라디안스 차를 dL/dT 로 환산) — 탐지 가능성의 물리 지표
    dLdT = (planck_band_radiance(T_ambient + 0.5) - planck_band_radiance(T_ambient - 0.5))
    dT_app = (L_sensor - L_bg) / (dLdT + 1e-30)
    dT_app_noisy = dT_app + rng.normal(0, p["netd_K"])
    dn = int(np.clip((L_sensor / (planck_band_radiance(T_ambient + p["span_K"]) + 1e-30)) * (2 ** p["bits"] - 1),
                     0, 2 ** p["bits"] - 1))
    detect = abs(dT_app_noisy) > 3.0 * p["netd_K"]           # ΔT 가 NETD 의 3배 넘으면 탐지
    return {"DN": dn, "dT_apparent_K": float(dT_app_noisy), "netd_K": p["netd_K"],
            "tau_lwir": float(tau), "tau_visible": math.exp(-(3.912 / max(V, 1.0)) * range_m),
            "detectable": bool(detect)}


# ─────────────────────────────── LiDAR (DIRSIG waveform core) ───────────────────────────────
def lidar_return(true_range_m, reflectivity=0.3, V=20000.0, params=None, rng=None):
    """레이저 pulse*표적 임펄스 → 광자검출 → peak → TOF → range. 반환 range·σ_R·검출·광자수.

    P_r ∝ ρ·exp(-2βR)/R² (2β=왕복소광). photon=Poisson. σ_R ≈ c·t_pulse/(2·√SNR)(peak 지터). [출처:조각]"""
    p = dict(pulse_ns=5.0, tx_photons=1e9, bg_photons=50.0, det_eff=0.4, bits=12)
    if params:
        p.update(params)
    rng = rng or np.random.default_rng()
    beta = 3.912 / max(V, 1.0)                                # 안개 소광(가시 근처 파장)
    R = max(true_range_m, 1.0)
    Pr = p["tx_photons"] * reflectivity * math.exp(-2 * beta * R) / (R * R)
    sig = rng.poisson(max(0.0, Pr * p["det_eff"]))            # 신호 광자(shot)
    bg = rng.poisson(p["bg_photons"])                         # 배경광
    snr = sig / math.sqrt(sig + bg + 1e-9) if sig > 0 else 0.0
    t_pulse = p["pulse_ns"] * 1e-9
    sigma_R = C_LIGHT * t_pulse / (2.0 * math.sqrt(snr + 1e-9)) if snr > 0 else 1e9
    detect = snr >= 3.0                                       # peak 검출 임계
    R_meas = R + rng.normal(0, min(sigma_R, R)) if detect else float("nan")
    return {"range_m": float(R_meas), "sigma_R_m": float(sigma_R), "snr": float(snr),
            "photons": int(sig), "detectable": bool(detect)}


# ─────────────────────────────── IMU (IEEE Allan variance core) ───────────────────────────────
def imu_sample(true_a, true_w, t, state=None, dt=0.1, params=None, rng=None):
    """a_m=S·a+b+n, ω_m=S·ω+b+n. bias 는 Gauss-Markov(ḃ=-b/τ+w). Allan 성분(ARW·bias instab·RRW).

    state 로 bias 를 이어붙인다(시계열). 반환 측정 a/ω + bias + 위치불확실 성장 지표. [출처:조각]"""
    p = dict(arw=0.02, bias_instab=0.01, rrw=0.001, tau=100.0, scale_err=0.005, sigma_ss=9.0)
    if params:
        p.update(params)
    rng = rng or np.random.default_rng()
    st = state or {"ba": 0.0, "bg": 0.0}
    # Gauss-Markov bias 갱신
    st["ba"] += (-st["ba"] / p["tau"] + p["rrw"] * rng.standard_normal()) * dt
    st["bg"] += (-st["bg"] / p["tau"] + p["rrw"] * rng.standard_normal()) * dt
    a_m = (1 + p["scale_err"]) * true_a + st["ba"] + p["arw"] * rng.standard_normal() / math.sqrt(dt)
    w_m = (1 + p["scale_err"]) * true_w + st["bg"] + p["bias_instab"] * rng.standard_normal()
    # 위치 불확실도: 랜덤워크 성장 √t·ARW, 정상상태 sigma_ss 로 포화(GM)
    pos_sigma = p["sigma_ss"] * math.sqrt(max(0.0, 1.0 - math.exp(-2.0 * t / (p["tau"] * 0.55))))
    return {"a_meas": float(a_m), "w_meas": float(w_m), "bias_a": float(st["ba"]),
            "pos_sigma_m": float(pos_sigma), "state": st}


# ─────────────────────────────── GNSS (ESA signal/receiver core) ───────────────────────────────
def gnss_measure(env="open", n_sats=9, params=None, rng=None):
    """pseudorange→position. env(open/urban/canyon)로 가시위성·multipath·outage 를 바꾼다.

    position σ ≈ HDOP · UERE. multipath 는 도심서 bias 를 더한다. <4 위성이면 outage(해 없음).
    (전체 correlation/DLL·PLL 은 안 돌린다 — pseudorange→position 오차 chain 의 core.) [출처:조각]"""
    p = dict(uere_m=3.0, multipath_urban_m=8.0, multipath_canyon_m=20.0)
    if params:
        p.update(params)
    rng = rng or np.random.default_rng()
    vis = {"open": n_sats, "urban": max(0, n_sats - 4), "canyon": max(0, n_sats - 7)}[env]
    hdop = {"open": 1.0, "urban": 2.5, "canyon": 6.0}[env]
    mp = {"open": 0.0, "urban": p["multipath_urban_m"], "canyon": p["multipath_canyon_m"]}[env]
    if vis < 4:
        return {"available": False, "n_sats": vis, "pos_sigma_m": float("inf"), "env": env}
    sigma = hdop * p["uere_m"] + mp
    err = rng.normal(0, sigma, 2)
    return {"available": True, "n_sats": int(vis), "hdop": hdop, "pos_sigma_m": float(sigma),
            "east_err_m": float(err[0]), "north_err_m": float(err[1]), "env": env}


# ─────────────────────────────── Audio (Image Source RIR core) ───────────────────────────────
def audio_detect(source_xy, mic_xy, walls=None, source_db=65.0, wind_db=45.0, params=None, rng=None):
    """h(t)=Σ α_i/r_i δ(t-r_i/c)(직접+반사). 거리감쇠+바람잡음 → SNR·TDOA(마이크 배열 DOA).

    소리는 안개·수관·야간을 통과한다(광학과 다른 채널) — 사람이 부르는 소리 탐지용. [출처:조각]"""
    p = dict(alpha=0.6, c=343.0, n_mics=4, mic_spacing_m=0.3)
    if params:
        p.update(params)
    rng = rng or np.random.default_rng()
    sx, sy = source_xy; mx, my = mic_xy
    r0 = max(math.hypot(sx - mx, sy - my), 0.5)
    # 직접 경로 음압레벨: 구면확산 -6dB/거리배증 + 대기흡수(간이)
    level_db = source_db - 20.0 * math.log10(r0) - 0.005 * r0
    # 반사(image source): 벽마다 α/r 로 감쇠된 상(간이 1차 반사 합)
    refl = 0.0
    for (wx, wy) in (walls or []):
        rr = max(math.hypot(sx - wx, sy - wy) + math.hypot(wx - mx, wy - my), 1.0)
        refl += p["alpha"] / rr
    snr_db = level_db - wind_db
    detect = snr_db > 6.0
    # TDOA DOA(간이): 배열 기준 방위, 잡음으로 각오차
    doa = math.degrees(math.atan2(sy - my, sx - mx)) + (rng.normal(0, 5.0) if detect else 0.0)
    return {"snr_db": float(snr_db), "level_db": float(level_db), "reflections": float(refl),
            "doa_deg": float(doa), "detectable": bool(detect), "range_m": float(r0)}


# ─────────────────────────────── Sensor Model Specification ───────────────────────────────
SPEC = [
    # (센서, 참고모델, 입력물리량, 핵심방정식, 파라미터, noise, 환경변수, sampling/ADC, signal proc, raw format)
    ("RGB", "ISETCam 계열", "장면 radiance L(x,y,λ)",
     "N_e=∫E·QE·λ/hc dλ; shot~Poisson; read~N(0,σ); PRNU 곱성",
     "full_well·read_e·PRNU·dark_e·gain·bits", "shot·read·PRNU·dark",
     "fog(τ_vis)·illum·motion", "ADC bits", "Bayer→demosaic→WB→gamma→sRGB", "DN 격자→sRGB"),
    ("Thermal(LWIR)", "DIRSIG+MODTRAN", "표면온도 T·emissivity ε",
     "L_λ=2hc²/λ⁵/(e^{hc/λkT}-1); L_sensor=τ·εL+L_path", "NETD·span·bits·ε",
     "NETD·detector", "fog(τ_LWIR≪τ_vis)·T_amb·ΔT", "ADC bits", "DN→겉보기온도 ΔT", "DN 격자→radiometric"),
    ("LiDAR", "DIRSIG waveform", "range·reflectivity ρ",
     "P_r(t)=h_target*p(t); P_r∝ρe^{-2βR}/R²; R=ct/2", "pulse·tx_photons·det_eff",
     "background·shot·speckle", "fog(β)·ρ", "peak/threshold·TOF", "waveform→peak→TOF→range", "point cloud (R,θ,φ)→xyz"),
    ("IMU", "IEEE Allan variance", "true a·ω",
     "a_m=S·a+b+n; ḃ=-b/τ+w(Gauss-Markov)", "ARW·bias_instab·RRW·τ·scale",
     "ARW·bias·RRW·quant", "vibration·temp", "표본화(dt)", "적분→pos σ 성장", "샘플 a/ω + bias"),
    ("GNSS", "ESA signal/receiver", "위성기하·대기·multipath",
     "ρ=cτ; posσ≈HDOP·UERE(+multipath)", "UERE·multipath·HDOP",
     "thermal·multipath·outage", "urban·canyon(가시위성)", "acquisition→DLL/PLL", "correlation→pseudorange", "position fix + σ"),
    ("Audio", "Image Source(RIR)", "음원 s(t)·기하",
     "h(t)=Σ α_i/r_i δ(t-r_i/c); y=h*s+n", "α·c·n_mics·spacing",
     "wind·electronic", "wind·거리·반사면", "ADC", "RIR conv→SNR→TDOA DOA", "mic 신호 y[n] + DOA"),
]


def spec_md():
    L = ["# 센서 모델 Specification (radar 제외 — radar.py 소유)", ""]
    L.append("> 'truth+gaussian' 이 아니라 **생성 물리 + 신호처리 chain** 의 core. **상용 시뮬레이터"
             "(ISETCam·DIRSIG) 재현이 아님** — Level-2 reference. 파라미터는 문헌 대표값 [출처:조각]. 현장 validation 아님.")
    L.append("")
    L.append("| 센서 | 참고모델 | 입력 물리량 | 핵심 방정식 | 파라미터 | noise | 환경변수 | sampling/ADC | signal proc | raw format |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for row in SPEC:
        L.append("| " + " | ".join(row) + " |")
    L.append("")
    L.append("## 왜 이렇게 나누나 (사람 우선 UAV 정책의 근거)")
    L.append("- 환경 하나(안개·야간·수관·multipath)를 바꾸면 센서마다 raw→perception 이 다르게 무너진다.")
    L.append("- Thermal: LWIR τ 가 가시보다 커서(연기·박무·야간) 열대비 ΔT 가 남는다 — 단 **물방울 짙은 안개는 LWIR 도 먹는다(면역 아님)**.")
    L.append("- Audio: 소리는 광학과 다른 채널이라 수관·야간·안개를 통과 — 사람이 부르는 소리 탐지에 유효.")
    L.append("- GNSS: 도심·협곡에서 multipath·outage 로 무너진다 → IMU 추측항법으로 버틴다.")
    L.append("- 그래서 정책은 하나의 센서를 못 박지 않고 **환경별 정보품질로 센서를 고른다**(sensor_select).")
    L.append("")
    L.append("## 한계 (정직)")
    L.append("- 각 모델은 정의된 fidelity 의 core 다: RGB 는 full ISP 아님, GNSS 는 correlation/DLL·PLL 안 돌림,")
    L.append("  Audio 는 1차 반사 근사, LWIR 소광비는 대표값. 전부 [출처:조각], **현장 validation 아님**.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--spec", action="store_true")
    a, _ = ap.parse_known_args()
    if a.spec:
        print(spec_md()); raise SystemExit(0)
    # 간단 자기점검(수치 sanity)
    print("RGB DN(밝음):", rgb_raw(np.full((2, 2), 0.8))["snr"])
    print("Thermal 사람(308K) vs 배경(288K) 안개 V=40m:", thermal_dn(308.0, 288.0, V=40.0, range_m=180.0))
    print("LiDAR 180m ρ=0.3 안개 V=40:", lidar_return(180.0, 0.3, V=40.0)["detectable"])
    print("IMU t=60s pos σ:", imu_sample(0.1, 0.01, 60.0)["pos_sigma_m"])
    print("GNSS canyon:", gnss_measure("canyon"))
    print("Audio 사람 120m:", audio_detect((120.0, 0.0), (0.0, 0.0)))
