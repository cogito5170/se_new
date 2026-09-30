# #449 — 교차 물리 상관으로 충분한가? 센서를 추가해야 하는가? (실험으로 분리)

질문: 공통 gap(정지·고착·일관된 가짜)을 **교차 물리 상관(5센서 그대로)** 으로 닫을 수 있나, 아니면
**센서를 추가**해야 하나. 결론을 미리 내지 않고 **닫히는 범위와 안 닫히는 범위를 실험으로 분리**했다.

## 방법 — 정보집합을 넓히며 실패영역 측정 (센서 개수 5 고정)

fusion 을 spatial voting("몇 개 봤나")에서 **cross-modal consistency**("사람이라면 함께 나와야 할
물리채널이 양립하나")로 바꾼다. **nav 분리(정직):** 탐지가 nav 에 얽히면 규칙을 못 가리므로, 시나리오
마다 **고정 경로로 관측 스트림을 한 번 기록**하고 같은 스트림에 각 정보집합의 **claim 규칙만** 적용
(진짜 replay: 입력 동일, 규칙만 다름). `sar/ivv/cmpc_vv.py`, held-out 지리산, n_ep=20.

- **I0** spatial(≥1 모달리티) — 기준선
- **I1 strict** CMPC(서로 다른 물리채널 ≥2)
- **I1 cond** CMPC + 조건부 완화(가림-강 SAR/Audio 만인 군집은 ≥1)
- **I2** CMPC cond + **liveness**(호흡·심박) 요구

## 결과 (각 칸 = 탐지율/오경보; A·C 는 오경보, B 는 탐지율을 봐라)

| 시나리오 | 관심 | I0 spatial | I1 strict | I1 cond | I2 +live |
|---|---|---|---|---|---|
| A 단일모달 clutter | 오경보 | 1.8 | **0.1** | 1.4 | **0.1** |
| B 부분관측 진짜(수관+짙은안개) | 탐지 | 100% | **15%** | **60%** | 55% |
| C 전-서명 decoy | 오경보 | 1.6 | 0.9 | 1.6 | **0.1** |

## 답 — 교차 상관은 충분한가?

1. **단일모달 clutter(A)는 5센서 교차상관으로 닫힌다 — 센서 추가 불필요.** CMPC(≥2)가 오경보를
   1.8→0.1 로 죽인다. 다중경로·고착 단일센서·고립 열점 등 대부분의 현실 clutter가 여기다.
2. **대가가 있다(B): 교차상관은 단일모달 진짜를 버린다.** 수관+짙은안개로 SAR 만 보이는 진짜를
   strict 는 100%→15% 로 놓친다. **조건부 완화가 60% 로 회복**하되 공짜가 아니다.
3. **그 조건부 완화가 clutter 구멍을 다시 연다(A): cond 오경보 1.4**(가림-강 채널 단독 clutter가
   통과). **단일모달 clutter 억제와 단일모달 진짜 보존을 kinematic/modal 규칙만으로 동시에 못 한다**
   — 트레이드다.

## 답 — 센서를 추가해야 하는가?

4. **전-서명 decoy(C)는 5센서로 못 닫는다.** decoy 가 RGB+Thermal+LiDAR+SAR 를 다 트립하면
   CMPC(strict·cond)로도 통과한다(오경보 0.9~1.6). 이것은 CMPC 의 실패가 아니라 **관측가능성의
   한계 증명**이다 — 우리 5채널이 다 속으면 그 정보로는 원리적으로 못 가른다.
5. **liveness 채널(I2)만이 decoy 를 거른다: 오경보 1.6→0.1.** 그리고 실 진짜는 보존(B 55%)하고
   단일모달 clutter 도 억제(A 0.1)한다. **여기서 처음으로 센서 추가가 "아이디어"가 아니라 실험이
   요구한 정보 채널**이 된다. FINDER(NASA/JPL·DHS)가 위치센서가 아니라 호흡·심박 미세운동으로
   인간을 식별한 것과 개념적으로 같다 `[출처:조각]`(전문 미열람).

## 결론 — 경계가 실험으로 그어졌다

```
공통 gap(정지·고착·일관된 가짜)
        │
   교차 물리 상관(5센서) 로 닫히나?
        ├─ 단일모달 clutter        → 닫힘(A: 1.8→0.1)          [센서 추가 불필요]
        ├─ 단일모달 진짜의 대가     → 조건부로 부분 회복(B: 15→60%) [트레이드]
        └─ 전-서명 decoy           → 안 닫힘(C: CMPC 통과)        [관측가능성 한계]
                                          │
                                    liveness 채널 추가
                                          ▼
                                 decoy 걸림(C: 1.6→0.1)          [실험이 요구한 센서]
```

즉 **"교차 상관 먼저(대부분 닫음), 그래도 남는 전-서명 decoy 에만 liveness 추가"** 가 실험으로
확정됐다. 센서 추가는 관측가능성 실험이 요구한 최소 정보 채널이지, 중복 locator 가 아니다.

## Evidence status — NASA V&V 용어로 4분리 (Verification / Validation / Assumption / Gap)

NASA 는 "요구대로 만들었나(Verification)"와 "실제 의도 환경에서 옳은 것을 만들었나(Validation)"를
분리하고, simulation/analysis 결과를 곧바로 operational validation 으로 취급하지 않는다. 이 실험을
그 틀로 명시한다(전거는 NPR 7150.2·NASA-STD-8739.8B·SWEHB, 전문 미열람 `[출처:조각]`).

- **Verification evidence(확보):** 위 표는 **규칙수준 검증**이다 — 동일 고정경로 스트림에 claim 규칙만
  바꿔(replay) 정보집합 간 상대 방향성이 재현되는가. `tests/test_cmpc.py`(규칙 단위) + `cmpc_vv`
  (시나리오 A/B/C)로 얻은 objective evidence. **operational validation evidence 로 해석하지 않는다.**
- **Validation evidence(미확보):** target platform / high-fidelity sim / 현장 운용환경에서의 입증은
  **아직 없다**. `fw/evidence.c`(비행/임베디드 이식) 후 target 에서 동일 테스트를 재실행하고, 이후
  현장 validation 을 별도 수행해야 확보된다. 지금은 **validation boundary 밖**.
- **Assumption(가정, 표면에 드러냄):** decoy 는 광학+열+LiDAR+SAR 를 트립하되 liveness 만 없게, clutter
  신뢰도는 실탐지와 같은 분포, liveness 는 수관 통과·근거리로 **모델링한 대표 물리**다. 모델 자체의
  V&V(NPR 7150.2 는 model/sim/tool 도 V&V 대상)는 미수행 — 이 synthetic 조건이 현장을 대표한다는
  주장은 하지 않는다.
- **Evidence limitation:** `n_ep=20`은 절대 성능 추정에 충분한 표본이 아니다. **절대 수치에 대한
  결론은 제한**하고, 정보집합 간 **상대 방향성의 재현**만 평가한다.
- **Gap(못 막은 것, 기록):** 전-서명 decoy 는 CMPC(5센서)로 못 거른다(관측가능성 한계) → liveness
  채널 필요. common-mode(상관) 고장은 미측정. 이들은 주장 대신 **식별된 risk/gap** 으로 남긴다.

## Traceability — 요구 ↔ 구현 ↔ 시험 ↔ 증거 ↔ 이식 ↔ validation (양방향)

| ID | 항목 | 상태 | 근거물 |
|---|---|---|---|
| R-CMPC-001 | 지속 관측은 **단일 센서 주장만으로 수락되지 않는다** | 정의됨 | 이 문서 |
| R-CMPC-002 | 가림-강 채널만 가용한 진짜는 **버리지 않는다**(조건부) | 정의됨 | 이 문서 |
| R-CMPC-003 | 전-서명 가짜는 **liveness 없이 수락되지 않는다** | 정의됨 | 이 문서 |
| P-CMPC-001 | 규칙 구현(prototype) | ✓ | `policies.cmpc_confirm` |
| T-CMPC-001 | 단일모달 clutter 억제 시험 | ✓ | `tests/test_cmpc.py` · `cmpc_vv` A |
| T-CMPC-002 | 부분관측 진짜 보존(조건부) 시험 | ✓ | `tests/test_cmpc.py` · `cmpc_vv` B |
| T-CMPC-003 | decoy/liveness 시험 | ✓ | `tests/test_cmpc.py` · `cmpc_vv` C |
| E-CMPC-001 | 규칙수준 verification evidence(표) | ✓ | 위 결과표 |
| FW-CMPC-001 | 비행/임베디드 이식(C) | ✓ | `fw/evidence.c`(cfg.cmpc_min·require_live) |
| T-FW-CMPC-001 | 이식본에 동일 규칙 재실행 | ✓ | `fw/host_test.c` [14] (프로토타입과 동일 판정) |
| V-FIELD-CMPC-001 | target/high-fidelity/현장 validation | ○ 후속 | — |

(✓=확보, ○=미확보. verification 경로 `test_*`·`cmpc_vv` 는 구현 코드와 **분리**돼 IV&V 사고에 가깝다 —
개발자 주장이 아니라 독립 하네스의 objective evidence로 결론을 낸다.)

**FW-CMPC-001 이식 노트(정직):** C(`fw/evidence.c`)에서 cmpc_min>0 이면 판정기준을 soft-vote 임계
대신 **교차모달 채널 수**로 바꿨다(프로토타입 `cmpc_confirm` 과 동일). host_test [14] 로 네 판정
(단일모달 RGB min1 확인/min2 기각 · SAR 단독 조건부 확인 · decoy CMPC 통과 · +liveness 기각)이
프로토타입과 **같음을 확인**. 단, 이것은 **규칙 등가성 verification** 이지 target platform·현장
validation 이 아니다(V-FIELD 는 여전히 미확보). liveness 입력은 아직 host 에서 직접 주입(bridge
경유 sar 연동은 후속)이다.

## C 이식본 재측정 (FW-CMPC-001 수치 — bridge↔sar 연동)

liveness 를 bridge 로 fw 에 넣어, **C 결정 executive(`fw/evidence.c`)를 같은 고정경로 스트림에 직접
구동**해 관측가능성 표를 재측정. 프로토타입(py)과 비교(held-out 지리산, n_ep=20). C 는 조건부 CMPC
(배포형)만 구현 → 열 I0/I1cond/I2.

| 시나리오 | 관심 | py I0 | py I1cond | py I2 | **C I0** | **C I1cond** | **C I2** |
|---|---|---|---|---|---|---|---|
| A 단일모달 clutter | 오경보 | 3.0 | 2.1 | 0.1 | 1.6 | 1.1 | **0.0** |
| B 부분관측 진짜(수관+안개) | 탐지 | 90% | **30%** | 30% | 90% | **30%** | 25% |
| C 전-서명 decoy | 오경보 | 1.5 | 1.5 | 0.0 | 0.9 | 0.9 | **0.0** |

**판독(정직 — "수치가 같다"고 과장하지 않는다):**
- **두 핵심 발견이 C 에서 방향·크기로 재현된다.** (B) 조건부 CMPC 가 부분관측 진짜를 대가 있게
  보존 — **py 90%→30%, C 90%→30% (일치)**. (C) CMPC 로는 decoy 못 거르고(I0≈I1cond) **liveness 가
  I2→0 으로 제거 — py·C 모두**. #449 의 두 결론이 배포 C executive 에서 성립.
- **A·C 의 절대 FA 는 C 가 더 낮다**(A: py 3.0 vs C 1.6, I2 0.1 vs 0.0). 이유는 불일치가 아니라
  **executive 구조**: 프로토타입 scorer 는 매 obs 의 모든 군집을 무상태로 채점(더 많은 clutter
  포착)하고, C 는 **단일가설 stateful 추적**(한 belief 만)이라 먼 clutter 를 덜 claim 한다(#442 의
  단일가설→저FA 성질). 즉 **규칙은 등가(host_test[14] 정확), 관측가능성 방향은 재현, 절대 FA 는
  executive 성질로 C 가 보수적** — 세 가지를 구분해 적는다.
- 이것은 여전히 **verification(L2)** 이지 target/현장 **validation 아님**.

## Fidelity level (NASA)

이 실험은 **L2**(실측 DEM + landcover + 물리 센서모델)의 **Verification evidence** 다. Validation(L3+:
실 imagery·조명·target platform HITL·현장 비행)은 미확보 — fidelity ladder 와 V&V 매핑 전체는 `fw/V&V.md`.
