"""1단계 진입점 -- 주문 하나를 고정 모델에 묻고, 위조 게이트를 지나, 원장에서 그려 낸다.

    python3 -m agentic.run "물음"           # 그린 글을 찍는다. 끝값 0 = DONE, 1 = 그 밖
    python3 -m agentic.render <run_dir>      # 지난 실행을 원장에서 다시 그린다

아직 없는 것(2단계 이후): 도구 호출 · Sequencer · Gate01 평가 · 루프 탐지기 · MCP 클라이언트.
그래서 화면의 그 칸들은 'UNKNOWN / 평가 안 함 / 기록 없음' 으로 나온다 -- **그것이 맞는 답이다.**

모델에게 주는 머리말은 깃발 어휘를 **나열하지 않는다.** 금지 목록을 알려 주면 그 목록이 곧
흉내 낼 어휘가 된다(이 저장소 law/write 의 규율: 알려 주면 검사가 사양서가 된다).
"""
from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic import config as C                                         # noqa: E402
from agentic import forgery as F                                        # noqa: E402
from agentic.ledger import DiagnosticSink, Ledger, LoggingFailure, read_events  # noqa: E402
from agentic.model import Blocked, BudgetExhausted, FixedModel          # noqa: E402
from agentic.render import render                                       # noqa: E402

PREAMBLE = (
    "Answer the user's request directly.\n"
    "Do not report execution status, test or gate results, loop status, tool or protocol "
    "versions, or which model you are. The runtime records and reports those itself; "
    "anything you write about them is discarded.\n"
    "If you propose a follow-up task, put it on its own line starting with [Next].\n\n"
)
RETRY_NOTE = ("\n\nYour previous answer contained runtime status or version claims and was "
              "discarded. Answer again with only the content.\n")


def _head_sha() -> "str | None":
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                           text=True, timeout=10)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def runs_root(root=None) -> Path:
    import ledgerroot
    return Path(ledgerroot.뿌리(root, ROOT)) / "agentic" / "runs"


def run(prompt: str, cfg=None, root=None, keys=None, client_factory=None, run_id=None):
    """(종료 상태, run_dir, 그린 글). 로깅이 죽으면 원장에서 못 그리므로 그 사실만 그린다."""
    cfg = cfg or C.load()
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    run_dir = runs_root(root) / run_id
    try:
        L = Ledger(run_dir, run_id)
        sink = DiagnosticSink(L)
        L.emit("RUN_START", "code", {"config_sha256": cfg.sha256, "model": cfg.model,
                                     "head_sha": _head_sha(), "sandbox": cfg.sandbox})
        state = _drive(prompt, cfg, L, sink, keys, client_factory)
    except LoggingFailure as e:
        text = (f"상태: LOGGING_FAILURE ({e}) -- 원장을 쓰지 못해 이 실행은 검사할 수 없다.\n"
                f"원장 자리: {run_dir}\n답: (채택된 답 없음)")
        return "LOGGING_FAILURE", run_dir, text
    return state, run_dir, render(read_events(run_dir), run_dir)


def _drive(prompt, cfg, L, sink, keys, client_factory) -> str:
    M = FixedModel(cfg, L, sink, keys=keys, client_factory=client_factory)
    ask = PREAMBLE + prompt
    tries = 1 + cfg.budgets["forgery_retries"]
    try:
        for i in range(tries):
            res = M.call(ask)
            hits = F.scan(res.text)
            if hits:
                sink.write(f"forged_answer#{i + 1}", res.text)
                L.emit("MODEL_FLAG_FORGERY", "code", {"hits": hits[:20], "attempt": i + 1},
                       evidence=[res.event_id])
                ask = PREAMBLE + prompt + RETRY_NOTE
                continue
            nexts = F.next_proposals(res.text)
            for n in nexts:
                L.emit("NEXT_PROPOSED", "model", {"text": n[:300]}, evidence=[res.event_id])
            aid = L.emit("ANSWER_ADOPTED", "code", {"text": F.strip_next(res.text),
                                                    "identity": res.identity},
                         evidence=[res.event_id])
            L.terminal("DONE", "answer_adopted",
                       "모델 답 채택(도구 실행·게이트 평가 없음 -- 1단계)", [aid])
            return "DONE"
        L.terminal("NEEDS_REVIEW", "model_flag_forgery",
                   f"{tries}번 다 깃발·버전을 지어내 답을 채택하지 않았다")
        return "NEEDS_REVIEW"
    except Blocked as b:
        L.terminal("BLOCKED", b.reason, "모델 호출을 진행할 수 없다(다른 모델로 넘어가지 않는다)")
        return "BLOCKED"
    except BudgetExhausted as b:
        L.terminal("FAILED", b.reason, "예산을 다 썼다")
        return "FAILED"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="agentic 1단계: 고정 모델 + 위조 게이트 + 원장 렌더")
    ap.add_argument("prompt")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    try:
        cfg = C.load(a.config)
    except C.ConfigError as e:
        print(f"상태: BLOCKED (config:{e}) -- 설정이 정책 A 를 어긴다")
        return 1
    state, _, text = run(a.prompt, cfg)
    print(text)
    return 0 if state == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())
