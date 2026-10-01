"""제어부 -- 등록된 도구로 **바로**(greedy) 끝낼 수 있는 주문은 모델 없이 끝낸다.

    주문 ──> walp/se_router.route (LLM 없음: 낱말 사전 · 인자 뽑기 · 확실하지 않으면 ASK)
              │ TOOL 이 아님 · 등록 안 됨 · 인자 꼴이 선언과 다름 · 원문 해시가 바뀜
              │      -> CONTROLLER_MISS  (디스패치 전이다 -> 모델로 넘어간다)
              ▼
         작업 하나짜리 사슬(Sequencer · Gate01)
              primary  = 도구 실행(LLM 차단 실행기 walp/se_exec)
              post     = 출력 꼴이 맞고 · ok · LLM 시도 0
              필수검사 = sandbox 에서 `agentic.tools --verify <도구>` -- 커밋된 나무의 그 함수 원문이 등록과 같은가
              │ 승인 -> 도구 출력을 답으로(**신뢰 안 함** 표시)
              └ 아니면 그 상태로 끝난다. **모델로 넘어가지 않는다** -- 디스패치된 일이 게이트에서 졌는데 다른 길로
                돌아가면 정책 G 의 "다음 작업을 보내지 마라" 를 어긴다

제어부는 판단하지 않는다. 모호하면(ASK) 고르지 않고 놓친 것으로 넘긴다.
"""
from __future__ import annotations

from agentic import gate01 as G
from agentic import tools as TL
from agentic.sequencer import chain_in
from agentic.task import Action, Registry, TaskSpec


def _route(text: str) -> dict:
    from walp import se_router
    return se_router.route(text)


def try_tools(text, cfg, L, sink, runs_base, run_id, run_dir,
              registry=None, route_fn=None, executor=None, checks=None, src_sha=TL.source_sha):
    """None = 놓침(모델로). 아니면 (상태, 사유, 요약, 도구 이름, 출력 글 또는 None)."""
    registry = registry if registry is not None else TL.load_registry()
    r = (route_fn or _route)(text)
    status, name = r.get("status"), r.get("tool")
    rid = L.emit("CONTROLLER_ROUTE", "code", {"status": status, "tool": name, "why": r.get("why"),
                                              "missing": r.get("missing"),
                                              "candidates": [c if isinstance(c, str) else c[0]
                                                             for c in (r.get("candidates") or [])][:5]})

    def miss(reason):
        L.emit("CONTROLLER_MISS", "code", {"tool": name, "reason": reason}, [rid])
        return None

    if status != "TOOL":
        return miss(f"route:{status}:{r.get('why')}")
    args = r.get("args") or {}
    why = precheck(name, args, registry, src_sha, runs_base)
    if why:
        return miss(why)
    st, reason, summary, out = run_registered(name, args, text, cfg, L, sink, runs_base, run_id, run_dir,
                                              registry, executor, checks, event=run_id)
    return st, reason, summary, name, out


def precheck(name, args, registry, src_sha=TL.source_sha, runs_base=None) -> "str | None":
    """디스패치 전의 거절 사유. None 이면 보낼 수 있다. 제어부와 사고부가 같은 것을 쓴다.
    `runs_base` 를 주면 회로 차단기도 본다(열려 있으면 quarantined:breaker_open)."""
    ent = registry.get("tools", {}).get(name)
    if ent is None:
        why = registry.get("rejected", {}).get(name)
        return "not_registered" + (f":{why[0]}" if why else "")
    bad = TL.check_args(ent["declaration"], args)
    if bad:
        return "args_invalid:" + ",".join(bad[:3])
    if src_sha(name) != ent.get("source_sha"):
        return "quarantined:source_changed"
    if runs_base is not None:
        from agentic import breaker as BR
        if BR.state(runs_base, name, ent.get("source_sha"))["open"]:
            return "quarantined:breaker_open"
    return None


def run_registered(name, args, goal, cfg, L, sink, runs_base, run_id, run_dir, registry,
                   executor=None, checks=None, event=""):
    """등록된 도구 하나를 작업 하나짜리 Gate01 사슬로. (상태, 사유, 요약, 출력 글 또는 None).
    **precheck 를 먼저 통과한 것만** 여기 온다."""
    ent = registry["tools"][name]
    out_box = {}
    # 정책 C.1 · D.4: 기본 실행은 sandbox 안에서(HEAD 워크트리 · 고삐 · 비밀 없음 · LLM 차단)
    run = executor or (lambda n, a: TL.sandbox_execute(n, a, timeout=cfg.budgets["sandbox_seconds"]))

    def act(inputs, state, _n=name):
        out = run(_n, dict(inputs))
        out_box["out"] = out
        if isinstance(out, dict) and isinstance(out.get("sandbox"), dict):
            L.emit("SANDBOX_EXEC", "executor", {"tool": _n, **out["sandbox"]})
        if isinstance(out, dict) and isinstance(out.get("mcp"), dict):
            # 정책 A.4: 서버가 **이번 연결에서** 말한 버전 셋을 따로 -- 등록 때 값이 아니라
            L.emit("MCP_VERSION", "executor", {**out["mcp"], "tool": _n, "phase": "call"})
        return out if isinstance(out, dict) else {"ok": False, "error": "non_dict_output"}

    def tool_ok(state, spec):
        return TL.check_output(out_box.get("out")) == []

    reg = Registry({f"tool:{name}": Action(ent["kind"], act)}, {"tool_ok": tool_ok})
    spec = TaskSpec(name=f"tool:{name}", goal=goal[:200], primary=f"tool:{name}", post="tool_ok",
                    inputs=args, permissions=(ent["kind"],),
                    verify_argv=("python3", "-m", "agentic.tools", "--verify", name), event=event)
    st, reason, summary = chain_in([spec], reg, cfg, checks if checks is not None else {"sandbox": G.sandbox_check},
                                   L, sink, runs_base, run_id, run_dir)
    out = out_box.get("out")
    if out is not None:
        from agentic import breaker as BR
        broken = TL.broken_reason(out)
        if BR.note(runs_base, name, ent.get("source_sha"), broken, run_id, cfg.repair["trip_after"]):
            L.emit("TOOL_QUARANTINED", "code", {"tool": name, "reason": broken,
                                                "trip_after": cfg.repair["trip_after"]})
            t = BR.request_repair(runs_base, name, ent.get("source_sha"), args, broken, run_id)
            L.emit("REPAIR_REQUESTED", "code", {"tool": name, "ticket": t["id"], "reproduce": t["reproduce"],
                                                "hypotheses": len(t["diagnosis"]["hypotheses"])})
    text_out = out.get("result") if st == "DONE" and isinstance(out, dict) else None
    if st == "DONE" and not isinstance(text_out, str):
        return "FAILED", "tool_output_missing", "승인됐는데 출력이 없다", None
    return st, reason, summary, text_out
