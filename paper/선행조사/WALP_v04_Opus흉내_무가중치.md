# 선행조사 — "Opus 와 가장 비슷한 메커니즘, 학습된 가중치 없이" (WALP 다음 걸음 후보)

요청(사용자, 2026-09-29): "Opus(대형 LLM)와 가장 유사한 메커니즘을 설계하라 — 학습된 가중치 없이, LLM 없이."

**인용 수준을 먼저 밝힌다.** 이번 조사에서 WebFetch 는 arxiv.org · aclanthology.org · ojs.aaai.org ·
delph-in.github.io 가 전부 egress 프록시에 막혔다. 그래서 **전문도 초록도 읽은 것이 없다 — 아래 인용은
전부 `[출처:조각]`**(검색 결과 조각)이다. 조각에 나온 수는 그대로 옮기되, 원문에서 확인하지 않은 수다.

## 0. 정직한 결론부터

- **"LLM 수준의 폭(breadth)을 학습된 파라미터 없이" 낸 존재 증명은 찾지 못했다.** 가장 가까운 것들은 전부
  (a) 좁은 영역에서 정밀하거나(SHRDLU · Rosie · KALM · FlashFill), (b) 폭은 넓지만 **이해가 아니라 구문만**
  덮거나(ERG), (c) 수십 년·수천 인년을 들이고도 폭에 못 미쳤다(Cyc).
- 가중치 없이 폭을 얻은 유일한 부류는 **대규모 계수(count)** 다 — infini-gram(5조 토큰, 다음 토큰 정확도 47%).
  그러나 그것은 아래 §2 의 정의로 "학습된 가중치 없음" 의 경계에 걸리고, 추론·도구 선택을 하지 않는다.
- 따라서 이 요청에 대한 정직한 설계 목표는 "Opus 와 비슷한 것" 이 아니라 **"Opus 가 하는 일의 기능 분해 중
  WALP 가 잰 틈(거부 31~37%, 도구 정확도 64~70%, 잘못 실행 2~8)을 가장 많이 닫는 무가중치 부품"** 이다.

## 가장 가까운 선행연구

(능력별로 나눈다.)

형식: 무엇 · 인용 · 이미 한 것(조각의 수) · 알려진 실패 · 가중치 판정(§2 의 W0/W1/W2).

### (1) 넓은 언어 이해 · 바꿔 말하기/오타/동의어 강건성

- **English Resource Grammar (ERG, HPSG, DELPH-IN)** — Flickinger 외; DELPH-IN 2002~. 이미 한 것: 손으로 쓴
  정밀 문법이 "잘 편집된 영어의 94% 를 파싱"(2025 릴리스 문서 조각). 과거 BNC 평가에서는 어휘가 다 있는
  문장의 57% 만 파싱, 그중 83% 가 옳았다(조각, "Road-testing the ERG over the BNC"). 비교 연구:
  "A Comparative Analysis of Knowledge-Intensive and Data-Intensive Semantic Parsers", arXiv:1907.02298
  (제목만 봄). 실패: **범위 밖 입력에서 파싱 실패** — 모르는 낱말은 보통 품사 태거로 일반 어휘항을 붙여
  넘기는데, 그 태거는 **학습된 것**이다(일반 관행 조각, ERG 에 대해 원문 미확인). 23년 개발. W0(+태거는 W2).
  `[출처:조각]`
- **Grammatical Framework (GF) · Resource Grammar Library** — Ranta, "Grammatical Framework: Programming with
  Multilingual Grammars", CSLI 2011; "The GF Resource Grammar Library", LiLT. 이미 한 것: 공통 추상 구문 위의
  40여 개 언어 문법(한국어는 partial). 실패: 문법 스스로 "grammars leak — 범위 밖 입력에 syntax error 를
  낼지 추측할지" 가 문제라고 적고, 해법으로 **통계 평활·혼성**을 든다(조각). W0. `[출처:조각]`
- **Korean Resource Grammar (KRG)** — Kim, Yang, Song, Bond; 2003~, HPSG/LKB/MRS. 이미 한 것: 형 정의 394 ·
  문법 규칙 36 · 시험 문장 2100(조각). 실사용 말투에 대한 커버리지 수는 못 찾았다. W0. `[출처:조각]`
