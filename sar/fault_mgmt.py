#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fault Management 루프 (NASA Systems Engineering / Fault Management Handbook).

NASA FM: 정상 운용을 방해하는 상태를 Detect → Diagnose → Identify → Respond → Recover → Re-plan.
이 모듈은 그 중 **Detect·Diagnose·Identify·Respond** 를 물리(sensors.py 출력)에서 판정한다.
Recover·Re-plan 은 실행기(assurance/scenario)가 행동으로 수행한다.

핵심(NASA 구분): 원인을 물리로 규명한다 -- '탐지 안 됨'이 아니라 '왜 안 되는가'
(대기 소광 βR? 광자한계 저조도? 화염 글레어? 하드웨어 무응답? 관성 드리프트?).
그리고 그 원인이 **회복 가능한가**(recoverable)를 함께 낸다 -> Robustness vs Resilience 를 가른다.
"""

RHO_OK, RHO_LOW, SIGMA_SAFE = 0.60, 0.25, 30.0


def diagnose(rho, det, sig, rgb_failed, imu_failed, R_sense, sigma_safe=SIGMA_SAFE):
    """물리 상태 -> FM 판정 dict.
      detect      : 결함 있나(bool)
      diagnose    : 원인(물리 근거 문자열)
      identify    : 분류 (nominal / critical-hw / noncap-hw / nav-uncertain / degraded-*)
      respond     : 대응 행동
      recoverable : 이 결함을 완화·회복할 길이 있나(True=Resilience 가능, False=안전 강등만)
    """
    # ── Detect ──
    fault = imu_failed or rgb_failed or (rho < RHO_LOW) or (sig >= sigma_safe)
    if not fault:
        return dict(detect=False, diagnose="센서 신뢰도 충분 ρ_rgb=%.2f (≥%.2f)" % (rho, RHO_OK),
                    identify="nominal", respond="정상 탐색(RGB 시각고정→IMU 보정)", recoverable=True)
    # ── Diagnose + Identify + Respond ──
    if imu_failed:
        return dict(detect=True, diagnose="IMU 하드웨어 무응답 → 관성 상태추정 불가",
                    identify="critical-hw", respond="**MRC: 즉시 제자리 체공/착륙**", recoverable=False)
    if rgb_failed:
        return dict(detect=True, diagnose="RGB 하드웨어 무응답 → 영상 없음(탐지·시각주행 불가)",
                    identify="noncap-hw", respond="**IMU 추측항법 복귀(RTL)**", recoverable=False)
    if sig >= sigma_safe:
        return dict(detect=True,
                    diagnose="관성항법 드리프트 σ_p=%.1fm ≥ 임계 %.0fm(무시각고정 지속)" % (sig, sigma_safe),
                    identify="nav-uncertain", respond="**MRC: 위치 불확실 → 복귀/체공**", recoverable=False)
    if det.get("glare", 0.0) >= 0.5:
        return dict(detect=True, diagnose="화염 글레어 포화(글레어=%.2f) → 국소 실명" % det["glare"],
                    identify="degraded-recoverable", respond="화점 회피 후 재접근", recoverable=True)
    if det.get("rho_illum", 1.0) < 0.40:
        return dict(detect=True, diagnose="저조도 광자한계(조도 SNR 급락) → RGB 탐지 불가",
                    identify="degraded-env",
                    respond="주간 대기·IMU 항법 유지(야간 탐지는 열화상 필요)", recoverable=True)
    # 대기 소광(안개/연기/강우 산란)
    od = det.get("beta", 0.0) * R_sense
    return dict(detect=True,
                diagnose="대기 소광 광학깊이 βR=%.1f (β=%.4f/m, T=%.1e<대비문턱)" % (od, det.get("beta", 0.0), det.get("T", 0.0)),
                identify="degraded-recoverable",
                respond="감속·체공(저하) 또는 고지대 상승(안개 역전층 탈출)", recoverable=True)
