# 선행조사 — WALP 에 CMAC(타일 부호화)를 붙이기

요청(사용자, 2026-09-30): "CMAC 선행조사부터 해줘." 앞 답에서 "가중치 없이 배우는 부품" 후보로 CMAC ·
사례 기반 · 결정 트리를 들었고, 그중 CMAC 을 먼저 본다. **코드보다 먼저 커밋한다.**

**인용 수준을 먼저 밝힌다.** 이번 조사에서 WebFetch 는 arxiv.org · incompleteideas.net · proceedings.neurips.cc ·
en.wikipedia.org · ncbi.nlm.nih.gov · web.stanford.edu · courses.cs.duke.edu 가 전부 egress 프록시에 막혔다.
**전문도 초록도 읽은 것이 없다 — 아래 인용은 전부 `[출처:조각]`**(검색 결과 조각)이다. 서지(저자·권·쪽)는 조각에서
옮겼고, 조각에 없는 내용은 `[기억]` 으로 따로 적는다.

## 0. 정직한 결론부터

1. **CMAC 은 "가중치 없는" 방법이 아니다.** 겹친 격자(타일링)로 입력을 희소한 이진 특징으로 바꾸고, 그 위의
   **선형 가중치를 LMS 로 학습**한다. v04 조사 §2 의 층으로는 **W2(최적화 파라미터)** 이고, 개수는 타일 수만큼
   (수백~수천)이다. 지금 WALP 의 W2 는 이산 파라미터 한 자릿수다. 붙이면 **그 주장이 바뀐다** — 문서에 그렇게 적어야 한다.
2. **방법은 전부 있다.** 새것은 없다. 우리 몫이 있다면 WALP 의 관문(봉인 평가 · 쌍대 검정 · 안전층 거부권 ·
   힙 없는 고정 표)에 **묶는 것**뿐이다.
3. **WALP 에서 맞는 자리는 하나다 — 실행기의 결정(재관측할지·확정할지·넘어갈지)** (아래 §3 의 B). 원래 용도인
   연속 제어(A)는 WALP 에 실제 플랫폼이 없어 **잴 수 없고**, 자기개선 고리의 대리모형(C)은 **SMAC(랜덤 포레스트)
   이 이미 그 문제의 표준**이라 CMAC 을 고를 이유가 약하다.
4. **조사 중 따로 걸린 것:** 지금의 자기개선 고리(이웃 한 걸음 + 쌍대 검정으로 승격)는 **ParamILS / FocusedILS
   (Hutter 외 2009)** 와 거의 같은 꼴이다. v0.3 선행조사(Hooke–Jeeves · VNS · 공통 난수)는 이것을 못 봤다.
   §5 에 적는다.

## 1. CMAC 이 무엇인가

- 입력 공간을 격자로 자른 **타일링**을 여러 장, 서로 조금씩 어긋나게 겹친다. 한 입력은 타일링마다 타일 하나에
  들어가고, 출력은 **그 타일들의 가중치 합**이다. 학습은 오차를 그 타일들에 나눠 더하는 LMS 다.
- 가까운 입력은 타일을 많이 공유하므로 **비슷한 출력을 낸다(일반화)**. 먼 입력은 공유하지 않아 **서로 간섭하지
  않는다(국소성)** — MLP 와 달리 새것을 배워도 먼 곳의 옛것을 안 망가뜨린다.
- 계산은 타일링 수만큼의 **표 찾기와 덧셈**이다. 기억 크기가 고정이고, 한 번 계산하는 시간이 입력과 무관하게
  일정하다 → 힙 없는 C++ 코어·WCET 규칙과 맞는다.
- 차원이 늘면 표가 지수로 커진다. 해법은 **해싱**(기억을 과업이 실제로 쓰는 만큼만)과 일부 차원만 쓰는 타일링이다.

## 가장 가까운 선행연구

### (A) 원래 용도 — 로봇 제어

