# OceanWATERS 연동·문제 카탈로그 — fw 의 FDIR·전원 척추를 진짜 고장주입으로 잰다

NASA OceanWATERS(`nasa/ow_simulator`)에 우리 정책(`fw/`, C99 결정 executive)을 얹어, **시뮬이 만들어
내는 고장**에서 fw 가 어디서 무너지는지 관찰하고 그 문제를 여기 **따로 정리**한다. 손으로 시나리오를
짜는(R-09 류) 대신 시뮬이 상황을 낳는다 — sar/ivv 의 심판↔SUT 분리와 같은 결.

> **범위(정직):** OceanWATERS 는 fw 의 **이동·표적탐색**을 재는 도구가 **아니다**(§2 도메인 불일치).
> **fw 의 고장관리·전원 안전전이(FDIR)** 만 잰다. 그 축에서 OceanWATERS 는 sar/ivv 의 L2 하네스가
> 못 하는 **진짜 고장주입 + 물리 배터리 프로그노스틱스**를 준다. 이동 위험(절벽·경사·막다른 곳)은
> 여전히 Gazebo Harmonic skid-steer 몫이다(`fw/ROVER_VALIDATION.md` §6).

읽은 판: `nasa/ow_simulator` @ `bdcabec` (shallow clone, 2026-09-29). 인용은 그 트리의 실제 파일 경로다.

---

## 0. 정직 — 이 컨테이너에선 못 돌린다

- OceanWATERS 는 **Ubuntu 20.04 + ROS Noetic + Gazebo** 를 요구한다(`README.md` §Getting Started).
  이 세션 컨테이너엔 ROS/Gazebo 가 없다(`ROVER_VALIDATION.md` §6 과 같은 벽). **여기서 돌렸다고 하면
  그게 이 저장소가 앓은 거짓 초록이다.**
- 그래서 이 문서는 **실행 결과가 아니라 (a) 연동 계약과 (b) 문제 카탈로그**다. §4 의 P-01~P-06 은
  시뮬을 *돌리지 않고 인터페이스를 읽어* 이미 드러난 문제이고, 실제 실행에서 나오는 문제는 §4 에
  **번호를 이어 append** 한다(실행은 ROS 있는 외부 기계에서 — §6).

---

## 1. OceanWATERS 가 무엇인가 (파일에서 확인)

- **유로파(목성 위성) 표면의 고정 착륙선** 물리·시각 시뮬. 팔(arm)로 표토(regolith)를 파고 시료를
  담는다. 이동 로버가 아니다. (`README.md` §Overview)
- ROS 기반. 자율 executive 는 **별도 repo `ow_autonomy`** 에 있다(`README.md` §Code Organization) —
  즉 시뮬(물리·센서·고장)과 결정 executive 가 **분리**돼 있고, 그 자리에 fw 를 끼운다.
  (주의: `ow_autonomy` 는 아직 안 읽었다 — 여기 서술은 `ow_simulator` 트리로 확인한 것만.)
- **고장주입 프레임워크**: `ow_faults_injection`(dynamic_reconfigure 로 런타임 고장 설정) +
  `ow_faults_detection`. (`ow_faults_injection/README.md`, `cfg/Faults.cfg`)
- **전원 프로그노스틱스**: `ow_power_system` + `owl_msgs` 의 배터리 메시지(아래 §3).

---

## 2. 왜 FDIR·전원 축만 — 도메인 불일치와 전이되는 축

### 대응물 없음 (이동·탐색)

`owl_msgs/action/` 의 명령은 **전부 팔·삽·시료·카메라 작업**이다:
`ArmMoveCartesian/Joint(s)[Guarded]` · `ArmStow/Unstow` · `ArmFindSurface` · `ArmStop` ·
`TaskScoopCircular/Linear` · `TaskGrind` · `TaskDeliverSample/DiscardSample` ·
`PanTiltMove…` · `Camera…` · `LightSetIntensity` · `FaultClear`.

fw 의 행동(`SEARCH·APPROACH·INSPECT·RETURN·AVOID·RELOCALIZE·EMERGENCY`)은 이동·표적탐색용이라
이 명령 집합에 **대응물이 하나도 없다.** → **fw 를 "그대로" 얹는 건 성립하지 않는다**(P-01).

### 전이되는 축 (FDIR·전원)

반대로 fw 의 **안전 척추**(`safety.c` FDIR + `world.battery`→RETURN/EMERGENCY, §POLICY.md 2③)는
OceanWATERS 가 **진짜로** 만들어 주는 것과 정면으로 겹친다:

- 진짜 **관절 고장 주입**(frozen=고착·friction=과전력·free=헛돎) → fw 의 stale/stuck 판별(R-03 gap).
- **힘/토크 센서 편향·잡음 주입** → fw 의 bias 센서 대응(R-04 analog).
- **물리 배터리**(SoC·잔여수명·온도·전원고장 비트마스크) → fw 의 배터리 안전전이. 제 L2 의
  `1−t/400` 가짜 배터리와 비교가 안 된다.

