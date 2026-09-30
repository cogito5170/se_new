#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""센서 reliability 물리 모델 (RGB + IMU baseline). NHTSA ADS: OEDR + fallback/MRC.

'센서 reliability' = 그 조건에서 센서가 **물리적으로 쓸 정보를 주느냐** (하드웨어 강건성 아님).
모든 값은 아래 물리로 계산된다 -- 로그의 수치는 지어낸 것이 아니라 이 함수들의 출력이다.

물리 근거:
  · Beer-Lambert 소광:  투과율 T(R)=exp(-βR),  β=소광계수[1/m]
  · Koschmieder 가시거리: β = 3.912 / V   (대비문턱 0.02 에서 정의된 기상 가시거리 V[m])
  · 대비 전달:          장면 대비 C0 가 거리 R 뒤 C=C0·T. C<C_min 이면 표적이 배경과 안 갈림
  · 광자한계 SNR(야간):  검출 SNR ∝ √(조도). 저조도서 SNR 급락 (shot noise 한계)
  · 화염 글레어:        고휘도 화염이 센서를 국소 포화(blooming) -> 그 방향 실명
  · IMU 드리프트:       시각고정 없으면 가속도 바이어스 b 가 위치오차를 σ_p≈½·b·t² 로 키운다
                        (MEMS b~0.02 m/s²). 시각-관성 융합(VIO) 고정이 있으면 σ_p 재설정.
"""
import math

# ── 조건별 물리 파라미터 범위 (수리물리학적 근거) ──────────────────────────
#   V   = 기상 가시거리[m] 범위        lux = 장면 조도[lux] 범위
#   glare = 화염 글레어 계수[0..1]     설명 = 물리 출처
COND_PHYS = {
    "정상":   dict(V=(15000, 25000), lux=(8000, 20000),  glare=0.0,
                  설명="맑은 대기 β≈2e-4/m, 주간 조도"),
    "야간":   dict(V=(8000, 20000),  lux=(0.003, 0.3),   glare=0.0,
                  설명="달빛~흐린밤 0.003–0.3 lux, 광자한계 SNR 급락"),
    "안개":   dict(V=(40, 400),      lux=(2000, 9000),   glare=0.0,
                  설명="안개방울 β=3.912/V, V=40–400m (짙은~옅은 안개)"),
    "연기":   dict(V=(20, 300),      lux=(400, 5000),    glare=0.10,
                  설명="연소 에어로졸 고소광 β=0.013–0.2/m, 태양 차폐"),
    "화재":   dict(V=(30, 400),      lux=(1000, 8000),   glare=0.65,
                  설명="화염 글레어(포화)+연기, 화점 근처 국소 실명"),
    "먼지":   dict(V=(200, 2000),    lux=(1500, 8000),   glare=0.0,
                  설명="광물 먼지 β=0.002–0.02/m"),
    "비":     dict(V=(500, 4000),    lux=(1500, 7000),   glare=0.0,
                  설명="강우 방울 산란 β=0.001–0.008/m + 렌즈 물방울"),
    "센서고장": dict(V=(15000, 25000), lux=(8000, 20000),  glare=0.0,
                  설명="RGB 또는 IMU 중 하나가 죽는다(무작위)"),
}
C_MIN = 0.02        # 대비 검출 문턱 (Koschmieder 와 같은 값)
LUX_MIN, LUX_DAY = 0.01, 1.0e4
A_BIAS = 0.02       # IMU 가속도 바이어스[m/s²] (보정 안 된 MEMS)
SIGMA_FIX = 0.5     # VIO 시각고정 후 위치 잔차[m]


def beta_from_visibility(V_m):
    """기상 가시거리 V[m] -> 소광계수 β[1/m]. Koschmieder(대비문턱 0.02)."""
    return 3.912 / max(1.0, V_m)


def transmittance(beta, R_m):
    """Beer-Lambert 투과율 T=exp(-βR)."""
    return math.exp(-beta * R_m)


def rgb_reliability(beta, R_m, lux, glare, C0=1.0):
    """RGB 탐지 신뢰도 ρ∈[0,1] = 대기대비전달 × 조도SNR × (1-글레어). 전부 물리계산.
    반환: (ρ, 상세dict)  -- 상세는 로그에 그대로 찍을 중간 물리량."""
    T = transmittance(beta, R_m)                 # 투과율
    C = C0 * T                                   # 거리 R 뒤 남은 대비
    rho_atmos = max(0.0, (C - C_MIN) / (1.0 - C_MIN))
    # 야간 조도: √SNR 을 log 조도로 매핑 (shot-noise 한계)
    lg = math.log10(max(lux, 1e-4))
    rho_illum = min(1.0, max(0.0, (lg - math.log10(LUX_MIN)) /
                             (math.log10(LUX_DAY) - math.log10(LUX_MIN))))
    rho = max(0.0, rho_atmos * rho_illum * (1.0 - glare))
    return rho, dict(beta=beta, T=T, C=C, rho_atmos=rho_atmos, rho_illum=rho_illum, glare=glare)


def imu_sigma(t_since_fix_s, a_bias=A_BIAS):
    """시각고정 이후 경과 t[s] -> 관성항법 위치오차 σ_p[m] ≈ ½·b·t² (가속도 바이어스 이중적분)."""
    return 0.5 * a_bias * (t_since_fix_s ** 2)


def local_beta(base_beta, elev_m, fire_dist_cells, condition, inversion_h=900.0):
    """3D 지형 결합: 안개는 저지대(역전층 아래)에 두껍게, 연기·화재는 화점 근처에 짙게.
    같은 조건이라도 **어디 있느냐**로 소광이 달라진다 -> 고지대로 오르면 안개를 벗어난다."""
    b = base_beta
    if condition == "안개":
        # 역전층 아래일수록 두껍다. 위로 오르면 옅어진다(물리: 안개는 층운, 상한고도 존재).
        if elev_m < inversion_h:
            b *= (1.0 + 1.5 * (inversion_h - elev_m) / inversion_h)
        else:
            b *= 0.15
    elif condition in ("연기", "화재"):
        # 화점 근처일수록 짙다(연기 기둥). 멀면 옅다.
        b *= (1.0 + 3.0 * math.exp(-max(0.0, fire_dist_cells) / 4.0))
    return b


def sample_scenario(rng, condition):
    """조건 이름 -> 이 실행의 구체 물리 파라미터(무작위 강도) + 고장 여부."""
    p = COND_PHYS[condition]
    V = rng.uniform(*p["V"]); lux = 10.0 ** rng.uniform(math.log10(p["lux"][0]), math.log10(p["lux"][1]))
    sc = dict(condition=condition, V=V, lux=lux, glare=p["glare"], 설명=p["설명"],
              rgb_failed=False, imu_failed=False)
    if condition == "센서고장":
        if rng.random() < 0.5:
            sc["rgb_failed"] = True; sc["고장"] = "RGB"
        else:
            sc["imu_failed"] = True; sc["고장"] = "IMU"
    return sc