- **Fluid Construction Grammar (FCG)** — Steels (편), "Design Patterns in FCG", Benjamins 2011; "Diagnostics
  and Repairs in FCG", Springer 2012. 이미 한 것: 구문(construction)을 **부분 일치**로 적용하고, 막히면
  메타층의 진단·수리가 빠진 요소를 위에서 채운다 — 강건성을 설계 목표로 둔 유일한 손문법 계열. 실측
  커버리지 수는 못 찾았다. W0. `[출처:조각]`
- **통제 자연어(CNL) — Attempto(ACE)** — Fuchs, Kaljurand, Kuhn 2008; Kuhn, "A Survey and Classification of
  Controlled Natural Languages", Computational Linguistics 40(1) 2014. 이미 한 것: 모호하지 않은 1차 논리 번역.
  실패: 사용자가 **그 부분 언어를 배워야** 한다 — WALP 의 거부는 사실상 이 비용을 사용자에게 넘기는 것이다.
  W0. `[출처:조각]`
- **KALM** — Gao, Fodor, Kifer, "Knowledge Authoring and Question Answering with KALM", arXiv:1905.00840 (TPLP 계열).
  이미 한 것: FrameNet 기반 온톨로지(FrameOnt)+BabelNet 으로 "Mary buys a car" 와 "Mary makes a purchase of a car"
  를 **같은 논리식**으로 — 의미 불일치(semantic mismatch) 해소. bAbI 에서 99.3% 이상 정확(조각). 실패: CNL 입력
  전제, bAbI 는 합성 과제. 파서가 "incrementally-learned" 라는 조각이 있어 W0 인지 불확실. `[출처:조각]`
- **오타·발음 강건성(가중치 없음)** — SymSpell(Garbe 2012, 블로그/코드 — 논문 아님): 대칭 삭제로
  Damerau-Levenshtein 후보 생성, 거리 3 안의 약 300만 오타를 삭제 25개로 덮는다(조각). Double Metaphone
  (Philips, C/C++ Users Journal 2000): 발음 키 두 개. 한국어는 **자모 분해 편집거리**가 표준 기법이고,
  자모 단위 오타 분류 연구가 있다(arXiv:2608.30229, 제목·조각만 — LLM 취약성 연구). 실패: **새 낱말은 못
  잡는다**(`spot`·`택배` 는 오타가 아니다). 사전 빈도로 후보를 고르면 W1. `[출처:조각]`

### (2) 문맥 내 학습(몇 예시로 배우기)

- **FlashFill (PBE)** — Gulwani, "Automating String Processing in Spreadsheets Using Input-Output Examples",
  POPL 2011; FlashFill++ POPL 2023 doi:10.1145/3571226. 이미 한 것: 입출력 예 1~몇 개로 DSL 프로그램 합성
  (`Alan Turing → turing, alan`). 실패: DSL 밖은 불가 — "문자열을 글자열로만 보므로 계산이 든 변환은 못 배운다"
  (조각). W0(탐색 + 순위 휴리스틱; FlashFill++ 의 순위기는 확인 못 함). `[출처:조각]`
- **Meta-Interpretive Learning (Metagol → Popper)** — Muggleton, Lin, Tamaddoni-Nezhad, MLJ 2015;
  Cropper & Muggleton "Learning programs by learning from failures", arXiv:2005.02259. 이미 한 것: 양성 예 **하나**와
  배경 지식으로 논리 프로그램 합성; one-shot Logical Vision 이 30-shot 통계 학습기와 비슷(조각). 실패: 메타규칙·
  배경지식을 사람이 준다(편향이 곧 성능). W0. `[출처:조각]`
- **Interactive Task Learning — Rosie (Soar)** — Kirk & Laird, ACS 2013 "Interactive Task Learning for Simple
  Games"; Lindes et al., RoboNLP 2017; Mininger, AFRL-AFOSR-VA-TR-2019-0204. 이미 한 것: 제한 영어 지시로
  Three Men's Morris · Picaria · Othello · Breakthrough · Frogs and Toads 등 게임·퍼즐을 배움, 목표 표현을
  **예 하나**로(조각). 실패: 어휘·구문은 여전히 손문법 — 새 **과제**는 배우지만 새 **말투**는 약하다. W0.
  `[출처:조각]`
