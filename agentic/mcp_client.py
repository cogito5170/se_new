"""MCP 클라이언트(안쪽) -- 정책 A.4 · A.5 와 D 를 MCP 도구에.

`walp/docs/MCP.md` 가 설계만 해 두고 안 지은 자리다. 표준 라이브러리만 쓰는 stdio JSON-RPC 2.0 클라이언트.

**버전은 세 갈래로 따로, 서버가 실제로 말한 것만**(A.4 · A.5):

    protocol   initialize 응답의 protocolVersion(협상된 값). 없으면 "unreported"
    server     initialize 응답의 serverInfo.name/version. 없으면 "unreported"
    sdk        이 클라이언트가 쓰는 MCP SDK -- **없다**("none"). 대신 이 파일의 sha256 앞 12자를 client 로 적는다

요청한 프로토콜과 협상된 값이 지원 목록에 없으면 도구를 부르지 않는다(protocol_unsupported).

**등록 규율은 bot_tools 와 같다** -- 서버가 알려 준 도구를 그대로 믿지 않는다:
  · 서버마다 `agentic/mcp_servers.json` 에 **사람이 적은** 허용 목록(도구 · 부작용 종류 · 탐침)이 있다. 없으면 no_probe
  · inputSchema -> Gemini 선언. 배열·객체 인자는 거절(unsupported_param_type)
  · 탐침은 sandbox(HEAD 워크트리)에서 `agentic.mcp_client --probe` 로
  · 등록은 (이름 · 설명 · inputSchema · 서버 이름/버전) 의 해시에 묶는다. 부를 때 다시 나열해 해시가 다르면 격리
  · 서버 프로세스는 LLM 이 막힌 환경(walp/se_router.nollm_env)에서 띄우고 LLM 시도를 센다

Gemini 에 보이는 이름은 `mcp__<서버>__<도구>` 다(영문자·밑줄만 -- 이름 규칙이 기억으로 적은 것이라 가장 보수적인 꼴로).

    python3 -m agentic.mcp_client --versions walp
    python3 -m agentic.mcp_client --list walp
    python3 -m agentic.mcp_client --probe walp <도구> '<인자 JSON>' '<기대 글자>'      # sandbox 안에서
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SERVERS_PATH = ROOT / "agentic" / "mcp_servers.json"
REQUESTED_PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = ("2025-06-18",)
PREFIX = "mcp__"
SCHEMA_MAP = {"string": "STRING", "integer": "INTEGER", "number": "NUMBER", "boolean": "BOOLEAN"}


class MCPError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def client_sha() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]


def gemini_name(server: str, tool: str) -> str:
    return f"{PREFIX}{server}__{tool}"


def split_name(name: str) -> "tuple[str, str] | None":
    if not name.startswith(PREFIX):
        return None
    rest = name[len(PREFIX):]
    if "__" not in rest:
        return None
    s, t = rest.split("__", 1)
    return (s, t) if s and t else None


def load_servers(path: Path = SERVERS_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


class Session:
    """서버 프로세스 하나. 줄 단위 JSON-RPC. 읽기마다 시간 상한."""

    def __init__(self, command: list, timeout: float = 30.0, env=None, cwd=ROOT):
        self.timeout = timeout
        self.proc = subprocess.Popen(list(command), cwd=str(cwd), env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._buf = b""
        self._id = 0
        self.init: dict = {}

    def close(self) -> str:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
        try:
            return (self.proc.stderr.read() or b"").decode("utf-8", "replace")[-4000:]
        except (OSError, ValueError):
            return ""

    def _send(self, obj: dict) -> None:
        try:
            self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise MCPError("server_closed") from None

    def _line(self) -> dict:
        end = time.monotonic() + self.timeout
        fd = self.proc.stdout.fileno()
        while b"\n" not in self._buf:
            left = end - time.monotonic()
            if left <= 0:
                raise MCPError("timeout")
            r, _, _ = select.select([fd], [], [], left)
            if not r:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                raise MCPError("server_closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        try:
            return json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise MCPError("bad_json") from None

    def request(self, method: str, params: "dict | None" = None) -> dict:
        self._id += 1
        mid = self._id
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        while True:
            msg = self._line()
            if msg.get("id") != mid:          # 서버가 보낸 알림 등은 건너뛴다
                continue
            if "error" in msg:
                raise MCPError(f"rpc_error:{(msg['error'] or {}).get('code')}")
            res = msg.get("result")
            if not isinstance(res, dict):
                raise MCPError("result_not_object")
            return res

    def initialize(self) -> dict:
        self.init = self.request("initialize", {
            "protocolVersion": REQUESTED_PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "se-agentic", "version": client_sha()}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self.init

    def versions(self) -> dict:
        si = self.init.get("serverInfo") if isinstance(self.init.get("serverInfo"), dict) else {}
        pv = self.init.get("protocolVersion")
        name, ver = si.get("name"), si.get("version")
        return {"protocol": pv if isinstance(pv, str) and pv else "unreported",
                "requested_protocol": REQUESTED_PROTOCOL,
                "server": f"{name}/{ver}" if isinstance(name, str) and isinstance(ver, str) and name and ver
                          else "unreported",
                "sdk": "none", "client": f"agentic.mcp_client@{client_sha()}"}

    def tools(self) -> list:
        ts = self.request("tools/list").get("tools")
        if not isinstance(ts, list):
            raise MCPError("tools_not_list")
        return [t for t in ts if isinstance(t, dict) and isinstance(t.get("name"), str)]


def _env(log: str):
    from walp import se_router
    return se_router.nollm_env(log)


def open_session(server: str, servers: dict, log: str, timeout: float = 30.0) -> Session:
    spec = servers.get(server)
    if not spec or not isinstance(spec.get("command"), list):
        raise MCPError("server_not_configured")
    s = Session(spec["command"], timeout=timeout, env=_env(log))
    try:
        s.initialize()
    except MCPError:
        s.close()
        raise
    if s.versions()["protocol"] not in SUPPORTED_PROTOCOLS:
        s.close()
        raise MCPError(f"protocol_unsupported:{s.versions()['protocol']}")
    return s


def schema_sha(tool: dict, versions: dict) -> str:
    blob = {"name": tool.get("name"), "description": tool.get("description"),
            "inputSchema": tool.get("inputSchema"), "server": versions.get("server")}
    return hashlib.sha256(json.dumps(blob, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def to_declaration(server: str, tool: dict) -> "tuple[dict | None, list]":
    import re
    why = []
    name = gemini_name(server, tool.get("name", ""))
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
        why.append("name_invalid_for_gemini")
    desc = (tool.get("description") or "").strip()
    if not desc:
        why.append("no_description")
    sch = tool.get("inputSchema") or {}
    if sch.get("type", "object") != "object":
        why.append("input_not_object")
    props, req = {}, [r for r in (sch.get("required") or []) if isinstance(r, str)]
    for k, v in (sch.get("properties") or {}).items():
        t = SCHEMA_MAP.get((v or {}).get("type"))
        if t is None:
            why.append(f"unsupported_param_type:{k}:{(v or {}).get('type')}")
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", k):
            why.append(f"param_name_invalid_for_gemini:{k}")
            continue
        p = {"type": t, "description": k}
        if t == "STRING" and isinstance(v.get("enum"), list) and all(isinstance(x, str) for x in v["enum"]):
            p["enum"] = list(v["enum"])
        props[k] = p
    if why:
        return None, why
    return {"name": name, "description": desc[:1000],
            "parameters": {"type": "OBJECT", "properties": props, "required": [r for r in req if r in props]}}, []


def _attempts(log: str) -> int:
    try:
        n = sum(1 for l in Path(log).read_text().splitlines() if l.strip())
        os.unlink(log)
        return n
    except OSError:
        return 0


def live_sha(name: str, servers: "dict | None" = None, timeout: float = 30.0) -> "str | None":
    """지금 서버가 알려 주는 그 도구의 해시. 못 구하면 None(= 등록과 다름으로 읽힌다)."""
    st = split_name(name)
    if not st:
        return None
    servers = servers if servers is not None else load_servers()
    log = tempfile.mktemp(prefix="agentic-mcp-", suffix=".log")
    try:
        s = open_session(st[0], servers, log, timeout)
    except MCPError:
        return None
    try:
        for t in s.tools():
            if t["name"] == st[1]:
                return schema_sha(t, s.versions())
        return None
    except MCPError:
        return None
    finally:
        s.close()
        _attempts(log)


def execute(name: str, args: dict, servers: "dict | None" = None, expected_sha: "str | None" = None,
            timeout: float = 120.0) -> dict:
    """실행기 꼴(walp/se_router.execute 와 같다): {ok, result|error, llm_attempts, mcp: 버전}."""
    st = split_name(name)
    if not st:
        return {"ok": False, "error": "not_mcp_name", "llm_attempts": 0}
    servers = servers if servers is not None else load_servers()
    log = tempfile.mktemp(prefix="agentic-mcp-", suffix=".log")
    try:
        s = open_session(st[0], servers, log, timeout)
    except MCPError as e:
        return {"ok": False, "error": e.code, "llm_attempts": _attempts(log)}
    ver = s.versions()
    try:
        if expected_sha is not None:
            now = next((schema_sha(t, ver) for t in s.tools() if t["name"] == st[1]), None)
            if now != expected_sha:
                return {"ok": False, "error": "quarantined:schema_changed", "mcp": ver, "llm_attempts": 0}
        res = s.request("tools/call", {"name": st[1], "arguments": dict(args)})
        text = "\n".join(c.get("text", "") for c in (res.get("content") or [])
                         if isinstance(c, dict) and c.get("type") == "text")
        if res.get("isError"):
            return {"ok": False, "error": f"tool_error:{text[:120]}", "mcp": ver, "llm_attempts": 0}
        return {"ok": True, "result": text, "mcp": ver, "llm_attempts": 0}
    except MCPError as e:
        return {"ok": False, "error": e.code, "mcp": ver, "llm_attempts": 0}
    finally:
        s.close()
        n = _attempts(log)
        # finally 의 반환값을 덮어쓰지 않으려고 dict 를 바꾸지 못한다 -- 대신 attempts 는 아래 래퍼가 싣는다
        execute._last_attempts = n                                  # type: ignore[attr-defined]


def run_tool(name: str, args: dict, servers=None, expected_sha=None, timeout: float = 120.0) -> dict:
    out = execute(name, args, servers, expected_sha, timeout)
    out["llm_attempts"] = max(out.get("llm_attempts", 0), getattr(execute, "_last_attempts", 0))
    return out


def register(cfg, L, sink, servers: dict, runner=None, list_fn=None) -> "tuple[dict, dict]":
    """(등록, 거절). 서버마다 나열 -> 허용 목록 대조 -> 선언 -> 권한 -> sandbox 탐침."""
    from agentic import tools as TL
    if runner is None:
        from sandbox.run import 실행 as runner
    ok, bad = {}, {}
    for server in sorted(servers):
        spec = servers[server]
        allow = spec.get("tools") or {}
        try:
            listed, ver = (list_fn or _list_live)(server, servers)
        except MCPError as e:
            for t in allow:
                bad[gemini_name(server, t)] = [f"server_unavailable:{e.code}"]
                L.emit("TOOL_REJECTED", "code", {"name": gemini_name(server, t), "reasons": bad[gemini_name(server, t)]})
            continue
        L.emit("MCP_VERSION", "code", {**ver, "server_key": server, "phase": "register"})
        for t in listed:
            gname = gemini_name(server, t["name"])
            decl, why = to_declaration(server, t)
            a = allow.get(t["name"])
            if a is None:
                why.append("not_in_allowlist")
            else:
                kind = a.get("kind")
                if kind not in cfg.allowed_kinds:
                    why.append(f"kind_not_allowed:{kind}")
                pr = a.get("probe")
                if not why and not isinstance(pr, dict):
                    why.append("no_probe")
                if not why:
                    why += [f"probe_{w}" for w in TL.check_args(decl, pr.get("args"))]
            if not why:
                r = runner([sys.executable or "python3", "-m", "agentic.mcp_client", "--probe", server, t["name"],
                            json.dumps(pr["args"], ensure_ascii=False), pr["expect"]],
                           초=cfg.budgets["sandbox_seconds"])
                sink.write(f"probe:{gname}", f"exit={r.get('끝값')}\n{r.get('stdout', '')}\n{r.get('stderr', '')}")
                if not r.get("돌았나"):
                    why.append(f"sandbox_not_run:{str(r.get('메모', ''))[:60]}")
                elif r.get("끝값") != 0:
                    tail = (r.get("stdout") or "").strip().splitlines()[-1:] or [""]
                    why.append(f"probe_failed:exit={r.get('끝값')}:{tail[0][:80]}")
            if why:
                bad[gname] = why
                L.emit("TOOL_REJECTED", "code", {"name": gname, "reasons": why})
                continue
            ent = {"declaration": decl, "decl_sha": TL.sha(decl), "source_sha": schema_sha(t, ver),
                   "kind": a["kind"], "probe": a["probe"], "via": "mcp", "server": server, "tool": t["name"],
                   "server_version": ver["server"], "protocol": ver["protocol"]}
            ok[gname] = ent
            L.emit("TOOL_REGISTERED", "code", {"name": gname, "decl_sha": ent["decl_sha"][:16],
                                               "source_sha": ent["source_sha"][:16]})
    return ok, bad


def _list_live(server: str, servers: dict) -> "tuple[list, dict]":
    log = tempfile.mktemp(prefix="agentic-mcp-", suffix=".log")
    s = open_session(server, servers, log)
    try:
        return s.tools(), s.versions()
    finally:
        s.close()
        _attempts(log)


def _main_probe(server, tool, args_json, expect) -> int:
    from agentic import tools as TL
    out = run_tool(gemini_name(server, tool), json.loads(args_json))
    why = TL.check_output(out)
    if not why and expect not in out["result"]:
        why.append("expect_not_found")
    print(json.dumps({"tool": tool, "reasons": why, "mcp": out.get("mcp")}, ensure_ascii=False))
    return 0 if not why else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="agentic MCP 클라이언트")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--versions", metavar="SERVER")
    g.add_argument("--list", metavar="SERVER")
    g.add_argument("--probe", nargs=4, metavar=("SERVER", "TOOL", "ARGS_JSON", "EXPECT"))
    a = ap.parse_args(argv)
    if a.probe:
        return _main_probe(*a.probe)
    try:
        tools, ver = _list_live(a.versions or a.list, load_servers())
    except MCPError as e:
        print(json.dumps({"error": e.code}))
        return 1
    print(json.dumps(ver if a.versions else [t["name"] for t in tools], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
