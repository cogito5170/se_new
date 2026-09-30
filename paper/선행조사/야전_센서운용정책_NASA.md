# 선행조사 — 야전 센서 운용 정책 (NASA 근거의 열화-상황 임무-인지 센서 관리)

요청(사용자): "야전에서 RGB→Thermal→LiDAR 를 언제 켜라" 하나짜리 NASA 매뉴얼은 없다. 대신
policy 를 구성할 NASA 연구가 여러 갈래로 있으니 그것을 근거로 **Mission-aware sensor
management under degradation** 을 짓는다. 효용 U_i = ΔP(탐지|i)/T_i − λE_i − μC_i, U_i>U_현재면 모드 전환.

## 아키텍처 (사용자 확정) — sar 는 심판, 정책은 선수

**`sar/` 는 검증 환경(절대 레퍼런스)** 이다 — 어떤 정책에도 심판으로 쓴다(숨은 truth·독립 물리·
evaluator). **정책은 sar 안에 두지 않는다.** 두 후보 정책을 **하나의 시나리오**에서 sar 가 채점한다:

```
                 sar/ (검증 환경 = 절대 레퍼런스: reference 숨은 truth + evaluator)
                              │  하나의 공유 시나리오(예: 태백산 안개·수관)
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                      ↓
  NASA 방법론 정책 (M0)   ctrl/+ssm Mamba (M1)   [베이스라인 greedy]
        └─────────────────────┼─────────────────────┘
                              ↓  같은 evaluator·같은 truth 로 채점
                       가장 좋은 것을 채택
```

## 무엇을 짓기 전인가

`ivv/policy_nasa.py` — NASA 방법론 정책(선수 M0): 센서를 손규칙이 아니라 S4 식 **다목적 효용**
(탐지이득 대 시간·에너지·비용, T_i 는 measure.py 실측 지연 SAR≈RGB의 15배)으로 고르고, health/fault
게이팅·executive 히스테리시스·contingency 를 한다. 관측만 받는다(truth 못 봄 — IV&V 독립).
`ivv/compare.py` — 하나의 시나리오에서 M0·Mamba·베이스라인을 sar 레퍼런스로 **같은 지표 채점**.

## 정직한 성격 — 이것은 **NASA 개념의 이식이지 NASA 공식식이 아니다**

효용식 U_i 는 **우리 연구용 formulation** 이다(NASA 공식 수식이 아님). NASA 가 센서 선택에서
성능·coverage·cost·weight·reliability·fault-diagnosis 같은 상충 목적을 **조합최적화**로 다룬다는
근거(S4) 위에 얹은 것이다. 그래서 "AI 가 알아서 고른다"보다 방어하기 쉽다는 것이 요지이지,
새 이론 주장이 아니다(과장방지). 인용은 사용자 문서지도의 NTRS ID·요약뿐 — 원문 전문 미열람 → [출처:조각].

## 찾아본 질의

- `NASA systematic sensor selection strategy S4 combinatorial optimization`
- `NASA sensor health management fault diagnosis autonomous UAS Bayesian`
- `NASA variable autonomy executive UAS mode change diagnostic reasoner`
- `NASA autonomous contingency detection reaction unmanned aircraft`
- `NASA STORM search technology optimal rescue infrared microphone sequencing`
- `NASA STEReO ACERO DRCS disaster response UAS concept of operations`

## 가장 가까운 선행연구

| 무엇 | 출처(NTRS/URL) | 역할(우리 정책의 어느 조각) |
|---|---|---|
| Systematic Sensor Selection Strategy (S4) | NTRS 20120003357 [출처:조각] | 다목적(성능·coverage·cost·weight·reliability·fault) 센서 조합 → **효용 U_i 근거** |
| Sensor/SW Health & Safety Management for Autonomous UAS | NTRS 20150021506 [출처:조각] | 신호품질·Bayesian fault diagnosis → **신뢰 게이팅** |
| Design Considerations for a Variable Autonomy Executive (UAS) | NTRS 20180004247 [출처:조각] | diagnostic reasoner 불일치 → active mode change → **executive 히스테리시스** |
| Autonomous Contingency Detection and Reaction (UA) | TechPort 90150 [출처:조각] | 예상못한 변화 감지→임무가능성 판단→대안 → **contingency 반응** |
| STORM (Search Technology for Optimal Rescue Missions) | NTRS 20240012868 [출처:조각] | IR→후보→RGB→pose 확인, mic 는 ambient 먼저 재 필터 → **센서 시퀀싱 예시** |
| STEReO / ACERO / DRCS CONOPS | nasa.gov, disasters.nasa.gov/drcs-conops [출처:조각] | remote sensing→공통 작전상황도→변화대응 autonomy → **야전 운용개념** |

## 우리가 그것과 다른 점

- NASA 는 이 조각들이 **따로** 있다(하나의 센서-스위칭 정책 이름은 공개돼 있지 않다). 우리는
  이를 **한 SAR UAV 정책으로 합치고**, 우리 시뮬 환경변수(V·조도·land-cover·온도·풍·gnss_env)와
  **실측 센서 지연**(measure.py)에 fit 시켜 **돌아가는 코드 + 비교 실험**으로 만든다.
- "SAR 이 RGB 의 15배 느리고 비싸면 평상시 RGB, perception 무너지면 비싼 센서 활성화" 를
  임의 heuristic 이 아니라 **U_i = ΔP/T − λE − μC 의 자연스러운 귀결**로 만든다.
- 학습 정책(Mamba selective SSM · policy_core value head)과 **같은 지표로 비교**해 가장 좋은 것을
  채택한다 — NASA 효용정책이 baseline, 학습이 그것을 이겨야 채택된다.

## 아직 못 지운 가능성

- S4/health-mgmt/variable-autonomy 를 **이미 하나로 합친** UAS 센서관리 논문이 있을 수 있다(아직
  NTRS·IEEE 전수 못 봄). 있으면 우리는 재현/이식이 된다 — 신규성 주장 안 함.
- 효용식의 정확한 형태(ΔP 정의·λ,μ 값)는 문헌에 더 정립된 것이 있을 수 있다(POMDP 센서관리·
  value of information 계열). VoI/POMDP 센서스케줄링을 아직 대조 안 함 — 다음 조사 대상.
- STORM 의 실제 시퀀싱 규칙 전문을 못 읽었다(요약만). 세부가 다를 수 있다.
