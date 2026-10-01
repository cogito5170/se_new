"""1단계 진입점 -- 주문 하나를 고정 모델에 묻고, 위조 게이트를 지나, 원장에서 그려 낸다.

    python3 -m agentic.run "물음"           # 그린 글을 찍는다. 끝값 0 = DONE, 1 = 그 밖
    python3 -m agentic.render <run_dir>      # 지난 실행을 원장에서 다시 그린다

맨 앞에 WALP 앞단(`agentic/front.py`)이 있다: 잡담이면 모델을 안 부르고 WALP 가 답한다. `//` 로 시작하면 건너뛴다.
그다음 제어부(`agentic/controller.py`): 등록된 도구로 끝낼 수 있으면 모델 없이 끝낸다.
못 하면 사고부(`agentic/thinker.py`): Gemini 가 등록된 도구를 부르며 ReAct 로 푼다(루프 탐지기 · 예산).

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
from agentic import front as W                                          # noqa: E402
from agentic.ledger import DiagnosticSink, Ledger, LoggingFailure, read_events  # noqa: E402
from agentic.model import FixedModel                                    # noqa: E402
from agentic.render import render                                       # noqa: E402

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


def run(prompt: str, cfg=None, root=None, keys=None, client_factory=None, run_id=None, small_talk=None,
        controller_opts=None):
    """(종료 상태, run_dir, 그린 글). 로깅이 죽으면 원장에서 못 그리므로 그 사실만 그린다."""
    cfg = cfg or C.load()
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    run_dir = runs_root(root) / run_id
    try:
        L = Ledger(run_dir, run_id)
        sink = DiagnosticSink(L)
        L.emit("RUN_START", "code", {"config_sha256": cfg.sha256, "model": cfg.model,
                                     "head_sha": _head_sha(), "sandbox": cfg.sandbox})
        fr = W.judge(prompt, cfg, small_talk)
        fid = L.emit("WALP_FRONT", "code", {"route": fr.route, **fr.data})
        if fr.route == "small":
            # 잡담 -- 모델 호출 0. 답은 WALP 의 고정 문장이다(모델 글이 아니므로 위조 검사 대상이 아니다)
            aid = L.emit("ANSWER_ADOPTED", "code", {"text": fr.reply, "identity": "walp_front"}, [fid])
            L.terminal("DONE", "walp_front_smalltalk", f"WALP 앞단이 잡담({fr.act})으로 답했다 · 모델 호출 0", [aid])
            state = "DONE"
        else:
            if fr.route == "bypass":
                prompt = W.strip_bypass(prompt)
            from agentic import controller as K          # 늦게: controller -> sequencer -> run 순환을 피한다
            ctl = K.try_tools(prompt, cfg, L, sink, runs_root(root), run_id, run_dir, **(controller_opts or {}))
            if ctl is None:
                from agentic import thinker as TH
                from agentic import tools as TL
                o = dict(controller_opts or {})
                M = FixedModel(cfg, L, sink, keys=keys, client_factory=client_factory)
                state = TH.think(prompt, cfg, L, sink, M, runs_root(root), run_id, run_dir,
                                 o.get("registry") if o.get("registry") is not None else TL.load_registry(),
                                 o.get("executor"), o.get("checks"), o.get("src_sha"))
            else:
                st, reason, summary, tool, out = ctl
                if st == "DONE":
                    # 도구 출력은 신뢰하지 않는 데이터다(D.7) -- 답 칸에만, 그렇게 표시해서
                    aid = L.emit("ANSWER_ADOPTED", "code", {"text": out, "identity": f"tool:{tool}",
                                                            "untrusted": True})
                    L.terminal("DONE", "controller_tool", f"제어부가 등록된 도구 {tool} 로 끝냈다 · 모델 호출 0",
                               [aid])
                else:
                    L.terminal(st, reason, summary)
                state = st
    except LoggingFailure as e:
        text = (f"상태: LOGGING_FAILURE ({e}) -- 원장을 쓰지 못해 이 실행은 검사할 수 없다.\n"
                f"원장 자리: {run_dir}\n답: (채택된 답 없음)")
        return "LOGGING_FAILURE", run_dir, text
    return state, run_dir, render(read_events(run_dir), run_dir)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="agentic: 앞단 · 제어부 · 사고부 · 원장 렌더")
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
