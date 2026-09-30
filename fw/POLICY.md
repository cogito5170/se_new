# 정책 명세 — LLM 없는 자율 SAR 결정 executive (`fw/`)

이 문서는 `fw/`(bare-metal C99 결정 executive)의 **정책 명세**다. 각 조항은 실제 코드 동작에 대응하고,
구현 안 된 것·알려진 gap·시뮬 실증에 그친 것은 **정직히 표시**한다. 근거: `fw/README.md`(층·V&V) ·
`fw/경계지도.md` · `sar/`(독립 심판) · `fw/HW_BRINGUP.md`(HW gap) · 실측.

> **왜 이 정책인가:** 생사가 걸린 SAR 자율 결정은 재현·감사·인증 가능하고 가짜에 안 속아야 하는데,
> 학습된 블랙박스는 원리적으로 그럴 수 없다. 그래서 학습(perception)은 신뢰 못 할 부품으로 격리하고,
> **결정 척추는 학습 없이 결정론적으로** 짰다. 같은 입력 → 같은 행동열(외부 검증 가능).
>
> **이 문서는 SAR 도메인 *프로파일*(`profile_sar.c` = `FW_PROFILE_SAR`)의 명세다.** fw 는 도메인 종속
> 정책이 아니라 **정책을 세우는 도구**다 — 도메인 무관 커널(추정·증거융합·BT·중재·FDIR·결정성)과 도메인
> 프로파일(`PolicySpec`)이 갈려 있고, 새 프로젝트는 커널을 안 건드리고 프로파일만 꽂는다. 작성법·경계는
> **`fw/POLICY_TOOLKIT.md`**. 아래 조항은 SAR 프로파일이 그 커널 위에서 무엇을 정하는가이다.

행동 집합(구현): `NONE · SEARCH · APPROACH · INSPECT · RETURN · AVOID · RELOCALIZE · EMERGENCY · ABSTAIN`
(`blackboard.h` `Action`). 안전상태: `NORMAL · DEGRADED · RETURN · EMERGENCY`.

---

## §0. 시스템 경계 (System Boundary)

- **perception = 신뢰 못 할 부품(untrusted).** "저 관측이 사람인가"는 학습(NPU)이 답하고 **정책 밖**이다.
  정책은 그 출력(`obs[i].evidence` 0..1·위치주장)을 **증거로만** 받고, 그 자체를 진실로 믿지 않는다.
- **executive = 안전임계 결정층(safety-critical).** 학습 없이, 힙·stdio 없이, 결정론적으로 행동을 고른다
  (~8KB .text·~2.3KB RAM·freestanding `-Werror`, `HW_BRINGUP.md` §1).
- 경계 계약: 드라이버가 `Blackboard`(obs·health·world·live)를 채우고 `fw_agent_step` 을 부른다
  (`HW_BRINGUP.md` §2). perception·링크·구동은 executive 밖이다.

---

## §1. 임무 정책 (Mission Policy) — 행동 primitive

| 행동 | 언제 | 근거(코드) |
|---|---|---|
| **SEARCH** | 표적 미확정·탐색. 위험하면 접근 대신 여기로 강등 | `decision.c`·`safety_filter`(collision≥0.5 시 APPROACH→SEARCH) |
| **APPROACH** | `target_conf>0.5` & collision<0.5 & battery>0.25 → 접근 | `arbiter.c` precondition |
| **INSPECT** | `confirmed` & collision<0.5 & battery>0.3 → 정밀관측(최고가치) | `arbiter.c`(U=1.0·conf) |
| **RETURN** | battery<0.25 → 귀환 | `safety.c` `FW_BATTERY_RETURN` |
| **AVOID** | collision_risk≥0.80 → 무조건 회피(근접 반사) | `safety.c` `FW_COLLISION_HARD` |
| **RELOCALIZE** | `!imu_valid`(또는 측위 신뢰 상실) → 재정렬, **전진 금지** | `safety_filter` |
| **EMERGENCY** | battery<0.10 또는 충돌 임박 → 비상 | `safety.c` `FW_BATTERY_EMERG` |
| **ABSTAIN** | 후보(conf>0.5)인데 확인이 못 붙는 스텝이 `FW_ABSTAIN_N`(4) 이상 → 사람이라 **확정 거부** | `decision.c` `cond_abstain`·`belief.unconf_run` |
| **NONE** | `!actuator_ok` → 안전 정지(실행 불가) | `safety_filter` |

- **ABSTAIN 은 이제 별도 primitive 다(구현).** liveness 부재·CMPC 미달·운동 모순처럼 확인이 **원리적으로
  막힌** 후보를 지속 관측하면(`unconf_run ≥ FW_ABSTAIN_N`), NONE/SEARCH 와 **구분되는** 명시적 "확정
  거부"를 낸다(BT `cond_abstain`, `host_test` #15). 확인이 쌓이는 중(`confirm_run>0`)이면 리셋 —
  정상 확인 지연을 기권으로 오인하지 않는다. 실 임무층은 ABSTAIN→후보 거부·재탐색으로 옮긴다.