- **Albus, "A New Approach to Manipulator Control: The Cerebellar Model Articulation Controller (CMAC)",
  J. Dynamic Systems, Measurement, and Control 97(3):220–227, 1975.** 소뇌를 본뜬 함수 근사기로, 로봇 팔 제어기로
  처음 제안됐다. "비슷한 입력은 비슷한 출력" 이 전제다. `[출처:조각]`
- **Miller, Hewes, Glanz, "Real-time dynamic control of an industrial manipulator using a neural network based
  learning controller", IEEE Trans. Robotics and Automation 6:1–9, 1990.** 산업용 팔의 실시간 동역학 제어에
  CMAC 을 쓴 대표 사례. `[출처:조각]`
- **Miller, Glanz, Kraft, "CMAC: An associative neural network alternative to backpropagation", Proc. IEEE
  78(10):1561–1567, 1990.** 역전파 MLP 의 대안으로서의 CMAC 개관. `[출처:조각]`
- Commuri 외, "CMAC neural network control of robot manipulators", J. Robotic Systems 14(6), 1997 — 제목만 봄. `[출처:조각]`

### (B) 결정 학습 — 강화학습의 타일 부호화

- **Sutton, "Generalization in Reinforcement Learning: Successful Examples Using Sparse Coarse Coding", NIPS 8
  (1995), pp.1038–1044, MIT Press 1996.** CMAC(=타일 부호화)을 연속 상태 강화학습에 써서 성공한 예들. 선형
  타일 부호화 위의 Sarsa 류. `[출처:조각]`
- **Boyan & Moore, "Generalization in Reinforcement Learning: Safely Approximating the Value Function", NIPS 7
  (1995).** 동적계획 + 함수근사는 **아주 순한 경우에도 완전히 틀린 정책**을 낼 수 있음을 보였다(Sutton 1996 은
  이것에 대한 답). → 우리에게는 **실패 조건**이다. `[출처:조각]`
- **Stone, Sutton, Kuhlmann, "Reinforcement Learning for RoboCup Soccer Keepaway", Adaptive Behavior 13(3), 2005.**
  낮은 층 기술(드리블·패스)은 **손으로 짠 채** 두고, 높은 층의 결정(공을 쥘까 · 누구에게 넘길까)만 SMDP
  Sarsa(λ) + 선형 타일 부호화로 배워 여러 기준 정책을 이겼다. **WALP 와 구조가 가장 가깝다** — 손 규칙 실행기 위에서
  "어느 규칙을 부를지" 만 배우는 꼴. `[출처:조각]`
- Sutton & Barto, *Reinforcement Learning: An Introduction* 2판 §9.5.4 "Tile Coding" — 여러 장의 어긋난 타일링,
  **비대칭 어긋남**(대각선 인공물을 피함), 해시 표. `[출처:조각]` 걸음 크기 α≈1/(10·타일링 수) 같은 관례는 `[기억]`.

### (C) 자기개선 고리의 대리모형(정책 파라미터 → 성공률)

- **ParamILS — Hutter, Hoos, Leyton-Brown, Stützle, "ParamILS: An Automatic Algorithm Configuration Framework",
  JAIR 36:267–306, 2009 (doi:10.1613/jair.2861).** 순서형·범주형 파라미터에 대한 **확률적 국소 탐색**. FocusedILS
  는 설정마다 평가에 쓰는 시간을 **적응적으로 제한**한다. `[출처:조각]`
- **SMAC — Hutter 외 2011.** 랜덤 포레스트를 대리모형으로 써서 **정수·범주형 파라미터**를 바로 다루고, 잡음 있는
  목적은 반복 평가로 다룬다. `[출처:조각]`
- 대리모형 + 패턴 탐색 혼성(RBF 대리모형) — Springer, Struct. Multidisc. Optim. 2006 (doi 10.1007/s00158-006-0034-x),
  제목·조각만. `[출처:조각]`

### 이론과 한계

