# WALP 행동 기반 전환 — 선행조사 (2026-09-30, 코드보다 먼저)

사용자 목표(2026-09-30): "모델 위에 에이전트" 가 아니라 **행동들의 집합 자체가 모델**인 AI. 학습 단위를
`문장 → 행위 분류` 에서 `상태 조건 → 행동 → 결과 → 보상 → 그 행동의 가치 갱신` 으로 바꾼다.
상위 행동은 하위 행동의 출력을 **억제**한다. 성장망(분류기)은 중앙에서 내려와 **센서 하나**가 된다.

## 읽은 깊이

이 조사의 모든 항목은 **검색 조각만** 보았다. 전문을 열려던 두 편(Maes & Brooks 1990 AAAI PDF,
Mahadevan & Connell 1991 AAAI PDF)은 이 컨테이너의 망 정책에 막혔다(cdn.aaai.org · cim.mcgill.ca 차단).
그러니 아래 "그들이 한 것" 은 조각의 요지이지 읽은 내용이 아니다.

## 가장 가까운 선행 — 우리 제안은 새 방법이 **아니다**

| 선행 | 조각의 요지 | 우리 제안과 겹치는 것 |
|---|---|---|
| **Dorigo & Colombetti**, ALECSYS · *Robot Shaping* (MIT Press 1998), "Alecsys and the AutonoMouse" (Machine Learning 1994) `[출처:조각]` | 과제를 행동으로 쪼개고 **행동마다 학습 분류자 시스템(LCS) 모듈**이 규칙을 진화시킨다. 행동 사이의 우선순위(예: 도망 > 먹이 찾기)는 설계자가 정하고, 모듈 안의 규칙은 학습한다. 실제 로봇에서 Chase/Feed/Escape | **거의 그대로다.** "XCS 의 조건→행동을 행동 단위로" 는 이들이 30년 전에 LCS 로 했다 |
| **Mahadevan & Connell**, "Automatic programming of behavior-based robots using reinforcement learning", *Artificial Intelligence* 55 (1992); AAAI-91 `[출처:조각]` | 포섭 구조 로봇 OBELIX(상자 밀기)에서 **행동마다 따로 보상**을 주고 Q 학습 + 해밍 거리/군집으로 성분 행동을 배운다. 때로 손 코딩보다 낫고, 행동 기반 분해가 강화학습을 빠르게 한다 | 행동별 보상 · 해밍 거리 일반화(우리 grownet 의 해밍 RBF 와 같은 생각) |
| **Maes & Brooks**, "Learning to Coordinate Behaviors", AAAI-90 `[출처:조각]` | 행동들 사이의 **조율(언제 켜지나)** 을 양·음 피드백으로 배운다(Genghis 보행) | 억제/조율 자체를 학습하는 것 — 우리가 "새로" 할 뻔한 것 |
| **Maes**, "How To Do the Right Thing", *Connection Science* 1(3) 1989 `[출처:조각]` | 행동 망 — 행동 선택이 노드 사이의 활성/억제 역학에서 창발 | 중앙 분류기 없는 행동 선택 |
| **Brooks**, "Intelligence without representation", *AI* 47 (1991) `[출처:목록]` | 지각–행동에 직접 붙은 병렬 활동 생산자 · 억제/대체 신호 · 중앙 통제 없음 | 목표 구조 자체 |
| 되물을까/답할까 — Rao & Daumé-류, "Interactive Question Clarification in Dialogue via RL" (COLING 2020 industry), "Clarify or Answer" (arXiv:2601.16400), "Learning through Dialogue Interactions by Asking Questions" (arXiv:1612.04936) `[출처:조각]` | 되묻기/답하기를 **이진 정책**으로 두고, 되물음에 비용(사용자 인내)을 매겨 보상으로 배운다 | 우리 첫 두 행동(ReactiveAnswer · Clarify)의 대화 쪽 선행 그대로 |

## 우리가 다른 점 — 정직하게

**방법으로는 없다.** 행동별 LCS(Dorigo & Colombetti) · 행동별 보상(Mahadevan & Connell) · 조율 학습(Maes & Brooks) ·
되묻기 정책(대화 RL)이 다 있다. 남는 것은 **적용 조건의 조합**뿐이다:

1. 몸이 **텍스트 대화**다(선행은 이동 로봇). 보상은 사람의 다음 턴(감사·불만·고침)에서 온다 — 조각으로 본 선행 가운데
   LCS 행동 모듈을 사람 대화 결과로 기른 것은 **못 찾았다**(그러나 아래 '못 본 곳').
2. 사전학습 가중치 · 데이터셋 · GPU 없이, 한 사람과의 대화로 **온라인**.
3. 봉인 관문 · 래칫으로 교체를 판단한다(선행에 없는 것이 아니라 MLOps 관행 — WALP_진화대화.md 덧붙임).

그러니 이 전환을 **"새 ML 방법"** 이라고 부를 수 없다. 부를 수 있는 이름은 "Dorigo–Colombetti 식 행동별 LCS 를
대화 로봇에 옮긴 것" 이다. 사용자가 처음 말한 목표("Neocognitron + 역전파 = CNN 처럼 새 방법")에는 이것으로 닿지 않는다.