---

## §2. 증거 정책 (Evidence Policy) — decoy 를 사람으로 확정하지 않는다

한 표적을 **confirmed** 로 올리려면 동시에(`evidence.c`):

| 속성 | 뜻 | 기전(코드/설정) |
|---|---|---|
| **fresh** | 최근 갱신(오래된 관측으로 확정 안 함) | `belief.age` |
| **valid** | 관측 존재 + 센서 건강 | `obs.present`·`health[i]`(0=죽음, 융합서 배제) |
| **consistent** | 교차모달 물리 일치 | **CMPC** `cfg.cmpc_min`(≥2 채널; 가림-강 채널만이면 조건부 1) |
| **persistent** | 연속 확인창 통과 | `cfg.confirm_n`(기본 `FW_CONFIRM_N=3`)·`confirm_th`(0.60)·`confirm_run` |
| **liveness-supported** | 생체 신호 근접(§6) | `cfg.require_live` & `live.present` |
| **contradictory** | 운동 모순이면 **버린다** | **NIS 게이트** `cfg.nis_gate`(기본 24; NIS 초과 측정 제외) |
| **stale** | 값 얼어붙음(frozen)·bit동일 반복 | **차등 검출(구현)** — 다른 채널이 변할 때 얼어붙은 채널만 격리(`fw_stale_update`·EV_SENSOR_STALE) |

네 조건(CMPC + 시간확인 + NIS + require_live)을 다 통과해야 사람이라 주장한다. 하나라도 못 채우면
**후보로 접근·정밀관측(INSPECT)** 하되 **확정하지 않는다**; 확인이 지속적으로 막히면 **ABSTAIN**(§7).

