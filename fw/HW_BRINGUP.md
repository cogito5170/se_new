# 하드웨어 bring-up 준비 — fw 를 실 비행 MCU 에 올리는 계약과 gap

`POLICY.md`(정책)와 `sar/HW_DESIGN.md`(시스템·센서·통신)를 실행 가능한 **bring-up 체크리스트**로
묶는다. 목적: "무엇이 이미 준비됐고, 통합자가 무엇을 구현해야 하며, 인증까지 무엇이 남았나"를
정직히 못박는다. **fw 는 아직 인증된 실비행 시스템이 아니다** — 이 문서가 그 간극을 정확히 적는다.

---

## 1. 지금 준비된 것 — 실측 (이 세션에서 잰 정적 사실)

| 항목 | 실측값 | 의미 |
|---|---|---|
| 코드 크기(.text, 커널 10 + SAR 프로파일, -O2 -ffreestanding) | **9,688 B (~9.5 KB)** | 어떤 MCU flash 에도. 새 도메인은 자기 profile 만 링크(예시 profile_min 추가 시 +~0.9KB) |
| 가변 .data / .bss | **0 / 0** | 파일-정적 **가변** 전역 없음 → 상태는 **호출자 소유** |
| const .data.rel.ro | **168 B** | SAR 프로파일 vtable+행동이름(읽기전용, 재배치 후 flash 배치 — 가변 상태 아님) |
| 상태 RAM `sizeof(Blackboard)` | **360 B** | 센서·belief·world·cfg·KF·live·stale·spec 포인터 전부 |
| `sizeof(BtTree)` | **1,808 B** | 정적 행동트리(프로파일이 초기화 후 불변) |
| `sizeof(Agent)` 정책 상태 총 | **2,400 B (~2.4 KB)** | Blackboard 360 + BtTree 1808 + EventQueue 208 + … · STM32F4(192KB)·H7(1MB) 여유 |
| 동적 할당 | **malloc/calloc/free/realloc 0건** | 힙 없음, 단편화 없음 |
| stdio | **printf/fopen 0건** | 호스트 I/O 의존 없음 |
| 외부 헤더 | **`<math.h>` 하나** | libm 3콜: `sqrtf`×2·`fabsf`×1(KF) |
| 재귀 | BT tick 만, **정적 트리 깊이로 유계**(SELECTOR→SEQUENCE→노드, ~3단) | 스택 유계 |
| freestanding 컴파일 | **통과**(`cc -std=c99 -ffreestanding -Werror`) | 호스트/OS 의존 없음 증명 |
| 호스트 검사 | `make test` = host_test 17 + fault_test 7 **통과(-Werror)** | 결정 논리·FDIR·ABSTAIN·stale·설정해시·**프로파일 재사용** 검증 |
| 결정성 | 동일 입력 → 동일 행동열(fault_test replay) | HITL/IV&V 불변식 |

→ **정책 코드는 bare-metal 준비가 됐다**: ~8KB flash, ~2KB RAM, 힙·stdio 없음, FPU 로 float 3콜,
결정론적. 남은 것은 **드라이버(HAL)·타이밍·전원·인증**이지 정책 코드가 아니다.

---

## 2. HAL 계약 — 통합자가 구현할 경계 (이것만 채우면 fw 가 돈다)

fw 는 관측을 **어떻게** 얻는지 모른다. 드라이버가 매 스텝 `Blackboard` 를 채우고 `fw_agent_step`
을 부른다. 계약은 세 함수·네 입력 구조·한 출력이다.