- **Explanation-Based Generalization** — Mitchell, Keller, Kedar-Cabelli, Machine Learning 1(1):47–80, 1986;
  DeJong & Mooney, "EBL: An Alternative View", MLJ 1986. 이미 한 것: 예 하나 + 영역 이론 → 일반 규칙. 실패:
  영역 이론이 완전해야 한다(불완전하면 틀린 규칙을 일반화). Soar chunking 이 같은 계열. W0. `[출처:조각]`
- **초차원 계산(HDC/VSA)** — Kanerva, Cognitive Computation 2009, doi:10.1007/s12559-009-9009-8; Kleyko 외 서베이
  arXiv:2111.06077. 이미 한 것: 무작위(학습 안 한) 1만 차원 벡터로 글자 3-gram 을 묶어 EU 21개 언어 식별 97%(조각).
  실패: 무작위 **기저**는 학습이 아니지만 언어 **원형**은 훈련 문장을 더한 것 — 즉 계수다(W1). 의미 유사성은
  기저가 무작위라 **없다** — 동의어를 스스로 알 길이 없다. `[출처:조각]`
- **압축 거리 분류(gzip+kNN)** — Jiang 외, "'Low-Resource' Text Classification: A Parameter-Free Classification
  Method with Compressors", Findings of ACL 2023. 주장: 훈련 파라미터 없이 비사전학습 DNN 과 겨루고 OOD 5개에서
  BERT 초과(조각). **반박이 붙었다**: Schütte 가 kNN 이 아니라 top-2 정답 포함 여부를 정확도로 셌다는 버그를 찾았고
  공정하게 재면 14개 중 3위 → 11위, 일부 자료는 훈련/시험 오염(블로그 조각). Opitz, arXiv:2307.15002: 단순 BoW
  거리가 gzip 과 비슷하거나 낫다(조각). **교훈: "파라미터 없음" 주장에 거짓 초록이 가장 잘 붙는다.** W1.
  `[출처:조각]`

### (3) 다단계 추론 · 자기 검증

- **고전 계획(PDDL)** — Helmert, "The Fast Downward Planning System", JAIR 26:191–246, 2006, doi:10.1613/jair.1705.
  휴리스틱 탐색(인과 그래프 휴리스틱). 실패: 모형(행동 스키마)을 사람이 써야 한다 — 추론은 되지만 **문제를
  PDDL 로 옮기는 일**이 LLM 이 대신하던 몫이다. W0. `[출처:조각]`
- **SMT** — de Moura & Bjørner, "Z3: An Efficient SMT Solver", TACAS 2008, doi:10.1007/978-3-540-78800-3_24.
  건전한 검증기. 실패: 위와 같음 — 자연어→식 번역이 병목. W0. `[출처:조각]`
- **CEGIS / 반증 / 델타 디버깅** — 이미 `WALP_v03_도구배선_자기개선.md` 에 적힘(재인용 안 함).
- **ARC 에서 DSL 탐색** — ARC Prize 2024 Technical Report, arXiv:2412.04604. 2020 Kaggle 우승(icecuber):
  손으로 쓴 격자 함수 142개를 DAG 로 조합하는 **순수 탐색**으로 비공개 평가 20%; 같은 대회에서 딥러닝은 1%
  넘은 것이 없었다(조각). **가중치 없는 "추론" 의 가장 강한 공개 수치 중 하나이자, 그 상한(20%)을 보여 준다.**
  W0. `[출처:조각]`

### (4) 도구 선택 + 인자 채우기

- **NL2API · Genie/ThingTalk** — 이미 `WALP_v03_…md` 에 적힘. 둘 다 학습 파서(W2); Genie 는 템플릿 문법으로
  **합성 데이터를 만드는 부분**이 W0 — 그 문법 자체가 무가중치 라우터 후보다.
- **CCG 의미 파싱** — Zettlemoyer & Collins, UAI 2005: GeoQuery 79.3%(조각). 어휘 후보 생성(GENLEX)은 손 템플릿(W0),
  고르는 것은 로그선형 가중치(W2). 무가중치 판은 GENLEX 템플릿 + 결정적 순위뿐이다. `[출처:조각]`
