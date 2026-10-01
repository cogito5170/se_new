# WALP 를 LLM 앞단으로 — 선행조사 (2026-10-01, 코드보다 먼저)

사용자(2026-10-01): WALP 를 Opus/LLM 으로 가기 전의 **얇은 층**으로 개조한다. Deliberative – Sequencing – Control 세 층.
먼저 스스로 받아 해결하고, "모른다" 고 판단한 것만 LLM 의 답을 받고, **그것을 배운다** — 토큰을 줄이고 더 빨리 반응하려고.
물건 찾기에서 XCS 로 진화하던 구조를 그대로 옮긴다.

## 가장 가까운 선행 — 거의 같은 것이 있다 (전부 검색 조각만 봄 `[출처:조각]`)

| 선행 | 요지 | 우리와 |
|---|---|---|
| **Ramírez · Lindemann · Birch · Titov, "Cache & Distil: Optimising API Calls to Large Language Models"**, arXiv:2310.13561, ACL Findings 2024 | 작은 학생 모형이 요청을 먼저 받고, **정책**이 학생 답을 쓸지 LLM 을 부를지 정한다. LLM 의 답은 저장해 학생을 **계속 다시 기른다**("neural caching", 온라인 지식 증류). 정책은 능동학습 기준 — Margin Sampling · Query by Committee 가 일관되게 낫다. 분류 과업 | **사용자가 말한 설계와 뼈대가 같다.** 다른 점: 그들의 학생은 사전학습 LM(조각으로는 T5 계열 — 확인 못 함). 우리는 사전학습 가중치 없이 XCS · 성장망 |
| **FrugalGPT** (Chen · Zaharia · Zou, arXiv:2305.05176, 2023) | LLM 사슬(cascade) — 싼 것부터 시도하고 확신이 모자랄 때만 비싼 것으로. 비용 최대 98% 절감 보고 | "모르면 위로" 의 원형 |
| **RouteLLM** (2024) | 질의마다 약한/강한 모형을 고르는 학습된 라우터 — MT-Bench 에서 강한 모형 14% 만 쓰고 GPT-4 성능 95% | 우리 L1(되묻기) 자리에 "위로 보낼까" 결정이 온다 |
| **의미 캐시** — GPTCache, "GPT Semantic Cache"(arXiv:2411.05276) | 질의를 임베딩해 비슷한 질의의 답을 다시 쓴다. API 호출 최대 68.8% 절감 보고 | 우리는 임베딩(사전학습)이 없다 — 글자조각뿐. **teach_v1 에서 같은 뜻 다른 말을 1.7% 만 알아들었다** |
| **세 층 구조** — Gat, ATLANTIS(1991–93) · "On Three-Layer Architectures"(1998) · 3T | Controller(상태 없는 반응 고리) · Sequencer(이력을 보고 행동을 고름) · Deliberator(세계 모형 · 계획) | 사용자가 말한 세 층 그대로. 최근 TypeGo(arXiv:2607.05482)는 Deliberator · Sequencer 를 LLM 으로 돌린다 — 우리는 **Deliberator 만** LLM |
| LLM 교사 – 학생 분류 (arXiv:2411.19638) | 사람 라벨 없이 LLM 이 단 라벨로 학생 분류기를 기른다 | Cache & Distil 의 오프라인 판 |

XCS 를 LLM 교사와 붙인 연구는 조각에서 **못 찾았다**(그러나 아래 '못 본 곳').

## 우리가 다른 점 — 정직하게

뼈대(학생 먼저 · 정책이 위로 보냄 · LLM 답으로 학생을 다시 기름)는 **Cache & Distil 이다.** 남는 것은 조건뿐이다:

1. 학생에 **사전학습 가중치가 없다**(XCS · 성장망 · ESN). 그래서 학생이 배울 수 있는 것은 **부류(어느 처리기 · 행위)** 이지
   자유 문장이 아니다. 자유 답은 저장해 두었다가 같은 부류 · 비슷한 겉의 질문에 다시 쓰는 것(캐시)뿐이다.
2. 정책이 되묻기(L1)와 같은 자리에 있다 — 사람에게 물을지 · LLM 에게 물을지 · 스스로 답할지의 세 갈래.
3. 세 층(Gat)으로 갈라, LLM 은 맨 위 Deliberator 에만 둔다.

## 이 조건이 미리 말해 주는 한계

- 의미 캐시의 이득은 **임베딩이 같은 뜻 다른 말을 묶어 주는 데서** 온다. 우리 겉 닮음은 그것을 거의 못 한다(teach_v1: 1.7%).
  그러니 **자유 답 재사용의 절감은 거의 같은 말이 되풀이되는 일감에서만** 크다.
- 부류(행위 · 도구 · 처리기)는 XCS · 성장망이 일반화한다(봉인 v6 답 정확도 ~80%). 그래서 절감이 나는 곳은
  "LLM 이 무엇을 할지 정해 주던 것" — 라우팅 · 도구 고르기 · 정해진 답 — 이다.

## 찾아본 질의

- `Cache & Distil optimising API calls to large language models student model defers to LLM online knowledge distillation`
- `FrugalGPT LLM cascade RouteLLM router small model defer to large model cost reduction 2023 2024`
- `semantic cache LLM GPTCache reuse responses similar queries token cost reduction`
- `three-layer architecture 3T Gat ATLANTIS controller sequencer deliberator LLM agent hybrid reactive deliberative 2024 2025`
- `learning classifier system XCS with LLM teacher or LLM as oracle rule learning 2024 2025`
- `"neural caching" LLM student "deferral" policy margin sampling query by committee Ramírez 2023`

## 아직 못 본 곳

- 위 논문들의 전문(Cache & Distil 의 학생 모형 · 정책 세부 · 생성 과업 여부를 확인 못 함).
- LCS/XCS 와 LLM 교사를 붙인 GECCO · IWLCS 문헌(검색이 못 찾았을 뿐일 수 있다).
- 생성형 응답의 neural caching(분류가 아닌 자유 답)을 다룬 후속 연구.
