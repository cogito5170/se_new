"""Sequencer -- 정책 H(Automatic Next)를 코드로. 작업을 차례로 세우고, Gate01 이 승인한 것만 다음으로 넘긴다.

작업 하나마다 (H 의 열 걸음):

    1  작업 ID(run:Tn) · 멱등키(명세 + 레지스트리 해시)
    2  NEXT_RAISED
    3  명세·권한 검증          -> 어기면 TASK_REJECTED, 사슬 멈춤
       같은 멱등키가 이미 승인  -> DUPLICATE_SKIPPED (다시 안 돈다)
       같은 멱등키가 진행 중    -> 사슬 멈춤(죽은 실행이 남긴 것일 수 있다 -- 사람이 본다)
    4·5  Gate01 (안에서 필수 검사: 설정의 mandatory_checks, 기본 sandbox)
    6  GATE_DECISION + 승인 ID 를 원장에 쓴다
    7  다음 작업은 **앞 작업의 승인 ID 를 원장 파일에서 다시 읽어** 찾았을 때만 NEXT_DISPATCHED
    8·9  TOOL_START / TOOL_END (실행기 확인)
    10 사후조건(Gate01 의 술어)을 통과해야 TASK_COMPLETED

사슬이 멈추면 남은 작업은 하나하나 NEXT_NOT_DISPATCHED 로 적는다 -- 막힌 작업을 조용히 건너뛰지 않는다.

**지금은 사슬이 엄격하다:** 어느 작업이든 승인되지 않으면 그 뒤는 전부 안 보낸다. 의존이 없는 작업을
계속 보내는 것(설계 §2.2)은 아직 안 지었다.

    python3 -m agentic.sequencer --demo     # 저장소를 읽기만 하는 두 작업을 진짜 sandbox 검증과 함께
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

from agentic import config as C                                          # noqa: E402
from agentic import gate01 as G                                          # noqa: E402
from agentic.ledger import DiagnosticSink, Ledger, LoggingFailure, _append, read_events  # noqa: E402
from agentic.render import render                                        # noqa: E402
from agentic.run import _head_sha, runs_root                             # noqa: E402
from agentic.task import idempotency_key, validate                       # noqa: E402

_OUTCOME = {"RED_RED_STOP": "RED_RED_STOP", "FOLLOWUP_FAILED": "FAILED", "MANDATORY_FAILED": "BLOCKED"}


class IdemStore:
    """멱등키 원장. 덧쓰기만 한다. 같은 키의 마지막 줄이 지금 상태다."""

    def __init__(self, root: Path):
        self.path = Path(root) / "idempotency.jsonl"

    def latest(self, key: str) -> "dict | None":
        if not self.path.exists():
            return None
        last = None
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = json.loads(line)
                    if d.get("key") == key:
                        last = d
        except (OSError, json.JSONDecodeError) as e:
            raise LoggingFailure(f"{type(e).__name__}: idempotency.jsonl") from None
        return last

    def put(self, key, state, run_id, task_id, approval_id=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _append(self.path, json.dumps({"key": key, "state": state, "run_id": run_id, "task_id": task_id,
                                       "approval_id": approval_id, "ts": round(time.time(), 3)}) + "\n")


def _approval_on_disk(run_dir: Path, store: IdemStore, prev: tuple) -> bool:
    """앞 작업의 승인이 **파일에** 있는가. 메모리의 값을 믿지 않는다(H.6 → H.7)."""
    src, ref, aid = prev
    if src == "ledger":
        return any(e["type"] == "GATE_DECISION" and e["task_id"] == ref
                   and e["data"].get("decision") == "APPROVED" and e["data"].get("approval_id") == aid
                   for e in read_events(run_dir))
    rec = store.latest(ref)
    return bool(rec and rec.get("state") == "APPROVED" and rec.get("approval_id") == aid)


def run_chain(specs, reg, cfg=None, root=None, run_id=None, checks=None):
    """(종료 상태, run_dir, 그린 글)."""
    cfg = cfg or C.load()
    checks = checks if checks is not None else {"sandbox": G.sandbox_check}
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    base = runs_root(root)
    run_dir = base / run_id
    try:
        L = Ledger(run_dir, run_id)
        sink = DiagnosticSink(L)
        L.emit("RUN_START", "code", {"config_sha256": cfg.sha256, "model": cfg.model,
                                     "head_sha": _head_sha(), "sandbox": cfg.sandbox})
        reg_hash = reg.hash()
        L.emit("CHAIN_START", "code", {"tasks": len(specs), "registry_sha256": reg_hash,
                                       "mandatory_checks": list(cfg.mandatory_checks)})
        st, reason, summary = chain_in(specs, reg, cfg, checks, L, sink, base, run_id, run_dir, reg_hash)
        L.terminal(st, reason, summary)
        state_name = st
    except LoggingFailure as e:
        return "LOGGING_FAILURE", run_dir, (f"상태: LOGGING_FAILURE ({e}) -- 원장을 쓰지 못해 이 사슬은 "
                                            f"검사할 수 없다.\n원장 자리: {run_dir}")
    return state_name, run_dir, render(read_events(run_dir), run_dir)


def chain_in(specs, reg, cfg, checks, L, sink, runs_base, run_id, run_dir, reg_hash=None) -> tuple:
    """이미 열린 원장 안에서 사슬을 돈다. **종료 사건은 안 쓴다** -- (상태, 사유, 요약) 을 돌려주고
    부르는 쪽이 끝낸다(제어부는 그 사이에 도구 출력을 답으로 채택해야 한다)."""
    reg_hash = reg_hash or reg.hash()
    return _chain(specs, reg, reg_hash, cfg, checks, L, sink, IdemStore(runs_base), run_id, run_dir)


def _chain(specs, reg, reg_hash, cfg, checks, L, sink, store, run_id, run_dir) -> tuple:
    ex = G.Executor(reg, L, sink)
    state: dict = {}
    seen: dict = {}
    prev = None                     # ("ledger", task_id, approval_id) | ("store", key, approval_id)
    stop = None                     # (종료 상태, 사유)
    done = 0
    for i, spec in enumerate(specs):
        task_id = f"{run_id}:T{i + 1}"
        if stop is not None:
            L.emit("NEXT_NOT_DISPATCHED", "code", {"name": spec.name, "reason": f"upstream:{stop[1]}"},
                   task_id=task_id)
            continue
        if i >= cfg.budgets["tasks"]:
            stop = ("FAILED", "budget_tasks")
            L.emit("NEXT_NOT_DISPATCHED", "code", {"name": spec.name, "reason": "budget_tasks"},
                   task_id=task_id)
            continue
        key = idempotency_key(spec, reg_hash)
        L.emit("NEXT_RAISED", "code", {"name": spec.name, "goal": spec.goal, "key": key}, task_id=task_id)

        why = validate(spec, reg, cfg.allowed_kinds)
        if spec.name in seen and seen[spec.name] != spec.canonical():
            why.append("duplicate_name_with_different_spec")
        if why:
            L.emit("TASK_REJECTED", "code", {"reasons": why}, task_id=task_id)
            stop = ("BLOCKED", f"spec_invalid:{why[0]}")
            continue
        seen[spec.name] = spec.canonical()
        L.emit("TASK_VALIDATED", "code", {"name": spec.name}, task_id=task_id)

        prior = store.latest(key)
        if prior and prior.get("state") == "APPROVED":
            L.emit("DUPLICATE_SKIPPED", "code", {"name": spec.name, "prior_run": prior["run_id"],
                                                 "prior_task": prior["task_id"],
                                                 "approval_id": prior["approval_id"]}, task_id=task_id)
            prev = ("store", key, prior["approval_id"])
            done += 1
            continue
        if prior and prior.get("state") == "IN_FLIGHT":
            L.emit("TASK_REJECTED", "code", {"reasons": ["duplicate_in_flight"],
                                             "prior_run": prior["run_id"]}, task_id=task_id)
            stop = ("BLOCKED", "duplicate_in_flight")
            continue
        if reg.hash() != reg_hash:
            L.emit("TASK_REJECTED", "code", {"reasons": ["registry_changed"]}, task_id=task_id)
            stop = ("BLOCKED", "registry_changed")
            continue
        if prev is not None and not _approval_on_disk(run_dir, store, prev):
            L.emit("NEXT_NOT_DISPATCHED", "code", {"name": spec.name, "reason": "predecessor_approval_missing"},
                   task_id=task_id)
            stop = ("BLOCKED", "predecessor_approval_missing")
            continue

        store.put(key, "IN_FLIGHT", run_id, task_id)
        L.emit("NEXT_DISPATCHED", "code", {"name": spec.name,
                                           "predecessor_approval": prev[2] if prev else "root"},
               task_id=task_id)
        d = G.evaluate(spec, task_id, key, ex, state, cfg, checks, L, sink)
        store.put(key, d.decision, run_id, task_id, d.approval_id)
        if d.decision == "APPROVED":
            L.emit("TASK_COMPLETED", "code", {"name": spec.name, "path": d.path,
                                              "approval_id": d.approval_id}, [d.event_id], task_id)
            prev = ("ledger", task_id, d.approval_id)
            done += 1
        else:
            stop = (_OUTCOME[d.decision], d.reason)

    if stop is None:
        return "DONE", "chain_approved", f"작업 {done}/{len(specs)} 승인"
    return stop[0], stop[1], f"작업 {done}/{len(specs)} 승인 뒤 멈춤"


# --- 데모: 저장소를 읽기만 한다. 모델 호출 없음. sandbox 검증은 진짜로 돈다 ---------------------

def _demo():
    from agentic.task import Action, Registry, TaskSpec
    import hashlib

    def config_hash(inputs, state):
        return {"sha256": hashlib.sha256((ROOT / inputs["path"]).read_bytes()).hexdigest()}

    def count_lines(inputs, state):
        return {"lines": len((ROOT / inputs["path"]).read_text(encoding="utf-8").splitlines())}

    def hash_matches_loaded(state, spec):
        r = state["results"]
        got = next(v["primary"]["sha256"] for v in r.values() if "primary" in v and "sha256" in v["primary"])
        return got == C.load().sha256

    def has_lines(state, spec):
        r = state["results"]
        return any(v.get("primary", {}).get("lines", 0) > 0 for v in r.values())

    reg = Registry({"config_hash": Action("compute", config_hash), "count_lines": Action("read", count_lines)},
                   {"hash_matches_loaded": hash_matches_loaded, "has_lines": has_lines})
    specs = [
        TaskSpec("config_hash", "설정 파일 해시가 로더가 본 해시와 같은가", "config_hash", "hash_matches_loaded",
                 inputs={"path": "agentic/config.json"},
                 verify_argv=(sys.executable, "-c", "import agentic.config as c; c.load()")),
        TaskSpec("design_lines", "설계 문서가 비어 있지 않은가", "count_lines", "has_lines",
                 inputs={"path": "agentic/설계.md"},
                 verify_argv=(sys.executable, "tests/test_agentic_phase1.py")),
    ]
    return specs, reg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="agentic 2단계: Sequencer + Gate01")
    ap.add_argument("--demo", action="store_true", help="읽기만 하는 두 작업을 진짜 sandbox 검증과 함께")
    a = ap.parse_args(argv)
    if not a.demo:
        ap.print_help()
        return 2
    specs, reg = _demo()
    st, _, text = run_chain(specs, reg)
    print(text)
    return 0 if st == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())