즉 **여기서 재는 것은 fw 의 estimator/health/FDIR/전원 전이의 행동**이지, 팔 궤적 제어가 아니다.
팔 명령을 실제로 낼지는 얇은 어댑터가 정하되(대부분 "안전 정지/대기"), **핵심은 fw 가 주입된 고장에
안전전이로 옳게 반응하는가**다.

---

## 3. 연동 계약 — owl_msgs telemetry → fw Blackboard → Action

`HW_BRINGUP.md` 의 HAL 계약과 같은 꼴을, MCU 대신 **ROS 노드**로. 노드가 `libfw.so`(ctypes 또는
C++ 링크)를 감싸 매 주기 telemetry 로 `Blackboard` 를 채우고 `fw_agent_step` 을 부른다. 정책 C 는
안 건드린다.

```
OceanWATERS(Gazebo)  ─ owl_msgs(구독) ─▶  fw_ow_node
   /faults/*, battery*, arm FT, joint state         │  Blackboard 채움
                                                     ▼
                                        fw_agent_step (libfw.so)  ─ Action ─▶  얇은 어댑터
                                        estimator→evidence→safety→BT→arbiter        (대개 안전정지/
                                          →safety_filter                             ArmStop·대기;
                                                                                     팔궤적은 fw 밖)
```

**telemetry → Blackboard 매핑** (실제 필드는 `owl_msgs/msg/*.msg` 에서 확인):

| OceanWATERS (owl_msgs) | fw 입력(`Blackboard`) | 비고 |
|---|---|---|
| `BatteryStateOfCharge.value` (0–1) | `world.battery` | **직결.** 물리 배터리 SoC — 가짜 아님 |
| `BatteryRemainingUsefulLife.value` (초) | (없음) | fw 는 스칼라 battery 뿐 — RUL 프로그노스틱스 미소비(P-02) |
| `BatteryTemperature`, `PowerFaultsStatus.THERMAL_FAULT` | (없음) | fw 에 **열 채널 없음**(P-02) |
| `PowerFaultsStatus.LOW_STATE_OF_CHARGE` | `world.battery`(임계로 간접) | RETURN/EMERGENCY 트리거 |
| `ArmFaultsStatus.HARDWARE/E_STOP` | `world.actuator_ok` | **`fw_bridge_step` 이 미노출**(P-03) → 네이티브 `fault_test.c` #5 |
| `ArmFaultsStatus.COLLISION`, guarded move 힘초과 | `world.collision_risk` | 접촉/충돌 → AVOID |
| `ArmFaultsStatus.NO_FORCE_DATA`, FT zero_signal | `health[SENSOR]` | 센서 죽음 → FDIR 격리 |
| joint `frozen`(고착) / FT `signal_bias` | `health[·]` / `obs[·]` | **R-03·R-04 를 진짜 물리로**(P-05·P-06) |
| `SystemFaultsStatus.*_GOAL/EXECUTION_ERROR` | (없음) | 작업 실행오류 대응 입력 없음(P-04) |
| 관절 위치/속도/토크, 팔 pose | `world.position_error` 등(간접) | 착륙선엔 GNSS 없음 — 측위축은 부분만 |

**fw Action → 어댑터** (대부분 N/A — 정직):

| fw Action | 착륙선에서 | 
|---|---|
| EMERGENCY / RETURN | `ArmStop` + `ArmStow`(안전자세) · 작업 중단 | 
| AVOID | guarded move 중단 · `ArmStop` |
| RELOCALIZE | (착륙선은 이동 안 함) → 대기·재추정만 |
| SEARCH/APPROACH/INSPECT | **대응물 없음**(이동·표적탐색) → no-op |

→ 이 표 자체가 결론이다: **fw 의 안전전이(EMERGENCY/AVOID/격리)만 착륙선에서 뜻이 있고, 이동·탐색은
비어 있다.** 그래서 이 연동은 **FDIR/전원 검증기**이지 임무 executive 이식이 아니다.

---

## 4. 문제 카탈로그

시뮬을 *공부만 해도* 드러난 문제(P-01~P-06). 실제 실행에서 나오는 것은 번호를 이어 여기 붙인다.

