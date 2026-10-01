"""회로 차단기 · 수리 요청 -- 설계 §3.3 의 resilience.

도구가 **도구 탓으로**(인프라가 아니라) 이어서 실패하면 그 도구를 격리하고, 수리 요청을 남긴다.

    <원장 뿌리>/agentic/runs/breaker.jsonl        {tool, source_sha, 꼴: fail|ok|trip, error, run_id, ts}
    <원장 뿌리>/agentic/runs/repair_queue.jsonl   {id, tool, source_sha, args, error, reproduce, diagnosis, status}

  · 셈은 (도구, **원문 해시**) 마다다. 도구를 고쳐 재등록하면 해시가 바뀌므로 새 셈에서 시작한다 -- '풀기' 를 따로 두지 않는다
  · 성공 한 번이면 이은 실패 셈이 0 으로 돌아간다
  · 인프라 실패(판을 못 깔았다 · 시간 초과 · 서버 연결)는 세지 않는다(`tools.broken_reason`)
  · 문턱(`config.repair.trip_after`)에 닿으면 trip -> 그 뒤로 precheck 가 `quarantined:breaker_open` 으로 막는다

수리 요청에는 **모델 없는 진단**(`repair` 의 결정적 진단 = `diagnose.진단`)과 재현 명령을 붙인다. 고치는 일 자체는
쓰기라서 여기서 하지 않는다 -- `python3 -m agentic.repair_queue --fix <id> --apply` 를 사람이 부를 때만.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def _path(runs_base: Path, name: str) -> Path:
    return Path(runs_base) / name


def _lines(p: Path) -> list:
    if not p.exists():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            continue
    return out


def _append(p: Path, obj: dict) -> None:
    from agentic.ledger import _append as A
    p.parent.mkdir(parents=True, exist_ok=True)
    A(p, json.dumps(obj, ensure_ascii=False) + "\n")


def state(runs_base: Path, tool: str, source_sha: str) -> dict:
    """{"open": bool, "fails": 이은 실패 수}."""
    fails, opened = 0, False
    for r in _lines(_path(runs_base, "breaker.jsonl")):
        if r.get("tool") != tool or r.get("source_sha") != source_sha:
            continue
        if r["꼴"] == "fail":
            fails += 1
        elif r["꼴"] == "ok":
            fails = 0
        elif r["꼴"] == "trip":
            opened = True
    return {"open": opened, "fails": fails}


def note(runs_base: Path, tool: str, source_sha: str, broken: "str | None", run_id: str, trip_after: int) -> bool:
    """실패·성공을 적고, 이번에 문턱에 닿았으면 trip 을 적고 True."""
    p = _path(runs_base, "breaker.jsonl")
    now = round(time.time(), 3)
    if broken is None:
        _append(p, {"tool": tool, "source_sha": source_sha, "꼴": "ok", "run_id": run_id, "ts": now})
        return False
    _append(p, {"tool": tool, "source_sha": source_sha, "꼴": "fail", "error": broken, "run_id": run_id, "ts": now})
    st = state(runs_base, tool, source_sha)
    if not st["open"] and st["fails"] >= trip_after:
        _append(p, {"tool": tool, "source_sha": source_sha, "꼴": "trip", "run_id": run_id, "ts": now})
        return True
    return False


def diagnose(error: str) -> dict:
    """모델 없는 진단. 못 돌리면 그 사실을 돌려준다(막지 않는다)."""
    try:
        from repair import run as R
        d = R._진단기본(error)
        return {"hypotheses": [{"what": h.get("무엇"), "fix": h.get("고칠거리")} for h in d.get("가설", [])][:5],
                "said": d.get("말", "")}
    except Exception as e:                               # noqa: BLE001
        return {"hypotheses": [], "said": f"진단을 못 돌렸다: {type(e).__name__}"}


def request_repair(runs_base: Path, tool: str, source_sha: str, args: dict, error: str, run_id: str) -> dict:
    p = _path(runs_base, "repair_queue.jsonl")
    n = 1 + max([t.get("id", 0) for t in _lines(p)] or [0])
    reproduce = f"python3 -m agentic.tools --exec {tool} '{json.dumps(args, ensure_ascii=False)}'"
    t = {"id": n, "tool": tool, "source_sha": source_sha, "args": args, "error": error, "reproduce": reproduce,
         "diagnosis": diagnose(error), "status": "open", "run_id": run_id, "ts": round(time.time(), 3)}
    _append(p, t)
    return t


def tickets(runs_base: Path) -> list:
    """id 별 마지막 줄 -- 상태가 바뀌면 같은 id 로 새 줄이 붙는다(덧쓰기만)."""
    last = {}
    for t in _lines(_path(runs_base, "repair_queue.jsonl")):
        last[t.get("id")] = t
    return [last[k] for k in sorted(last)]


def update_ticket(runs_base: Path, ticket: dict, **changes) -> dict:
    t = {**ticket, **changes, "ts": round(time.time(), 3)}
    _append(_path(runs_base, "repair_queue.jsonl"), t)
    return t
