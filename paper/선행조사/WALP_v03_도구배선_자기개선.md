# 선행조사 — WALP v0.3: SE 도구 배선(LLM 없는 도구 라우팅) + SE 원리의 자기 개선 고리

요청(사용자, 2026-09-29): "SE agent의 원리를 최대한 활용해서, 더 높은 수준의 LLM 개입 없는 ai를 만들어라"
· "SE agent에 있는 많은 tool을 최대한 배선해라".

코드보다 먼저 커밋한다. 인용은 전부 검색 결과 조각 수준 — `[출처:조각]`.

## 가장 가까운 선행연구

**(가) 자연어 → 도구(API) 호출, LLM 없이**
- **NL2API** — Su, Awadallah, Khabsa, Pantel, Gamon, "Building Natural Language Interfaces to Web APIs",
  CIKM 2017, doi:10.1145/3132847.3133009. 이미 한 것: 자연어 명령 → API 호출을 의미 파싱으로, 학습 데이터를
  크라우드소싱으로 모았다. 학습된 파서다(신경망) — 우리는 규칙·사전이다. `[출처:조각]`
- **Almond / ThingTalk / Genie** — Campagna et al., "Almond: …Programmable Virtual Assistant", WWW 2017;
  "Genie: A Generator of Natural Language Semantic Parsers for Virtual Assistant Commands", PLDI 2019,
  doi:10.1145/3314221.3314594, arXiv:1904.09020. 이미 한 것: 명령을 실행 가능한 언어(ThingTalk: when-get-do)로
  옮기는 가상 비서. 템플릿으로 데이터를 합성해 **신경망 파서**를 학습 — 실사용 입력 정확도 62%(조각).
  `[출처:조각]`
- **NL2Bash** — arXiv:1802.08979 (2018). 자연어 → 셸 명령 말뭉치와 파서. `[출처:조각]`

**(나) 반례로 이끄는 합성·반증·감독**
- **CEGIS** — Solar-Lezama et al., 2006(조합적 스케치). 합성기 ↔ 검증기(반례) 고리. 우리 자기 개선 고리의
  골격(반례 사냥 → 후보 → 증명 → 승격)이 이것이다. `[출처:조각]`
- **S-TaLiRo** — Annpureddy, Liu, Fainekos, Sankaranarayanan, TACAS 2011(dl.acm.org/doi/10.5555/1987389.1987416).
  시뮬레이션 기반으로 외란 공간을 최적화해 **요구사항을 깨는 입력을 찾는다**(반증). 우리 반례 사냥꾼이 하는
  일이다 — 그들은 강건도(robustness)를 최소화하는 최적화, 우리는 무작위+국소 탐색. `[출처:조각]`
- **Shielding** — Alshiekh, Bloem, Ehlers, Könighofer, Niekum, Topcu, "Safe Reinforcement Learning via
  Shielding", AAAI 2018. 학습 에이전트 옆에서 안전하지 않은 행동을 막는 **실드**를 명세에서 합성한다.
  WALP 의 안전 감독기가 이 자리이고, v0.3 의 '위반에서 불변식 조이기' 는 실드를 명세 대신 반례에서 조인다.
  `[출처:조각]`
- **Delta debugging** — Zeller & Hildebrandt, "Simplifying and Isolating Failure-Inducing Input", IEEE TSE 2002.
  통과·실패 두 실행의 차이에서 **실패를 뒤집는 최소 변경**을 찾는다. v0.3 의 반사실 진단(한 번에 하나만 바꿔
  실패→성공을 뒤집는 변경을 원인으로 본다)은 이것의 정책-파라미터 판이다. `[출처:조각]`
- **Mutation testing** — DeMillo, Lipton, Sayward, "Hints on Test Data Selection", IEEE Computer 1978.
  일부러 틀린 변형을 넣어 검사가 잡는지 본다. 검증기의 건전성(아무거나 승인하지 않는가)을 이것으로 잰다.
  SE 의 `falsegreen/`·`mutate.py`·G008 이 같은 원리. `[출처:조각]`

