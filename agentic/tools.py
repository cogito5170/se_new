"""도구 생성·검증·등록 -- 정책 D 를 코드로. 저장소의 도구를 **Gemini 함수 선언**으로 옮기고, 통과한 것만 등록한다.

    카탈로그(walp/se_tools: bot_tools.py 의 @tool 을 AST 로 · dispatch 명령)
       │ D.1 선언 만들기      to_declaration   -- Gemini functionDeclarations 꼴(OpenAPI 부분집합)
       │ D.2·D.3 검증·권한    authorize        -- 설정의 allowed_kinds 밖 · LLM 을 쓰는 도구는 거절
       │ D.4 sandbox 탐침     agentic/tool_probes.json 에 적힌 인자로 HEAD 워크트리에서 진짜로 돌린다
       │                     (LLM 차단 실행기 walp/se_exec · 출력 꼴 · 기대 글자 · LLM 시도 0)
       │ D.5 등록             통과한 것만 agentic/tool_registry.json 에
       └ D.6 묶기             선언 해시 + **함수 원문 해시** + HEAD. 원문이 바뀌면 그 도구는 다시 등록될 때까지 격리
    D.7 도구 출력은 신뢰하지 않는 데이터다 -- 답 칸에 '신뢰 안 함' 으로만 그리고, 지시로 읽지 않는다.

**카탈로그의 부작용 분류와 LLM 표지는 추정이다**(se_tools 가 스스로 그렇게 적는다). 실측: `orchestrator_solve` 는
'계산' 으로 분류되지만 백그라운드 런을 띄우고 그 런이 LLM 을 부른다. 그래서 **추정만으로 등록하지 않는다** --
사람이 탐침을 적은 도구만, 그 탐침이 sandbox 에서 실제로 통과했을 때만 등록한다. 탐침이 없으면 `no_probe` 로 거절된다.

**원문 해시의 한계:** `bot_tools.py` 의 그 함수 몸통만 해시한다. 몸통이 부르는 다른 모듈이 바뀌어도 해시는 같다.

**Gemini 이름 규칙은 기억으로 적었다**(영문자·밑줄로 시작, 영숫자·밑줄·점·대시, 64자 이하). 실호출로 확인하지 않았다.

    python3 -m agentic.tools --register        # 등록(탐침은 sandbox 에서). bot_tools + MCP 서버(agentic/mcp_servers.json)
    python3 -m agentic.tools --declarations    # 등록된 도구의 functionDeclarations(JSON)
    python3 -m agentic.tools --probe <이름> '<인자 JSON>' '<기대 글자>'   # sandbox 안에서 쓰는 것
    python3 -m agentic.tools --verify <이름>   # 이 나무의 원문 해시가 등록과 같은가(제어부의 필수 검사)
    python3 -m agentic.tools --exec <이름> '<인자 JSON>'   # 도구 하나를 실행(sandbox 안에서 쓰는 것). 0 = 성공
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REGISTRY_PATH = ROOT / "agentic" / "tool_registry.json"
PROBES_PATH = ROOT / "agentic" / "tool_probes.json"

TYPE_MAP = {"str": "STRING", "int": "INTEGER", "float": "NUMBER", "bool": "BOOLEAN"}
PY_OF = {"STRING": str, "INTEGER": int, "NUMBER": (int, float), "BOOLEAN": bool}
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$")
KIND_ALIAS = {"network": "net"}           # se_tools 의 이름 -> 설정의 이름


def _canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def sha(obj) -> str:
    return hashlib.sha256((obj if isinstance(obj, str) else _canon(obj)).encode()).hexdigest()


def source_sha(name: str, root: Path = ROOT) -> "str | None":
    """bot_tools.py 의 그 @tool 함수 원문 해시. 없으면 None.
    MCP 도구(`mcp__서버__도구`)면 **지금 서버가 알려 주는** (이름·설명·inputSchema·서버 버전) 해시."""
    from agentic import mcp_client as MC
    if MC.split_name(name):
        return MC.live_sha(name)
    p = root / "bot_tools.py"
    try:
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return None
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            seg = ast.get_source_segment(src, n) or ""
            return sha(seg) if seg else None
    return None


def catalog() -> list:
    from walp import se_tools
    return se_tools.catalog()


def to_declaration(t) -> "tuple[dict | None, list]":
    why = []
    if not NAME_RE.match(t.name or ""):
        why.append("name_invalid_for_gemini")
    desc = (t.doc or "").strip()
    if not desc:
        why.append("no_description")
    props, required = {}, []
    for p in t.params:
        typ = TYPE_MAP.get(p.type)
        if typ is None:
            why.append(f"unsupported_param_type:{p.name}:{p.type}")
            continue
        if not NAME_RE.match(p.name):
            why.append(f"param_name_invalid_for_gemini:{p.name}")
            continue
        props[p.name] = {"type": typ, "description": p.name + ("" if p.default is None else f" (기본 {p.default})")}
        if p.default is None:
            required.append(p.name)
    if why:
        return None, why
    decl = {"name": t.name, "description": desc[:1000],
            "parameters": {"type": "OBJECT", "properties": props, "required": required}}
    return decl, []


def authorize(t, cfg) -> list:
    why = []
    kind = KIND_ALIAS.get(t.kind, t.kind)
    if kind not in cfg.allowed_kinds:
        why.append(f"kind_not_allowed:{kind}")
    if t.llm:
        # 도구 안에서 Gemini 나 Claude 를 부르면 그것이 곧 모델 경로 바꾸기다(정책 A.2)
        why.append("tool_uses_llm:" + ",".join(t.llm_via[:3]))
    if t.source != "bot_tools":
        why.append(f"source_not_bot_tools:{t.source}")
    return why


def check_args(decl: dict, args) -> list:
    if not isinstance(args, dict):
        return ["args_not_object"]
    props = decl["parameters"]["properties"]
    why = [f"unknown_arg:{k}" for k in args if k not in props]
    why += [f"missing_arg:{k}" for k in decl["parameters"]["required"] if k not in args]
    for k, v in args.items():
        if k in props:
            want = PY_OF[props[k]["type"]]
            # bool 은 int 의 하위형이다 -- INTEGER 칸에 true 가 들어가면 안 된다
            if (isinstance(v, bool) and props[k]["type"] != "BOOLEAN") or not isinstance(v, want):
                why.append(f"arg_type:{k}:{props[k]['type']}")
    return why


def check_output(out) -> list:
    """walp/se_exec 실행 결과의 꼴. 이것이 도구 출력 스키마다."""
    if not isinstance(out, dict):
        return ["output_not_object"]
    why = []
    if not isinstance(out.get("ok"), bool):
        why.append("output_ok_not_bool")
    elif out["ok"] and not isinstance(out.get("result"), str):
        why.append("output_result_not_str")
    elif not out["ok"]:
        why.append(f"tool_not_ok:{str(out.get('error'))[:80]}")
    if out.get("llm_attempts") != 0:
        why.append(f"llm_attempts:{out.get('llm_attempts')}")
    return why


def execute(name: str, args: dict, timeout: int = 120) -> dict:
    from agentic import mcp_client as MC
    if MC.split_name(name):
        ent = load_registry().get("tools", {}).get(name) or {}
        return MC.run_tool(name, args, expected_sha=ent.get("source_sha"), timeout=timeout)
    from walp import se_router
    return se_router.execute(name, args, timeout=timeout)


INFRA_ERRORS = ("sandbox_not_run", "timeout", "no_output", "server_unavailable", "protocol_unsupported",
                "server_closed", "quarantined", "denied", "unregistered")


def sandbox_execute(name: str, args: dict, timeout: int = 180, runner=None) -> dict:
    """정책 C.1 · D.4: **도구 실행 자체를** sandbox(HEAD 워크트리 · 고삐 · 비밀 변수 없음)에서.
    안에서 `agentic.tools --exec` 가 LLM 차단 실행기로 그 도구를 돌리고 JSON 한 줄을 낸다.

    결과는 실행기 꼴 그대로에 `sandbox` 를 더한다. 판을 못 깔았으면 `sandbox_not_run`(인프라 -- 도구 탓이 아니다).
    **도구는 커밋된 나무를 본다** -- 작업 트리에만 있는 파일은 안 보인다(정책 B.4 · B.5: 기존 클론을 안 쓴다)."""
    if runner is None:
        from sandbox.run import 실행 as runner
    r = runner(["python3", "-m", "agentic.tools", "--exec", name, json.dumps(args, ensure_ascii=False)], 초=timeout)
    meta = {"exit": r.get("끝값"), "ran": bool(r.get("돌았나")), "seconds": r.get("걸린초"),
            "tree": (r.get("판") or "")[:80]}
    if not r.get("돌았나"):
        return {"ok": False, "error": f"sandbox_not_run:{str(r.get('메모', ''))[:60]}", "llm_attempts": 0,
                "sandbox": meta}
    line = next((l for l in reversed((r.get("stdout") or "").splitlines()) if l.startswith('{"exec":')), None)
    if line is None:
        return {"ok": False, "error": f"no_output:exit={r.get('끝값')}", "llm_attempts": 0, "sandbox": meta,
                "stderr_tail": (r.get("stderr") or "")[-300:]}
    try:
        out = json.loads(line)["exec"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"ok": False, "error": "no_output:bad_json", "llm_attempts": 0, "sandbox": meta}
    if not isinstance(out, dict):
        return {"ok": False, "error": "no_output:not_object", "llm_attempts": 0, "sandbox": meta}
    out["sandbox"] = meta
    return out


def broken_reason(out) -> "str | None":
    """이 실패가 **도구 탓**인가(회로 차단기가 셀 것인가). 인프라 실패(판 · 시간 · 서버 연결)는 None."""
    if not isinstance(out, dict):
        return "output_not_object"
    if out.get("llm_attempts"):
        return f"llm_attempts:{out['llm_attempts']}"
    if out.get("ok") is True:
        return None
    err = str(out.get("error", ""))
    if err.startswith(INFRA_ERRORS):
        return None
    return err[:200] or "not_ok"


def probe(name: str, args: dict, expect: str, executor=execute) -> list:
    out = executor(name, args)
    why = check_output(out)
    if not why and expect not in out["result"]:
        why.append("expect_not_found")
    return why


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tools": {}, "rejected": {}}


def register(cfg, L, sink, probes: dict, cat=None, runner=None, head_sha=None,
             src_sha=source_sha) -> dict:
    """후보 전부를 보고 등록부(dict)를 돌려준다. 원장에 TOOL_REGISTERED / TOOL_REJECTED 를 하나씩 남긴다."""
    cat = cat if cat is not None else catalog()
    if runner is None:
        from sandbox.run import 실행 as runner
    reg = {"head_sha": head_sha, "config_sha256": cfg.sha256, "tools": {}, "rejected": {}}
    for t in sorted(cat, key=lambda x: x.name):
        decl, why = to_declaration(t)
        why += authorize(t, cfg)
        pr = probes.get(t.name)
        if not why and pr is None:
            why.append("no_probe")
        if not why:
            why += [f"probe_{w}" for w in check_args(decl, pr.get("args"))]
            if not isinstance(pr.get("expect"), str) or not pr.get("expect"):
                why.append("probe_expect_missing")
        s_sha = src_sha(t.name) if not why else None
        if not why and s_sha is None:
            why.append("no_source")
        if not why:
            r = runner(["python3", "-m", "agentic.tools", "--probe", t.name,
                        json.dumps(pr["args"], ensure_ascii=False), pr["expect"]],
                       초=cfg.budgets["sandbox_seconds"])
            sink.write(f"probe:{t.name}", f"exit={r.get('끝값')}\n{r.get('stdout', '')}\n{r.get('stderr', '')}")
            if not r.get("돌았나"):
                why.append(f"sandbox_not_run:{str(r.get('메모', ''))[:60]}")
            elif r.get("끝값") != 0:
                tail = (r.get("stdout") or "").strip().splitlines()[-1:] or [""]
                why.append(f"probe_failed:exit={r.get('끝값')}:{tail[0][:80]}")
        if why:
            reg["rejected"][t.name] = why
            L.emit("TOOL_REJECTED", "code", {"name": t.name, "kind": t.kind, "reasons": why})
            continue
        entry = {"declaration": decl, "decl_sha": sha(decl), "source_sha": s_sha,
                 "kind": KIND_ALIAS.get(t.kind, t.kind), "probe": pr}
        reg["tools"][t.name] = entry
        L.emit("TOOL_REGISTERED", "code", {"name": t.name, "decl_sha": entry["decl_sha"][:16],
                                           "source_sha": s_sha[:16]})
    return reg


def _main_probe(name, args_json, expect) -> int:
    why = probe(name, json.loads(args_json), expect)
    print(json.dumps({"tool": name, "reasons": why}, ensure_ascii=False))
    return 0 if not why else 1


def _main_exec(name, args_json) -> int:
    """sandbox 안에서 쓰는 것. 실행기 결과를 `{"exec": ...}` 한 줄로. 끝값 0 = 출력 꼴이 맞고 ok · LLM 시도 0."""
    out = execute(name, json.loads(args_json))
    print(json.dumps({"exec": out}, ensure_ascii=False))
    return 0 if check_output(out) == [] else 1


def _main_verify(name) -> int:
    ent = load_registry().get("tools", {}).get(name)
    now = source_sha(name)
    ok = bool(ent) and now is not None and now == ent.get("source_sha")
    print(json.dumps({"tool": name, "registered": bool(ent), "match": ok}))
    return 0 if ok else 1


def _main_register() -> int:
    import secrets
    import time
    from agentic import config as C
    from agentic.ledger import DiagnosticSink, Ledger
    from agentic.run import _head_sha, runs_root
    cfg = C.load()
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-reg-" + secrets.token_hex(3)
    L = Ledger(runs_root() / run_id, run_id)
    sink = DiagnosticSink(L)
    probes = json.loads(PROBES_PATH.read_text(encoding="utf-8"))
    reg = register(cfg, L, sink, probes, head_sha=_head_sha())
    from agentic import mcp_client as MC
    m_ok, m_bad = MC.register(cfg, L, sink, MC.load_servers())
    reg["tools"].update(m_ok)
    reg["rejected"].update(m_bad)
    L.terminal("DONE", "registry_built", f"등록 {len(reg['tools'])} · 거절 {len(reg['rejected'])}")
    REGISTRY_PATH.write_text(json.dumps(reg, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"등록 {len(reg['tools'])}: {', '.join(sorted(reg['tools']))}")
    counts = {}
    for why in reg["rejected"].values():
        k = why[0].split(":")[0]
        counts[k] = counts.get(k, 0) + 1
    print(f"거절 {len(reg['rejected'])}: " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])))
    print(f"HEAD {reg['head_sha']} · 원장 {L.dir}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="agentic 3단계: 도구 선언·검증·등록")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--register", action="store_true")
    g.add_argument("--declarations", action="store_true")
    g.add_argument("--probe", nargs=3, metavar=("NAME", "ARGS_JSON", "EXPECT"))
    g.add_argument("--verify", metavar="NAME")
    g.add_argument("--exec", nargs=2, metavar=("NAME", "ARGS_JSON"))
    a = ap.parse_args(argv)
    if a.probe:
        return _main_probe(*a.probe)
    if a.verify:
        return _main_verify(a.verify)
    if a.exec:
        return _main_exec(*a.exec)
    if a.declarations:
        print(json.dumps([e["declaration"] for e in load_registry()["tools"].values()], ensure_ascii=False, indent=1))
        return 0
    return _main_register()


if __name__ == "__main__":
    sys.exit(main())
