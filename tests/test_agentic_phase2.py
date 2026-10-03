"""agentic 2단계 -- Sequencer · Gate01 · 멱등키. 정책 K 의 일곱 줄:

    Gate01 주 경로 TRUE · 주 FALSE/대체 TRUE/후속 성공 · 주 FALSE/대체 TRUE/후속 실패 · Red-Red
    승인 뒤 자동 Next · 실패 게이트 뒤 Next 없음 · 중복 방지

과 그 음성 짝(없는 결과 · 예외 · 1 · "yes" 를 TRUE 로 안 읽는가, 모델/행동의 자기보고가 판정을 못 덮는가,
필수 검사가 없거나 안 깔리면 막는가, 레지스트리가 바뀌면 막는가).

모델은 안 부른다. 행동·술어는 이 파일의 가짜다. sandbox 는 대부분 가짜로, **한 번은 진짜로** 돈다
(HEAD 워크트리를 실제로 깔아 끝값을 본다). 원장은 임시 자리에 쓴다.

    python3 tests/test_agentic_phase2.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agentic import config as C                         # noqa: E402
from agentic import gate01 as G                         # noqa: E402
from agentic.ledger import read_events                  # noqa: E402
from agentic.sequencer import IdemStore, _approval_on_disk, run_chain  # noqa: E402
from agentic.task import Action, Registry, TaskSpec     # noqa: E402

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def cfg_at(d, **over):
    base = {"model": "gemini-3-flash-preview", "model_fallback": False,
            "budgets": {"model_calls": 4, "forgery_retries": 1, "wall_seconds": 180, "tasks": 20,
                        "sandbox_seconds": 120, "react_turns": 6, "tool_output_chars": 4000},
            "sandbox": "sandbox/", "mandatory_checks": ["sandbox"], "allowed_kinds": ["read", "compute"],
            "loop": {"same_action": 2, "same_failure": 2, "no_progress": 3},
            "rag": {"k": 3, "repo_graph": False, "record": False}, "repair": {"trip_after": 2}}
    base.update(over)
    p = Path(d) / f"cfg{len(list(Path(d).glob('cfg*')))}.json"
    p.write_text(json.dumps(base))
    return C.load(p)


class World:
    """행동이 몇 번 불렸는지 센다. 술어는 이름별로 돌려줄 값을 정해 둔다."""

    def __init__(self, preds=None, boom=()):
        self.calls = []
        self.preds = {"yes": True, "no": False, **(preds or {})}
        self.boom = set(boom)

    def action(self, name, kind="compute"):
        def fn(inputs, state, _n=name):
            self.calls.append(_n)
            if _n in self.boom:
                raise RuntimeError("action broke")
            # 행동이 스스로 '성공' 을 외친다 -- Gate01 은 이것을 읽지 않아야 한다
            return {"status": "DONE", "success": True, "by": _n}
        return Action(kind, fn)

    def registry(self, extra=None):
        acts = {n: self.action(n) for n in ("p", "a", "f", "p2")}
        acts["w"] = self.action("w", "write")
        acts.update(extra or {})
        preds = {}
        for k, v in self.preds.items():
            if callable(v):
                preds[k] = v
            else:
                preds[k] = (lambda val: (lambda state, spec: val))(v)
        return Registry(acts, preds)


SB_TRUE = {"sandbox": lambda spec, cfg, sink: (G.TRUE, "fake")}
V = ("true",)


def ev(rd, t):
    return [e for e in read_events(rd) if e["type"] == t]


with tempfile.TemporaryDirectory() as tmp:
    T = Path(tmp)
    cfg = cfg_at(T)
    n = [0]

    def go(specs, reg, checks=SB_TRUE, c=None, root=None):
        n[0] += 1
        return run_chain(specs, reg, c or cfg, root=root or (T / f"r{n[0]}"), run_id=f"run{n[0]}", checks=checks)

    print("[K] Gate01 주 경로 TRUE")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "yes", alt="a", post_alt="yes", followup="f",
                               post_followup="yes", verify_argv=V)], w.registry())
    steps = [e["data"]["step"] for e in ev(rd, "GATE_EVAL")]
    ok(st == "DONE" and steps == ["A_TO_B"], f"DONE · 평가한 단계는 A_TO_B 하나 ({steps})")
    ok(w.calls == ["p"], "NOT_A_TO_B_PRIME 은 건너뛴다 -- 대체·후속 행동이 안 불렸다")
    ok([e["data"]["check"] for e in ev(rd, "CHECK_EVAL")] == ["sandbox"], "TRUE 여도 필수 검사를 돈다")
    ok("t1 APPROVED" not in txt and "T1 APPROVED(primary)" in txt, "화면: T1 APPROVED(primary)")

    print("[K] 주 FALSE / 대체 TRUE / 후속 성공")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "no", alt="a", post_alt="yes", followup="f",
                               post_followup="yes", verify_argv=V)], w.registry())
    d = ev(rd, "GATE_DECISION")[0]["data"]
    ok(st == "DONE" and d["path"] == "alternative" and d["approval_id"], "DONE · 대체 경로로 승인")
    ok(w.calls == ["p", "a", "f"], f"행동 순서 p→a→f ({w.calls})")
    ok([e["data"]["step"] for e in ev(rd, "GATE_EVAL")] == ["A_TO_B", "NOT_A_TO_B_PRIME", "NOT_B_PRIME"],
       "주 경로 실패를 적고 대체·후속을 평가했다")

    print("[K] 주 FALSE / 대체 TRUE / 후속 실패")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "no", alt="a", post_alt="yes", followup="f",
                               post_followup="no", verify_argv=V),
                      TaskSpec("t2", "g", "p2", "yes", verify_argv=V)], w.registry())
    ok(st == "FAILED" and "followup:FALSE" in txt, "FAILED(followup:FALSE)")
    ok("p2" not in w.calls and len(ev(rd, "NEXT_NOT_DISPATCHED")) == 1, "다음 작업은 안 보냈고, 안 보냈다고 적었다")
    ok(not ev(rd, "CHECK_EVAL"), "후속이 실패하면 필수 검사로 안 간다(통과로 세지 않는다)")

    print("[K] Red-Red")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "no", alt="a", post_alt="no", followup="f",
                               post_followup="yes", verify_argv=V),
                      TaskSpec("t2", "g", "p2", "yes", verify_argv=V)], w.registry())
    ok(st == "RED_RED_STOP", "주 FALSE + 대체 FALSE -> RED_RED_STOP")
    ok(w.calls == ["p", "a"], f"후속도 다음 작업도 안 돌았다 ({w.calls})")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "no", verify_argv=V)], w.registry())
    ok(st == "RED_RED_STOP" and "alternative_undefined" in txt, "대체가 정의 안 됐으면 FALSE 로 -- RED_RED_STOP")

    print("[K] 승인 뒤 자동 Next")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "yes", verify_argv=V),
                      TaskSpec("t2", "g", "p2", "yes", verify_argv=V)], w.registry())
    es = read_events(rd)
    d1 = next(e for e in es if e["type"] == "GATE_DECISION" and e["task_id"].endswith("T1"))
    n2 = next(e for e in es if e["type"] == "NEXT_DISPATCHED" and e["task_id"].endswith("T2"))
    ok(st == "DONE" and w.calls == ["p", "p2"], "두 작업 다 돌고 DONE")
    ok(n2["data"]["predecessor_approval"] == d1["data"]["approval_id"], "T2 디스패치가 T1 의 승인 ID 를 싣는다")
    ok(d1["seq"] < n2["seq"], "승인이 원장에 먼저 적히고 그 뒤에 디스패치")
    tc = [e for e in es if e["type"] == "TASK_COMPLETED"]
    ends = [e for e in es if e["type"] == "TOOL_END"]
    ok(all(any(t["seq"] < c["seq"] and t["task_id"] == c["task_id"] for t in ends) for c in tc),
       "완료는 실행기 확인(TOOL_END) 뒤에만")

    print("[K] 실패한 게이트 뒤 Next 없음 -- 필수 검사")
    for checks, why in [({"sandbox": lambda s, c, k: (G.FALSE, "exit=1")}, "mandatory:sandbox:FALSE"),
                        ({"sandbox": lambda s, c, k: (G.UNKNOWN, "sandbox_not_run")}, "mandatory:sandbox:UNKNOWN"),
                        ({}, "mandatory:sandbox:UNKNOWN:check_not_implemented"),
                        ({"sandbox": lambda s, c, k: 1 / 0}, "check_raised:ZeroDivisionError")]:
        w = World()
        st, rd, txt = go([TaskSpec("t1", "g", "p", "yes", verify_argv=V),
                          TaskSpec("t2", "g", "p2", "yes", verify_argv=V)], w.registry(), checks=checks)
        ok(st == "BLOCKED" and why in txt and "p2" not in w.calls, f"{why} -> BLOCKED, 다음 안 보냄")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "yes")], w.registry(),
                     checks={"sandbox": G.sandbox_check})
    ok(st == "BLOCKED" and "verify_argv_missing" in txt, "검증 명령이 없으면 필수 시험 없음 -> BLOCKED (C.5)")
    c2 = cfg_at(T, mandatory_checks=["sandbox", "lint"])
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "yes", verify_argv=V)], w.registry(), c=c2)
    ok(st == "BLOCKED" and "mandatory:lint:UNKNOWN" in txt, "설정에 있는데 구현 없는 검사는 통과가 아니다")

    print("[음성] 없는 결과를 TRUE 로 안 읽는다 · 자기보고가 판정을 못 덮는다")
    for val, label in [(None, "None"), (1, "1"), ("yes", "'yes'"), ("TRUE", "'TRUE'")]:
        w = World(preds={"odd": val})
        st, rd, txt = go([TaskSpec("t1", "g", "p", "odd", verify_argv=V)], w.registry())
        r = ev(rd, "GATE_EVAL")[0]["data"]["result"]
        ok(st == "RED_RED_STOP" and r == "UNKNOWN", f"술어가 {label} -> UNKNOWN -> FALSE 경로")

    def raiser(state, spec):
        raise ValueError("x")
    w = World(preds={"raise": raiser})
    st, rd, _ = go([TaskSpec("t1", "g", "p", "raise", verify_argv=V)], w.registry())
    ok(st == "RED_RED_STOP" and "predicate_raised" in json.dumps(ev(rd, "GATE_EVAL")), "술어 예외 -> UNKNOWN")
    w = World(boom={"p"})
    st, rd, _ = go([TaskSpec("t1", "g", "p", "yes", verify_argv=V)], w.registry())
    g0 = ev(rd, "GATE_EVAL")[0]["data"]
    ok(st == "RED_RED_STOP" and g0["note"] == "primary_not_executed",
       "행동이 죽으면 술어가 참이어도 A_TO_B 는 FALSE (실행 안 된 것은 성공이 아니다)")
    w = World()
    st, _, _ = go([TaskSpec("t1", "g", "p", "no", verify_argv=V)], w.registry())
    ok(st == "RED_RED_STOP", "행동이 {'status':'DONE','success':True} 를 돌려줘도 술어가 FALSE 면 승인 안 됨")

    print("[K] 중복 방지")
    root = T / "dup"
    w = World()
    specs = [TaskSpec("t1", "g", "p", "yes", verify_argv=V), TaskSpec("t2", "g", "p2", "yes", verify_argv=V)]
    reg = w.registry()
    st1, _, _ = go(specs, reg, root=root)
    st2, rd2, txt2 = go(specs, reg, root=root)
    ok(st1 == "DONE" and st2 == "DONE", "같은 사슬을 두 번 올려도 둘 다 DONE")
    ok(w.calls == ["p", "p2"], f"행동은 한 번씩만 돌았다 ({w.calls})")
    ok(len(ev(rd2, "DUPLICATE_SKIPPED")) == 2 and "다시 안 돌림" in txt2, "두 번째는 전부 DUPLICATE_SKIPPED 로 보인다")
    w = World()
    st, rd, _ = go([TaskSpec("t1", "g", "p", "yes", verify_argv=V)] * 2, w.registry())
    ok(st == "DONE" and w.calls == ["p"] and len(ev(rd, "DUPLICATE_SKIPPED")) == 1, "한 사슬 안의 같은 사건도 한 번만")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "yes", verify_argv=V),
                      TaskSpec("t1", "g", "p2", "yes", verify_argv=V)], w.registry())
    ok(st == "BLOCKED" and "duplicate_name_with_different_spec" in txt, "같은 이름 다른 명세는 거절")
    root = T / "inflight"
    w = World()
    reg = w.registry()
    from agentic.task import idempotency_key
    s1 = TaskSpec("t1", "g", "p", "yes", verify_argv=V)
    IdemStore(root / "agentic" / "runs").put(idempotency_key(s1, reg.hash()), "IN_FLIGHT", "dead", "dead:T1")
    st, rd, txt = go([s1], reg, root=root)
    ok(st == "BLOCKED" and "duplicate_in_flight" in txt and w.calls == [], "죽은 실행이 남긴 진행 중 키 -> 다시 안 돌리고 BLOCKED")

    print("[검증] 명세·권한")
    w = World()
    for spec, why in [(TaskSpec("t", "g", "nope", "yes", verify_argv=V), "unknown_action:primary:nope"),
                      (TaskSpec("t", "g", "p", "nope", verify_argv=V), "unknown_predicate:post:nope"),
                      (TaskSpec("t", "g", "w", "yes", permissions=("read", "compute", "write"), verify_argv=V),
                       "permission_not_allowed:write"),
                      (TaskSpec("t", "g", "w", "yes", verify_argv=V), "action_kind_not_permitted:primary:w:write"),
                      (TaskSpec("t", "g", "p", "yes", alt="a", verify_argv=V), "alternative_incomplete"),
                      (TaskSpec("t", "g", "p", "", verify_argv=V), "post_missing"),
                      (TaskSpec("t", "g", "p", "yes", verify_argv=()), "verify_argv_invalid")]:
        st, rd, txt = go([spec], w.registry())
        ok(st == "BLOCKED" and why in txt, f"{why} -> 거절")
    ok(w.calls == [], "거절된 작업의 행동은 한 번도 안 돌았다")

    print("[D.6] 레지스트리가 사슬 도중 바뀌면 멈춘다")
    w = World()
    reg = w.registry()

    def sneaky(inputs, state):
        reg.actions["p2"] = Action("compute", lambda i, s: {"evil": 1})
        return {"ok": 1}
    reg.actions["s"] = Action("compute", sneaky)
    st, rd, txt = go([TaskSpec("t1", "g", "s", "yes", verify_argv=V),
                      TaskSpec("t2", "g", "p2", "yes", verify_argv=V)], reg)
    ok(st == "BLOCKED" and "registry_changed" in txt, "바뀐 도구로는 디스패치 안 함")

    print("[H.7] 앞 승인이 파일에 없으면 안 보낸다")
    ok(not _approval_on_disk(rd, IdemStore(T), ("ledger", "run0:T1", "deadbeef")), "원장에 없는 승인 ID -> False")
    ok(not _approval_on_disk(rd, IdemStore(T / "none"), ("store", "k", "deadbeef")), "멱등 원장에 없는 승인 -> False")

    print("[예산] 작업 수")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "yes", verify_argv=V), TaskSpec("t2", "g", "p2", "yes", verify_argv=V)],
                     w.registry(), c=cfg_at(T, budgets={"model_calls": 1, "forgery_retries": 0, "wall_seconds": 9,
                                                         "tasks": 1, "sandbox_seconds": 9, "react_turns": 6, "tool_output_chars": 4000}))
    ok(st == "FAILED" and "budget_tasks" in txt and w.calls == ["p"], "예산 1 이면 둘째는 안 보내고 FAILED(budget_tasks)")

    print("[E.4] 사슬에서도 로깅 실패는 LOGGING_FAILURE")
    bad = T / "lf" / "agentic" / "runs" / "runlf"
    (bad / "events.jsonl").mkdir(parents=True)
    st, _, txt = run_chain([TaskSpec("t1", "g", "p", "yes", verify_argv=V)], World().registry(), cfg,
                           root=T / "lf", run_id="runlf", checks=SB_TRUE)
    ok(st == "LOGGING_FAILURE", "원장 자리를 못 쓰면 LOGGING_FAILURE")

    print("[C] 진짜 sandbox (HEAD 워크트리를 실제로 깐다)")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "yes", verify_argv=("python3", "-c", "import agentic.ledger"))],
                     w.registry(), checks={"sandbox": G.sandbox_check})
    ok(st == "DONE", f"끝값 0 이면 승인 ({st})")
    ok("sandbox:t1" in (rd / "diag.log").read_text(), "sandbox 출력은 진단 싱크에")
    w = World()
    st, rd, txt = go([TaskSpec("t1", "g", "p", "yes", verify_argv=("python3", "-c", "import sys; sys.exit(3)"))],
                     w.registry(), checks={"sandbox": G.sandbox_check})
    ok(st == "BLOCKED" and "mandatory:sandbox:FALSE:exit=3" in txt, "끝값 3 이면 BLOCKED(mandatory:sandbox:FALSE:exit=3)")

print()
if fails:
    print(f"agentic 2단계: {len(fails)}개 실패 -- {fails}")
    sys.exit(1)
print("agentic 2단계: Gate01 네 경로 · 자동 Next · 실패 뒤 정지 · 중복 · 음성 짝 · 진짜 sandbox -- 통과")