- **BM25** — Robertson & Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond", FnTIR 3(4) 2009,
  doi:10.1561/1500000019. k1·b 두 자유 파라미터(관례값) + 모음에서 센 IDF. 실패: 낱말이 안 겹치면 0 — **바꿔
  말하기에 무력**. W1. `[출처:조각]`
- **상용 의도 분류 벤치** — Coucke 외, "Snips Voice Platform", arXiv:1805.10190: Snips NLU vs Luis·Watson·
  Dialogflow·Rasa, 의도 F1(조각). 규칙 라우터 vs 학습 라우터의 **학술 비교는 이번에도 못 찾았다.** `[출처:조각]`

### (5) 세계·상식 지식

- **Cyc** — Lenat, "CYC: Using Common Sense Knowledge to Overcome Brittleness and Knowledge Acquisition Bottlenecks",
  AI Magazine 6(4) 1985, doi:10.1609/aimag.v6i4.510. 이미 한 것: 150만 개념 · 2500만~3000만 단언, 약 2억 달러 ·
  2000 인년(조각, 2차 자료). 실패: "지식이 충분히 쌓이면 스스로 배우기 시작한다" 는 예측이 실현되지 않았다(조각).
  **폭을 손으로 채우려 한 가장 큰 실험이고, 결과는 부정적이다.** W0. `[출처:조각]`
- **WordNet** — Miller, CACM 38(11):39–41, 1995, doi:10.1145/219717.219748. **KorLex**: 13만 synset · 15만 의미(조각).
  **FrameNet** — Baker, Fillmore, Lowe, COLING-ACL 1998. 전부 손 저작(W0). `[출처:조각]`
- **ConceptNet 5.5** — Speer, Chin, Havasi, AAAI 2017, doi:10.1609/aaai.v31i1.11164, arXiv:1612.03975. 전문가 자원 ·
  크라우드소싱 · 게임으로 모은 다국어 지식 그래프(조각). 그래프 자체는 W0 에 가깝지만 논문의 주 용도는 **임베딩과
  결합**(W2). `[출처:조각]`
- **PPDB** — Ganitkevitch, Van Durme, Callison-Burch, NAACL-HLT 2013: 영어 바꿔말하기 쌍 2.2억(어휘 800만)(조각).
  이중언어 피벗으로 뽑는데 그 **정렬은 통계 기계번역의 학습된 정렬 모형**에서 온다 → W2 산출물(가중치는 안 싣지만
  가중치로 만든 표). `[출처:조각]`
- **Winograd Schema Challenge 2016** — IJCAI-16: 최고 58%(Liu, 상식 강화 **임베딩**); 지식 기반 참가작들은 공개 예제용
  지식만 넣어 새 문제에서 **우연 수준**(조각, Davis 페이지). "The Defeat of the WSC", arXiv:2201.02387 (제목만).
  `[출처:조각]`

### (6) 알맞게 되묻기 · 거부하기

- **Unanimity principle** — Khani, Rinard, Liang, "Unanimous Prediction for 100% Precision with Application to
  Learning Semantic Mappings", ACL 2016 (P16-1090), arXiv:1606.06368. **자료와 모순 없는 모든 모형이 같은 답을 낼
  때만 답하고 아니면 "모른다"** — 의미 파싱에서 100% 정밀도를 겨냥(조각). WALP 의 "추측 안 함" 의 이론적 형태이며,
  무가중치 가설 공간(사전 후보 해석 전부)에 그대로 적용된다. `[출처:조각]`
- **Rosie** — 모르는 낱말을 감지하면 되묻는다(위 (2), 기존 `WALP.md` 에도). `[출처:조각]`

### (7) 생성

- **SimpleNLG** — Gatt & Reiter, ENLG 2009 (W09-0613): 굴절·어순·일치·대명사화를 하는 규칙 표면 실현기, 여러 언어로
  이식(조각). 실패: **무엇을 말할지**(내용 선택)는 안 한다 — 주어진 구조를 문장으로만. ERG·GF 도 역방향 생성이 된다.
  W0. `[출처:조각]`
- **SHRDLU** — Winograd 1971(MIT 박사논문). 닫힌 세계에서 파싱 · 질의응답 · 생성까지; 실패: 50여 낱말, **완전히
  파싱되는 문장만**, 새 물체 종류를 못 배움(조각, 위키·2차). WALP 의 가장 먼 조상이자 같은 병. `[출처:조각]`