**stale 검출은 차등이다(정직한 경계):** 한 채널이 byte-동일로 `FW_STALE_N`(5) 스텝 얼어붙고 **다른 present
채널은 변하면** 그 채널을 stuck 으로 격리한다(융합 제외+EV_SENSOR_STALE). 그러나 **'모두-정지'**(변하는
기준 채널이 없음)는 못 가른다 — 정지한 **실표적**과 정지 가짜를 반복만으로는 구분할 수 없기 때문이다
(정지 실표적을 죽이면 안 된다). 그 경계는 오직 **§6 liveness** 로만 닫힌다(`fault_test` #6 잔여 gap·#7 차등).

---

## §3. 안전 불변식 (Safety Invariants) — 어떤 결정도 이걸 못 어긴다

`safety_filter` 가 arbiter 결정 위에 **하드 override**(`safety.c`). 우선순위 순:

1. **actuator 제약**: `!actuator_ok` → NONE(안전 정지). *(주의: `fw_bridge_step` 은 이 입력 미노출 —
   네이티브 `fault_test.c` #5 만. `OCEANWATERS.md` P-03.)*
2. **collision 제약**: `collision_risk ≥ 0.80` → AVOID.
3. **energy 제약**: battery<0.10 → EMERGENCY, battery<0.25 → RETURN.
4. **localization 제약**: `!imu_valid`(측위 신뢰 상실) → RELOCALIZE, **추측항법 위 전진 금지**.
5. **sensor 제약**: 죽은 센서는 health→0 으로 융합서 배제, 과불확실(공분산 상한 초과) → 행동 금지.

이 불변식은 결정 논리에 버그가 있어도 마지막에 걸리는 방어선이다(§8 우선순위의 최상단).

---

## §4. 위험/FDIR 정책 (Hazard / FDIR Policy)

`safety.c` 가 cFS/FDIR 형식으로:

- **fault detection**: 충돌·저전력·센서 죽음·구동계·공분산 폭발 감시 → 이벤트.
- **isolation**: 죽은 센서(health→0)를 융합서 격리. 죽은 센서 ≥2 → DEGRADED.
- **degradation**: `SAFE_DEGRADED`(imu/gps 무효 또는 센서 다수 죽음) — 능력 낮춰 계속.
- **recovery**: 측위는 RELOCALIZE 로 재정렬. *(immobilization 복구(도랑)는 fw 밖 — 모션층,
  `ROVER_VALIDATION.md` §4.5.)*
- **safe-state transition**: `NORMAL→DEGRADED→RETURN→EMERGENCY`(`SafetyState`). 전이는 §3 임계로 결정론적.
- **stale/frozen 검출**: `fw_stale_update` 가 융합 전에 차등 freeze 를 잡아 stuck 채널을 격리(§2, `fault_test` #7).

**⚠ 남은 FDIR gap(정직):** **모두-정지**(변하는 기준 없음)와 bias 센서는 여전히 통과한다(§2·`fault_test` #6·R-04).
구동계 고장은 `fault_test.c`#5, 모두-정지 잔여 gap 은 #6 이 네이티브로 박아 둔다.

---

## §5. 시간 정책 (Temporal Policy)

- **persistence**: 연속 `confirm_n` 스텝 `confirm_th`(0.60) 초과라야 confirmed(`confirm_run`).
  플리커·transient clutter(매 스텝 새 위치)를 거른다.
- **timeout**: `belief.age` 가 커지면(갱신 없음) 신뢰·확인 소멸 — 오래된 관측으로 행동 안 함.
- **hysteresis**: confirmed 진입/이탈에 확인창을 둬 경계에서 떨림 방지(단일 임계 아님).
- **confirmation window**: `confirm_n`. 스윕(held-out 지리산 실 DEM)에서 **N=2 가 transient clutter
  균형점**(오경보 baseline 의 1/3~1/8)이었다(기본 매크로는 3, 런타임 설정 가능 `Config`).

대가(정직): 확인창을 키우면 탐지 지연↑·실탐 놓침(FN) 가능. 표는 `fw/README.md`.

---

## §6. Liveness 정책 (Liveness Policy) — 전-서명 decoy 를 거르는 유일한 축

- **liveness evidence**: RF 미세도플러 심폐 신호(호흡·심박). 따뜻한 바위·동물·고착 센서는 열·외양·
  정지성이 같아도 **생체 미세운동이 없다** → §2 의 stale/persistent gap 을 여기서 닫는다.
- **liveness unavailable**: `cfg.require_live` 인데 `live.present` 아님 → **확정 보류(ABSTAIN)**, 접근·관측만.
- **liveness contradiction**: 생체신호가 belief 위치와 안 맞으면 확인에 못 쓴다.
- **NEVER: absence = non-human.** liveness 부재는 **"사람 아님의 증거가 아니다"** — 가려짐·거리·자세로
  신호가 안 잡힐 수 있다. 그래서 부재는 **"사람이라 확정하지 않음"**(보류)이지 **"비-사람이라 확정"이 아니다.**
- **실측(정직):** `sar/liveness_ref.py`(n=400, SNR 6dB) 정지 사람 vs 정지 온난 decoy 분리도
  **AUC 0.977 · 대칭 D_KL 16.5 nats.** 모델 x(t)=A_r sin2πf_r t + A_h sin2πf_h t, φ=(4π/λ)x,
  z=위상대역에너지[0.15,2]Hz. `sar/observable_stack.py` Z_min(E): 정지 사람 vs 온난 decoy 는 **오직
  미세도플러로만** 갈린다(열·운동 불가). 사람 vs 동물은 못 가름(둘 다 생체 — 잔여 사각).
- **⚠ 시뮬 실증만.** 실 mmWave 생체 레이더(60GHz FMCW) 미통합(`HW_BRINGUP.md` G1) — L4 현장 몫.

---

## §7. 미지/기권 정책 (Unknown / Abstention Policy)

- **unknown**: §2 네 조건 중 하나라도 못 채우면 사람이라 주장하지 않는다(미확정).
- **hold / additional observation**: 확정 전엔 후보를 접근·정밀관측(APPROACH/INSPECT)하며 증거를 더 모은다.
- **abstain**: 확인이 지속적으로 막히면(`unconf_run ≥ FW_ABSTAIN_N`) 명시적 **ACT_ABSTAIN**(확정 거부, §1).
  NONE/SEARCH 와 구분되는 별도 행동이다 — "관측했으나 사람이라 확정하지 않음"을 트레이스에 남긴다.
- **return**: 자원 제약(§3 energy)이면 RETURN. 임무층은 ABSTAIN·reject_after 로 후보 거부(FP)하고 탐색 복귀.
- 원칙: **의심스러우면 확정하지 않는다.** 거짓 확정(사람 아닌 걸 사람이라)이 미확정보다 위험하다.

---

## §8. 중재 정책 (Arbitration Policy)

**안전 > 고장보호 > 임무목표 > 효율** (`arbiter.c` + `safety_filter`):

1. **safety(§3) 하드 override** 가 최상단 — 어떤 임무 효용도 못 뒤집는다.
2. 그 아래에서 precondition 만족 행동 중 **효용 argmax**:
   `U = mission − 1.0·collision − 0.3·energy − uncert`.
   mission: INSPECT=1.0·conf · APPROACH=0.7·conf · SEARCH=0.35 · RELOCALIZE=0.4·pos_err · RETURN=0.2.
3. BT 제안이 precondition 을 만족하면 그대로 존중(우선순위 selector), 아니면 효용 최대로 대체.

즉 효율(에너지)은 언제나 최하위 — 안전·고장보호·임무가 다 만족될 때만 가른다.

---

## §9. 결정성 정책 (Determinism Policy)

- **동일한 완전 상태 + 이벤트 + 설정 → 동일한 결정 트레이스.** 부동소수 재현 가능, 힙·난수 없음.
- 이것이 **IV&V 불변식**이다: `fault_test.c` 가 같은 입력열을 재생해 같은 행동열을 확인한다(-Werror 통과).
- BT tick 은 정적 트리 깊이로 유계(재귀 스택 유계), malloc/printf 0건(`HW_BRINGUP.md` §1).

---

## §10. 설정 정책 (Configuration Policy)

- **threshold(구현):** `Config`(런타임) — `confirm_n·confirm_th·nis_gate·cmpc_min·require_live`.
  기본은 `evidence.h`/`safety.h` 매크로. 튜닝은 이 구조체로만(코드 재빌드 없이).
- **version(구현):** `Config.version` — 정책 설정 판번호. 브리지 `fw_bridge_set_version`.
- **hash(구현):** `fw_cfg_hash`(FNV-1a 32bit) — 같은 설정→같은 해시, 임계 하나만 바뀌어도 달라진다
  (`host_test` #16). 트레이스에 스탬프해 "어느 설정이 이 행동열을 냈나"를 §9 결정성 검증에 묶는다.
- **mission load:** 임무별 설정 = `Config` 채우고(setter) 판번호·해시로 스탬프하는 것. 브리지
  `fw_bridge_cfg_hash` 로 노출. (여러 임무 프로파일을 파일서 로드하는 상위 관리자는 통합자 몫.)

---

## §11. 런타임 감시 (Runtime Monitoring)

- **invariant monitor(구현):** `safety_filter` 자체가 매 스텝 §3 불변식을 강제한다 — 결정 버그의 마지막 방어선.
- **health monitor(구현):** `safety.c` FDIR 이 센서 건강·공분산·전력·충돌을 감시.
- **RTA·watchdog(fw 밖·시스템층, 정직):** Run-Time Assurance/geofence/RTL 과 워치독은 **비행 MCU·독립
  RTA 의 몫**이지 이 C 라이브러리 안이 아니다(`HW_BRINGUP.md` §3, `sar/HW_DESIGN.md` §3.3). 링크·NPU 가
  죽어도 비행·RTA 는 산다.

---

## §12. 독립 검증 (Independent V&V)

- **SUT ≠ truth**: `sar/`(참조세계·평가기)가 채점하고, 정책은 센서만 받고 truth 를 못 본다(공간 분리).
  `sar/ivv/fw_vv.py` 가 **실 C 코드**(libfw.so, ctypes)를 돌린다(파이썬 재구현 아님).
- **replay**: `fault_test.c` — 동일 입력 → 동일 행동열(§9).
- **fault injection**: `fault_test.c`(구동계·stale 등 6군데) + 외부 OceanWATERS 진짜 고장주입
  (`OCEANWATERS.md`, FDIR·전원 축).
- **adversarial scenarios**: decoy/clutter/지속 가짜(R-08)·경계지도의 gap 시나리오.
- **coverage**: host_test 16 + fault_test 7(-Werror 통과; ABSTAIN·설정해시·stale 차등검출 포함). 확인창 스윕(held-out 실 DEM).
- **evidence trace**: 행동열·안전전이·belief 를 telemetry 로 남겨 외부 검증.

---

## 부록 — 정직한 한계 (경계 밖)

- **단일 가설 belief**: 표적 둘이면 하나만 claim → 탐지율 상한이 눌린다(`HW_BRINGUP.md` G4).
- **정지·persistent·전-서명 가짜**: §6 liveness 로 **시뮬에서** 닫았으나 실 생체 레이더 없이는 실증 안 됨(G1).
  사람 vs 동물은 미세도플러로도 못 가름.
- **stale 는 차등만 검출**: 얼어붙은 채널을 '움직이는 기준' 대비 격리한다(구현). **모두-정지**(기준 없음)와
  bias 센서는 여전히 못 가른다 — 정지 실표적과 반복만으로 구분 불가라 §6 liveness 몫(§2·§4·`fault_test` #6).
- **시뮬 L2**: 실측 DEM+물리 센서모델이나 실 위성 imagery/실 센서 아님. 센서 모델 V&V(스펙시트 대조)
  미실시(G3). L3~L5는 `HW_BRINGUP.md`·`ROVER_VALIDATION.md` §6.
- **이동·구동은 fw 밖**: 조향·경로회피·도랑탈출은 모션/항법 층(`ROVER_VALIDATION.md` §4.5). fw 는 모드만 고른다.
- **인증된 실비행 시스템 아님.** 실비행 명령은 사람이 승인한다(intent 게이트).
