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
    ent = registry.get("tools", {}).get(name)
    if ent is None:
        why = registry.get("rejected", {}).get(name)
        return miss("not_registered" + (f":{why[0]}" if why else ""))
    args = r.get("args") or {}
    bad = TL.check_args(ent["declaration"], args)
    if bad:
        return miss("args_invalid:" + ",".join(bad[:3]))
    now = src_sha(name)
    if now != ent.get("source_sha"):
        return miss("quarantined:source_changed")

    out_box = {}
    run = executor or TL.execute

    def act(inputs, state, _n=name):
        out = run(_n, dict(inputs))
        out_box["out"] = out
        return out if isinstance(out, dict) else {"ok": False, "error": "non_dict_output"}

    def tool_ok(state, spec):
        return TL.check_output(out_box.get("out")) == []

    reg = Registry({f"tool:{name}": Action(ent["kind"], act)}, {"tool_ok": tool_ok})
    spec = TaskSpec(name=f"tool:{name}", goal=text[:200], primary=f"tool:{name}", post="tool_ok",
                    inputs=args, permissions=(ent["kind"],),
                    verify_argv=("python3", "-m", "agentic.tools", "--verify", name), event=run_id)
    st, reason, summary = chain_in([spec], reg, cfg, checks if checks is not None else {"sandbox": G.sandbox_check},
                                   L, sink, runs_base, run_id, run_dir)
    out = out_box.get("out")
    text_out = out.get("result") if st == "DONE" and isinstance(out, dict) else None
    if st == "DONE" and not isinstance(text_out, str):
        return "FAILED", "tool_output_missing", "승인됐는데 출력이 없다", name, None
    return st, reason, summary, name, text_out