```c
#include "agent.h"
Agent a;
fw_agent_init(&a);                 /* 1회: BT 구성·상태 0 */
a.bb.cfg = (Config){ .confirm_n=2, .confirm_th=0.6f, .nis_gate=24.0f,
                     .cmpc_min=2, .require_live=true };   /* 튜닝(POLICY.md §3) */

for (;;) {                         /* 제어 주기마다 (예: 10 Hz) */
    /* ── 드라이버가 채운다 (HAL 경계) ── */
    for (i=0;i<FW_N_SENSOR;i++) {  /* 센서 순서: RGB,THERMAL,LIDAR,SAR,AUDIO */
        a.bb.obs[i]   = (SensorObs){ .evidence=..., .x=..., .y=..., .present=... };
        a.bb.health.health[i] = ...;      /* 0=죽음..1=정상 (FDIR 입력) */
    }
    a.bb.live  = (LiveObs){ .present=..., .x=..., .y=... };   /* mmWave 생체 레이더 (POLICY §2④) */
    a.bb.world = (WorldState){ .battery=..., .collision_risk=..., .position_error=...,
                               .gps_valid=..., .imu_valid=..., .actuator_ok=..., .t=k };
    /* ── 결정 ── */
    Action act = fw_agent_step(&a);   /* NONE/SEARCH/APPROACH/INSPECT/RETURN/AVOID/RELOCALIZE/EMERGENCY/ABSTAIN */
    /* ── 비행제어가 act 를 웨이포인트/거동으로 옮긴다 (PX4/ArduPilot) ── */
    fc_execute(act, a.bb.belief.px, a.bb.belief.py);
}
```

**누가 무엇을 채우나 (센서→obs 어댑터, `sar/HW_DESIGN.md` §1 센서표와 1:1):**

| Blackboard 입력 | 채우는 주체(HW) | 비고 |
|---|---|---|
| `obs[RGB/THERMAL]` evidence·x·y | 엣지 NPU 사람탐지기(EO+열) → 격자좌표 | 학습 지각은 정책 밖 |
| `obs[LIDAR/SAR/AUDIO]` | 해당 센서 드라이버 | 없으면 present=false |
| `health[i]` | 센서 self-test·watchdog | FDIR 입력 |
| `live` | **60 GHz FMCW mmWave 레이더**(호흡·심박 micro-Doppler) | **§4 gap: 미통합** |
| `world.battery` | 전력계 | RETURN/EMERGENCY 트리거 |
| `world.collision_risk` | depth/LiDAR·근접 | AVOID 트리거 |
| `world.gps_valid/imu_valid` | GNSS/IMU 헬스 | RELOCALIZE 트리거 |
| `world.actuator_ok` | ESC/모터 피드백 | 안전 정지 트리거 |

출력 `Action` + `belief.px,py`(격자) → 비행제어. 격자↔실좌표는 GNSS+DEM georegistration
(`sar/HW_DESIGN.md` §5). **fw 는 모터를 직접 안 돌린다** — 행동을 고를 뿐, 실행은 오토파일럿.

---

## 3. 칩 분담 (sar/HW_DESIGN.md 확정) — 안전은 학습·링크 밖

```
 엣지 NPU (Jetson Orin/Hailo)      비행 MCU (STM32H7/PX4)              독립 RTA (같은 MCU)
   사람탐지기(EO+열) ─ obs ─▶   fw_agent_step (POLICY.md)  ─ Action ─▶  RTA/geofence/RTL
   (유일한 학습 조각)           힙·재귀 없음·결정적·~2KB RAM          링크·NPU 죽어도 산다
```

- **perception = 학습(NPU)**, **정책 = 결정적(MCU, fw)**, **안전 = RTA(링크·NPU 무관)**.
- NPU 가 죽으면 belief 갱신만 멈추고 비행·RTA 는 유지. 링크(Discord/LTE)는 명령·감시용이지
  비행-임계 루프가 아니다(비행 루프는 온보드에 닫힘).

---

## 4. Fidelity ladder 상태 + gap 목록 (심각도·주인)

`fw/다음세션_계획_VFIELD.md` 의 L0–L5 사다리에 이번 세션 결과를 얹는다.

| 계단 | 무엇 | 상태 |
|---|---|---|
| L0–L2 Verification(시뮬) | 결정 논리·CMPC·FDIR·liveness·경계지도 | **✓ 확보**(README·경계지도·POLICY) |
| L3 high-fidelity sim(HW 없이) | 실 위성 imagery 텍스처·센서모델 V&V·HITL 코드준비 | ◔ 부분(실 DEM·3D 렌더 O; 모델 V&V·imagery 주입 남음) |
| L4 field validation(HW 필요) | 실 센서·실 decoy/clutter·**실 생체 레이더로 전-서명 decoy 거부** | ✗ |
| L5 system validation | fw 를 실 MCU 에 cross-gcc+HAL → HITL → 비행 | ✗ |

