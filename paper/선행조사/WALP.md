# 선행조사 — WALP (Weight-free Autonomous Language Policy) v0.1

요청(사용자, 2026-09-29): LLM 에이전트가 하던 목표 해석·기억 검색·계획·행동·결과 평가를
**학습된 언어 모델 없이** 구현하고, 각 기능의 효과와 한계를 실험으로 검증한다(H1~H4).
SE 에이전트와의 유사점·차이점도 확인한다.

**이 문서는 코드보다 먼저 커밋된다**(CLAUDE.md '짓기 전에 조사한다'). 인용은 전부 검색 결과
조각·초록 수준이고 전문을 읽지 않았다 — 그래서 모두 `[출처:조각]` 이다.

## 정직한 성격 — 새 이론이 아니다

LLM 없이 제한된 자연어 명령을 받아 기억·계획·학습을 하는 에이전트는 **LLM 이전에 이미
있었다**(Soar/Rosie, SHRDLU, CBR, BDI). WALP 가 "LLM 에이전트 기능을 LLM 없이 처음으로
구현했다" 고 주장하면 그것은 틀린 주장이다. WALP 의 몫은 아래 "다른 점" 에 적은 **좁은 것**뿐이다.

## 가장 가까운 선행연구

- **Rosie (Soar ITL agent)** — Mohan & Laird, "Learning Goal-Oriented Hierarchical Tasks from
  Situated Interactive Instruction", AAAI 2014; Lindes et al., "Grounding Language for Interactive
  Task Learning", ACL RoboNLP workshop 2017 (aclanthology W17-2801). 이미 한 것: 신경망 언어모델 없이
  제한된 영어 지시를 Soar 안에서 기호로 접지하고, 새 과제·개념을 지시로 배우고, 모르는 것을
  감지하면 되묻는다. 로봇 조작·실내 이동. **WALP 의 R3(제한 NL·모호하면 되묻기)와 H1 의 가장
  가까운 선례.** `[출처:조각]`
- **Soar 인지 아키텍처** — Laird, "The Soar Cognitive Architecture", MIT Press 2012; Laird,
  "Introduction to the Soar Cognitive Architecture", arXiv:2205.03854 (2022). 이미 한 것: 절차·의미·
  일화 기억, 작업기억, 규칙 기반 결정 주기, chunking 으로 계획을 반응 규칙으로 바꾸는 학습.
  CoALA 가 스스로 이 계보 위에 서 있다고 밝힌다. `[출처:조각]`
- **CoALA** — Sumers, Yao, Narasimhan, Griffiths, "Cognitive Architectures for Language Agents",
  arXiv:2309.02427 (2023). 이미 한 것: LLM 에이전트를 기억(작업/일화/의미/절차)·행동 공간·결정
  절차로 분해하는 틀. WALP 의 모듈 분해가 이것을 따른다. `[출처:조각]`
- **ReAct** arXiv:2210.03629 (2022), **Reflexion** arXiv:2303.11366 (2023), **LLM 에이전트 계획
  서베이** arXiv:2402.02716 (2024). 이미 한 것: 행동-관측 반복, 실패 반성을 다음 시도에 쓰는 것,
  계획 기능 분류. 전부 LLM 을 쓴다 — WALP 는 그 **기능 역할**만 가져온다. `[출처:조각]`
- **Case-Based Reasoning** — Aamodt & Plaza, "Case-Based Reasoning: Foundational Issues,
  Methodological Variations, and System Approaches", AI Communications 1994 (retrieve·reuse·revise·
  retain 4R 순환). 로봇 항법 CBR: "Case-Based Reasoning in Robot Indoor Navigation", ICCBR 2007
  (Springer doi:10.1007/978-3-540-74141-1_20). 이미 한 것: 과거 사례 검색으로 항법·탐색을 돕는 것.
  WALP 의 §4.2 는 이것 그대로다. `[출처:조각]`
- **BDI / PRS** — Rao & Georgeff, "BDI Agents: From Theory to Practice", ICMAS 1995. 이미 한 것:
  목표·믿음·의도를 기호로 들고 실행 중 새 증거로 계획을 바꾸는 실시간 에이전트. `[출처:조각]`