**(다) SE 저장소 안** — `self_challenge.py`(RED/GREEN 증명 → 게이트 승격), `falsegreen/`(반례 사냥, "RED 는
증서, UNRESOLVED 는 증명이 아니다"), `scripts/capability_ratchet.py`(한 번 도달한 능력은 후퇴 금지),
`dispatch.py` 자연어표(LLM 앞에서 정규식으로 고정 명령 고르기), G008/G009(검증기 무결성).

## 우리가 그것과 다른 점

1. **도구 라우팅을 학습 없이** 한다(NL2API·Genie 는 신경망 파서). 도구 목록은 SE 의 `bot_tools.py` 에서 AST 로
   **자동으로** 뽑고, 사람이 쓰는 것은 도구별 낱말 사전(`data/tools.csv`) 한 장이다. 그리고 "LLM 없음" 을
   분류로 주장하지 않고 **실행 중에 막고 센다**(LLM 호스트 차단 · 키 제거 · `claude` 심) — 선행연구에서
   이 모양의 강제를 못 찾았다(못 찾은 것이다).
2. 자기 개선 고리의 부품(CEGIS 식 고리 · S-TaLiRo 식 반증 · delta debugging 식 원인 · 실드 · 변이 검사)은
   전부 있는 것이다. 우리 몫은 **이것들을 한 정책의 개선 고리로 엮고, v0.2 의 규칙 템플릿 학습기와 같은
   시뮬레이션 예산에서 나란히 재는 것**뿐이다.

## 찾아본 질의

- `natural language interface to web APIs NL2API Su 2017 CIKM semantic parsing API calls`
- `counterexample-guided inductive synthesis CEGIS falsification cyber-physical systems S-TaLiRo shield synthesis safe reinforcement learning Alshiekh 2018`
- `delta debugging Zeller isolating failure-inducing changes minimal counterfactual cause autonomous agent policy repair`
- `Genie ThingTalk Almond virtual assistant semantic parser Campagna 2017 WWW rule-based skill routing without LLM`

## 아직 못 지운 가능성

- **규칙 기반 챗봇·인텐트 라우터**(AIML, Rasa 의 규칙 정책, 음성비서의 grammar 기반 NLU)는 산업에 흔하다 —
  "LLM 없는 도구 라우팅" 자체는 새것이 아니다. 학술 비교(규칙 라우터 vs 학습 라우터의 정확도)를 안 찾았다.
- **자동 프로그램 수리(APR)**·**search-based software engineering** 쪽에 '반례 → 후보 → 회귀 시험 → 승격' 이
  거의 그대로 있다(GenProg 등). 정책 파라미터에 적용한 것만 다를 수 있다.
- 로봇 정책의 **반사실 설명·수리**(counterfactual policy repair) 문헌을 안 봤다 — 강화학습 쪽에 있을 가능성이 크다.
- S-TaLiRo 뒤의 반증 도구들(Breach, falsification 벤치마크 ARCH-COMP)을 안 봤다.

## 보탬 (2026-09-29) — 한 걸음 고리가 대기 8 에서 멈춘 뒤, 고치기 전에

측정(`walp_cli landscape`): 대기 4→8 의 참 이득은 300판 중 −1/+16(평탄), 8→12 는 +14/+13, 16→20 은 잡음 폭.
고리가 멈춘 이유 셋: 평탄한 구간에서 한 걸음이 잡음과 안 갈린다 · 승격 뒤 같은 방향을 처음부터 다시 투표한다 ·
투표가 잡음 바닥(아무 이웃이나 반례의 ~17% 를 고친다) 위에 있는지 안 본다. 셋 다 이미 있는 처방이 있다.

- **Hooke & Jeeves (1961)** "Direct Search" Solution of Numerical and Statistical Problems, J. ACM 8:212–229,
  doi:10.1145/321062.321069 `[출처:조각]` — 탐색 이동이 성공하면 같은 방향으로 **패턴 이동**. 불연속·이산 값에서도 된다.
- **Mladenović & Hansen (1997)** Variable neighborhood search, Computers & Operations Research 24(11):1097–1100,
  doi:10.1016/S0305-0548(97)00031-2 `[출처:조각]` — 이웃의 **크기를 체계적으로 바꿔** 평탄·국소 최적을 넘는다.
- **공통 난수(common random numbers)·순위 선택(ranking and selection)** — 예: arXiv:1410.6782 `[출처:조각]`.
  우리의 '같은 시드로 짝지은 비교' 는 이 오래된 분산 감소 기법 그대로다. 새것이 아니다.

우리가 다른 점: 없다 — 이 셋을 **정책 규칙 고리에 붙이고 같은 예산에서 전후를 재는 것**만 우리 몫이다.
투표 문턱을 '이웃들의 투표 중앙값(잡음 바닥) 대비' 로 두는 것은 우리가 정한 경험칙이고 문헌 근거를 못 찾았다.

찾아본 질의: `Hooke Jeeves 1961 "Direct search" ... pattern move` ·
`Mladenović Hansen 1997 variable neighborhood search Computers & Operations Research` ·
`noisy local search sequential testing policy parameter improvement paired comparison common random numbers ranking and selection`

아직 못 지운 가능성: 잡음 있는 직접 탐색(noisy pattern search, 예: Anderson & Ferris 류)과 시뮬레이션 최적화의
'순차 순위 선택 + 국소 탐색' (COMPASS 등) 이 우리 v3 와 거의 같은 것일 수 있다 — 안 읽었다.

## 보탬 (2026-09-30) — 가장 가까운 것을 잘못 짚었다: ParamILS

CMAC 조사(`WALP_CMAC.md`) 중에 걸렸다. 이 고리(이웃 한 걸음 · 검정으로 승격 · 헛수고 멈춤)와 가장 가까운 것은
Hooke–Jeeves 나 VNS 가 아니라 **알고리즘 설정(algorithm configuration)** 계열이다.

- **ParamILS / FocusedILS** — Hutter, Hoos, Leyton-Brown, Stützle, JAIR 36:267–306, 2009 (doi:10.1613/jair.2861).
  순서형·범주형 파라미터의 확률적 국소 탐색, 설정마다 평가 예산을 적응적으로 제한. `[출처:조각]`
- **SMAC** — Hutter 외 2011. 랜덤 포레스트 대리모형, 정수·범주형, 잡음은 반복 평가로. `[출처:조각]`

우리 고리의 새로움 주장은 원래 없었다. 달라지는 것은 비교 기준선이다 — 고리를 평가할 때 **같은 예산의 ParamILS
식 탐색**이 맞는 대조다(아직 안 했다).

찾아본 질의: `ParamILS Hutter Hoos Leyton-Brown Stützle 2009 JAIR "automatic algorithm configuration framework" iterated local search FocusedILS`