## 검증 — 이름만 Brooks 가 아닌지 (사용자가 정한 다섯, 구현 여부로 판별)

| | 판별 | 거짓이 되는 모습 |
|---|---|---|
| V1 | 행동이 **직접** 행위(답 · 되물음 · 시뮬 걸음)를 고른다 | 행동이 라벨을 내고 뒤에서 틀이 답을 고른다 |
| V2 | 결과(보상)가 **그 행동의** 가치를 바꾼다 | 보상이 공용 분류기만 바꾼다 |
| V3 | 상위 행동이 하위 행동의 출력을 **실제로** 억제한다 | 우선순위 사슬에서 먼저 나온 답을 고를 뿐 |
| V4 | 새 행동을 더할 때 **중앙 분류기 재학습 없이** 는다 | 행동 하나 더하면 ACTS 가 늘어 전부 다시 기른다 |
| V5 | 숙고층(STRIPS)을 꺼도 바닥 행동이 계속 돈다 | 숙고층 없으면 답을 못 한다 |

각각을 **끄고 켜는 검사**로 붙든다(V3: 억제 선을 끊으면 하위 출력이 나와야 한다 등).

## 찾아본 질의

- `Mahadevan Connell 1992 automatic programming behavior-based robots reinforcement learning subsumption OBELIX`
- `learning classifier system behavior-based robot subsumption Dorigo Colombetti ALECSYS robot shaping`
- `Maes 1989 behavior network action selection "how to do the right thing" learning from experience`
- `behavior-based dialogue system subsumption architecture conversational agent reactive layers`
- `learning when to ask clarification question dialogue reinforcement learning clarify vs answer policy`
- `hierarchical XCS subsumption architecture learning arbitration behaviors mobile robot 2020..2026`

## 아직 못 본 곳 — "없다" 가 아니다

- 위 논문들의 **전문**(망 차단). 특히 Dorigo–Colombetti 가 조율(우선순위)까지 학습했는지 — 조각에 "Learning to
  Coordinate Behaviors in Soft Behavior-Based Systems Using RL" 이 따로 있다.
- 대화 시스템에서 행동 기반/포섭 구조를 쓴 1990–2000년대 문헌(Traum 류 정보 상태 대화 관리, 대화 행동 로봇 — HRI 쪽)을 안 찾았다.
- LCS 를 대화 정책에 쓴 연구(있다면 가장 가까울 것)를 따로 안 찾았다.
- Wilson 의 ZCS/XCS 원 논문의 다단계(multi-step) 설정 — 대화 턴이 여러 걸음이면 필요하다.

## 덧붙임 (2026-09-30) — 손 규칙·단서를 빼고, 고침·되물음을 자연어로

사용자(2026-09-30): "손규칙 없애고 그냥 자연어로 쓸 건데 … 내가 format 에 맞춰야 해? 내가 자연인데."

가장 가까운 선행:
- **Hancock · Bordes · Mazaré · Weston, "Learning from Dialogue after Deployment: Feed Yourself, Chatbot!"**, ACL 2019
  (arXiv:1901.05415) `[출처:조각]` — 배포 뒤 대화에서 스스로 학습 예를 뽑는다. 사용자 **만족을 추정**해, 잘 가면 사용자의 말을 흉내 낼
  예로 삼고, 불만이면 **자연어로 피드백을 청해** 그것을 예로 쓴다. 특별한 피드백 형식이 없다. 조각의 요지: 만족 분류가
  **불확실성 기반 방법보다 크게 낫다** — 우리 L1(되묻기)은 불확실성 기반이다. 뒤집힐 수 있는 자리로 적어 둔다.
- 개관: "Lifelong and Continual Learning Dialogue Systems" (Liu & Mazumder, arXiv:2211.06553, AAAI 2021 판) `[출처:조각]` —
  대화 중에 새 표현·지식·학습 예를 얻는다. 피드백은 대개 답 자체가 아니라 **힌트**다.
- "Learning Improvised Chatbots from Adversarial Modifications of Natural Language Feedback" (arXiv:2010.07261) `[출처:조각]`.
- 손 특징 없는 작은 자료 의도 분류 — 조각으로 본 최근 방법은 전부 사전학습 임베딩/BERT 에 기댄다(우리 제약에서 못 씀).
  사전학습 없는 쪽은 n-gram + 고전 분류기(SVM · 나무)이고, 차가운 시작은 규칙 아니면 대량 라벨이라는 조각. `[출처:조각]`

우리가 다른 점: Hancock 등은 사전학습된 신경 대화 모형 위에서 한다(우리는 가중치 없이 시작). 만족 추정기 · 자연어 피드백 청하기는
**그들의 것**이다 — 우리가 붙이면 그 생각을 옮기는 것이다.

찾아본 질의: `Hancock 2019 "Learning from Dialogue after Deployment: Feed Yourself, Chatbot!" satisfaction feedback` ·
`learning from natural language corrections dialogue user feedback implicit signals chatbot continual learning without annotation` ·
`intent classification without handcrafted features character n-gram learned from scratch small data cold start dialogue act`

아직 못 본 곳: 한국어 · 가중치 없는 조건에서 자연어 고침을 해석한 연구. 전문은 하나도 못 읽었다.