- **SE 저장소 안** — `fw/`(C99 결정 executive: KF 추정·증거융합·BT·중재·FDIR·결정성 재생),
  `policy_core/`(OS 독립 능동탐색 C 코어), `self_challenge.py`(RED/GREEN 증명을 통과해야 규칙이
  게이트로 승격 = 검증된 규칙 갱신), `paper/선행조사/무LLM_자율결정구조.md`. **WALP 의 D(Executive &
  Safety)·E(Platform) 대부분이 이미 여기 있다.**

## 우리가 그것과 다른 점

좁게 적는다. 이것 말고는 다른 점이 없다고 보는 것이 안전하다.

1. **LLM 에이전트 기능 분해(CoALA 식)를 하나씩 끄는 ablation 을 한 시뮬레이터·같은 행동 공간·같은
   센서·같은 안전 제약에서 잰다.** Rosie/Soar 문헌은 능력 시연(새 과제를 배운다)이 중심이고, "사례
   검색만 뺐을 때 · 계획 탐색만 뺐을 때 · 검증 없이 규칙을 갱신했을 때" 를 같은 판에서 비교한
   표를 우리는 아직 못 찾았다(못 찾은 것이지 없다는 뜻이 아니다 — 아래 '못 지운 가능성').
2. **검증된 갱신 vs 무검증 자동 갱신(H3)을 같은 후보 생성기에서 갈라 잰다.** 후보 규칙을 만드는
   부분은 같고, 회귀 시험·불변식 검사를 거치느냐만 다르다. Soar chunking 은 검증 관문 없이 규칙을
   만든다. SE 의 `self_challenge.py` 는 코드 게이트에 대해 같은 관문을 두지만 정책 파라미터에는
   아니다.
3. **고정 크기·힙 없는 C++17 코어**에서 파서(명령 시점)와 자율 루프(구조화된 목표만)를 가르고,
   결정마다 규칙 ID·증거 ID·정책 버전·거부 사유를 남겨 **기록만으로 결정을 재구성**하는 비율을 잰다.
4. 사용자 친화성은 **저자가 끼지 않은 상태**(Discord 고정 명령, LLM 경로 없음)에서 원장으로 잰다 —
   저자가 쓴 파서 시험 문장은 파서와 같은 사람이 써서 순환이므로 그것을 사용성 근거로 쓰지 않는다.

## 찾아본 질의

- `symbolic agent without LLM reimplementing LLM agent memory planning reflection cognitive architecture comparison 2025`
- `Soar cognitive architecture chunking episodic memory robot controlled natural language commands`
- `case-based reasoning robot navigation ablation fixed FSM baseline verified rule update regression`
- `"without large language models" autonomous agent symbolic planning case retrieval embedded microcontroller evaluation`
- `Rosie Soar interactive task learning robot natural language instruction Mohan Laird`

## 아직 못 지운 가능성

- **Soar/Rosie 쪽 평가 논문 전문을 안 읽었다.** Kirk & Laird(ACS 2013, 게임 과제 학습), Mohan 박사
  논문에 기능별 ablation 이 있을 수 있다. 있으면 다른 점 1 은 사라진다.
- **ICARUS·ACT-R/E(Trafton et al., JHRI 2013)** 의 로봇 평가를 안 봤다.
- **계획·실행 감시(plan execution monitoring) · 런타임 보증(RTA, Simplex)** 문헌에 "학습된 규칙을
  회귀 시험 후 승격" 하는 것이 이미 표준일 수 있다(예: 로그 궤적 기반 회귀 방지 특허 US 12085942 가
  검색에 떴다 — 안 읽었다).
- **"Structured World-State Reasoning for Agentic Robotic Search", arXiv:2609.23841** 가 검색에 떴다.
  제목만 봤다. LLM 기반인지, 구조화된 세계상태 추론을 LLM 없이 하는지 확인 못 했다 — 가장 먼저
  읽어야 할 것.
- **CBR 공동체(ICCBR)** 에서 "사례 검색 vs 고정 정책" 을 분포 이동 아래 비교한 연구는 많을 것이다.
  우리의 H2 결과는 그 결과의 재현일 가능성이 높다.
- 제한 자연어(controlled natural language) 로봇 명령 문법(예: Attempto 계열, 로봇 CNL)을 안 봤다.