- **Wong & Sideris, "Learning convergence in the cerebellar model articulation controller", IEEE Trans. Neural
  Networks 3(1):115–121, 1992.** 어떤 이산 학습 자료에 대해서도 CMAC 학습이 **임의 정확도로 수렴**함을 보였다
  (푸리에 해석). 해시 충돌은 흔히 무시되지만 수렴을 늦춘다는 후속 조각이 있다. `[출처:조각]`
- **Brown, Harris, Parks, "The interpolation capabilities of the binary CMAC", Neural Networks 6:429–440, 1993.**
  이진 CMAC 은 **임의의 다변수 표를 일반적으로 재현하지 못한다** — 표현할 수 있는 것은 (대략) 일변수 조각상수
  함수들의 합 꼴이다. → 입력 사이 **상호작용이 강한 결정**이면 CMAC 이 구조적으로 틀린다. `[출처:조각]`
- 차원의 저주: 해싱으로 기억을 "과업이 실제로 쓰는 만큼" 으로 줄이지만, 그만큼 충돌이 는다. `[출처:조각]`
- 하드웨어: FPGA 구현(Virtex · Altera, 16비트 고정소수점)이 여럿 있다 — 실시간 제어 용도. `[출처:조각]`
- 요즘: IEEE 개관 "Review of the Cerebellar Model Articulation Controller"(IEEE doc 9901793, 2022 무렵),
  층을 쌓은 "Deep CMAC"(잡음 제거) — 제목·조각만. Xing, "A Historical Review of Forty Years of Research on CMAC",
  arXiv:1702.02277 — **막혀서 못 읽었다.** `[출처:조각]`

## 2. 우리가 그것과 다른 점

없다 — 방법은 전부 있다. 붙인다면 우리 몫은 WALP 규칙에 묶는 것뿐이다.

1. **결정의 틀은 손 규칙이 쥔다.** CMAC 은 정책 그래프가 허락한 행동들 **사이에서만** 고르고, 안전층의 거부권은
   그대로다(keepaway 가 낮은 층을 손으로 둔 것과 같은 배치).
2. **승격은 지금처럼** 봉인 평가 + 쌍대 검정을 통과해야 한다. CMAC 가중치 표 자체가 한 "정책 버전" 이 되고,
   롤백·CRC·불변식 검사를 받는다.
3. **힙 없는 고정 표**(타일링 수 × 타일 수 × 행동 수, 컴파일 때 크기 고정). 해싱을 쓰면 충돌 수를 잰다.
4. **W2 가 늘어난 것을 숨기지 않는다** — "신경망 가중치 없음, 최적화 파라미터 N개" 의 N 이 한 자릿수에서 수천이 된다.

## 3. WALP 의 자리별 적합성

| 자리 | 입력 | 잴 수 있나 | 가장 가까운 선행 | 판정 |
|---|---|---|---|---|
| **A 제어층**(연속 제어) | 관절·속도 등 연속값 | **못 잰다** — IPlatform 구현이 시뮬레이터뿐, 연속 동역학 없음 | Albus 1975, Miller 1990 | 보류. 실제 플랫폼이 생기면 다시 |
| **B 실행기 결정**(재관측/확정/넘어가기) | 가설의 표 수·관측 수·남은 에너지·다음 후보까지 거리 등 저차원 | 잰다 — 시뮬레이터 + 봉인 평가 | **Stone·Sutton·Kuhlmann 2005**, Sutton 1996 | **맞는다.** 지금은 `k_confirm`·`observe_max`·`theta_pct` 문턱으로 정한다 |
| **C 고리의 대리모형**(파라미터 → 성공률) | 정책 파라미터 13+ (범주형 `rule_action` 포함) | 잰다 | **SMAC(RF)**, ParamILS | 약함. 범주형·상호작용에 RF 가 더 맞고, 대리모형은 호스트 쪽이라 힙 없음 이점도 없다 |

### B 를 한다면 — 붙일 대조와 죽일 사소한 설명

