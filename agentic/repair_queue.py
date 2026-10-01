"""수리 요청 대기열 -- 격리된 도구를 `repair/` 로 고치는 **사람이 부르는** 길.

    python3 -m agentic.repair_queue --list                 # 열린 수리 요청(재현 명령 · 모델 없는 진단)
    python3 -m agentic.repair_queue --fix <id>             # 무엇을 할지만 보인다(아무것도 안 바꾼다)
    python3 -m agentic.repair_queue --fix <id> --apply     # repair.고치기 를 돌린다 -- 작업 트리를 바꿀 수 있다

왜 자동으로 안 고치나:
  · `repair.고치기` 는 패치를 **진짜 작업 트리에** 적용하고 재현이 실패하면 되돌린다 -- 쓰기다. 이 설정의 권한
    (`allowed_kinds`)은 읽기·계산이라 자동 경로에 두지 않는다. `--apply` 가 사람의 명시적 허락이다
  · `repair` 의 기본 제안기는 `router` 의 '수리기'(llm_pool -- 모델을 바꿔 가며 부른다)다. 정책 A.2(폴백 없음)에
    어긋나므로 **제안기를 이 설정의 고정 모델로 바꿔 끼운다**(FixedModel: 한 모델 · 키만 돌림 · 정체 대조)

고친 뒤: 도구의 원문 해시가 바뀌므로 제어부·사고부는 그 도구를 `quarantined:source_changed` 로 계속 막는다.
**커밋하고 `python3 -m agentic.tools --register` 로 다시 등록해야** 쓸 수 있다(sandbox 는 커밋된 나무를 본다).
재등록하면 새 해시로 셈하므로 회로 차단기도 새로 시작한다.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic import breaker as BR                                        # noqa: E402
from agentic import config as C                                          # noqa: E402
from agentic.ledger import DiagnosticSink, Ledger                        # noqa: E402
from agentic.model import FixedModel                                     # noqa: E402
from agentic.run import _head_sha, runs_root                             # noqa: E402


def fixed_model_proposer(cfg, L, sink, keys=None, client_factory=None):
    """repair 의 제안기 자리에 끼울 함수: (prompt) -> str. 이 설정의 모델 하나로만 묻는다."""
    M = FixedModel(cfg, L, sink, keys=keys, client_factory=client_factory)

    def propose(prompt: str) -> str:
        return M.call(prompt).text
    return propose


def fix(ticket_id: int, apply: bool, cfg=None, root=None, keys=None, client_factory=None, fixer=None) -> "tuple[int, str]":
    """(끝값, 보고). fixer 는 검사 주입: (명령, 증상, 제안기) -> repair 결과 dict."""
    cfg = cfg or C.load()
    base = runs_root(root)
    t = next((x for x in BR.tickets(base) if x.get("id") == ticket_id), None)
    if t is None:
        return 1, f"수리 요청 #{ticket_id} 이 없다"
    plan = (f"수리 요청 #{t['id']} · 도구 {t['tool']} · 상태 {t['status']}\n"
            f"증상: {t['error']}\n재현: {t['reproduce']}\n"
            f"진단(모델 없음): " + ("; ".join(f"{h['what']} -> {h['fix']}" for h in t["diagnosis"]["hypotheses"])
                                   or t["diagnosis"].get("said") or "가설 없음") + "\n"
            f"제안기: {cfg.model} (폴백 없음)")
    if not apply:
        return 0, plan + "\n\n(--apply 를 주지 않았다 -- 아무것도 바꾸지 않았다. --apply 는 작업 트리를 바꿀 수 있다)"
    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-repair{t['id']}-" + secrets.token_hex(2)
    L = Ledger(base / run_id, run_id)
    sink = DiagnosticSink(L)
    L.emit("RUN_START", "code", {"config_sha256": cfg.sha256, "model": cfg.model, "head_sha": _head_sha(),
                                 "sandbox": cfg.sandbox})
    propose = fixed_model_proposer(cfg, L, sink, keys, client_factory)
    if fixer is None:
        from repair import run as R

        def fixer(cmd, symptom, proposer):
            old = R.제안기
            R.제안기 = proposer
            try:
                return R.고치기(cmd, symptom)
            finally:
                R.제안기 = old
    try:
        res = fixer(t["reproduce"], t["error"], propose)
    except Exception as e:                               # noqa: BLE001 -- 결과로 적는다
        res = {"해결": False, "남은것": f"{type(e).__name__}: {str(e)[:160]}"}
    solved = bool(res.get("해결"))
    BR.update_ticket(base, t, status="fixed_pending_register" if solved else "unfixed",
                     result={"해결": solved, "바퀴": res.get("바퀴"), "남은것": str(res.get("남은것", ""))[:300]})
    L.terminal("DONE" if solved else "NEEDS_REVIEW", "repaired" if solved else "repair_unsolved",
               f"수리 요청 #{t['id']} {t['tool']}")
    tail = ("\n\n고쳐졌다(재현 명령 끝값 0). 그 도구는 아직 격리돼 있다 -- 바뀐 것을 커밋하고 "
            "`python3 -m agentic.tools --register` 로 다시 등록해야 쓰인다." if solved else
            f"\n\n못 고쳤다: {res.get('남은것', '')}")
    return (0 if solved else 1), plan + tail + f"\n원장: {L.dir}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="agentic 수리 요청 대기열")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--fix", type=int, metavar="ID")
    ap.add_argument("--apply", action="store_true", help="repair.고치기 를 실제로 돌린다(작업 트리를 바꿀 수 있다)")
    a = ap.parse_args(argv)
    if a.list:
        ts = BR.tickets(runs_root())
        if not ts:
            print("수리 요청 없음")
        for t in ts:
            print(json.dumps({k: t[k] for k in ("id", "tool", "status", "error", "reproduce")}, ensure_ascii=False))
        return 0
    code, text = fix(a.fix, a.apply)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
