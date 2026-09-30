# 정책 tool — 새 프로젝트에서 fw 커널 재사용하기

`fw/` 는 **한 도메인의 정책**이 아니라 **정책을 세우는 도구**다. 도메인 무관 **커널**(추정·증거융합·
BT 엔진·중재 argmax·FDIR·stale 검출·결정성·설정해시)과, 도메인의 **프로파일**(`PolicySpec`)이 갈려 있다.
새 프로젝트는 **커널을 한 줄도 안 건드리고** `PolicySpec` 하나만 채워 꽂는다. SAR 는 그 프로파일의 하나일 뿐.

OceanWATERS 에서 드러난 P-01(fw 의 SAR 행동집합이 착륙선에 대응물 없음)이 이 분리로 풀린다 — 착륙선은
자기 프로파일을 쓰고 같은 안전·추정·결정성 척추를 재사용한다.

## 커널 vs 프로파일 (경계)

| 커널(그대로 재사용, `fw/` 손 안 댐) | 프로파일(도메인이 채움, `profile_<도메인>.c`) |
|---|---|
| `estimator.c` Kalman · `bt.c` BT 엔진 · `event.c` 큐 | 행동 집합·이름 (`n_actions`, `action_names`) |
| `evidence.c` 융합수학(soft-vote·무게중심·시간확인·NIS·공분산가드·stale·ABSTAIN 카운터) | 우선순위 트리 `build_bt` |
| `arbiter.c` precondition+효용 **argmax** | `precondition` · `utility`(에너지 포함) |
| `safety.c` 건강엣지 FDIR·stale 검출 | 안전 불변식 `safety_filter`·`safety_update`(임계·상태전이) |
| `decision.c` BT tick · `agent.c` 루프 | 계획 진행/재계획 `plan_update` |
| 결정성·`fw_cfg_hash` 설정해시 | 지각 가중 `vote_w`·CMPC 채널역할 `blocked_mask`/`allw_mask` |

## 새 프로파일 짓는 3단계

1. **`profile_<도메인>.c` 를 쓴다** — `PolicySpec` 하나를 채운다(예시: `profile_min.c`, 참조: `profile_sar.c`).
   행동 id 는 정수 공간(0..n_actions-1)이고 이름·의미는 프로파일이 정한다(같은 정수, 다른 도메인).

   ```c
   #include "policy_spec.h"
   #define D_HOLD 0
   #define D_GO   1
   #define D_STOP 2
   #define D_N    3
   static const char *const D_NAMES[D_N] = { "HOLD", "GO", "STOP" };
   static const float D_VOTE_W[FW_N_SENSOR] = { 1.0f, 0.5f, 0, 0, 0 };

   static void   d_build_bt(BtTree *t) { /* SELECTOR[SEQ[cond→행동]...] — profile_sar.c 참조 */ }
   static bool   d_precond(const Blackboard *bb, int a) { return true; }
   static float  d_utility(const Blackboard *bb, int a) { return a==D_GO ? bb->belief.target_conf : -1e30f; }
   static int    d_filter(const Blackboard *bb, int p)  { return bb->world.battery<0.1f ? D_STOP : p; }
   static void   d_safety(Blackboard *bb, EventQueue *q){ bb->safety = bb->world.battery<0.1f?SAFE_EMERGENCY:SAFE_NORMAL; }
   static void   d_plan(Blackboard *bb) { bb->mode = MODE_SEARCH; }

   const PolicySpec FW_PROFILE_D = {
       .name="my-domain", .n_actions=D_N, .action_names=D_NAMES,
       .act_none=D_HOLD, .act_fallback=D_GO,
       .build_bt=d_build_bt, .precondition=d_precond, .utility=d_utility,
       .safety_filter=d_filter, .safety_update=d_safety, .plan_update=d_plan,
       .vote_w=D_VOTE_W, .blocked_mask=0u, .allw_mask=0u,
   };
   ```

2. **꽂는다** — `fw_agent_init_profile(&agent, &FW_PROFILE_D);` (기본 `fw_agent_init` 은 SAR). 끝. 커널 루프
   (`fw_agent_step`)·추정·안전 척추·결정성·설정해시가 그대로 이 도메인 위에서 돈다.

3. **드라이버가 `Blackboard` 를 채운다** — 센서→`obs[]`·`health[]`·`live`·`world`. HAL 계약은 `HW_BRINGUP.md` §2.
   행동 출력(`fw_agent_step` 반환 정수 id)을 도메인 액추에이터/어댑터로 옮긴다.

## 무엇이 자동으로 딸려 오나 (공짜로 재사용)

- **네 방어축**: 시간(확인창)·운동(NIS)·FDIR·liveness — evidence 융합에 내장(프로파일은 `require_live` 등 Config 로 켠다).
- **ABSTAIN**: 확인 못 붙는 후보 거부(프로파일이 그 행동 id 를 트리에 넣으면).
- **stale 차등 검출**·**설정 해시**·**결정성 replay**·**공분산 폭발 가드** — 전부 커널.

## 정직한 경계

- 행동 id 공간 상한은 `ACT_N`(현재 9). 더 필요하면 enum 확장(커널 변경 아님, id 공간만).
- 센서 채널 상한은 `FW_N_SENSOR`(현재 5). 프로파일은 그 이하를 `vote_w`·마스크로 쓴다.
- 프로파일 vtable 은 `const`(`.data.rel.ro`, 읽기전용→flash) — 가변 전역 아님(`.data/.bss` 여전히 0).
- 커널이 도메인에 대해 아는 것은 이 vtable **뿐**이다. 도메인 상수를 커널에 하드코딩하면 이 분리가 깨진다 — 하지 말 것.
- `tests/`(host_test #17)가 SAR 아닌 `FW_PROFILE_MIN` 을 같은 커널로 돌려 재사용을 잠근다.
