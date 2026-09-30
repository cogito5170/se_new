# NASA 자율시스템 보증 프레임 — 우리 SAR policy 에의 적용

NASA 는 이 문제를 한 권 매뉴얼이 아니라 **여러 문서를 연결한 시스템공학 체계**로 다룬다.
그 4계층을 우리 RGB+IMU SAR 시스템에 그대로 매핑한다.

| 계층 | NASA 문서 | 우리 코드 |
|---|---|---|
| ① System Architecture | *Principles for Architecting Autonomous Systems* (NTRS 20230005685) | `policy_core/`(Sense→Plan→Act 결정층) + `sar/`(perception·terrain) |
| ② Exploration / Decision under uncertainty | *Reliability-Aware Requirements Development for Autonomy Software* (NTRS 20230007020) | `scenario_run.py`(belief·정책 결정), `sensors.py`(불확실성=물리 reliability) |
| ③ Reliability / Robustness / Resilience | *Going Beyond Reliability to Robustness and Resilience* (NTRS 20205010168) | `assurance.py`(3축 평가) |
| ④ Fault / Recovery | *NASA SE Handbook + Fault Management Handbook* | `fault_mgmt.py`(Detect→Diagnose→Identify→Respond) + 실행기(Recover→Re-plan) |

(위 문서는 사용자가 제시한 NTRS 인용 — 이 저장소에서 원문 전문을 재열람하지 않음 `[출처:조각]`.)

## 세 축의 구분 (NASA Jones) — 우리 정의·측정

| 축 | NASA 정의 | 우리 측정(`assurance.py`) |
|---|---|---|
| **Reliability** | 규정된(nominal) 환경에서 요구 만족 | 정상 조건 전원-확인률 (실측 ~85%) |
| **Robustness** | **예상된** off-nominal(야간·안개·비…)에서도 유지 | 8조건 정지 실행, ≥1명 탐지·안전률 |
| **Resilience** | **예상 못 한** 사건 후 적응·복구 | 임무 중 사건 주입(안개 급습·RGB/IMU 소실) 후 회복·안전강등률 |

핵심: Robustness 는 **시작부터 알려진** 나쁜 조건, Resilience 는 **임무 중 예상 못 하게** 닥친 사건.
그래서 Resilience 는 정상으로 시작해 중간에 주입하고, **회복(탐지 재개) vs 안전 강등**을 가른다.

## Fault Management 루프 (`fault_mgmt.diagnose`)

```
Detect    : ρ_rgb<0.25 or σ_p≥30m or 센서 무응답  (물리로 감지)
Diagnose  : 왜? 대기 소광 βR / 저조도 광자한계 / 화염 글레어 / HW 무응답 / 관성 드리프트
Identify  : nominal · critical-hw · noncap-hw · nav-uncertain · degraded-(env/recoverable)
Respond   : 정상 / 감속 / 고지대 상승 / 추측항법 / RTL / MRC
Recover   : (회복 가능이면) 상승해 역전층 탈출 -> ρ_rgb 복원                [실행기]
Re-plan   : 복원되면 belief 기반 탐색 재개                                  [실행기]
```
'탐지 안 됨'이 아니라 **원인을 물리로 규명**하고, 그 원인이 **회복 가능한지**를 낸다 —
이것이 Robustness(견딤)와 Resilience(복구)를 코드에서 가르는 분기점이다.

## 실측 요약 (`python3 sar/assurance.py`, 그림 `out/assurance.png`)

- **① Reliability**: 정상 ~85% 전원확인 — 규정 환경 요구 달성.
- **② Robustness**: 비 ~80%·먼지 ~25% 탐지, **야간·안개·연기·화재 ≈0% 탐지**이나 **안전(fallback) 100%**.
  → 정직한 baseline 한계: RGB 는 어둠·짙은 소광에서 정보를 못 준다(열화상 보강 필요).
- **③ Resilience**: 안개 급습은 FM 이 **상승·재계획으로 탐지 되살림(~38%)**, 하드웨어 소실은
  회복 불가하나 **안전 강등 100%**(RTL/MRC).

> 정직: 모든 수치는 `sensors.py` 물리 + 실 DEM 에서 계산된 것이며, baseline(RGB+IMU)의 한계를
> 숨기지 않는다. 이 한계(야간·소광 탐지)가 다음 센서(열화상) 추가의 정량적 근거가 된다.
