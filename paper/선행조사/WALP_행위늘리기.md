# WALP 행위를 대화로 늘리기 — 선행조사 (2026-09-30, 코드보다 먼저)

사용자(2026-09-30): "12개면 충분해?" — 아니다. 12 행위(인사 · 찾기 · …)도 손으로 정한 목록이다. 손을 빼려면 **행위 목록 자체가
대화로 자라야** 한다: 선택지에 없는 뜻을 사람이 자연어로 말하면 WALP 가 새 행위를 만들고, 그 행위에 할 말도 사람에게 배운다.

## 가장 가까운 선행 (전부 검색 조각만 보았다 `[출처:조각]`)

| 선행 | 요지 | 우리와 |
|---|---|---|
| **새 의도 발견(NID) · 열린 의도 탐지** — Vedula 등 "Towards Open Intent Discovery for Conversational Text" (arXiv:1904.08524); GID(Mou 등 2022); CGID "Continual Generalized Intent Discovery" (Song 등, arXiv:2310.10184); "Uncertainty-Aware Continual Learning for Open-World Intent Discovery Under an Evolving Label Space" (arXiv:2609.17866) | 모르는 말을 가려내고, 라벨 없는 말들을 **군집**해 새 의도로 늘린다. 옛 의도는 재생 기억 · 증류로 지킨다 | 우리는 군집이 아니라 **사람이 말해 준 이름**으로 늘린다. 그들은 전부 사전학습 문장 표현 위에서 한다 |
| **가르칠 수 있는 대화 에이전트** — "Interactive Teaching for Conversational AI" (arXiv:2012.00958); Liu 등 "Dialogue Learning with Human Teaching and Feedback" (arXiv:1804.06512); 평생 학습 대화(Liu & Mazumder, AAAI 2021) 의 NL2NL 로 새 명령을 행동에 이어 붙이기 | 이해의 빈 곳을 **물어서 메우고**, 사람의 가르침을 흉내 낸다 · 모르는 표현을 대화 중에 행동에 붙인다 | 방법의 뼈대가 같다(묻기 → 가르침 → 붙이기) |
| **XCS 덮기(covering)** — Wilson 1995; 개관 "State of XCS Classifier System Research" | 맞는 규칙 집합에 없는 행동이 있으면 덮기가 그 행동의 규칙을 만든다 | **행동 수를 늘려도 집단을 버리지 않고** 새 행동만 덮기로 자란다 — V4(다시 기르지 않고 는다)를 행위 수준까지 넓힐 길 |

## 우리가 다른 점 — 정직하게

방법으로는 없다(묻기 → 가르침 → 새 부류 · 덮기). 다른 것은 조건뿐이다: 사전학습 표현이 없다 · 한 사람 · 새 행위의 **답도**
사람에게서 배운다(WALP 는 지어내지 않는다 — 가르쳐 준 말을 그대로 쓴다).

## 짓는다면(사용자에게 보이고 나서)

- 되물음 대답이 어느 선택지도 가리키지 않으면 → "처음 듣는 뜻이에요. 이런 말에는 뭐라고 답하면 될까요?" → 사람의 말을 새 행위의 답으로.
- 새 행위 = L0 XCS 의 행동 하나 더(덮기로 자란다, 집단 유지). 센서(성장망)는 다음 진화에서 새 행위를 배운다.
- 재는 법: 한 사람 대화를 흉내 낸 대본(새 뜻 k 개를 가르침)에서 가르친 뒤 같은 뜻의 **다른** 말을 알아듣는 비율 — 대본은 독립 에이전트가 쓰고 봉인.

## 찾아본 질의

- `open intent discovery new intent detection dialogue continual learning new intents from user conversation`
- `learning new dialogue acts or skills from user teaching interactive task learning conversational agent "teach" new command`
- `XCS classifier system adding new actions online growing action set`

## 아직 못 본 곳

- 위 논문들의 전문(망 차단 · 읽지 않음). 사전학습 없이 군집으로 새 의도를 찾은 연구는 따로 안 찾았다.
- 대화형 로봇(HRI)에서 사람이 새 명령어를 가르치는 문헌(예: 말로 새 기술 가르치기)을 안 찾았다.
