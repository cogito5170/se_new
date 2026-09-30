# fw/ — LLM 없는 자율 결정 executive (bare-metal C)

로봇/우주비행에서 검증된 구조(Subsumption·3T·Behavior Tree·POMDP belief·NASA cFS/FDIR)를 조합한
**OS 없는 결정 executive**. AI 가 행동을 생성하지 않는다 — 소프트웨어가 관측을 구조화하고 미리
정의된 primitive 를 조합해 고른다. 선행조사: `paper/선행조사/무LLM_자율결정구조.md`.

## closed loop (한 스텝) — 계보가 하나의 폐루프로 닫힌다

```
센서 obs + health
    ↓  estimator.c  (Kalman: 측정 → x̂ + 공분산 P; 안 보면 P 성장)          ← Kalman(1960)
    ↓  evidence.c   (health 가중 soft vote + 시간적 확인 → belief, sigma=√trP)  ← POMDP belief
belief (신뢰·위치·공분산·확인)
    ↓  safety.c     (충돌·전력·센서고장 → FDIR 이벤트 · 감독자 상태)         ← NASA FDIR
    ↓  planner.c    (HTN 순차+재계획: SEARCH→APPROACH→INSPECT→REPORT → mode)  ← 3T/Remote Agent
    ↓  decision.c   (BT: 우선순위 selector 로 행동 제안)                     ← BT / Subsumption
    ↓  arbiter.c    (precondition + 효용 U=mission−충돌−에너지−불확실도)       ← S4 다목적 효용
    ↓  safety.c     (safety_filter: 최종 하드 override — 결정 버그 방어선)     ← Subsumption suppress
행동 → (telemetry / replay) 동일 입력 → 동일 행동열, 외부 검증 가능           ← telemetry/IV&V
```

즉 **Planner → Executive(BT/arbiter) → Estimator(KF) → FDIR(safety) → Replay(결정성) → IV&V(sar 심판)**
가 하나의 폐루프. #441 계보의 각 갈래가 실제 C 모듈로 닫혔다(아래 표).

## 층과 파일 — 계보 매핑

| 파일 | 역할 | 20세기 근거 |
|---|---|---|
| `blackboard.[ch]` | 정적 공용 상태(belief·world·health·mode·plan), malloc 없음 | Blackboard(1990) |
| `estimator.[ch]` | **Kalman(축별 스칼라): 측정→x̂+공분산, belief 의 수치 기반** | Kalman(1960) |
| `evidence.[ch]` | 센서 융합·시간적 확인·**CMPC 교차모달 게이트+liveness**(cfg.cmpc_min·require_live) | POMDP belief / #449 |
| `planner.[ch]` | **HTN 식 임무 순차 + 재계획(3T sequencer/RA executive)** | 3T / Remote Agent |
| `bt.[ch]` | 최소 Behavior Tree(SELECTOR/SEQUENCE/CONDITION/ACTION), 정적 | BT robotics |
| `decision.[ch]` | HFSM(백업) + BT(행동 제안) | 3T executive |
| `arbiter.[ch]` | precondition + 효용 argmax(안전 위에 효용) | S4 / Subsumption |
| `safety.[ch]` | 감독자 FSM + FDIR + 최종 하드 필터 | NASA FDIR |
| `event.[ch]` | 고정 링 이벤트 큐(오버플로는 dropped 로 계상) | cFS SB |
| `agent.[ch]` | 위를 순서대로 엮는 superloop 한 스텝 | Subsumption |

**estimator/planner 추가 효과(정직)**: clutter=0 서 KF 평활로 위치 RMSE 가 N=1 0.84→0.81, N=2 0.80→0.72
로 소폭 개선(탐지·오경보 불변). 성능이 목적이 아니라 **계보를 닫는 것**이 목적 — 새 성능 주장 아님.
Kalman 은 축별 스칼라 정위치 모델(EKF/UKF·상태 [x,y,vx,vy] 아님), planner 는 최소 HTN(풍부한
task network 아님), replay 는 결정성 확인(기록된 센서 로그 재생·fault injection 은 후보).