| # | 문제 | 축 | 심각도 | 주인 | 메모 |
|---|---|---|---|---|---|
| P-01 | **도메인 불일치** — fw 행동집합(이동·탐색)이 착륙선 명령(팔·삽)에 대응물 없음 | 구조 | 높음 | 설계 | fw 를 그대로 못 얹는다. FDIR/전원 축만 유효(§2) |
| P-02 | fw 는 **스칼라 battery** 뿐 — SoC 는 받지만 **RUL·온도·전원고장 종류**를 못 받는다 | 전원 | 중 | 정책 | 프로그노스틱스(잔여수명)·열 안전전이 미표현. 새 입력=설계변경 |
| P-03 | **`fw_bridge_step` 이 `actuator_ok` 미노출** — arm HARDWARE/E_STOP 을 브리지로 못 넣는다 | 구동 | 중 | 브리지 | 네이티브 `fault_test.c`(#5)만 다룸. ROS 연동엔 브리지 확장 필요 |
| P-04 | **작업 실행오류 입력 없음** — `SystemFaultsStatus`(GOAL/EXECUTION_ERROR)에 fw 대응 채널 없음 | 계획 | 중 | 정책 | fw 는 HTN 재계획이나 "행동 실패 피드백" 경로가 다르다 |
| P-05 | **frozen joint(고착) = R-03 gap** — OceanWATERS 가 진짜 ground-truth 로 재현 | 센서 | 높음 | 정책 | fw 의 stale-sensor 미검출 gap 을 **고충실도로 확인/재현할 자리**. 해법=서명/일관성 채널 |
| P-06 | **FT signal_bias/noise = R-04 analog** — 물리 힘센서 편향·잡음 주입 | 센서 | 중 | 정책 | bias 센서에 belief 가 얼마나 끌려가나 — NIS 게이트가 잡나 |

> 실행 시 채울 슬롯(예): 배터리 급방전(`battery_nodes_to_disconnect`)에서 RETURN→EMERGENCY 전이가
> 물리 SoC 곡선의 어느 지점에 걸리나 · `high_power_draw` custom CSV 프로파일에서 오검출/지연 ·
> 고착 관절 다중동시(bitmask)에서 FDIR 격리 순서 · 열고장에서 (열 채널 없어) 무반응 여부.
> **실행 전엔 이 슬롯을 추측으로 채우지 않는다** — 돌린 뒤 로그로 적는다.

---

## 5. 주입 가능한 고장 → fw 방어축 (`ow_faults_injection/cfg/Faults.cfg`)

| OceanWATERS 주입 | 뜻 | fw 방어축(POLICY §2) | 예상(실측 아님) |
|---|---|---|---|
| joint `frozen` / `*_joint_locked_failure` | 관절 고착(엔코더 죽음) | ③ FDIR (stale/stuck) | **gap** — fw 는 고착 미검출(R-03 동뿌리) |
| joint `friction` | 과전력 소모 | 전원 + ③ | 전력↑ → 배터리 전이 앞당김 |
| joint `free` | 헛돎(무저항) | ③ / 구동 | actuator_ok 축(P-03) |
| FT `signal_bias_failure` | 힘센서 편향 | ② NIS 게이트 | bias 가 innovation 으로 잡히나(R-04) |
| FT `zero_signal_failure` / `NO_FORCE_DATA` | 힘센서 무신호 | ③ health 격리 | health→0 → 융합서 배제 |
| `high_power_draw` / custom CSV | 고전력·프로파일 방전 | 전원 안전전이 | RETURN(0.25)→EMERGENCY(0.10) |
| `battery_nodes_to_disconnect` | 배터리 내부 고장(급방전) | 전원 | 급강하 SoC 에 전이가 따라가나 |
| `THERMAL_FAULT` | 열고장 | (fw 채널 없음) | **무반응 예상**(P-02) — 정직히 gap |

---

## 6. 어떻게 돌리나 (외부, L3+)

1. Ubuntu 20.04 + ROS Noetic + Gazebo 준비, OceanWATERS 빌드
   (`oceanwaters/doc/setup_dev_env.md`, `setup_oceanwaters.md`; 자율은 `nasa/ow_autonomy`).
2. `fw_ow_node` 작성: `libfw.so` 링크, §3 표대로 owl_msgs 구독→Blackboard→`fw_agent_step`→어댑터.
   브리지에 `actuator_ok` 노출 추가(P-03).
3. `ow_faults_injection`(rqt / CLI / python, `custom_fault_profile` CSV)으로 §5 고장을 주입.
   **CSV 프로파일 = 재현 가능한 회귀**(고정 입력 → 고정 행동열, IV&V 불변식).
4. fw 행동열·안전전이 시점을 로그로 남기고, **나온 문제를 §4 에 번호 이어 append**.
   초록이라 말하지 말고 무엇이 왜 실패하는지 그대로 적는다(이 저장소 규율).

---

## 7. 정직한 한계

- **아직 안 돌렸다.** §4 P-01~P-06 은 인터페이스를 읽어 나온 것이고, 실행 문제는 외부 기계에서 채운다.
- **이식이 아니라 부분 검증이다.** 이동·탐색(fw 의 대부분)은 착륙선에 대응물이 없다(P-01). 이 연동은
  fw 의 **FDIR·전원 축**만 고충실도로 잰다. 이동 위험은 Gazebo skid-steer(`ROVER_VALIDATION.md` §6).
- **`ow_autonomy` 미독.** 자율 executive 가 사는 repo 는 아직 안 읽었다 — 실제 노드 연동 지점은 그걸
  읽고 확정한다.
- OceanWATERS 는 **유로파 착륙선** 도메인이다. 배터리·열·중력·표토 물리는 지구 SAR-UAV/로버와 다르다.
  전이되는 것은 **고장→안전전이의 구조**이지 물리 상수가 아니다.
