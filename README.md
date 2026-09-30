# SE — 자기수정 에이전트 저장소

Discord 로 지시를 받아 스스로 코드를 고치고, 고친 결과를 **강제 게이트**로 검사한 뒤에만 커밋하는 에이전트.
모든 오케스트레이션이 한 원칙 위에 있다 — **생성자와 심판을 분리하고, 심판은 LLM 이 아니다.**

## 한눈에

| 부분 | 무엇 | 자세히 |
|---|---|---|
| Discord 에이전트 | Oracle VM 에서 상시 구동. admin 채널(화이트리스트)과 공개 채널을 Gemini + LangGraph 가 처리 | 아래 §1 |
| 게이트 | 커밋 직전 `gatekeeper.py` + `gates/` 가 규칙을 실행 경로에서 강제 | 아래 §2 |
| WALP | LLM·사전학습 가중치·GPU 없이 대화로 규칙과 행동을 기르는 작은 로봇 두뇌 | [`walp/README.md`](walp/README.md) |
| 소설 | 씨앗 → 세계 → 조립 → 집필 → 기계 관문. DRIFT(자유 연속 집필, `/drift`) · MATHDRIFT(수식 파생, `/mathdrift`) | [`novel/README.md`](novel/README.md) · [`novel/DRIFT.md`](novel/DRIFT.md) · [`mathdrift/README.md`](mathdrift/README.md) |
| 법 | 인용한 조문이 실재하는가를 사실로 판정하는 관문(생성기는 아직 없다) | [`law/README.md`](law/README.md) |
| 오케스트레이터 | 계획 → 컴포넌트 + 검증 코드 → 실패하면 계획 수리 | [`orchestrator/README.md`](orchestrator/README.md) |
| 행렬곱 자가개선 | 3×3 행렬곱 스킴을 CP-ALS 로 탐색, 심판은 정확 검산 | `mathmetics/matrix_exponent/` |
| 그 밖 | 자기소개서 관문(`jaso/`) · 적분 문제 생성(`mathgen/`) · 압축 코덱(`compression/`) · 삼진 NPU(`npu/`) | 각 폴더의 README |

## 1. Discord 에이전트

| 파일 | 역할 |
|---|---|
| `discord_bot_server.py` | 이벤트 라우팅 · admin 에이전트 · `git_sync`(게이트 → 커밋 → push) |
| `main_public.py` · `bot_tools.py` | 공개 채널 에이전트와 공유 도구, (키 × 모델) 폴백 풀 |
| `orchestrator_tool.py` | admin 채널에서 오케스트레이터 런을 백그라운드로 띄우고 · 보고 · 재개 · 중지 |
| `agent_context.py` | 요청 단위 호출자 맥락 · 게스트 차단 |
| `agent_memory.py` | 공개 채널 장기 기억 — **이 기계에만 쌓고 git 에 남기지 않는다** |
| `quota_tracker.py` · `log_streamer.py` | 호출 한도 · 로그 스트리밍 |

## 2. 게이트 — 규칙을 실행 경로에 둔다

- `gatekeeper.py` + `gates/` — 커밋 직전에 게이트를 전부 돌리고 하나라도 걸리면 커밋하지 않는다.
  산문 규칙은 읽히지 않으면 아무것도 막지 못한다.
- `self_challenge.py` — 진단을 검사 코드로 써서 **사고 커밋에서 실패(RED) · 지금 통과(GREEN)** 를 둘 다 보여야 게이트로 승격한다.
- `tests/test_gates_on_incidents.py` — 실제 사고 커밋에서 게이트가 걸리는지 재증명한다. **전체 이력이 필요하다** —
  이력이 없는 새 저장소에서는 CI 의 이 단계가 옳게 빨개진다(사고 커밋을 되살려야 한다).
- 게이트는 두 곳에서 강제된다: VM 의 `git_sync()` 와 `.github/workflows/gates.yml`.

```bash
python3 gatekeeper.py            # 게이트 전체 (통과 0 / 위반 1)
python3 gatekeeper.py --list     # 게이트와 그 사고 이력
bash scripts/precheck.sh         # 밀기 전 검사 — HEAD 를 임시 워크트리로 꺼내 돌린다
```

## 3. 무엇을 git 에 남기지 않는가

사람들의 **대화 · 요청 · 검색어 · 올린 파일 · 공개 채널 산출물**은 이 기계에만 두고 커밋하지 않는다(`.gitignore`).
저장소가 공개되면 남의 말과 검색 기록이 인터넷에 그대로 남기 때문이다.

| git 에 없다(기계에만) | git 에 있다 |
|---|---|
| `public_agent_memory/` 기억 노트 · `inbox/` 올린 파일 · `Public_agent/*.md` · 검색·요청 원장(`dig` · `repair` · `improve` · `research`) · `원장.json` · `.env` | 판정 원장(`eval` · `router` · `graph` · `falsegreen` · `codify` · `secaudit`) — 사람의 말이 없고, **G020** 이 지키는 채점 기록이다 |

- **저장소는 비공개로 둔다.** 공개가 꼭 필요하면 위 목록 밖의 것도 다시 훑는다(남의 논문 PDF · 수집한 웹페이지 등).
- `.env` 는 절대 커밋하지 않는다 — G004 가 자격증명 커밋과 로그 출력을 막는다.

## 배포 · 설정

- `main` 에 push 하면 `.github/workflows/deploy-oracle.yml` 이 Oracle VM 에 SSH 로 들어가 서비스를 다시 띄운다
  (`deploy/*.service`: `se-discord-bot` · `se-log-streamer` · `se-matrix-search`). VM 비밀값이 없으면 이 단계는 실패로 끝나고 서버에 닿지 않는다.
- `.env.example` 을 `.env` 로 복사해 채운다. 의존성은 `requirements.txt`.
- 작업 규칙(백그라운드 실행 · 머지 순서 · 측정 규율 등)은 [`CLAUDE.md`](CLAUDE.md).
