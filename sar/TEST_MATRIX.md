# NASA V&V 테스트 매트릭스 — UAV 자율탐색 시나리오 재구성

NASA SE Handbook 의 V&V 사고방식으로 시나리오를 **평평한 (장소·날씨·인원)**에서
**직교 축의 구조 + 시나리오 ID + 상태전이 결함주입 + V&V 근거**로 재구성한다(`sar/scn.py`).

## NASA 근거

- **Verification vs Validation** (SE Handbook): "요구대로 만들었나" vs "의도한 운용 시나리오에서
  실제로 작동하나". Validation 은 규정 환경 또는 relevant environment 에서 operational scenario 로.
- **불확실성→의사결정→위험→테스트 시나리오** (*Reliability-Aware Requirements ...*, NTRS 20230007020):
  자율 시스템은 모든 시나리오를 사람이 못 적으므로 decision·uncertainty·risk 에서 시나리오를 만든다.
- **상태 전이 전/중/후 결함 주입** (*Automated Generation ... Test Cases*, NTRS 20090035797):
  state change 직전·순간·도중·직후에 anomaly 를 넣어 coverage gap 을 줄인다.
- **Reliability/Robustness/Resilience 구분** (Jones, NTRS 20205010168): 평가축.

(위 문서는 사용자가 제시한 NTRS 인용 — 원문 전문 재열람 안 함 `[출처:조각]`.)

## ConOps → Requirement → Scenario → Outcome

```
ConOps: "산악 조난자 탐색 UAV. 센서가 열화·고장해도 안전을 잃지 않는다."
  → Requirement: (R1)규정 환경서 탐지, (R2)예상 off-nominal서 기능/안전 유지, (R3)예상못한 사건서 복구/안전강등
  → Operational Scenario = 아래 직교 축의 한 조합(=시나리오 ID)
  → Environment/Uncertainty/Fault → Autonomy(policy_core) → Path/Control → Outcome → V&V 판정
```

## 직교 축 (구조화 시나리오)

| 축 | 값 | 물리 매핑 |
|---|---|---|
| **Geometry** | open / cluttered / confined | 지형 LOS 차폐(DEM 능선). confined 일수록 능선 뒤 차폐↑ |
| **Visibility** | normal / degraded / intermittent | 대기: 정상 / 먼지·박무(β↑) / **안개 급습**(간헐) |
| **Disturbance** | none / wind / sensor_noise | 바람→IMU 드리프트 계수↑ / 탐지 reliability 에 측정잡음 |
| **Sensor** | nominal / degraded / faulted | 정상 / ρ_rgb 상한 저하(노후) / **시작부터 RGB 고장** |
| **Fault(+타이밍)** | RGB_FAIL·IMU_FAIL·FOG @ at_start·at_first_detect·during_replan | **상태 전이 지점**에 예상못한 결함 주입 |

각 조합에 **시나리오 ID**(`SCN-REL/ROB/RES-nnn`)를 붙이고 기대행동·측정·판정을 함께 관리한다.

## 3계층 매트릭스 (`build_matrix`)

- **Reliability(REL)**: 전부 nominal. 규정 환경 baseline. 기대=임무 성공.
- **Robustness(ROB)**: 한 축씩 off-nominal(+복합 2건). 기대=탐지 유지 또는 안전강등.
- **Resilience(RES)**: 상태 전이 지점에 결함 주입(RGB/IMU 소실·안개 급습 × 3 타이밍). 기대=복구 또는 안전강등.

## V&V 판정 (`verdict`)

| 판정 | 뜻 |
|---|---|
| PASS(전원/탐지/복구) | 임무 달성 또는 사건 후 탐지 복구 |
| DEGRADED-SAFE | 탐지는 못 해도 **안전하게 강등**(RTL/MRC) — 손실 없음 |
| FAIL | unsafe(설계상 없음) 또는 규정 환경 미탐 |

## 실측 (예: 오대산 실 DEM, reps=8/SCN) — `out/testmatrix.png`

- **Reliability**: 3/3 PASS(전원) — 규정 환경 임무 달성.
- **Robustness**: 10 중 PASS(탐지) 5 / DEGRADED-SAFE 5. cluttered·confined·wind·잡음·노후센서는 탐지 유지,
  간헐 안개·시작-RGB고장·복합악조건은 안전강등.
- **Resilience**: 9 중 PASS(복구) 2~3 / DEGRADED-SAFE 6~7. **안개 급습은 FM 이 상승·재계획으로 복구**,
  하드웨어 소실은 안전강등. **전이 타이밍이 결과를 가른다**(RGB_FAIL@at_start=미탐 vs @first_detect=1명 확보 후 복귀).

> 어떤 SCN 도 unsafe 가 없다(RTA/MRC 설계). 야간·짙은 소광·confined 차폐에서 탐지 급감은
> 숨기지 않는다 — 이것이 **열화상 보강**의 정량 근거다(다음 실험: 열화상 추가 후 매트릭스 재측정).