## 2. 경계 — 계수 통계는 "학습된 가중치" 인가 (정의 제안)

조각들이 보여 주는 것: "파라미터 없음" 은 느슨하게 쓰이고(gzip 논문), 무작위 기저(HDC)나 계수(infini-gram)도
결국 **훈련 자료에서 온 수**를 싣는다. 그래서 이진이 아니라 **세 층**으로 적자고 제안한다.

| 층 | 정의 | 예 | WALP 에서 |
|---|---|---|---|
| **W0 손 저작** | 모든 기호·수가 사람이 적었거나 명세에서 결정적으로 나온다 | 문법, 사전, WordNet/KorLex, PDDL, DSL, 편집거리 | 파서·`lexicon.csv`·`tools.csv`·안전층 |
| **W1 닫힌꼴 계수** | 모든 수가 **선언된 모음**에 대한 셈의 닫힌꼴 함수이고, (i) 각 수를 기여한 사례까지 되짚을 수 있고, (ii) 사례 하나를 지우면 그 기여만 정확히 빠지며, (iii) 목표 라벨에 맞춰 **탐색·최적화한 자유 파라미터가 관례값 몇 개(k1, b 등) 이하** | BM25 IDF, n-gram/∞-gram, HDC 원형, 사전 빈도로 고른 오타 교정, 사례 저장소 | 사례 검색(CBR) |
| **W2 최적화 파라미터** | 손실·보상에 대해 탐색/경사로 맞춘 수. 개수와 무관 | 신경망, 로그선형 CCG, SMT 정렬(→PPDB), 학습 품사 태거 | **v0.2/v0.3 에서 승격된 정책 파라미터**(대기 20 등 — 결과에 맞춰 탐색·검정으로 고른 수) |

- 마지막 줄을 숨기지 않는다: **WALP 의 자기개선 고리는 이미 W2 를 한다** — 몇 개의 이산 파라미터를 결과에 맞춰
  고른다. 차이는 개수(한 자릿수), 이산성, 검정·회귀 관문뿐이다. "학습된 가중치 없음" 이라고 쓰려면 "**신경망
  가중치 없음 · 최적화 파라미터는 N개, 전부 이름·값·승격 근거가 원장에 있음**" 으로 적는 것이 정확하다.
- W1 을 허용하면 "무가중치" 주장은 약해진다: infini-gram 은 가중치 0개로 다음 토큰 47%(작은 n 은 29%)를 낸다(조각;
  Liu, Min, Zettlemoyer, Choi, Hajishirzi, COLM 2024, arXiv:2401.17377). 그 폭은 **5조 토큰을 외운 것**에서 온다.
  계수가 커지면 W1 은 "투명한 가중치" 일 뿐이다. 그래서 층 표시는 **주장마다** 붙여야 한다.

## 3. WALP 의 잰 틈을 가장 많이 닫을 후보 3+1 (순위)

잰 틈(RESULTS §1, §9): 봉인 문장의 OK 라벨 중 거부 31~37%(1위 사유 `unknown_word` — `spot` · `forest-green` · `주시고요` ·
`택배` · `before`), 도구 정확도 59~70%, 잘못 실행 8/108(다른 도구 5 · 되물어야 할 것 실행 3). 코드를 보니 파서는
**정확 일치 토큰 사전 + 한국어 앞머리 표**, 라우터는 **부분문자열 일치 + 글자수 무게**(IDF·편집거리 없음).

1. **어휘 강건층: 자모 편집거리 + 대칭 삭제 + 발음 키, 만장일치로만 수락** (SymSpell · Double Metaphone ·
   Khani 2016). 층 W0/W1. 닫는 것: 오타·띄어쓰기·활용 꼬리(`주시고요` 같은 어미 변이는 앞머리/꼬리 규칙 확장으로).
   **거부된 `unknown_word` 중 오타·어미 변이의 몫만** 닫는다 — 그 몫이 얼마인지 아직 안 쟀다(먼저 거부 목록을
   손으로 분류해 상한을 재야 한다). 교정 후보가 둘 이상이거나 타입이 안 맞으면 되묻기 — 잘못 실행을 늘리지 않는
   유일한 방식이다. 못 하는 것: `spot`→"자리", `before`→기한 같은 **진짜 새 낱말**.
