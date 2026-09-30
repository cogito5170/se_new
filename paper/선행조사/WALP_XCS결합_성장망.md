# 선행조사 — XCS 에 CMAC · RBF · Echo 를 붙이기, "경량 학습 → 은닉층 성장"

요청(사용자, 2026-09-30): "CMAC RBF Echo 고려해봐 xcs에 붙히는거" · "경량 학습->은닉층 성장".
맥락: 진화 효과 실험(`walp/eval/PREREG_진화효과.md`, 봉인 v3 한 번) — GA 는 덮기만보다 확실히 낫지만(85/0), 진화한 XCS 는
**셈만 하는 나이브 베이즈(NB)에 5/45 로 지고**, 자료가 늘어도 안 올랐다(57.6 → 56.4 → 57.0%). NB 73.2%, MLP 71.4%(늘수록 오름).
→ 문제는 "진화가 안 일한다" 가 아니라 **XCS 가 학습기로 약하다**(표본 579, 12 행동에 규칙 1600).

인용은 전부 검색 조각 — `[출처:조각]`.

## 가장 가까운 선행연구

### (1) XCS 안에 신경망/RBF 를 넣기
- **X-NCS / X-NFCS** — Bull & O'Hara, "Accuracy-based neuro and neuro-fuzzy classifier systems", GECCO 2002. 규칙마다 조건·행동이
  **작은 MLP**(X-NCS) 또는 **RBF**(X-NFCS)이고, 그 가중치를 XCS 의 GA 가 진화시킨다. 6-멀티플렉서 · Woods2 를 풀었다. `[출처:조각]`
- **XCSF + 신경 예측** — "Use of a Connection-Selection Scheme in Neural XCSF"(LNCS) · "Neural Rules for RL with XCSF"(2025, 제목만). `[출처:조각]`
- **"XCS: Is Covering All You Need?"**(GECCO '24 Companion) — 신경 예측을 쓰면 **덮기만으로도** 배우고, GA 는 규칙을 필요 이상 만들며
  이득이 작거나 불안정했다. → 신경망을 XCS 안에 넣으면 우리 H1(GA 효과)이 도리어 사라질 수 있다. `[출처:조각]`

### (2) 은닉층이 자라는 경량 학습
- **RAN(자원 할당 망)** — Platt, "A Resource-Allocating Network for Function Interpolation", Neural Computation 1991. 새 입력이
  기존 단위들과 **멀고**(새로움) 오차가 **크면** RBF 단위를 **하나 더한다**, 아니면 LMS 로 조금 고친다. **"경량 학습 → 은닉층 성장" 그 자체.** `[출처:조각]`
- **Cascade-Correlation** — Fahlman & Lebiere, NIPS 2 (1990) pp.524–532. 최소 망에서 시작해 **후보 단위 여럿(pool)** 을 기르고, 남은
  오차와 가장 상관 높은 것을 **하나 붙이고 얼린다**. `[출처:조각]`
- **EPNet** — Yao & Liu 1997. 진화 프로그래밍으로 구조와 가중치를 같이 진화 — 돌연변이 순서가 "훈련 → 단위 지우기 → 연결 지우기 →
  연결 더하기 → **단위 더하기**"(단순한 쪽을 먼저 시험). `[출처:조각]` · **NEAT**(2002, 앞 조사) 도 구조를 키운다.

### (3) CMAC · Echo
- **CMAC** — `WALP_CMAC.md`(앞 조사). 겹친 격자 + LMS. **연속 입력**에서 일반화가 이점이다. 우리 입력은 **이진 비트**라 CMAC 은
  "비트 조합(해시) + 선형 LMS" 로 줄어든다 — NB 나 선형 모형과 거의 같다. **이득이 작을 것**으로 본다(재 보지 않음).
- **ESN(에코 상태 망)** — Jaeger 2001. 순환 은닉층을 **무작위로 고정**하고 **출력 가중치만** 배운다(경량). 텍스트 분류에 쓴 예가 있으나
  대개 **사전학습 임베딩(트랜스포머)** 위에서다 — 그건 우리 제약 위반. **글자 순서를 직접 읽는 ESN 으로 대화 행위를 가른 예는 못 찾았다.**
  우리에게 ESN 의 이점은 하나: 손 단서·글자조각 목록 없이 **글자 흐름을 그대로** 읽는다(새 말투·오타에 강할 수 있다). `[출처:조각]`

## 우리가 그것과 다른 점(후보)

**"진화가 은닉 단위를 제안하고, 경량 학습기가 받아들인다"** — 셋의 결합:
1. XCS/GA 가 만드는 규칙 조건(예: `'잘' 과 '가' 가 있고 '찾' 은 없다`)을 **은닉 단위 후보**로 쓴다(CasCor 의 후보 pool 을 진화로).
2. RAN 식 기준으로 **남은 오차를 줄이는 후보만 은닉층에 붙인다** — 대화가 쌓일수록 은닉층이 자란다.
3. 출력층은 가벼운 선형/소프트맥스(LMS) — 붙은 단위 위에서만 배운다.
4. (선택) ESN 글자 저수지를 입력 곁가지로 — 무작위 고정, 출력만 배움.

붙은 단위 하나하나가 **사람이 읽는 조건**이라 "읽을 수 있는 자라는 망" 이 된다. 가장 가까운 것은 X-NFCS(규칙=RBF)와 CasCor(후보 pool)
이고, 새로움 주장은 약하다 — 없다고 보는 편이 맞다.

## 짓는다면 붙일 대조(사전등록할 것) — 새 봉인 v4 필요(v3 는 열렸다)

| 조건 | 왜 |
|---|---|
| NB | **지금 가장 센 기준선(73.2%)** — 이걸 못 이기면 끝 |
| MLP(고정 32) | 은닉층이 자라지 않는 신경망 |
| 성장망(GA 후보) | 제안 |
| 성장망(**무작위 후보**) | 진화 효과 분리 — GA 대신 무작위 조건을 후보로 |
| ESN 출력만 · 성장망+ESN | 글자 흐름 곁가지의 몫 |
| 학습 곡선 25/50/100% | "대화가 늘수록" 오르는가(XCS 는 안 올랐다) |

## 찾아본 질의
- `XCSF neural network prediction learning classifier system radial basis function Bull O'Hara accuracy-based neuro classifier system`
- `resource allocating network Platt 1991 growing RBF hidden units; cascade-correlation Fahlman Lebiere 1990 constructive neural network add hidden units`
- `echo state network reservoir computing character-level text classification dialogue act short utterance Jaeger 2001`
- `EPNet Yao Liu 1997 evolving artificial neural networks add hidden nodes evolutionary constructive; genetic algorithm candidate hidden units`

## 아직 못 지운 가능성
- 표본이 579 뿐이다 — 어떤 망이든 NB 를 넘기 어려울 수 있다(NB 는 작은 자료에 강하다). 성장망이 NB 를 못 이기면, 정직한 답은 "WALP 의 학습기는 NB" 다.
- "진화가 후보를 낸다" 가 "무작위 후보" 보다 나은지는 문헌에서 못 봤다 — 우리 실험의 핵심 대조다.
- 원문은 하나도 못 읽었다(프록시).