## 검사

```
make test          # gcc 로 빌드해 host_test 를 돌린다(-Werror)
```

`host_test.c` 는 행동을 **잰다**(스텁 아님, 13군데): 외로운 Audio 확인 안 됨(오경보 억제)·RGB+Thermal
코로보 → INSPECT·플리커 거부·저전력 RETURN override·충돌 AVOID·센서 2고장 FDIR+RELOCALIZE·
IMU무효 RELOCALIZE·큐 오버플로 dropped·arbiter 대체·health 가중·**Kalman 공분산 수렴/성장·planner
순차+재계획·replay 결정성**. `tests/test_fw_decision.py`(host_test)·`test_fw_bridge.py`(브리지)가
CI 에서 컴파일·실행한다.

## V&V — sar 심판이 채점한 결과 (held-out 지리산 실제 DEM, n_ep=16)

`sar/ivv/fw_vv.py` 가 **실제 C 코드**(libfw.so, ctypes)를 sar reference·evaluator 로 채점한다
(파이썬 재구현 아님). 확인창 N(연속 스텝) 스윕:

| 정책 | 탐지율 | 위치RMSE | 오경보 | 평균센서비용/스텝 |
|---|---|---|---|---|
| fw C (확인창 N=3) | 0% | — | **0.00** | 0.162 |
| fw C (확인창 N=2) | 19% | 0.80 | **0.00** | 0.285 |
| fw C (확인창 N=1) | 62% | 0.84 | **0.00** | 0.563 |
| Baseline(RGB) | 38% | 0.83 | 0.19 | 0.100 |
| NASA-rule(5센서) | 50% | 0.90 | 0.25 | 0.250 |
| Mamba-RL(보상) | 62% | 1.16 | 1.31 | 0.154 |
| RL+SoftVote(t0.9) | 38% | 0.76 | 0.12 | 0.499 |

읽는 법(정직 — 무효화 조건 포함):
- **오경보 0.00 의 참뜻(과장 정정).** 실측: N=1 에서 fw 는 22표적에 claim 을 **13개**만 내고 13개
  전부 truth 에 매칭 → unmatched 0. 그런데 **sar reference 는 clutter(헛 표적)를 안 만든다** —
  모든 센서 탐지가 `진짜 표적+잡음`(reference.py 의 `*_dets.append` 가 전부 표적 루프 안). 그래서
  evaluator 의 오경보(=총claim−매칭claim)는 여기서 **빗나간 위치(>2.5셀)·표적수 초과 중복 claim**
  으로만 난다. 즉 **fw 의 0 은 "빗나간·중복 claim 을 안 만든다"는 뜻이지 "clutter/오탐을 거른다"가
  아니다** — 이 검증엔 clutter 가 없어 그건 증명 안 됨. 게다가 0 의 상당부분은 fw 가 **적게 claim
  하는 보수성**(13<22) 덕이고, 그 보수성이 탐지율을 눌러 절반은 아예 claim 안 한다.
  (대조로 RL 은 22표적에 36 claim 과다 → 21개 빗나가거나 중복 → FA 1.31.)
- **확인창 N 이 탐지/지연 손잡이다.** N=3(프레임레이트 가정, 0.3s@10Hz)은 sar 의 **웨이포인트
  케이던스**에선 너무 엄격해 0% — 연속 3스텝 같은 표적을 못 본다. **단위 불일치**이지 설계 실패가
  아니다. N=1 이면 RL 과 같은 ~62% 탐지를 **RMSE 1.16→0.84** 로 낸다(오경보는 위 무효화 조건 하에서 0).
- **대가**: 융합이 present 센서를 다 켜므로 비용이 높다(N=1 에서 0.563 — SoftVote 0.499 급).
- **한계**: fw 는 belief 를 **단일 가설**로 든다 → 한 시나리오에 표적이 둘이면 하나만 claim,
  탐지율 상한이 눌린다. 학습이 아니라 손으로 짠 결정론적 executive 다.
### clutter(헛 탐지) 넣고 오탐 거부를 진짜로 재기