2. **손 저작 어휘 자원 수입: KorLex/WordNet 동의·상하위 관계 + FrameNet/KALM 식 프레임 사상** (W0). 근거: WALP 스스로
   관계 추론을 켜자 새 표현 27% → 63% 였고 "이득은 사전에 그 관계가 적혀 있을 때만" 이었다 — 즉 병목은 **관계의 양**이고,
   13만 synset 짜리 손 저작 자원이 있다. 위험: `lime`→초록 잘못 실행처럼 **수입한 지식의 경계가 평가자와 다를 수
   있다** — 색·브랜드 같은 과업 핵심 칸은 수입 관계로 **실행하지 말고 되묻기**로만 쓰는 것이 안전하다. PPDB·ConceptNet
   임베딩은 W2 산출물이라 넣으면 층을 바꿔 적어야 한다.
3. **도구 라우터: 도구 설명문 BM25 + Genie 식 템플릿 문법으로 인자 + 만장일치 거부** (W1+W0). 지금의 글자수 무게를
   도구 목록 자체에서 센 IDF 로 바꾸면(모음 = 69개 도구의 docstring·`tools.csv`), "보여" 같은 흔한 낱말이 여러 도구에
   점수를 주는 것을 자동으로 누른다. 잘못 실행 중 "다른 도구 5" 는 이 부류일 가능성이 높다(확인 안 함 — 8건을 먼저
   분류해야 한다). 못 하는 것: 겹치는 낱말이 없는 바꿔 말하기. gzip 사건이 보여 주듯, 여기서 수를 낼 때는 **같은 봉인
   모음, 같은 분모**로만 비교한다.
4. **(+1) 대화형 어휘 학습 — Rosie 식 "그게 뭐예요?" + EBG/PBE 식 일반화, 검증 뒤 사전 승격** (W0 규칙, 사용으로 자람).
   유일하게 **쓸수록 거부가 줄어드는** 부품이다 — 거부를 "`spot` 은 무슨 뜻인가요? (구역/물체/색)" 되묻기로 바꾸고,
   사람이 준 답을 WALP 의 기존 승격 관문(회귀·불변식)을 거쳐 `lexicon.csv` 에 올린다. 봉인 평가 수는 올리지 못한다
   (평가 중엔 사람이 없다) — 효과는 `!walp 결과` 의 사람 원장에서만 잴 수 있다.

**이 넷이 못 하는 것 — 그대로 적는다.** 넷 다 **닫힌 과업의 어휘 틈**을 줄이는 부품이다. Opus 의 폭(임의 영역의 이해,
상식, 몇 예시로 새 과제, 내용을 정하는 생성)은 아무것도 안 준다. 폭을 손으로 채운 가장 큰 실험(Cyc)과 지식 기반 WSC
참가작, 손문법의 한계 서술(GF "grammars leak"), ARC 탐색 상한(20%)이 같은 쪽을 가리킨다. **학습된 파라미터 없이 LLM 수준의
폭을 낸 존재 증명은 이번 조사에서 없었다** — 없다는 증명이 아니라 못 찾은 것이다(아래).

## 우리가 그것과 다른 점

좁다. 부품은 전부 있는 것이다.

1. 부품을 **실패 닫힘(fail-closed)** 으로 묶고 대가를 잰다 — 각 부품을 켤 때 거부율과 **잘못 실행 수를 함께**, 봉인
   모음에서. 조각으로 본 선행연구(ERG 커버리지 · KALM 정확도 · gzip 정확도)는 "받아들인 것의 정확도" 나 "파싱 비율" 을
   내지 "추측으로 실행한 수" 를 따로 내지 않는다(원문을 안 읽어서 확정 못 함).
2. 무가중치를 **층(W0/W1/W2)으로 적고 실행 중 강제**한다(`nollm/` 의 LLM 차단 계수에 층 표시를 더하는 것). 층 표시를
   주장마다 붙이자는 제안은 선행연구에서 못 찾았다.
3. 대화형 어휘 학습(후보 4)을 WALP 의 검증 승격 관문과 결합 — Rosie 는 가르친 것을 회귀 관문 없이 받는다(조각 수준의 인상,
   미확인).

## 찾아본 질의

