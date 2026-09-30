# 선행조사 — WALP 숙고기: Shakey/SPA 의 STRIPS 로 여러 걸음 요청을 계획하기

요청(사용자, 2026-09-30): 처음 설계의 "2. 숙고기 = 숙고형의 원형 — Shakey 와 SPA(1966~1980년대)". 지금 WALP 는
`multiple_targets`("찾을 것이 둘 이상이다 — 한 번에 하나만") 로 여러 걸음 요청을 **거부**한다.

인용은 전부 검색 조각 — `[출처:조각]`.

## 가장 가까운 선행연구
- **STRIPS** — Fikes & Nilsson 1971(SRI). 연산자 = 전제조건 + 더할 목록 + 지울 목록. "STRIPS 가정": 연산자는 적힌 것만 바꾼다.
  Nilsson, "STRIPS, a retrospective"(Artificial Intelligence 1993). `[출처:조각]`
- **삼각 표 · PLANEX** — Fikes, Hart, Nilsson 1972(앞 조사): 성공한 계획을 일반화해 매크로로 재사용 · 실행 감시. `[출처:조각]`
- **조건부/우발 계획(contingency planning)** — 결과가 불확실하면 조건 가지(대체 경로)를 계획에 미리 넣는다. 최근 LLM 에이전트의
  "plan-then-execute" 도 조건부 대체 가지를 계획 그래프에 넣는다(arXiv:2509.08646, 제목·조각). `[출처:조각]`
- **자연어 → 로봇 계획** — 요즘은 LLM 이 단계 목록·코드로 옮긴다(ProgPrompt, SayCan 류). 우리는 **LLM 없이** 손 문법으로 옮긴다
  — 그 부분이 LLM 이 대신하던 몫이다(v04 조사에서도 적었다). `[출처:조각]`

## 우리가 다른 점
없다 — 방법은 1971~72 년 것 그대로다. 우리 몫은 WALP 규칙에 묶는 것:
1. 절 나누기(그리고 · 랑 · 그다음 · 없으면 · 아니면 · and · then · if not)와 **공유 수식어**(한 번 말한 피할 곳은 모든 걸음에, 색은 붙은 명사에만)를 손 문법으로.
2. 연산자 하나 `find(o)`: 전제 없음 · 결과가 불확실 → 더할 목록 {found(o)} 또는 {notfound(o)}. 목표 `A && B` 는 순서 계획, `A || B` 는 **우발 가지**(A 가 notfound 일 때만 B).
3. 걸음마다 지금의 C++ 실행기(시뮬)를 부른다 — 숙고기는 순서만 정한다(SPA 의 P).
4. 모르는 연결이나 가져오기·옮기기는 **거부**(추측 안 함). 성공한 계획의 **꼴**(예: `색+물건 || 색+물건`)을 삼각 표처럼 적어 둔다.

## 찾아본 질의
- `STRIPS Fikes Nilsson 1971 planning operators preconditions add delete lists; conditional contingency planning; natural language instruction to plan robot "if not found" fallback`

## 아직 못 지운 가능성
- 이 도메인의 계획은 얕다(찾기 하나뿐) — "STRIPS" 라 부르기에 과한 이름일 수 있다. 가치는 "여러 걸음을 거부하던 것을 푼다" 에 있고,
  그것은 **사소한 대조(쉼표·그리고로 자르기만)** 와 비교해야 보인다.
- 모음을 LLM 에이전트가 썼다.