- **기준선 1 — 지금의 문턱 정책**(v0.3 승격본). 이것을 못 이기면 끝이다.
- **기준선 2 — 타일링 1장짜리 CMAC = 그냥 표.** CMAC 이 이겨도, 표가 똑같이 이기면 이득은 **일반화가 아니라
  "상태별로 따로 정했다"** 는 데서 온 것이다. 이 대조 없이는 CMAC 이 도왔다고 말하지 않는다.
- **사소한 설명:** (i) 학습 모음과 평가 모음이 겹쳐 외운 것 — 봉인 모음으로 막는다. (ii) 문턱 정책의 파라미터를
  같은 예산으로 다시 고르면 같은 이득이 나는 것 — 같은 에피소드 예산으로 문턱 재탐색을 대조로 둔다.
  (iii) Brown·Harris·Parks 의 표현 한계 — 입력 쌍 상호작용이 크면 결합 타일링(2차원)을 넣고 그 효과를 따로 잰다.
- **실패 조건(Boyan & Moore):** 부트스트랩 가치 학습이 발산·진동할 수 있다. 몬테카를로 반환(에피소드 끝 결과)으로
  먼저 하고, Sarsa(λ) 는 그다음.

## 4. 찾아본 질의

- `Albus 1975 "A new approach to manipulator control: the cerebellar model articulation controller (CMAC)" Journal of Dynamic Systems Measurement and Control`
- `Miller Glanz Kraft 1990 "CMAC: an associative neural network alternative to backpropagation" Proceedings of the IEEE`
- `Sutton 1996 "Generalization in reinforcement learning: successful examples using sparse coarse coding" tile coding CMAC`
- `Brown Harris Parks "interpolation capabilities of the binary CMAC" Neural Networks 1993 limitations`
- `CMAC learning convergence Wong Sideris 1992 IEEE Transactions Neural Networks hashing collisions`
- `CMAC FPGA fixed-point hardware implementation embedded microcontroller cerebellar model articulation controller`
- `CMAC curse of dimensionality memory requirement high-dimensional input limitation compared RBF networks`
- `CMAC reinforcement learning robot soccer keepaway tile coding Stone Sutton 2005`
- `Boyan Moore 1995 "Generalization in reinforcement learning: safely approximating the value function" function approximation divergence`
- `surrogate-assisted pattern search noisy simulation optimization discrete parameters response surface common random numbers`
- `Bayesian optimization noisy integer-valued parameters simulation tuning algorithm configuration SMAC random forest surrogate Hutter 2011`
- `ParamILS Hutter Hoos Leyton-Brown Stützle 2009 JAIR "automatic algorithm configuration framework" iterated local search FocusedILS`

## 5. 아직 못 지운 가능성

- **원문을 하나도 못 읽었다.** 특히 Xing 의 40년 개관(arXiv:1702.02277)과 Sutton 1996 전문. 수렴 조건·타일링
  설계 관례는 거기서 확인해야 한다.
- **B 에 CMAC 보다 맞는 것이 있을 수 있다:** 국소 가중 회귀(Atkeson·Moore·Schaal 1997, 기억 기반 — W1 에 가깝다)
  · 결정 트리(규칙 표로 바로 바뀐다 — WALP 규칙과 더 맞을 수 있다) · 퍼지 CMAC. 셋 다 안 봤다.
- **ParamILS 가 지금 고리의 선행연구다.** v0.2/v0.3 의 "이웃 한 걸음 + 검정으로 승격 + 헛수고 멈춤" 은 FocusedILS
  의 "국소 탐색 + 적응적 평가 예산" 과 같은 계열이다. v0.3 선행조사(`WALP_v03_도구배선_자기개선.md`)에 이 줄을
  보태야 한다 — 우리 고리의 새로움 주장은 없다(원래 없다고 적었지만, 가장 가까운 것을 잘못 짚었다).
- 결정 B 의 **입력이 정말 저차원인지** 안 쟀다. 가설 여럿·구역 여럿이 얽히면 입력이 커지고 해싱 충돌이 는다.
- keepaway 의 이득이 "타일 부호화" 덕인지 "높은 층만 배우는 배치" 덕인지는 조각으로 가를 수 없다.