reference 에 clutter 항 추가(센서 독립·드론 FOV 안 임의 위치·표적서 ≥4셀·신뢰도는 실탐지와 동일
분포). clutter 율을 올리며 전 정책 동일 시나리오로 채점(오경보=평균/에피소드):

| 정책 | clutter=0 FA | 0.15 FA | 0.30 FA | (0.30 탐지율) |
|---|---|---|---|---|
| fw C N=3 | 0.00 | **0.06** | **0.19** | 0% |
| fw C N=2 | 0.00 | **0.56** | **0.69** | 25% |
| fw C N=1 | 0.00 | 2.25 | 3.50 | 6% |
| Baseline | 0.19 | 1.88 | 3.06 | 3% |
| NASA-rule | 0.25 | 1.75 | 2.81 | 3% |
| Mamba-RL | 1.31 | 2.44 | 3.62 | 0% |
| RL+SoftVote | 0.12 | 1.25 | 2.25 | 9% |

**진짜 결론(이제 clutter 가 있으니):**
- **fw N=1 은 clutter 를 못 거른다** — FA 가 Baseline 만큼(또는 그 이상) 오른다(0.30 서 3.50).
  앞서 본 N=1 의 "0 FA" 는 clutter 가 없던 탓이었다(PR #442 정정이 옳았다).
- **fw N=2·N=3 은 clutter 를 진짜로 거른다** — 0.30 서 FA 0.69/0.19 로, 남들(1.75~3.62)의 1/3~1/18.
  기전은 **단일가설 융합이 아니라 시간적 확인**이다: clutter 는 매 스텝 새 위치로 튀어 연속 N스텝
  같은 자리에 안 선다. 실 표적은 드론이 머무는 동안 여러 스텝 잡혀 confirmed.
- **대가는 탐지/지연**: N=3 은 FA 최저지만 케이던스 과엄격으로 탐지 0%. **N=2 가 균형점** —
  clutter=0.30 서 탐지 25%(전 정책 최고 중 하나)에 FA 0.69.
- clutter 가 높아지면 **전 정책의 탐지가 붕괴**(0.30 서 대부분 0~9%) — 헛 탐지가 표적을 덮고
  드론이 clutter 를 쫓는다. 이건 환경 난이도이지 특정 정책 탓이 아니다.

정직: n_ep=16 으로 절대수치는 노이즈가 있다. 그러나 **FA 가 N 에 단조(1<2<3 순으로 낮아짐),
clutter 에 단조(율 오르면 FA 오름)** 는 일관돼 결론은 견고하다. clutter 신뢰도를 실탐지와 같은
분포로 줬으므로(신뢰도만으론 못 거름) fw 의 이점은 오로지 시간적 확인에서 온다.

### clutter 공간 지속성(worst case F) — temporal confirmation 의 한계

위 결론은 **clutter 가 매 스텝 새 위치로 튄다(transient)**는 가정에 전적으로 의존한다. 실 환경엔
**몇 스텝 같은 자리에 서는 지속 false target**(햇빛 데운 바위, 고정 다중경로)이 있다. `clutter_persist`
(같은 위치에 머무는 스텝)를 스윕(clutter=0.20 고정, n_ep=16):

| clutter=0.20 | persist=1(transient) | persist=2 | persist=4 |
|---|---|---|---|
| fw N=3 오경보 | **0.12** | 0.81 | **2.19** |
| fw N=2 오경보 | **0.56** | 2.38 | 2.38 |
| Baseline 오경보 | 2.56 | 2.25 | 2.06 |
| NASA-rule 오경보 | 2.06 | 2.19 | 2.00 |

**지속성이 오르면 fw 의 이점이 사라진다.** persist=4 에서 fw N=3(2.19)은 Baseline(2.06)·NASA(2.00)
보다도 나쁘다. 이유는 정확하다: **지속 clutter 는 실 표적처럼 연속 N 스텝 같은 자리에 서므로 시간적
확인을 그대로 통과한다.** temporal confirmation 은 "이 위치가 지속되나?"만 보는데, 지속 false
target 은 지속된다 → 구분 불가. 즉 **시간적 확인은 transient clutter 만 거르고, 지속 false target
(persist ≥ N)에는 방어가 전혀 없다.** 그걸 거르려면 다른 신호(외양/의미 판별, clutter 에 없는 교차
센서 상관, 운동 일관성)가 필요한데 fw 엔 없다.

방어적 결론(V&V 문서 표현):
> **The observed false-alarm rejection of fw is attributable to temporal confirmation rather than
> confidence-based filtering. Under the current independent, transient clutter model, N=2 substantially
> reduced false alarms while retaining some detections. Increasing confirmation depth to N=3 further
> reduced false alarms but caused excessive detection loss under the tested observation cadence.
> This advantage collapses when clutter is spatially persistent (persist ≥ N): persistent false
> targets pass temporal confirmation exactly like real targets.**

"N=2 가 균형점"은 **보편 최적이 아니라 이 reference·cadence·target dwell·transient clutter·n_ep=16
조건에서의 trade-off**다. N=3→탐지 0%(앞 표)도 temporal confirmation 이 나쁜 게 아니라 **관측
cadence·target persistence 가 N=3 요구를 못 채운 것**일 가능성이 크다.

### motion-consistency 경계 — NIS(innovation consistency)를 evidence 로

지속 clutter 를 N 만 올려 잡으려 하면 실 표적의 dwell·maneuver 도 같이 놓친다. 그래서 **시간 지속성**
과 **운동학적 일관성**을 분리해 잰다. 등속 KF(estimator.c)가 매 갱신의 NIS `d²=rᵀS⁻¹r` 를 내고,
`nis_gate` 로 NIS 큰(궤적 모순) 측정을 확인서 제외한다. 표적 운동(reference)을 static/const/accel/
turn 으로, 운동 표적은 **시각 맞춰**(스텝별 궤적) 채점. fw N=2, gate off vs NIS(chi² 2-dof≈9):

| 조건 | gate | 탐지율 | RMSE | 오경보 | 평균NIS |
|---|---|---|---|---|---|
| A 정지·transient clutter | off | 9% | 0.76 | 0.56 | 23.65 |
| A 정지·transient clutter | **NIS** | 0% | — | **0.06** | 7.54 |
| B 정지·persistent clutter | off | 19% | 0.96 | 2.06 | 6.07 |
| B 정지·persistent clutter | **NIS** | 3% | 0.79 | **1.56** | 1.12 |
| C 등속 표적 | off/NIS | 9% | 0.47 | 0.00 | 0.64 |
| D 가속 표적 | off/NIS | 3% | 0.85 | 0.00 | 0.41 |
| E 방향전환 표적 | off | 28% | 0.71 | 0.00 | 1.56 |
| E 방향전환 표적 | **NIS** | 25% | 0.48 | 0.00 | 0.51 |
| F 등속표적+persistent clutter | off | 3% | 1.73 | 2.31 | 5.66 |

**경계가 정확히 드러난다:**
- **transient clutter 는 운동 모순(NIS≈24)** → NIS 게이트가 FA 를 0.56→0.06 으로 더 죽인다(시간적
  확인에 상보). 점프하는 clutter 는 궤적과 어긋난다.
- **persistent clutter 는 NIS 가 낮다(6.07→ 게이트 후에도 FA 1.56)** — 정지 false target 은 정지
  실표적과 **운동학적으로 동일**해 NIS 로 못 가른다. **motion consistency 는 persistent clutter 를
  못 고친다**(#444 경계 재확인). 그건 외양/의미 판별이 필요하다(fw 엔 없음).
- **CV KF 는 등속 표적을 따라간다**(C·E: NIS 0.5~1.6, 게이트가 안 버림). 단 **탐지율은 nav/dwell 이
  누른다**(움직이는 표적이 드론 FOV 를 벗어남; 가속 D 는 3%).
- **NIS 게이트의 대가는 false negative**: 실 신호의 NIS 가 튀는 경우(clutter 혼입 A, 급회전 E)
  실 탐지도 같이 버린다(A 9→0%, E 28→25%). 그래서 게이트는 공짜가 아니다.

즉 **시간(persistence)과 운동(NIS)은 서로 다른 clutter 를 거른다**: 시간은 transient 를 여러 번
봐서, 운동은 점프를 궤적으로. **둘 다 정지 persistent false target 은 못 거른다** — 그건 다음 축이다.

정직: n_ep=16 절대 탐지율은 낮고(운동+clutter 결합 난이도) 노이즈가 있다. 결론은 **NIS 의 조건별
대비**(transient 높음/persistent·real 낮음)와 **게이트의 FA↓·FN↑ 방향성**에서 온다.

### deterministic replay + fault injection — FDIR 존재 이유 검증

`fault_test.c`: 기록 장면을 재생하면 **동일 입력 → 동일 행동열**(결정적 = IV&V invariant 의 기반).
그 위에 fault 를 하나씩 주입해 executive 가 옳게 열화하는지 본다.

| fault | 주입 | FDIR 응답(측정) |
|---|---|---|
| 센서 dropout | health→0 | EV_SENSOR_FAIL, 남은 센서로 융합 계속(conf 0.56); 복구 시 EV_SENSOR_RECOVER |
| KF 공분산 폭발 | 40스텝 blind | sigma 유한(109), 상한 초과 → confirmed 취소(과불확실 추적에 행동 금지) |
| planner 상태 오염 | plan_phase=999 | 유효 단계로 복구(방어적 default) |
| actuator 고장 | actuator_ok=false | EV_ACTUATOR_FAIL, 행동 ACT_NONE(안전 정지) |
| **stale/stuck 센서** | 매 스텝 동일값 | **GAP: 실표적으로 오인(confirmed)** — fw 엔 정지성·bias 판별이 없다 |

**정직한 gap**: fw 는 **stale(고착)·biased 센서를 못 거른다.** 고착 센서는 정지 persistent false
target 과 같아(시간·운동 모두 일관) 확인을 통과한다 — motion-consistency 경계에서 본 그 한계와
같은 뿌리다. 거르려면 **센서별 서명(외양/의미)·교차센서 물리 상관·bit-동일 반복 탐지**가 필요하고,
그건 fw 의 다음 축이다(현재 없음, 정직히 fault_test 에 gap 으로 박음).

### 경계 지도 (한 화면)

지금까지 찾은 모든 경계를 한자리에 모은 **결합 스윕(확인창 N × 지속성 × 운동)** + 세 방어축의
직교성 + 공통 gap: **`fw/경계지도.md`** (`python3 sar/ivv/fw_vv.py --mode grid`). 요지: 시간·운동·
FDIR 은 서로 다른 가짜를 거르지만, **정지·고착·일관된 가짜 신호**에서 셋 다 동시에 무너진다.

### 아직 못 잰 것 (남은 축)

- **정지 persistent false target / stale·biased 센서 판별**: 시간·운동·FDIR 모두 못 거른다 →
  외양/의미(센서별 서명)·교차센서 물리 상관·staleness(bit-동일 반복) 탐지가 필요. fw 다음 축.
- **target dwell** 을 nav 로 늘려 N=3 탐지 회복 확인 — dwell 은 현재 nav(belief 추종)에 결합돼
  독립 축으로 못 뺐다. 결합 스윕은 N×persistence×motion 3축까지(경계지도.md).

## 정직 — 이것은 배선·행동 골격이지 실비행 시스템이 아니다

실제 STM32/ESP32 HAL·인터럽트·타이밍·전원·인증(FDIR 커버리지 증명)은 하지 않았다. host_test 는
호스트에서 결정 논리의 **행동만** 잰다. 실타깃에선 cross-gcc + HAL 드라이버로 링크하고, 센서
드라이버가 `blackboard.obs`/`health` 를 채운다. `ssm/fw/ssm.c`(selective-SSM 커널)와 같은 배포
철학이며, 학습 정책(Mamba)을 쓰려면 그 커널을 evidence/arbiter 앞단에 얹는다.
