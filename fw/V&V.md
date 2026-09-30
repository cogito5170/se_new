# fw V&V 구조 — NASA Verification/Validation/IV&V 틀에 매핑

이 세션의 fw 작업(#440~#449)을 NASA 소프트웨어 V&V 철학에 맞춰 정리한다. 목적은 "실험했으니 현장도
된다"는 **논리 점프를 차단**하는 것: **Verification(요구대로 만들었나) ≠ Validation(실제 의도 환경에서
옳은 것을 만들었나)**. 전거는 NPR 7150.2 · NASA-STD-8739.8B · SWEHB · JPL M&S 사례들이며 전문 미열람
이라 전부 `[출처:조각]`(문서 끝 목록).

## 1. 작업 ↔ NASA 개념 매핑

| 이 저장소 작업 | NASA 개념 |
|---|---|
| `policies.cmpc_confirm`·`fw/*.c` 규칙 검증 | Verification |
| replay / fault injection (`fault_test.c`, `cmpc_vv`) | requirements-based / off-nominal verification |
| `fw/evidence.c` 등 bare-metal 이식 | implementation |
| 이식본에 동일 테스트 재실행 | software verification |
| target platform / high-fidelity simulation | Validation |
| 실제 현장·운용환경 | operational validation |
| 못 막은 fault 를 gap 으로 기록 | evidence-based risk/gap |
| `n_ep` 한계 명시 | evidence limitation / uncertainty |
| decoy·liveness·clutter 대표 물리 | model/simulation assumption |
| "현장 검증 아님" 명시 | validation boundary |
| 요구↔테스트↔결과 연결 | bidirectional traceability |
| 검증 하네스를 구현 코드와 분리 | IV&V 에 가까운 구조 |

## 2. 3D/시뮬레이션은 "시각화"가 아니라 검증 환경의 일부

NASA(JPL M&S, ROAMS, ALHAT, SPLICE, Mars2020 TRN)는 terrain·dynamics·sensor·actuator·SW 를 하나의
통합 모델에 넣고 **closed-loop** 로 onboard SW 를 반복 시험한다. 즉 3D scene 은 **Ground Truth
generator + Sensor Simulator + Scenario Generator** 다 `[출처:조각]`.

SE 의 `sar/` 는 이미 그 역할을 한다(그림용 렌더가 아니다):

```
DEM(terrain.fetch_dem, 실측) + landcover(ESA WorldCover) + scene 재질
        ↓  ground truth(숨은 표적·decoy·liveness)
물리 센서 모델(sensors_ref: Planck·Koschmieder·LiDAR·GNSS·Audio)
        ↓  synthetic sensor observation
fusion(CMPC) → state estimate(KF) → policy/FDIR → action
        ↓
(현재 nav 는 belief 추종; dynamics 는 간이)  ↺  다시 관측
```

**sar 는 심판(reference truth + evaluator)이고 fw 는 선수** — 이 분리 자체가 IV&V 사고의 핵심.

## 3. Fidelity ladder — SE 는 지금 어디에 있나 (verification/validation 경계)

| Level | 3D/센서 환경 | 의미 | SE 현재 |
|---|---|---|---|
| L0 | primitive | policy debug | host_test(합성 obs) |
| L1 | procedural terrain | Monte Carlo | 합성 DEM 스윕 |
| **L2** | **실측 DEM + landcover + 물리 센서모델** | **sensor simulation** | **← 지금 여기(sar held-out 지리산)** |
| L3 | DEM + 실제 imagery + 검증 조명 | high-fidelity sim | 미도달 |
| L4 | 실제 terrain + 실제 센서 | field validation | 미도달 |
| L5 | 실제 platform+센서+SW | system validation | 미도달 |