- `English Resource Grammar coverage percentage Wikipedia sentences DELPH-IN Flickinger`
- `Grammatical Framework Ranta resource grammar library languages coverage robustness`
- `Fluid Construction Grammar Steels robustness open-ended language processing`
- `FlashFill Gulwani POPL 2011 programming by example string transformations few examples`
- `Metagol meta-interpretive learning one-shot learning Muggleton few examples logic programs`
- `ARC-AGI program synthesis DSL search without neural network Kaggle 2020 icecuber accuracy`
- `Cyc Lenat common sense knowledge base lessons failure evaluation`
- `hyperdimensional computing random vectors language identification Kanerva without training`
- `KALM knowledge authoring logic machine Gao Fodor Kifer FrameNet controlled natural language accuracy`
- `Khani Rinard Liang unanimous prediction 100% precision semantic mappings ACL 2016 abstain`
- `infini-gram unbounded n-gram language model trillion tokens suffix array Liu 2024 next token accuracy`
- `gzip kNN text classification critique Ken Schutze top-2 accuracy inflated results`
- `Winograd Schema Challenge 2016 results knowledge-based systems accuracy commonsense symbolic`
- `Korean Resource Grammar HPSG Kim Yang LKB coverage; KorLex Korean WordNet`
- `SymSpell symmetric delete spelling correction edit distance Damerau-Levenshtein speed`
- 그 밖에: Zettlemoyer&Collins CCG · ConceptNet 5.5 · Copycat · EBG · WordNet/FrameNet · SimpleNLG · Snips · Fast Downward ·
  Rosie ITL · PPDB · Attempto/CNL · SHRDLU · Z3 · Double Metaphone/자모 편집거리 · Opitz gzip vs BoW · BM25

## 아직 못 지운 가능성

- **아무 원문도 못 읽었다**(WebFetch 가 arxiv · ACL Anthology · AAAI · DELPH-IN 에서 전부 차단). ERG 94%, KALM 99.3%, infini-gram
  47%, HDC 97%, icecuber 20%, Cyc 인년·비용은 전부 조각의 수다. 특히 ERG 94% 는 "잘 편집된 글" 기준이고 무엇을 "파싱" 으로
  셌는지(옳은 파스인지 아무 파스인지) 확인 못 했다 — BNC 의 57%·83% 와 크게 다르다.
- **ERG 의 모르는 낱말 처리**가 학습된 태거에 기대는지 ERG 에 대해 직접 확인 못 했다(일반 관행 조각뿐). 기대면 "무가중치 넓은
  문법" 의 가장 강한 사례가 W2 를 품는다.
- **Copycat/SME** 는 조각만 봤고(SME: Falkenhainer, Forbus, Gentner, AIJ 41, 1989; Copycat: Hofstadter & Mitchell, *Fluid Concepts
  and Creative Analogies*, 1995) 수치 결과가 없어 본문 표에 넣지 않았다. 유비 엔진이 WALP 의 새 낱말 처리(구조로 뜻 추측)에
  쓸모 있을 수 있다 — 안 쟀다.
- **규칙 라우터 vs 학습 라우터의 학술 비교**는 두 번째 조사에서도 못 찾았다(Rasa 규칙 정책, AIML, 음성비서 grammar NLU).
- **한국어 무가중치 형태소 분석**(사전·규칙 기반 분석기)의 커버리지 수를 안 찾았다 — 거부 사유 중 `주시고요` 같은 어미 변이는 이
  문헌이 직접 답할 수 있다. 널리 쓰는 한국어 분석기 다수가 CRF 등 학습 모형(W2)이라는 점도 확인 필요.
- **최신(2025~2026) 뉴로심볼릭·"LLM-free" 에이전트**를 따로 찾지 않았다. 비신경 방법으로 ARC-AGI-2 나 도구 사용 벤치에서 의미
  있는 수를 낸 것이 있을 수 있다(arXiv:2606.31543 "Modality-Driven Search … ARC-AGI-2" 가 검색에 떴다 — 제목만, LLM 사용 여부 모름).
- 후보 1·3 의 효과 크기는 **추정조차 안 했다.** 거부 25건과 잘못 실행 8건을 먼저 손으로 분류(오타/어미/진짜 새 낱말/흔한 낱말
  오염)해야 각 부품의 상한이 나온다 — 그것이 짓기 전의 첫 걸음이다.
