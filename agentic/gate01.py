"""Gate01 -- 정책 G 를 실행 가능한 함수로.

    A_TO_B           = primary 가 실행됐고(실행기 확인) AND post(state) 가 정확히 True
    NOT_A_TO_B_PRIME = alt 가 정의돼 있고 AND 실행됐고 AND post_alt(state) 가 정확히 True
    NOT_B_PRIME 후속 = followup 실행 AND post_followup(state) 가 정확히 True

    A_TO_B TRUE              -> 필수 검사 전부(설정의 mandatory_checks) -> APPROVED(primary)
    A_TO_B FALSE/UNKNOWN     -> NOT_A_TO_B_PRIME
        FALSE/UNKNOWN        -> RED_RED_STOP
        TRUE -> 후속 -> 성공 + 필수 검사 전부 -> APPROVED(alternative)
                     -> 실패                  -> FOLLOWUP_FAILED

판정은 세 값(TRUE · FALSE · UNKNOWN)이고 **UNKNOWN 은 FALSE 로 간다.** 건너뛴 단계는 성공이 아니다:
대체가 정의돼 있지 않으면 NOT_A_TO_B_PRIME 은 '평가했고 FALSE' 가 아니라 '정의 안 됨' 으로 적히고
FALSE 로 간다.

모델은 여기 안 들어온다. 모델이 "성공했다" 고 써도 이 함수는 그것을 읽지 않는다(G 마지막 줄).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

TRUE, FALSE, UNKNOWN = "TRUE", "FALSE", "UNKNOWN"


@dataclass
class Decision:
    decision: str        # APPROVED | RED_RED_STOP | FOLLOWUP_FAILED | MANDATORY_FAILED
    reason: str
    path: str            # primary | alternative | -
    approval_id: "str | None"
    event_id: str


def tri(v) -> str:
    if v is True:
        return TRUE
    if v is False:
        return FALSE
    return UNKNOWN


class Executor:
    """행동을 실제로 돌리고 TOOL_START / TOOL_END 를 남긴다. TOOL_END 가 없으면 실행은 확인되지 않은 것이다."""

    def __init__(self, reg, L, sink):
        self.reg, self.L, self.sink = reg, L, sink

    def act(self, task_id: str, slot: str, name: str, inputs: dict, state: dict) -> "tuple[bool, str]":
        a = self.reg.actions[name]
        sid = self.L.emit("TOOL_START", "executor", {"slot": slot, "action": name, "kind": a.kind},
                          task_id=task_id)
        try:
            out = a.fn(dict(inputs), state)
        except Exception as e:                           # noqa: BLE001 -- 실패도 사건이다
            self.sink.write(f"action_error:{task_id}:{name}", f"{type(e).__name__}: {e}")
            eid = self.L.emit("TOOL_END", "executor", {"slot": slot, "action": name, "ok": False,
                                                       "error": type(e).__name__}, [sid], task_id)
            return False, eid
        if not isinstance(out, dict):
            eid = self.L.emit("TOOL_END", "executor", {"slot": slot, "action": name, "ok": False,
                                                       "error": "result_not_dict"}, [sid], task_id)
            return False, eid
        state.setdefault("results", {}).setdefault(task_id, {})[slot] = out
        eid = self.L.emit("TOOL_END", "executor", {"slot": slot, "action": name, "ok": True,
                                                   "keys": sorted(out)[:20]}, [sid], task_id)
        return True, eid

    def pred(self, task_id: str, step: str, name: str, spec, state: dict) -> "tuple[str, str]":
        try:
            v = tri(self.reg.predicates[name](state, spec))
            note = ""
        except Exception as e:                           # noqa: BLE001
            v, note = UNKNOWN, f"predicate_raised:{type(e).__name__}"
        eid = self.L.emit("GATE_EVAL", "code", {"step": step, "predicate": name, "result": v,
                                                "note": note}, task_id=task_id)
        return v, eid


def sandbox_check(spec, cfg, sink, runner=None) -> "tuple[str, str]":
    """정책 C: 작업이 들고 온 검증 명령을 sandbox(HEAD 워크트리 · 고삐 · 비밀 없음)에서 돌린다.
    명령이 없으면 UNKNOWN(필수 시험 없음 -- C.5 가 막는다). 판을 못 깔았으면 UNKNOWN. 끝값 0 만 TRUE."""
    if not spec.verify_argv:
        return UNKNOWN, "verify_argv_missing"
    if runner is None:
        from sandbox.run import 실행 as runner
    r = runner(list(spec.verify_argv), 초=cfg.budgets["sandbox_seconds"])
    sink.write(f"sandbox:{spec.name}", f"exit={r.get('끝값')}\n{r.get('stdout', '')}\n{r.get('stderr', '')}")
    if not r.get("돌았나"):
        return UNKNOWN, f"sandbox_not_run:{r.get('메모', '')[:60]}"
    return (TRUE, "exit=0") if r.get("끝값") == 0 else (FALSE, f"exit={r.get('끝값')}")


def _mandatory(spec, task_id, cfg, checks, L, sink) -> "tuple[bool, str, list]":
    evid = []
    for name in cfg.mandatory_checks:
        fn = checks.get(name)
        if fn is None:
            v, note = UNKNOWN, "check_not_implemented"
        else:
            try:
                v, note = fn(spec, cfg, sink)
            except Exception as e:                       # noqa: BLE001
                v, note = UNKNOWN, f"check_raised:{type(e).__name__}"
        evid.append(L.emit("CHECK_EVAL", "code", {"check": name, "result": v, "note": note},
                           task_id=task_id))
        if v != TRUE:
            return False, f"mandatory:{name}:{v}:{note}", evid
    return True, "", evid


def _approval(key: str, evid: list) -> str:
    return hashlib.sha256((key + "|" + ",".join(evid)).encode()).hexdigest()[:16]


def evaluate(spec, task_id: str, key: str, ex: Executor, state: dict, cfg, checks, L, sink) -> Decision:
    def decide(decision, reason, path, evid, approve=False):
        aid = _approval(key, evid) if approve else None
        eid = L.emit("GATE_DECISION", "code", {"decision": decision, "reason": reason, "path": path,
                                               "approval_id": aid}, evid, task_id)
        return Decision(decision, reason, path, aid, eid)

    evid = []
    ran, e = ex.act(task_id, "primary", spec.primary, spec.inputs, state)
    evid.append(e)
    if ran:
        a_to_b, e = ex.pred(task_id, "A_TO_B", spec.post, spec, state)
    else:
        a_to_b = FALSE
        e = L.emit("GATE_EVAL", "code", {"step": "A_TO_B", "predicate": spec.post, "result": FALSE,
                                         "note": "primary_not_executed"}, task_id=task_id)
    evid.append(e)

    if a_to_b == TRUE:
        ok, why, ce = _mandatory(spec, task_id, cfg, checks, L, sink)
        evid += ce
        if not ok:
            return decide("MANDATORY_FAILED", why, "primary", evid)
        return decide("APPROVED", "A_TO_B", "primary", evid, approve=True)

    # 주 경로 실패를 적고 대체로
    if spec.alt is None:
        e = L.emit("GATE_EVAL", "code", {"step": "NOT_A_TO_B_PRIME", "predicate": None, "result": FALSE,
                                         "note": "alternative_undefined"}, task_id=task_id)
        evid.append(e)
        return decide("RED_RED_STOP", f"primary:{a_to_b}+alternative_undefined", "-", evid)
    ran, e = ex.act(task_id, "alt", spec.alt, spec.inputs, state)
    evid.append(e)
    if ran:
        prime, e = ex.pred(task_id, "NOT_A_TO_B_PRIME", spec.post_alt, spec, state)
    else:
        prime = FALSE
        e = L.emit("GATE_EVAL", "code", {"step": "NOT_A_TO_B_PRIME", "predicate": spec.post_alt,
                                         "result": FALSE, "note": "alt_not_executed"}, task_id=task_id)
    evid.append(e)
    if prime != TRUE:
        return decide("RED_RED_STOP", f"primary:{a_to_b}+alternative:{prime}", "-", evid)

    ran, e = ex.act(task_id, "followup", spec.followup, spec.inputs, state)
    evid.append(e)
    if ran:
        fu, e = ex.pred(task_id, "NOT_B_PRIME", spec.post_followup, spec, state)
    else:
        fu = FALSE
        e = L.emit("GATE_EVAL", "code", {"step": "NOT_B_PRIME", "predicate": spec.post_followup,
                                         "result": FALSE, "note": "followup_not_executed"}, task_id=task_id)
    evid.append(e)
    if fu != TRUE:
        return decide("FOLLOWUP_FAILED", f"followup:{fu}", "alternative", evid)
    ok, why, ce = _mandatory(spec, task_id, cfg, checks, L, sink)
    evid += ce
    if not ok:
        return decide("MANDATORY_FAILED", why, "alternative", evid)
    return decide("APPROVED", "NOT_A_TO_B_PRIME+NOT_B_PRIME", "alternative", evid, approve=True)
