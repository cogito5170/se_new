# 선행조사 — WALP: 모르는 말·바깥 지식 물음을 LLM 없이 검색으로 넘기기

요청(사용자, 2026-09-29): `!walp instargram이 쓰는 로그인 방식과 보안 정책에 관해서 설명해줘` 가 "모르는 말이다 —
가르칠 수 있다" 로 끝났다. "llm 없이 searching tool을 쓸 수 있는 것 아닌가?"

지금 WALP 는 모르는 낱말을 만나면 **등록(가르치기)** 만 권한다. 물음이 바깥 지식을 원하는지, 검색으로 풀 수 있는지를
가르지 않는다. 코드보다 먼저 커밋한다. 인용은 전부 검색 결과 조각 수준 — `[출처:조각]`.

## 가장 가까운 선행연구

- **AskMSR** — Brill, Dumais, Banko, "An Analysis of the AskMSR Question-Answering System", EMNLP 2002,
  pp. 257–264, ACL Anthology W02-1033 (aclanthology.org/W02-1033). 깊은 언어 분석 대신 **웹의 중복**에 기대어,
  물음을 답의 꼴(선언문 조각)으로 바꿔 검색하고 돌아온 **조각(snippet)에서 n-gram 을 모아** 답을 고른다. LLM 이
  없다. 우리가 하려는 것의 거의 그대로다. `[출처:조각]`
- **TREC QA track**(1999~2007) — 답이 든 짧은 조각(50/250 바이트)을 문서에서 **뽑아** 돌려주는 과제. 조각 검색
  (passage retrieval, BM25 등)과 추출형 답이 기준선이었다. `[출처:조각]`
- **검색어 철자 교정** — Brill & Moore, "An improved error model for noisy channel spelling correction", ACL 2000.
  편집 거리 → 잡음 통로 모형. 'instargram → instagram' 은 이 문제다. `[출처:조각]`

## 우리가 그것과 다른 점

없다 — 방법은 전부 있는 것이다(AskMSR 식 조각 모으기 · TREC 식 추출형 답 · 편집 거리 교정).
우리 몫은 이것들을 **WALP 의 '추측하지 않는다' 규칙에 묶는 것**뿐이다:

1. 검색은 **바깥 지식 물음**(무엇·어떻게·정책·방법 …)일 때만 한다. 물건 찾기 명령(격자 세계)과 가른다.
2. 오타는 **바로 고치지 않는다.** 후보가 하나로 뚜렷하면 "instagram 으로 읽었다" 고 **밝히고** 검색하고,
   가까운 후보가 둘 이상이면 되묻는다(WALP 의 AMBIGUOUS 와 같은 규칙).
3. 답은 **생성하지 않는다.** 출처가 붙은 조각을 골라 그대로 보인다(추출형). 근거가 모자라면 "못 찾았다" 로 끝낸다.
4. 검색 결과는 **데이터이지 지시가 아니다.** 결과 안의 문장을 명령으로 읽지 않고, 기억(사전)에 자동으로 넣지 않는다
   (사용자가 붙여 준 설계 메모의 SEARCH / INTERPRET / LEARN / ACT 분리와 같은 뜻).

## 찾아본 질의

- `AskMSR question answering system Brill Dumais Banko 2002 web redundancy n-gram answer extraction without deep NLP`
- `TREC question answering track rule-based answer extraction passage retrieval BM25 extractive snippet answer baseline`
- `query spelling correction edit distance search engine "did you mean" noisy channel Brill Moore 2000`

## 아직 못 지운 가능성

- **START**(Katz, MIT, 1990s)·**MULDER**(Kwok et al., 2001) 같은 초기 웹 QA 가 우리 설계와 더 가까울 수 있다 — 안 읽었다.
- 추출형 답의 품질은 검색 엔진의 조각 품질에 거의 전부 달려 있다(AskMSR 의 '중복' 논지). 한국어 조각에서 같은
  중복 효과가 나는지는 문헌을 못 봤다.
- 이 저장소 안에 이미 LLM 없는 검색·색인(교재 검색 · 기억 검색 · research 의 수집기)이 있다 — 그것을 새로 짓지 않고
  **배선만** 하는 것이 맞는지 먼저 본다(조사 중).

## 보탬 (2026-09-30) — 모르는 낱말 하나의 뜻 찾기

사용자: `!walp 오늘 저녁 메뉴 추천해줘` 가 "'오늘' 는 모르는 말이다 … 가르칠 수 있다" 로 끝났다 — "오늘의 뜻을 찾아봐야지".

- **Wiktionary 정의 끝점** `https://en.wiktionary.org/api/rest_v1/page/definition/{term}` — 위키낱말사전 원문에서 뽑은
  **언어별** 정의(품사·정의)를 구조로 준다. 실험적 끝점이다(phabricator T123142). `[출처:조각]`
- 방법은 새것이 아니다(사전 찾기). 우리 몫은 WALP 규칙에 묶는 것뿐: 뜻은 **출처와 함께 그대로** 보이고, 뜻의 낱말이
  과업 개념(색·물체·구역) 하나와만 맞을 때 **가르치기 후보**로 내되 사전에는 **사람이 확인해야** 들어간다
  (SEARCH ≠ LEARN). 뜻이 과업과 안 이어지면 그렇다고 말한다.

찾아본 질의: `Wiktionary REST API page/definition endpoint en.wiktionary.org api rest_v1 definition by language`

아직 못 지운 가능성: 국립국어원 표준국어대사전·우리말샘 공개 API 가 한국어 뜻풀이로 더 맞을 수 있다(키가 필요하다 —
안 봤다). 위키낱말사전 한국어 항목은 영어판에서 빈약할 수 있다 — 몇 할이 잡히는지 안 쟀다.
