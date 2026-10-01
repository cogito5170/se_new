"""agentic 3단계 -- 도구 생성·검증·등록(정책 D)과 제어부(greedy). 정책 K 의 '도구 생성과 검증' 줄.

  · 선언: 저장소 도구 -> Gemini functionDeclarations. 못 옮기는 것은 사유를 달고 거절
  · 권한: 설정의 allowed_kinds 밖 · LLM 을 쓰는 도구 · dispatch 명령은 거절
  · 등록: 탐침이 sandbox 에서 통과한 것만. 선언 해시 + 함수 원문 해시에 묶는다
  · 커밋된 `agentic/tool_registry.json` 이 지금 나무와 맞는가(원문이 바뀌었는데 재등록 안 했으면 빨강)
  · 제어부: 등록된 도구는 모델 없이 Gate01 사슬로 바로, 못 하면 모델로, 게이트에서 지면 모델로 안 간다

모델은 가짜. sandbox 는 대부분 가짜로, 끝에서 한 번 **진짜로**(등록부에 있는 read_file 을 HEAD 워크트리 검증과 함께).

    python3 tests/test_agentic_phase3.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestrator"))

from agentic import config as C                         # noqa: E402
from agentic import gate01 as G                         # noqa: E402
from agentic import tools as TL                         # noqa: E402
from agentic.ledger import DiagnosticSink, Ledger, read_events  # noqa: E402
from agentic.run import run                             # noqa: E402
from walp.se_tools import Param, ToolInfo               # noqa: E402

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


MODEL = "gemini-3.1-flash-lite"


def cfg_at(d, **over):
    base = {"model": MODEL, "model_fallback": False,
            "budgets": {"model_calls": 4, "forgery_retries": 1, "wall_seconds": 180, "tasks": 20,
                        "sandbox_seconds": 120, "react_turns": 6, "tool_output_chars": 4000},
            "sandbox": "sandbox/", "mandatory_checks": ["sandbox"], "allowed_kinds": ["read", "compute"],
            "loop": {"same_action": 2, "same_failure": 2, "no_progress": 3},
            "rag": {"k": 3, "repo_graph": False, "record": False},
            "front": {"walp": False}}
    base.update(over)
    p = Path(d) / f"cfg{len(list(Path(d).glob('cfg*')))}.json"
    p.write_text(json.dumps(base))
    return C.load(p)


def tool(name="read_x", kind="read", params=None, doc="읽는다", llm=False, source="bot_tools"):
    return ToolInfo(name, source, params if params is not None else
                    [Param("path", "str", None), Param("lines", "int", "400"), Param("scale", "float", "1.0"),
                     Param("raw", "bool", "False")], doc, kind, llm, ["x.py"] if llm else [])


with tempfile.TemporaryDirectory() as tmp:
    T = Path(tmp)
    cfg = cfg_at(T)

    print("[D.1] 선언")
    d, why = TL.to_declaration(tool())
    ok(not why and d["parameters"]["properties"]["lines"]["type"] == "INTEGER"
       and d["parameters"]["properties"]["scale"]["type"] == "NUMBER"
       and d["parameters"]["properties"]["raw"]["type"] == "BOOLEAN", "str/int/float/bool -> STRING/INTEGER/NUMBER/BOOLEAN")
    ok(d["parameters"]["required"] == ["path"], "기본값 없는 인자만 required")
    for t, w in [(tool(name="cmd:!소설"), "name_invalid_for_gemini"),
                 (tool(params=[Param("xs", "list", None)]), "unsupported_param_type:xs:list"),
                 (tool(params=[Param("정책", "str", "'pi'")]), "param_name_invalid_for_gemini:정책"),
                 (tool(doc=""), "no_description")]:
        d, why = TL.to_declaration(t)
        ok(d is None and w in why, f"거절: {w}")
    cat = TL.catalog()
    res = [TL.to_declaration(t) for t in cat]
    ok(all((d is None) != (not w) for d, w in res), f"진짜 카탈로그 {len(cat)}개 전부 선언 또는 사유 (말 없이 빠지는 것 없음)")

    print("[D.2·D.3] 권한")
    for t, w in [(tool(kind="shell"), "kind_not_allowed:shell"), (tool(kind="network"), "kind_not_allowed:net"),
                 (tool(kind="write"), "kind_not_allowed:write"), (tool(llm=True), "tool_uses_llm"),
                 (tool(source="dispatch"), "source_not_bot_tools:dispatch")]:
        ok(any(x.startswith(w) for x in TL.authorize(t, cfg)), f"거절: {w}")
    ok(TL.authorize(tool(), cfg) == [], "읽기·LLM 없음·bot_tools 는 통과")

    print("[D.2] 입력·출력 스키마")
    d, _ = TL.to_declaration(tool())
    for a, w in [({"path": "a", "nope": 1}, "unknown_arg:nope"), ({}, "missing_arg:path"),
                 ({"path": 3}, "arg_type:path:STRING"), ({"path": "a", "lines": True}, "arg_type:lines:INTEGER"),
                 ({"path": "a", "raw": 1}, "arg_type:raw:BOOLEAN"), ("x", "args_not_object")]:
        ok(w in TL.check_args(d, a), f"인자 거절: {w}")
    ok(TL.check_args(d, {"path": "a", "lines": 3, "scale": 2}) == [], "NUMBER 칸의 정수는 받는다")
    for o, w in [("x", "output_not_object"), ({"result": "a", "llm_attempts": 0}, "output_ok_not_bool"),
                 ({"ok": True, "result": 3, "llm_attempts": 0}, "output_result_not_str"),
                 ({"ok": False, "error": "boom", "llm_attempts": 0}, "tool_not_ok:boom"),
                 ({"ok": True, "result": "a", "llm_attempts": 1}, "llm_attempts:1"),
                 ({"ok": True, "result": "a"}, "llm_attempts:None")]:
        ok(w in TL.check_output(o), f"출력 거절: {w}")
    ok(TL.probe("t", {}, "zz", executor=lambda n, a: {"ok": True, "result": "aa", "llm_attempts": 0})
       == ["expect_not_found"], "기대 글자가 없으면 탐침 실패")

    print("[D.4·D.5·D.6] 등록 -- sandbox 탐침을 통과한 것만, 해시에 묶어")
    calls = []

    def runner(argv, 초):
        calls.append(argv)
        name = argv[4]
        if name == "boom":
            return {"끝값": 1, "돌았나": True, "stdout": '{"reasons": ["expect_not_found"]}', "stderr": ""}
        if name == "nosb":
            return {"끝값": 3, "돌았나": False, "메모": "판을 못 깔았다"}
        return {"끝값": 0, "돌았나": True, "stdout": "{}", "stderr": ""}
    good = tool("good")
    cands = [good, tool("boom"), tool("nosb"), tool("noprobe"), tool("sh", kind="shell"), tool("llmy", llm=True),
             tool("badargs"), tool("nosrc")]
    probes = {n: {"args": {"path": "agentic/config.json"}, "expect": "x"}
              for n in ("good", "boom", "nosb", "sh", "llmy", "nosrc")}
    probes["badargs"] = {"args": {"path": 1}, "expect": "x"}
    L = Ledger(T / "reg", "reg")
    reg = TL.register(cfg, L, DiagnosticSink(L), probes, cat=cands, runner=runner, head_sha="h",
                      src_sha=lambda n: None if n == "nosrc" else f"src-{n}")
    ok(list(reg["tools"]) == ["good"], f"등록된 것은 good 하나 ({list(reg['tools'])})")
    e = reg["tools"]["good"]
    ok(e["source_sha"] == "src-good" and e["decl_sha"] == TL.sha(e["declaration"]), "선언 해시 · 원문 해시에 묶임")
    rj = reg["rejected"]
    for n, w in [("boom", "probe_failed:exit=1"), ("nosb", "sandbox_not_run"), ("noprobe", "no_probe"),
                 ("sh", "kind_not_allowed:shell"), ("llmy", "tool_uses_llm"), ("badargs", "probe_arg_type:path"),
                 ("nosrc", "no_source")]:
        ok(any(x.startswith(w) for x in rj.get(n, [])), f"{n}: {w}")
    ran = sorted(a[4] for a in calls)
    ok(ran == ["boom", "good", "nosb"], f"sandbox 탐침은 앞 검사를 통과한 후보에서만 돌았다 ({ran})")
    ok(calls[0][:4] == ["python3", "-m", "agentic.tools", "--probe"], "탐침은 sandbox 안의 `agentic.tools --probe`")
    evs = read_events(T / "reg")
    ok(sum(e["type"] == "TOOL_REGISTERED" for e in evs) == 1 and sum(e["type"] == "TOOL_REJECTED" for e in evs) == 7,
       "원장에 등록 1 · 거절 7 -- 하나도 말 없이 빠지지 않는다")

    print("[D.6] 커밋된 등록부가 지금 나무와 맞는가")
    R = TL.load_registry()
    probes_real = json.loads(TL.PROBES_PATH.read_text(encoding="utf-8"))
    ok(TL.REGISTRY_PATH.exists() and R.get("tools"), "agentic/tool_registry.json 이 있고 등록된 도구가 있다")
    cat_by = {t.name: t for t in cat}
    for n, ent in R.get("tools", {}).items():
        if n.startswith("mcp__"):
            continue                         # MCP 도구는 tests/test_agentic_phase5.py 가 본다
        ok(TL.source_sha(n) == ent["source_sha"], f"{n}: 함수 원문이 등록 때와 같다 (다르면 재등록: --register)")
        d, _ = TL.to_declaration(cat_by[n])
        ok(d == ent["declaration"] and TL.sha(d) == ent["decl_sha"], f"{n}: 선언이 지금 카탈로그에서 다시 만든 것과 같다")
        ok(ent["kind"] in cfg.allowed_kinds and not cat_by[n].llm and n in probes_real, f"{n}: 권한 안 · LLM 없음 · 탐침 있음")
    ok({n for n in set(R.get("tools", {})) | set(R.get("rejected", {})) if not n.startswith("mcp__")} == set(cat_by),
       "카탈로그의 도구 전부가 등록 또는 거절에 있다")

    print("[제어부] 등록된 도구는 모델 없이, 아니면 모델로")
    fake_reg = {"tools": {"read_file": {"declaration": TL.to_declaration(cat_by["read_file"])[0],
                                        "source_sha": "S", "kind": "read"}},
                "rejected": {"serdes_link": ["no_probe"]}}
    ex_calls = []

    def ex(name, args, out=None):
        ex_calls.append((name, args))
        return out or {"ok": True, "result": "1\t{\n2\t  \"model\": ... NO_LOOP_DETECTED", "llm_attempts": 0}

    class Fac:
        def __init__(self):
            self.n = 0

        def __call__(self, m, k):
            fac = self

            class _C:
                def invoke(self, p):
                    fac.n += 1

                    class R:
                        content, model_version = "모델 답", MODEL
                    return R()
            return _C()

    SB = {"sandbox": lambda s, c, k: (G.TRUE, "fake")}
    k = [0]

    def go(text, route, executor=ex, checks=SB, src="S"):
        k[0] += 1
        f = Fac()
        st, rd, txt = run(text, cfg, root=T / "ctl", keys=[("K", "k")], client_factory=f, run_id=f"c{k[0]}",
                          controller_opts={"registry": fake_reg, "route_fn": lambda t: route, "executor": executor,
                                           "checks": checks, "src_sha": lambda n: src})
        return st, rd, txt, f

    TOOL = {"status": "TOOL", "tool": "read_file", "args": {"path": "agentic/config.json"}}
    st, rd, txt, f = go("agentic/config.json 파일 읽어줘", TOOL)
    ok(st == "DONE" and f.n == 0 and "controller_tool" in txt, "등록된 도구 -> DONE(controller_tool), 모델 호출 0")
    ok("답(도구 출력 · 신뢰 안 함 · tool:read_file):" in txt, "답 칸에 '신뢰 안 함' 표시")
    ok("루프: UNKNOWN" in txt and txt.count("NO_LOOP_DETECTED") == 1 and txt.index("NO_LOOP_DETECTED") > txt.index("답("),
       "도구 출력의 깃발 낱말은 답 칸에만 있고 상태 칸을 못 바꾼다")
    es = read_events(rd)
    ok([e["data"]["step"] for e in es if e["type"] == "GATE_EVAL"] == ["A_TO_B"]
       and any(e["type"] == "CHECK_EVAL" for e in es), "Gate01 과 필수 검사를 거쳤다")
    spec_v = [e for e in es if e["type"] == "NEXT_DISPATCHED"]
    ok(len(spec_v) == 1, "작업 하나가 디스패치됐다")

    for route, w in [({"status": "ASK", "why": "two_tools_close"}, "route:ASK:two_tools_close"),
                     ({"status": "REJECT", "why": "no_tool_matched"}, "route:REJECT"),
                     ({"status": "TOOL", "tool": "serdes_link", "args": {}}, "not_registered:no_probe"),
                     ({"status": "TOOL", "tool": "read_file", "args": {"path": 3}}, "args_invalid:arg_type:path")]:
        n0 = len(ex_calls)
        st, rd, txt, f = go("q", route)
        ok(f.n == 1 and len(ex_calls) == n0 and w in txt, f"놓침 {w} -> 모델로, 도구는 안 돌았다")
    n0 = len(ex_calls)
    st, rd, txt, f = go("q", TOOL, src="CHANGED")
    ok(f.n == 1 and len(ex_calls) == n0 and "quarantined:source_changed" in txt, "원문이 바뀐 도구는 격리 -> 모델로")

    st, rd, txt, f = go("q", TOOL, executor=lambda n, a: ex(n, a, {"ok": True, "result": "x", "llm_attempts": 1}))
    ok(st == "RED_RED_STOP" and f.n == 0, "도구가 LLM 을 부르려 했다 -> RED_RED_STOP, 모델로 안 넘어간다")
    st, rd, txt, f = go("q", TOOL, checks={"sandbox": lambda s, c, k: (G.FALSE, "exit=1")})
    ok(st == "BLOCKED" and f.n == 0 and "mandatory:sandbox:FALSE" in txt, "sandbox 검증 실패 -> BLOCKED, 모델로 안 넘어간다")

    n0 = len(ex_calls)
    go("같은 말", TOOL)
    go("같은 말", TOOL)
    ok(len(ex_calls) == n0 + 2, "다른 사건(메시지)이 같은 것을 시키면 다시 돈다 -- 읽기는 그때마다 새로")

    print("[C] 진짜: 등록부의 read_file 을 진짜 라우터 · 진짜 실행기 · 진짜 sandbox 검증으로")
    f = Fac()
    st, rd, txt = run("agentic/config.json 파일 읽어줘", cfg, root=T / "real", keys=[("K", "k")], client_factory=f,
                      run_id="real1")
    ok(st == "DONE" and f.n == 0 and "gemini-3.1-flash-lite" in txt, f"DONE · 모델 0 · 진짜 파일 내용 ({st})")
    ok(any(e["type"] == "CHECK_EVAL" and e["data"]["result"] == "TRUE" for e in read_events(rd)),
       "sandbox 안에서 `agentic.tools --verify read_file` 가 통과했다")

print()
if fails:
    print(f"agentic 3단계: {len(fails)}개 실패 -- {fails}")
    sys.exit(1)
print("agentic 3단계: 선언 · 권한 · 입출력 스키마 · sandbox 등록 · 해시 묶기 · 제어부 -- 통과")
