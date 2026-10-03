"""agentic 5단계 -- MCP 클라이언트(정책 A.4 · A.5 · D)와 RAG/Graph 기억. 정책 K 의 'MCP 버전 보고' 줄.

MCP 는 **진짜 서버**(walp/mcp_server.py)와 tmp 에 지은 **가짜 서버들**(정보를 안 주는 · 다른 프로토콜 · 멈추는 ·
곧 죽는 · 오류를 내는 · 도구 설명이 바뀐)로 본다. 모델은 함수 호출을 하는 가짜. 원장 · 기억은 전부 임시 자리.

    python3 tests/test_agentic_phase5.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestrator"))

from agentic import config as C                         # noqa: E402
from agentic import gate01 as G                         # noqa: E402
from agentic import mcp_client as MC                    # noqa: E402
from agentic import memory as MEM                       # noqa: E402
from agentic import tools as TL                         # noqa: E402
from agentic.ledger import DiagnosticSink, Ledger, read_events  # noqa: E402
from agentic.run import run                             # noqa: E402
import gemini_http as GH                                # noqa: E402

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


MODEL = "gemini-3-flash-preview"

FAKE = r'''
import json, os, sys
MODE = sys.argv[1]
LOG = sys.argv[2]
DESC = "읽기 도구" if MODE != "changed" else "설명이 바뀌었다"
TOOLS = [{"name": "peek", "description": DESC,
          "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}]
if MODE == "die":
    sys.exit(0)
for line in sys.stdin:
    m = json.loads(line)
    if "id" not in m:
        continue
    meth = m["method"]
    if MODE == "hang":
        continue
    if meth == "initialize":
        if MODE == "noinfo":
            res = {"capabilities": {}}
        elif MODE == "oldproto":
            res = {"protocolVersion": "2024-11-05", "serverInfo": {"name": "fake", "version": "1"}}
        else:
            res = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "fake", "version": "9.9"}}
        out = {"jsonrpc": "2.0", "id": m["id"], "result": res}
    elif meth == "tools/list":
        out = {"jsonrpc": "2.0", "id": m["id"], "result": {"tools": TOOLS}}
    elif meth == "tools/call":
        open(LOG, "a").write("called\n")
        if MODE == "rpcerr":
            out = {"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32603, "message": "boom"}}
        elif MODE == "iserr":
            out = {"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": "나빴다"}], "isError": True}}
        else:
            out = {"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": "peek:" + m["params"]["arguments"]["q"]}]}}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n"); sys.stdout.flush()
'''


def cfg_at(d, rag=None):
    base = {"model": MODEL, "model_fallback": False,
            "budgets": {"model_calls": 10, "forgery_retries": 1, "wall_seconds": 180, "tasks": 20,
                        "sandbox_seconds": 60, "react_turns": 6, "tool_output_chars": 4000},
            "sandbox": "sandbox/", "mandatory_checks": ["sandbox"], "allowed_kinds": ["read", "compute"], "loop": {"same_action": 2, "same_failure": 2, "no_progress": 3},
            "rag": rag or {"k": 3, "repo_graph": False, "record": True}, "repair": {"trip_after": 2}}
    p = Path(d) / f"cfg{len(list(Path(d).glob('cfg*')))}.json"
    p.write_text(json.dumps(base))
    return C.load(p)


class Native:
    def __init__(self, *script):
        self.script, self.seen = list(script), []

    def __call__(self, model, key):
        fac = self

        class _C:
            def invoke_tools(self, contents, decls, system):
                fac.seen.append({"contents": json.loads(json.dumps(contents)), "decls": decls})
                return GH.ToolReply(fac.script.pop(0), MODEL)
        return _C()


SB = {"sandbox": lambda s, c, k: (G.TRUE, "fake")}

with tempfile.TemporaryDirectory() as tmp:
    T = Path(tmp)
    os.environ["SE_LEDGER_ROOT"] = str(T / "ledgerroot")       # walp 서버의 사용성 원장도 여기로(나무를 안 더럽힌다)
    fake = T / "fake_server.py"
    fake.write_text(FAKE)
    calls_log = T / "calls.log"

    def srv(mode):
        return {"f": {"command": [sys.executable, str(fake), mode, str(calls_log)]}}

    print("[A.4 · A.5] 버전 세 갈래 -- 서버가 실제로 말한 것만")
    log = str(T / "n1.log")
    s = MC.open_session("walp", MC.load_servers(), log)
    v = s.versions()
    s.close()
    ok(v["protocol"] == "2025-06-18" and v["server"] == "walp/0.2" and v["sdk"] == "none"
       and v["client"].startswith("agentic.mcp_client@"), f"진짜 walp 서버: {v}")
    s = MC.Session([sys.executable, str(fake), "noinfo", str(calls_log)], timeout=5)
    s.initialize()
    v = s.versions()
    s.close()
    ok(v["protocol"] == "unreported" and v["server"] == "unreported", "서버가 안 밝히면 unreported -- 지어내지 않는다")
    for mode, code in [("noinfo", "protocol_unsupported:unreported"), ("oldproto", "protocol_unsupported:2024-11-05"),
                       ("die", "server_closed")]:
        try:
            MC.open_session("f", srv(mode), str(T / "x.log"), timeout=5).close()
            ok(False, f"{mode} -> {code}")
        except MC.MCPError as e:
            ok(e.code == code, f"{mode} -> {e.code}")
    try:
        MC.open_session("f", srv("hang"), str(T / "x.log"), timeout=1).close()
        ok(False, "hang -> timeout")
    except MC.MCPError as e:
        ok(e.code == "timeout", f"멈춘 서버 -> {e.code} (시간 상한)")
    ok(MC.run_tool("mcp__f__peek", {"q": "a"}, srv("rpcerr"))["error"] == "rpc_error:-32603", "RPC 오류는 오류로")
    ok(MC.run_tool("mcp__f__peek", {"q": "a"}, srv("iserr"))["error"].startswith("tool_error:"), "isError 는 ok=False")
    good = MC.run_tool("mcp__f__peek", {"q": "a"}, srv("ok"))
    ok(good["ok"] and good["result"] == "peek:a" and good["mcp"]["server"] == "fake/9.9", "정상 호출 · 버전이 같이 온다")

    print("[D.6] 도구 설명이 바뀌면 부르지 않는다")
    sha_ok = MC.live_sha("mcp__f__peek", srv("ok"))
    n0 = len(calls_log.read_text().splitlines()) if calls_log.exists() else 0
    r = MC.run_tool("mcp__f__peek", {"q": "a"}, srv("changed"), expected_sha=sha_ok)
    n1 = len(calls_log.read_text().splitlines())
    ok(r["error"] == "quarantined:schema_changed" and n1 == n0, "해시 불일치 -> 격리, tools/call 은 한 번도 안 갔다")
    ok(MC.live_sha("mcp__f__peek", srv("changed")) != sha_ok, "설명이 바뀌면 해시가 바뀐다")

    print("[D.1 · D.3] 선언 · 등록 규율")
    d, why = MC.to_declaration("walp", {"name": "walp_sus", "description": "x", "inputSchema": {
        "type": "object", "properties": {"answers": {"type": "array"}}}})
    ok(d is None and "unsupported_param_type:answers:array" in why, "배열 인자는 거절")
    d, why = MC.to_declaration("walp", {"name": "walp_run", "description": "x", "inputSchema": {
        "type": "object", "properties": {"text": {"type": "string"}, "family": {"type": "string", "enum": ["a", "b"]}},
        "required": ["text"]}})
    ok(d["name"] == "mcp__walp__walp_run" and d["parameters"]["properties"]["family"]["enum"] == ["a", "b"]
       and d["parameters"]["required"] == ["text"], "enum · required 를 옮긴다 · 이름은 mcp__서버__도구")
    cfg = cfg_at(T)
    listed = [{"name": n, "description": "d", "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}}
              for n in ("good", "w", "noprobe", "boom", "unlisted")]
    servers = {"s": {"command": ["x"], "tools": {"good": {"kind": "read", "probe": {"args": {"q": "a"}, "expect": "a"}},
                                                  "w": {"kind": "write", "probe": {"args": {"q": "a"}, "expect": "a"}},
                                                  "noprobe": {"kind": "read"},
                                                  "boom": {"kind": "read", "probe": {"args": {"q": "a"}, "expect": "a"}}}}}
    ran = []

    def runner(argv, 초):
        ran.append(argv[5])
        return {"끝값": 1 if argv[5] == "boom" else 0, "돌았나": True, "stdout": "{}", "stderr": ""}
    L = Ledger(T / "reg", "reg")
    m_ok, m_bad = MC.register(cfg, L, DiagnosticSink(L), servers, runner=runner,
                              list_fn=lambda s, a: (listed, {"server": "s/1", "protocol": "2025-06-18", "sdk": "none"}))
    ok(list(m_ok) == ["mcp__s__good"] and m_ok["mcp__s__good"]["via"] == "mcp", "등록은 good 하나, via=mcp")
    for n, w in [("w", "kind_not_allowed:write"), ("noprobe", "no_probe"), ("boom", "probe_failed"),
                 ("unlisted", "not_in_allowlist")]:
        ok(any(x.startswith(w) for x in m_bad.get(f"mcp__s__{n}", [])), f"{n}: {w}")
    ok(sorted(ran) == ["boom", "good"], f"sandbox 탐침은 앞 검사를 통과한 것만 ({ran})")
    ok(any(e["type"] == "MCP_VERSION" and e["data"]["phase"] == "register" for e in read_events(T / "reg")),
       "등록 때도 서버가 말한 버전을 원장에")

    print("[D.6] 커밋된 등록부의 MCP 도구가 지금 서버와 맞는가")
    R = TL.load_registry()
    mcp_ok = {n: e for n, e in R["tools"].items() if n.startswith("mcp__")}
    ok("mcp__walp__walp_se_catalog" in mcp_ok, "walp_se_catalog 가 등록돼 있다")
    for n, e in mcp_ok.items():
        ok(MC.live_sha(n) == e["source_sha"], f"{n}: 지금 서버의 해시 == 등록 해시 (다르면 --register)")
    ok(any(x.startswith("kind_not_allowed:write") for x in R["rejected"].get("mcp__walp__walp_interpret", [])),
       "walp_interpret 는 쓰기(사용성 원장에 덧씀)라 거절돼 있다")

    print("[A.4] 사고부가 MCP 도구를 부르면 그 연결의 버전 셋이 원장 · 화면에")
    m = Native([{"function_call": {"name": "mcp__walp__walp_se_catalog", "args": {}}}], [{"text": "도구 목록을 봤다."}])
    st, rd, txt = run("SE 도구 목록", cfg, root=T / "r1", keys=[("K", "k")], client_factory=m, run_id="m1",
                      controller_opts={"route_fn": lambda t: {"status": "REJECT", "why": "x"}, "checks": SB})
    mv = [e for e in read_events(rd) if e["type"] == "MCP_VERSION"]
    ok(st == "DONE" and mv and mv[-1]["data"]["phase"] == "call" and mv[-1]["data"]["server"] == "walp/0.2",
       f"MCP_VERSION(call) 사건 ({st})")
    ok("MCP: protocol 2025-06-18 · sdk none · server walp/0.2" in txt, "화면 MCP 칸: 세 갈래가 따로")

    print("[RAG] 적고 · 꺼내고 · 대조한다")
    root = T / "rag"
    m = Native([{"text": "CTLE 는 연속시간 선형 등화기다."}])
    st, rd, txt = run("CTLE 설명해 줘", cfg, root=root, keys=[("K", "k")], client_factory=m, run_id="g1",
                      controller_opts={"route_fn": lambda t: {"status": "REJECT", "why": "x"}, "checks": SB})
    mw = [e for e in read_events(rd) if e["type"] == "MEMORY_WRITTEN"]
    note = MEM.memory_root(root / "agentic" / "runs") / "notes" / "g1.md"
    ok(st == "DONE" and mw and mw[0]["data"]["result"] == "적었다" and note.is_file(), "끝날 때 노트를 적었다")
    body = note.read_text()
    ok("상태: DONE" in body and "연속시간 선형 등화기" in body and "위조 검사만 통과" in body, "노트: 상태 · 답 · 확인수준")
    ok("ctle" in mw[0]["data"]["flags"] and "agentic" in mw[0]["data"]["flags"], "깃발: 물음 낱말 · agentic")
    ok("기억: 조회 0건 · 기록 적었다" in txt, "화면 기억 칸")

    m = Native([{"text": "다시 답한다."}])
    st, rd, txt = run("CTLE 가 뭐였지", cfg, root=root, keys=[("K", "k")], client_factory=m, run_id="g2",
                      controller_opts={"route_fn": lambda t: {"status": "REJECT", "why": "x"}, "checks": SB})
    mr = [e for e in read_events(rd) if e["type"] == "MEMORY_RETRIEVED"][0]["data"]["hits"]
    first = m.seen[0]["contents"][0]["parts"]
    ok(mr and mr[0]["source"] == "notes/g1.md" and mr[0]["hash_ok"], "다음 실행이 지난 노트를 꺼냈다(해시 일치)")
    ok(len(first) == 2 and "untrusted" in first[1]["text"] and "연속시간 선형 등화기" in first[1]["text"],
       "꺼낸 노트는 '신뢰 안 함' 으로 물음 옆에 붙었다")

    note.write_text(body + "\n- 누가 손댔다\n")
    m = Native([{"text": "또."}])
    st, rd, txt = run("CTLE 다시", cfg, root=root, keys=[("K", "k")], client_factory=m, run_id="g3",
                      controller_opts={"route_fn": lambda t: {"status": "REJECT", "why": "x"}, "checks": SB})
    ok("WARNING: the source has changed" in m.seen[0]["contents"][0]["parts"][1]["text"]
       and "원본이 바뀐 것" in txt, "원본이 바뀌면 경고를 같이 넘기고 화면에도 보인다")

    print("[RAG] 실패도 적는다 · 기록 실패는 조용하지 않다 · 저장소 graph 는 읽기만")
    m = Native(*[[{"function_call": {"name": "nope", "args": {}}}] for _ in range(3)])
    st, rd, txt = run("없는 도구를 불러", cfg, root=root, keys=[("K", "k")], client_factory=m, run_id="g4",
                      controller_opts={"route_fn": lambda t: {"status": "REJECT", "why": "x"}, "checks": SB})
    n4 = MEM.memory_root(root / "agentic" / "runs") / "notes" / "g4.md"
    ok(st == "LOOP_LIMIT_REACHED" and n4.is_file() and "상태: LOOP_LIMIT_REACHED" in n4.read_text(),
       "고리로 끝난 실행도 노트로 남는다(부정 결과를 지우지 않는다)")
    bad = T / "badmem"
    (MEM.memory_root(bad / "agentic" / "runs") / "graph" / "ledger.jsonl").mkdir(parents=True)
    m = Native([{"text": "답."}])
    st, rd, txt = run("기록이 막힌 자리", cfg, root=bad, keys=[("K", "k")], client_factory=m, run_id="g5",
                      controller_opts={"route_fn": lambda t: {"status": "REJECT", "why": "x"}, "checks": SB})
    ok(st == "DONE" and any(e["type"] == "MEMORY_WRITE_FAILED" for e in read_events(rd)) and "기록 실패(" in txt,
       "기억을 못 적어도 실행은 끝나고, 실패는 원장 · 화면에")

    repo = T / "fakerepo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "ctle.md").write_text("CTLE 노트 원본")
    from graph import store
    store.적기("CTLE 의 피킹 이득에 대한 저장소 노트", ["ctle", "피킹"], "docs/ctle.md", repo=repo)
    before = (repo / "graph" / "ledger.jsonl").read_text()
    cfg_rg = cfg_at(T, rag={"k": 3, "repo_graph": True, "record": True})
    m = Native([{"text": "답."}])
    st, rd, txt = run("ctle 피킹", cfg_rg, root=T / "rg", keys=[("K", "k")], client_factory=m, run_id="g6",
                      controller_opts={"route_fn": lambda t: {"status": "REJECT", "why": "x"}, "checks": SB,
                                       "repo_graph_root": repo})
    hits = [e for e in read_events(rd) if e["type"] == "MEMORY_RETRIEVED"][0]["data"]["hits"]
    ok(any(h["store"] == "repo" and h["source"] == "docs/ctle.md" for h in hits), "저장소 graph 에서도 꺼냈다")
    ok((repo / "graph" / "ledger.jsonl").read_text() == before, "저장소 graph 원장은 한 줄도 안 늘었다(읽기만)")

    print("[RAG] 조회가 터져도 막지 않되 적는다")
    from agentic import thinker as TH
    from agentic.model import FixedModel
    L = Ledger(T / "rf", "rf")
    M = FixedModel(cfg, L, DiagnosticSink(L), keys=[("K", "k")], client_factory=Native([{"text": "답."}]))

    def broken(q):
        raise RuntimeError("x")
    st = TH.think("q", cfg, L, DiagnosticSink(L), M, T / "rf_runs", "rf", T / "rf", {"tools": {}}, recall=broken)
    mr = [e for e in read_events(T / "rf") if e["type"] == "MEMORY_RETRIEVED"][0]["data"]
    ok(st == "DONE" and mr.get("error") == "RuntimeError", "조회 예외 -> MEMORY_RETRIEVED(error), 실행은 계속")

    del os.environ["SE_LEDGER_ROOT"]

print()
if fails:
    print(f"agentic 5단계: {len(fails)}개 실패 -- {fails}")
    sys.exit(1)
print("agentic 5단계: MCP 버전 셋 · 가짜 서버 여섯 · 격리 · 등록 규율 · RAG 적기·꺼내기·대조 · 실패 기록 -- 통과")
