# 학습 가치 head + 결정적 RTA 봉투 (아키텍처 ②)

정책의 **판단 보강 한 조각만 학습**에 맡기고, belief 수학·안전(RTA)은 결정적으로 남긴다.
"부정확한 상태에서의 판단을 LLM(선택적 SSM)에 맡긴다"는 것을 **안전을 우회하지 않는 형태**로
구현한 것. 코어는 학습 백엔드를 모른다(`PC_ValueHead` 함수포인터만 본다).

## 왜 이 자리인가 — 측정이 가리킨 병

`policy_core` 의 greedy 는 두 가지를 **측정으로** 드러냈다(RESULTS.md):
- **freeze**: 확산 prior 에서 근시안 greedy 는 제자리(이동 0셀). `cost_uncert_pow` 로 완화했으나
  근본은 value-to-go 부재.
- **myopia**: 한 스텝 EV 만 봐 국소 최적에 갇힘. `la2`(2-스텝 lookahead)는 여기서 오히려 조금
  졌다(84.4 greedy vs 83.8 la2) — 얕은 lookahead 의 tail 추정(greedy value-to-go)이 거칠어서다.

**학습 가치 head 의 자리는 바로 그 tail 추정이다.** lookahead 가 leaf(첫 이동 후 belief)에서
쓰는 value-to-go 를 greedy 대신 학습된 `V(문맥, leaf)` 로 바꾼다 — AlphaZero 식 "탐색+학습 가치".

## 무엇을 학습에 맡기고, 무엇을 안 맡기나

| 조각 | 결정적/학습 | 근거 |
|---|---|---|
| belief 갱신(베이즈) | **결정적** | 검증 가능·재현. 학습이 확률을 왜곡하면 못 잡는다 |
| J = αEV − βT − γE | **결정적** | 목적함수는 명시적이어야 값을 잰다 |
| RTA keep-out/속도상한 | **결정적, 무조건 최후** | 안전은 학습 밖. `pc_rta_filter` 가 선택 후 항상 적용 |
| **value-to-go(tail)** | **학습(선택)** | freeze·myopia 를 원리적으로 흡수. 여기만 |

## 합성 수식 (`pc_policy_step_val`)

각 첫 이동 후보 c 에 대해:
```
J1(c)   = restricted greedy J at c        (센서·τ 는 greedy 로 고름)
b1      = belief 를 c 에서 '기대 미탐지'로 갱신 (leaf)
J2(c)   = greedy value-to-go at b1        (기존 la2 의 tail)
V(c)    = value_head( 지속문맥, feat(b1) ) (학습 tail)
tail(c) = (1-λ)·J2(c) + λ·V(c)
total(c)= J1(c) + disc·tail(c)
```
`argmax_c total(c)` 로 첫 이동 선택 → **RTA 적용** → 행동.

**하위호환 불변식**: `λ=0` 또는 `vh==NULL` ⇒ `tail=J2` ⇒ `pc_policy_step_la2` 와 **비트동일**.
`pc_policy_step_la2` 는 실제로 `pc_policy_step_val(...,vh=NULL)` 로 위임한다(구조적 보장).
`host_test` 가 이것과 "head 가 실제로 첫 이동을 바꾼다(죽은 코드 아님)"를 함께 잠근다.

## PC_ValueHead 계약 (안전의 핵심)

```c
float (*value)(const void *state, const float *feat, uint8_t n_feat);   /* 순수 읽기 */
void  (*advance)(void *state, const float *feat, uint8_t n_feat);       /* 지속 전진 */
```
- **`value()` 는 순수**: 지속상태(실제 궤적의 이력 문맥)를 읽되 **갱신하지 않는다.** lookahead 가
  후보 leaf 를 여럿 점수매겨도 재귀가 오염되지 않게 — 백엔드는 상태를 복사해 한 스텝 돌리고
  버린다. 이 성질을 `ssm/fw/host_test` 가 확인한다(value 전후 `‖h‖²` 불변).
- **`advance()`** 는 실제로 커밋된 관측주기마다 호출해 이력 문맥을 전진시킨다.
- **`feat`**: 코어가 뽑은 센서-무관 belief 요약(`pc_belief_features`). 백엔드는 의미를 몰라도 됨:
  `[0]`=H_norm(확산=freeze 신호), `[1]`=첨두확률 p*, `[2]`=목적지belief/첨두 비율, `[3]`=예산.

## 백엔드: 선택적 SSM(Mamba 원자) — `ssm/fw/ssm_value.c`

가치 head 를 `ssm/fw` 커널(입력변조 1차 IIR 뱅크)로 채운다. 지속 `SSM_State` = 이력 문맥,
`value()` 는 그 상태를 복사해 한 스텝(순수), `advance()` 는 지속상태 전진. 스칼라 읽기 = `y[0]`
(실제 학습 head 는 `w_out·y`). MLP 등 다른 백엔드로 바꿔도 코어 불변.

## 학습·배포 흐름

```
오프디바이스(GPU): 시뮬 rollout/TD 로 V(문맥,leaf) 학습 → 가중치 export(const 배열)
                                    ↓
온디바이스(MCU): ssm/fw 커널이 그 가중치로 추론(힙/재귀 없음). policy_core 결정적 뼈대 안.
```

## 한계 — 아직 학습 전 (과장방지)

- **학습 가중치가 없다.** 지금 코드는 *배선·순수성·결정성·liveness* 만 붙든다. `λ`는 학습 전
  **0 으로 둔다** — 안 잰 이득을 켜지 않는다.
- **성능 주장(예: "freeze/myopia 개선")은 학습·측정 후에만.** `sim` 에 SSM head 를 아직
  안 물렸다 — 미학습 가중치로 낸 성공률은 뜻이 없으므로(과장방지 규칙 2: 성한 동작점서만
  잰다) 일부러 측정을 미룬다.
- 측정할 때는 **독립 대조**(λ 스윕: 0=la2 기준선, 그 위 개선폭)와 **사소한 설명 배제**
  (head 가 상수만 내면 argmax 불변 → liveness 로 이미 배제)를 붙여 RESULTS.md 에 적는다.
