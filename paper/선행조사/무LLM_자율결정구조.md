# 선행조사 — LLM 없는 자율 결정 구조 (bare-metal, 로봇/우주비행 검증 구조의 조합)

요청(사용자): "LLM 을 넣지 않는 autonomous decision architecture 라면, 로봇/우주비행체에서 오래
검증된 소프트웨어 구조를 조합하는 것이 더 명확하다. Event-driven Hybrid = State Estimator +
Belief/Evidence State + Rule/Guard + Hierarchical FSM/Behavior Tree + Arbitration + Safety
Supervisor + Action Executor. RTOS 조차 없는 STM32/ESP32급 bare-metal C 로 내려간다."

핵심 명제(사용자): **AI 가 다음 행동을 생성하는 것이 아니라, 소프트웨어가 관측을 구조화하고 미리
정의된 decision primitive 를 조합해 행동을 고른다.** 그래서 방어·검증이 쉽다.

## 정직한 성격 — 이것은 **알려진 구조의 공학적 조합이지 새 이론이 아니다**

Subsumption → 3T → Behavior Tree → belief/POMDP → NASA cFS/FDIR 계열의 **이미 검증된** 구조를
임베디드에 맞게 조합한다. 새 아키텍처를 주장하지 않는다(과장방지). 아래 인용은 전부 사용자가 준
링크의 **검색 조각·요약** 수준이다 — 원문 전문 미열람이므로 전부 `[출처:조각]`. 전문을 읽고 나서야
`전문` 으로 올린다.

## 가장 가까운 선행연구

- **Subsumption Architecture** — Brooks, "A Robust Layered Control System for a Mobile Robot",
  IEEE J. Robotics & Automation 1986 (MIT AIM-864/AIM-1091). 이미 한 것: 중앙 planner 없이 여러
  단순 FSM behavior 를 계층으로 쌓아 sensor→state→actuator 를 직결. deterministic·빠름·fault
  isolation. `[출처:조각]`
- **3-tier / 3T (ATLANTIS, 3T)** — Gat 1998 "On Three-Layer Architectures"; Bonasso et al. 1997.
  이미 한 것: Deliberator / Executive(Sequencer) / Reactive controller 로 나누고, **deliberator 는
  항상 돌 필요 없다**(reactive 가 즉각 대응, 필요할 때만 심의). `[출처:조각]`
- **Behavior Trees** — Colledanchise & Ögren, "Behavior Trees in Robotics and AI" (2018 book) /
  Annual Reviews of Control 2022. 이미 한 것: modularity·hierarchy·feedback·task-switching·
  robustness·transparency; 3T 의 executive-controller 를 tree tick 으로 구현. task 복잡도가 오르면
  BT 유지보수성이 FSM 보다 유리(arXiv:2405.16137 비교). `[출처:조각]`
- **POMDP belief-space** — 관측 못 하는 실제 상태 대신 **belief distribution** 유지; 행동이
  uncertainty 를 줄이는 것을 명시 모델링(active perception). 실로봇에선 상태공간이 커 full POMDP 는
  상위 mission planning 에만(ScienceDirect S0921889007000279 등). `[출처:조각]`
- **NASA cFS / cFE** — Goddard core Flight System: Platform→OSAL→cFE(executive)→Applications 의
  component+event+table+executive 구조. software bus·time·event·table·file service. 여러 실제
  mission 에 사용. `[출처:조각]`
- **FDIR / autoNGC** — NASA autonomy(TechPort 101856, autoNGC): autonomous planning/scheduling/
  execution 과 **fault detection/isolation/recovery** 를 하나의 framework 에. `[출처:조각]`

## 우리가 그것과 다른 점 — 그리고 **SE 에 이미 있는 것**

이 저장소는 이 구조의 상당 부분을 **이미 다른 이름으로 구현·검증**하고 있다. 새로 짓는 것은
"OS 없는 C 결정 executive 로 층을 명시적으로 갈라 내리는 것"이지, 개념을 처음 만드는 것이 아니다.

| 아키텍처 계층 | SE 에 이미 있는 것 | 위치 |
|---|---|---|
| 검증 환경(심판) | 숨은 truth·독립 물리·evaluator (IV&V) | `sar/` (절대 레퍼런스) |
| Perception/Fusion(증거누적) | **센서 융합 투표(health 가중 soft vote)** = evidence accumulator | `sar/ivv/policies.py` VotingPolicy (PR #439) |
| Belief State | belief grid + 신뢰·위치·불확실도 | `sar/ivv/` bel, telemetry |
| Temporal memory | selective SSM 상태 재귀(시간 일관성) | `ctrl/model/mamba_selector.py` |
| Arbitration | NASA S4 식 효용 U_i=D−λC−μE argmax | `sar/ivv/policies.py` NASARulePolicy |
| Safety supervisor | MRC(IMU/GPS 열화 시 안전 정지) | `sar/ivv/policies.py` step() MRC 분기 |
| Bare-metal 실행 | selective-SSM 커널 C, host_test PASS | `ssm/fw/ssm.c`, `ssm/배포_정책_하드웨어.md` |

**새로 짓는 것(`fw/`)**: 위 개념을 RTOS 없는 C 로 **명시적 층**으로 내려 — blackboard(belief+
evidence+health+temporal) · HFSM(mission mode) · 최소 BT(guarded action) · arbiter(safety-hard-
filter + utility) · safety supervisor(FDIR) · event queue · superloop. malloc 없음. gcc host_test
로 행동을 **재서** 검증한다(외로운 Audio 는 확인 안 됨 = PR #439 의 오경보 억제를 C 로).

**정직**: 이 C 는 **배선·행동 골격이지 실비행 검증 시스템이 아니다.** 실제 STM32/ESP32 HAL·타이밍·
전원·인증(DO-178/FDIR 커버리지)은 하지 않았다. host_test 는 결정 논리의 행동만 잰다.

## 찾아본 질의

- `Brooks subsumption architecture layered control mobile robot`
- `three-layer architecture 3T deliberator executive reactive Gat`
- `behavior trees robotics survey Colledanchise Ogren modularity`
- `behavior tree vs finite state machine comparison maintainability`
- `POMDP belief state active perception information gathering robot`
- `NASA core flight system cFE cFS component executive FDIR autoNGC`

## 아직 못 지운 가능성

- **BT 구현 라이브러리 생태계**(BehaviorTree.CPP, ROS2 nav2 BT, py_trees)의 tick 규약·메모리
  모델을 아직 안 봤다 — 우리 최소 BT 가 그들과 어긋나는 규약을 쓸 수 있다.
- **cFS 앱 패턴**(SB/TBL/EVS API)을 전문으로 안 읽었다 — event queue/table 설계가 cFS 관례와
  다를 수 있다.
- **guard/precondition 집합의 형식 검증**(model checking, 안전성 증명) 문헌을 안 봤다.
- 위 인용 논문 **전문을 안 읽었다** — 3T 의 executive 의무·BT robustness 정리의 전제가 우리
  가정과 다를 수 있다.
- 임베디드 자율결정에서 **arbitration=priority vs utility** 선택을 정면으로 다룬 최신 서베이를
  아직 못 찾았다(있을 수 있다).