**gap 목록(정직):**

| # | gap | 심각도 | 주인 | 닫는 법 |
|---|---|---|---|---|
| G1 | **mmWave 생체 레이더 미통합** — liveness(POLICY §2④)의 실 센서. 없으면 전-서명 decoy 거부가 시뮬로만 실증 | **높음** | HW | 60GHz FMCW 페이로드 + `live` 어댑터, L4서 실 decoy 거부 실측 |
| G2 | **ARM 크로스빌드 미실시** — 이 컨테이너에 `arm-none-eabi-gcc` 없음 | 중 | 빌드 | §5 명령으로 타깃 .elf 생성 + 정적 스택/타이밍 분석 |
| G3 | **NPU 사람탐지기 미실측** — `obs.evidence`(p_useful)가 대표 곡선. 항공 top-down 탐지 병목 | **높음** | 지각 | SAR 학습데이터(HERIDAL/SARD)로 학습, 현장 캘리브(`policy_core/CALIBRATION.md`) |
| G4 | **단일 가설 belief** — 표적 다수서 하나만 claim | 중 | 정책 | 다가설(MHT)·belief 확장(설계 변경) |
| G5 | **사람 vs 동물** — 둘 다 생체라 미세도플러로도 못 가름 | 낮음(정직 표기) | 정책 | 외양/의미 판별(다음 축) |
| G6 | **타이밍·전원·인증** — 실시간 마진·워치독·FDIR 커버리지 증명 미실시 | **높음** | 시스템 | NPR 7150.2 high-fidelity sim(동일 processor/timing/memory) + 비행 인증 |
| G7 | **BVLOS 규제** — 가시선 밖 비행 승인 | 높음 | 운용 | 국내 특별비행승인; 데모는 가시선/허가 구역 |

---

## 5. 지금 당장 할 수 있는 bring-up (HW 없이, L3 접근)

1. **타깃 크로스빌드(G2).** 정책 C 는 freestanding 통과 확인됨. 툴체인만 있으면:
   ```
   arm-none-eabi-gcc -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard \
       -std=c99 -Os -ffreestanding -Wall -Wextra -Werror \
       -c blackboard.c estimator.c evidence.c bt.c event.c safety.c arbiter.c decision.c planner.c agent.c \
          profile_sar.c    # 커널 10 + 도메인 프로파일 1개(새 프로젝트는 자기 profile_<도메인>.c 로 교체)
   ```
   libm 3콜(`sqrtf`·`fabsf`)은 타깃 libm 또는 CMSIS-DSP 로 링크. 그 뒤 `-fstack-usage` 로 스택
   상한, `size` 로 flash/RAM 확정.
2. **모델 V&V 먼저(G3 전제).** `sar/sensors_ref.py` 물리모델(Planck·Koschmieder·LiDAR·GNSS·Audio)을
   센서 스펙시트/문헌값에 대조하는 원장 — 시뮬 신뢰성의 전제.
3. **HITL 스텁.** `fw_agent_step` 를 실 센서 로그 재생으로 구동(결정성은 fault_test 로 이미 확인).

---

## 6. 정직 — 아직 못 하는 것

- **실비행 인증 아님.** 실 STM32/ESP32 HAL·인터럽트·실시간 타이밍·전원 마진·FDIR 커버리지 증명은
  안 했다(§4 G6). host/freestanding 검사는 **결정 논리의 행동만** 잰다.
- **liveness 는 시뮬 실증.** 전-서명 decoy 를 실제로 거르는 것은 실 생체 레이더(G1)의 L4 몫.
- **비행 명령은 사람이 승인한다.** 이 저장소의 intent 게이트(공개 채널서 승인 불가) 그대로.
- 이 문서는 **bring-up 계약·gap 지도**이지 감항 증명이 아니다.