**경계:** L0~L2 에서 얻은 모든 수치(#440~#449)는 **Verification evidence** 다. **Validation 은 L3+**
(실 imagery·조명·target platform HITL·현장 비행)에서 별도로 얻어야 하며 **아직 없다**. NASA TRN/
Mars2020 도 고품질 sim 으로 끝내지 않고 field·HITL·flight 시험을 병행했다 `[출처:조각]`.

```
[VERIFICATION]  synthetic 3D env (L0–L2)        ≠   [VALIDATION]  real (L3–L5)
- 대표 terrain/센서·명시된 물리 가정                 - 실 terrain·실 센서·대표 고도
- Monte Carlo / replay / fault injection            - 실 조명/기상·현장/비행 시험
```

또한 NPR 7150.2 는 **model/sim/tool 자체도 V&V 대상**이라 한다 `[출처:조각]`. SE 의 센서·decoy·
liveness 모델은 대표 물리이며 **모델 V&V 미수행** — synthetic 조건이 현장을 대표한다는 주장은 안 한다.

## 4. Evidence 4분리 원칙 (모든 fw 측정에 적용)

측정을 보고할 때 **Verification evidence / Validation evidence / Assumption / Gap** 넷으로 나눈다.
예시는 `fw/CMPC_관측가능성.md`(#449)와 `fw/경계지도.md`(#448)에 적용돼 있다. 요지: 확보한 것과
미확보(validation)·가정·못 막은 것(risk)을 섞지 않는다.

## 5. IV&V 독립성 (조직 아닌 구조로 근사)

NASA-STD-8739.8B 는 IV&V 를 technical/managerial/financial 독립으로 본다 `[출처:조각]`. SE 는 조직적
IV&V 는 아니지만 **검증 경로를 구현과 분리**해 근사한다:

```
개발: policies.cmpc_confirm · fw/*.c
   ↓
독립 하네스: cmpc_vv · fault_test · test_* (replay·fault injection, raw logs+metrics)
   ↓
결론: expected vs observed 를 evidence 로 (개발자 주장 아님)
```

## 6. Traceability (요구↔구현↔시험↔증거↔이식↔validation)

각 요구를 ID 로 잡고 구현·시험·증거·validation 까지 양방향으로 잇는다. CMPC(#449)는
`CMPC_관측가능성.md` 의 R/P/T/E/FW/V-FIELD 표. **FDIR(#447)** 도 같은 꼴로 채운다:

| ID | 요구/항목 | 상태 | 근거물 |
|---|---|---|---|
| R-FDIR-001 | 센서 고장(health↓)은 **감지·격리**되고 임무는 남은 센서로 계속 | ✓ | fault_test [2] |
| R-FDIR-002 | 과불확실 추적(공분산 폭발)엔 **행동하지 않는다** | ✓ | fault_test [3] |
| R-FDIR-003 | 상태 오염(planner)에서 **유효 상태로 복구** | ✓ | fault_test [4] |
| R-FDIR-004 | 구동계 고장 시 **안전 정지** | ✓ | fault_test [5] |
| R-FDIR-005 | 기록 장면 재생은 **결정적**(동일 입력→동일 행동) | ✓ | fault_test [1] |
| P-FDIR | 구현 | ✓ | `fw/safety.c`·`evidence.c`(sigma guard)·`event.c` |
| T-FDIR | off-nominal 시험 | ✓ | `fw/fault_test.c` · `tests/test_fw_fault.py` |
| E-FDIR | objective evidence | ✓ | fault_test 출력(막은 것/못 막은 것) |
| **GAP-FDIR-001** | stale/stuck·bias 센서는 **못 거른다**(정지·일관 가짜) | 기록됨 | fault_test [6] · #448/#449 gap |
| V-FIELD-FDIR | target/현장 fault 주입 validation | ○ 후속 | — |

정직: R-FDIR-001~005 는 verification(L0–L2) 확보, GAP-FDIR-001 은 **주장 아닌 식별된 risk** 로
남긴다(개발자가 "다 막았다"고 하지 않는다 — NASA IV&V 의 evidence/risk 원칙). V-FIELD 는 미확보.

## 정직 / [출처:조각] (전문 미열람, 전거 목록)

- NPR 7150.2 (NASA Software Engineering Requirements) — V/V 구분, model/sim/tool V&V, bidirectional
  traceability, high-fidelity sim(동일 processor/timing/memory/interface) validation.
- NASA-STD-8739.8B (Software Assurance & Software Safety) — IV&V 독립성, off-nominal/fault·hazard
  response 를 objective evidence 로 평가.
- NASA SWE Handbook (SWEHB) — 위 해설.
- JPL Robotics M&S · ROAMS · ALHAT · SPLICE · Mars2020 TRN · "Building Maps for TRN Using Blender"
  (NTRS) · ATRN(NTRS) — 3D terrain→센서→SW closed-loop, virtual+physical testbed 병행, field/HITL/
  flight 시험 병행.

이 문서는 사용자(2인)가 제공한 위 전거 요약에 기반한다. 링크는 봤으나 **원문 전문은 미열람**이므로
전부 `[출처:조각]`. SE 의 현재 위치(L2·Verification)와 미확보(Validation)를 섞지 않는 것이 이 문서의 목적.
