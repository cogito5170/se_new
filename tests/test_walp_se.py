#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP 의 SE 도구 배선 — 목록 · 봉인 채점 · LLM 차단 · 닫힌 실패를 **실제로 돌려** 본다.

기대는 먼저 적는다:
  1. 목록: bot_tools.py 의 `@tool` 수(글자로 따로 센 수)와 AST 목록의 bot_tools 수가 같다. 고정 명령도 실린다.
     쓰기·셸·네트워크 도구는 execute 가 기본으로 거부한다.
  2. 봉인 v2 모음의 sha 가 그대로이고, 지금 라우터로 다시 채점한 수가 기록(route_heldout_v2.json)과 같다 —
     기록 이후 사전을 고쳐 수를 올렸다면 여기서 빨개진다(그러면 새 봉인 모음이 필요하다).
  3. LLM 차단: 자식 환경에서 LLM 호스트 조회는 막히고 **세어진다**, `claude` 는 대역(97)으로 끝난다,
     LLM 키 환경변수는 지워진다. 일반 호스트 조회는 막지 않는다(과차단은 도구를 죽인다).
  4. 닫힌 실패: 절 하나라도 불확실하면 execute 가 **한 번도** 안 불린다. 전부 확실하면 차례로 불린다.
  5. 흔적: 이 검사가 추적 파일을 하나도 안 바꾼다(git status 전후 비교).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import hashlib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
fails: list[str] = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def _status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "-uno"], cwd=REPO, capture_output=True, text=True).stdout


def main() -> int:
    before = _status()
    tmp = tempfile.mkdtemp(prefix="walp-se-")
    os.environ["SE_LEDGER_ROOT"] = tmp
    from walp import se_router, se_tools, front

    print("[1] 목록")
    cat = se_tools.catalog()
    src = open(os.path.join(REPO, "bot_tools.py"), encoding="utf-8").read()
    n_decor = len(re.findall(r"^@tool(?:\(|$)", src, re.M))
    n_bot = sum(t.source == "bot_tools" for t in cat)
    ok(n_decor > 0 and n_bot == n_decor, f"bot_tools 도구 {n_bot} == 글자로 센 @tool {n_decor}")
    ok(sum(t.source == "dispatch" for t in cat) >= 10, "고정 명령 10개 이상")
    names = {t.name for t in cat}
    ok("cmd:!walp" in names, "고정 명령에 !walp 가 있다")
    for t in ("run_shell", "edit_file", "send_email"):
        if t in names:
            r = se_router.execute(t, {})
            ok(str(r.get("error", "")).startswith("denied:"), f"{t} 기본 거부 ({r.get('error')})")
    ok(se_router.execute("없는_도구", {}).get("error") == "unregistered_tool", "목록에 없는 도구 거부")
    # 이름표(KIND_BY_NAME)에 없어도 몸통이 파일을 쓰거나 자식 프로세스를 띄우면 compute 로 통과하지 않는다.
    # 이 셋은 이름표에 없다 — 이름표에 넣어서 초록을 내면 이 검사의 뜻이 사라진다.
    kinds = {t.name: t.kind for t in cat}
    for t, want in (("report_pdf", "write"), ("ruh2_make", "shell"), ("recon_make", "shell")):
        if t in kinds:
            ok(t not in se_tools.KIND_BY_NAME, f"{t} 는 이름표 밖(표지로 갈라야 한다)")
            ok(kinds[t] == want, f"{t} 표지로 {want} ({kinds[t]})")
            ok(str(se_router.execute(t, {}).get("error", "")).startswith("denied:"), f"{t} 기본 거부")
    ok(kinds.get("run_rtl") == "compute", f"대조: 표지 없는 run_rtl 은 compute ({kinds.get('run_rtl')})")

    print("[2] 봉인 v2 채점 재현")
    corp = os.path.join(REPO, "walp", "eval", "tool_corpus_v2.tsv")
    sha = hashlib.sha256(open(corp, "rb").read()).hexdigest()
    ok(sha == "f267f9134b3e302968749171f2fa6f8076b1c3194cb73172a387269c986144fe", "봉인 v2 sha 그대로")
    from walp import eval_router
    rows = [tuple(l.split("\t", 1)) for l in open(corp, encoding="utf-8").read().splitlines() if "\t" in l]
    dic = se_router.load_dict()
    c, _ = eval_router.score(rows, lambda t: se_router.route(t, dic))
    # v0.4: v2 는 D(인자 모양)의 개발 모음이 됐다 — 기록은 route_v2_v04.json(v0.3 은 route_heldout_v2.json)
    rec = json.load(open(os.path.join(REPO, "walp", "eval", "results", "route_v2_v04.json"),
                         encoding="utf-8"))["walp_router"]
    for k in ("tool_ok", "wrong_execution", "rej_ok", "arg_ok"):
        ok(c[k] == rec[k], f"{k} {c[k]} == 기록 {rec[k]}")
    ok(c["tool_ok"] > eval_router.score(rows, lambda t: eval_router.name_only(t, sorted(dic)))[0]["tool_ok"],
       "이름만 기준선보다 낫다")

    print("[3] LLM 차단(자식 프로세스)")
    log = os.path.join(tmp, "nollm.log")
    os.environ["GEMINI_API_KEY"] = "sentinel"   # 부모 환경에 키가 있어도 자식에는 안 넘어가야 한다
    env = se_router.nollm_env(log)
    del os.environ["GEMINI_API_KEY"]
    ok(not any("GEMINI" in k for k in env), "LLM 키 환경변수 제거")
    probe = ("import socket,json\nr={}\n"
             "for h in ('generativelanguage.googleapis.com','api.anthropic.com','localhost'):\n"
             "  try:\n    socket.getaddrinfo(h,443); r[h]='ok'\n"
             "  except Exception as e:\n    r[h]=type(e).__name__\n"
             "print(json.dumps(r))\n")
    p = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=60)
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        r = {}
    ok(r.get("generativelanguage.googleapis.com") not in (None, "ok"), f"Gemini 호스트 차단 ({r})")
    ok(r.get("api.anthropic.com") not in (None, "ok"), "Anthropic 호스트 차단")
    ok(r.get("localhost") == "ok", "일반 호스트는 막지 않는다")
    n_log = len(open(log).read().splitlines()) if os.path.exists(log) else 0
    ok(n_log >= 2, f"막힌 시도가 세어진다 ({n_log})")
    q = subprocess.run(["claude", "-p", "hi"], env=env, capture_output=True, text=True, timeout=30)
    ok(q.returncode == 97, f"claude 대역 종료코드 97 ({q.returncode})")

    print("[4] 닫힌 실패")
    calls = []
    real = se_router.execute
    se_router.execute = lambda tool, args, **kw: calls.append(tool) or {"ok": True, "result": "가짜", "wall_s": 0}
    try:
        out = front.se_tool("CTLE 개념 알려줘 그리고 합성하고 lint 해줘", "test", "test")
        ok(calls == [] and "아무것도" in out, f"불확실한 절이 있으면 한 번도 안 부른다 (calls={calls})")
        # 섞인 경우 — 첫 절은 확실(TOOL), 둘째는 설계가 없어 되물음. 이것이 진짜 닫힌 실패 시험이다
        mixed = "serdes 링크 시뮬 손실 20 db snr 25 db 그리고 합성해줘"
        st = [se_router.route(x)["status"] for x in front._clauses(mixed)]
        ok(st[:1] == ["TOOL"] and "TOOL" not in st[1:], f"섞인 문장 전제: {st}")
        front.se_tool(mixed, "test", "test")
        ok(calls == [], f"확실한 절이 앞에 있어도 뒤가 불확실하면 안 부른다 (calls={calls})")
        out = front.se_tool("오늘 점심 뭐 먹지", "test", "test")
        ok(calls == [], "관계없는 말은 안 부른다")
        # 둘 다 확실한 절 — 라우터가 TOOL 로 보는 문장을 골라 쓴다(먼저 route 로 확인)
        a, b = "serdes 링크 시뮬 손실 20 db snr 25 db", "adc 해상도 스윕 비트 4,5,6"
        if se_router.route(a)["status"] == "TOOL" and se_router.route(b)["status"] == "TOOL":
            front.se_tool(f"{a} 그리고 {b}", "test", "test")
            ok(calls == [se_router.route(a)["tool"], se_router.route(b)["tool"]], f"확실하면 차례로 부른다 ({calls})")
        else:
            ok(False, f"대조 문장이 TOOL 이 아니다: {se_router.route(a)['status']} / {se_router.route(b)['status']}")
    finally:
        se_router.execute = real

    print("[4b] 부작용 도구 — 확인 표 없이는 안 돈다")
    import re as _re
    from walp import discord_cmd as dc
    real_who = dc._누구
    calls2 = []
    real = se_router.execute
    se_router.execute = lambda tool, args, **kw: calls2.append((tool, kw.get("allow_write"))) or {"ok": True, "result": "가짜", "wall_s": 0}
    try:
        dc._누구 = lambda: "alice"
        r = dc.run("!walp 도구 셸에서 이 명령 실행해줘 `echo hi`")
        m = _re.search(r"확인 (\w+)`", r or "")
        ok(bool(m) and calls2 == [], "셸 도구는 고른 뒤 바로 안 돌고 확인 표를 낸다")
        tok = m.group(1) if m else "x"
        ok("관리 채널에서만" in dc.run(f"!walp 확인 {tok}", allow_write=False) and calls2 == [], "공개 채널 확인은 거부")
        dc._누구 = lambda: "mallory"
        ok("요청한 사람만" in dc.run(f"!walp 확인 {tok}") and calls2 == [], "다른 사람의 확인은 거부")
        dc._누구 = lambda: "alice"
        dc.run(f"!walp 확인 {tok}")
        ok(calls2 == [("run_shell", True)], f"본인·관리 채널 확인이면 그 인자 그대로 한 번 돈다 ({calls2})")
        ok("없다" in dc.run(f"!walp 확인 {tok}") and len(calls2) == 1, "같은 표는 두 번 못 쓴다")
        r = dc.run("!walp 도구 GITHUB_TOKEN 값은 abc123-fake 로 .env 에 저장해줘")
        led = open(os.path.join(tmp, "walp_usability.jsonl"), encoding="utf-8").read()
        ok("abc123" not in (r or "") and "abc123" not in led, "비밀 값은 확인 화면·사용성 원장에 안 남는다")
    finally:
        se_router.execute = real
        dc._누구 = real_who

    print("[4c] 봉인 v3(부작용 도구 11종) 채점 재현")
    corp3 = os.path.join(REPO, "walp", "eval", "tool_corpus_v3.tsv")
    ok(hashlib.sha256(open(corp3, "rb").read()).hexdigest().startswith("78c270027c688f71"), "봉인 v3 sha 그대로")
    rows3 = [tuple(l.split("\t", 1)) for l in open(corp3, encoding="utf-8").read().splitlines() if "\t" in l]
    c3, _ = eval_router.score(rows3, lambda t: se_router.route(t, dic))
    rec3 = json.load(open(os.path.join(REPO, "walp", "eval", "results", "route_v3_v04.json"), encoding="utf-8"))["walp_router"]
    for k in ("tool_ok", "wrong_execution", "rej_ok", "arg_ok"):
        ok(c3[k] == rec3[k], f"v3 {k} {c3[k]} == 기록 {rec3[k]}")

    print("[4c'] 봉인 v5 채점 재현 + v0.4 D(인자 모양)")
    corp5 = os.path.join(REPO, "walp", "eval", "tool_corpus_v5.tsv")
    ok(hashlib.sha256(open(corp5, "rb").read()).hexdigest().startswith("9529f18ae5e297b1"), "봉인 v5 sha 그대로")
    rows5 = [tuple(l.split("\t", 1)) for l in open(corp5, encoding="utf-8").read().splitlines() if "\t" in l]
    c5, _ = eval_router.score(rows5, lambda t: se_router.route(t, dic))
    rec5 = json.load(open(os.path.join(REPO, "walp", "eval", "results", "route_v5_v04.json"), encoding="utf-8"))["walp_router"]
    base5 = json.load(open(os.path.join(REPO, "walp", "eval", "results", "route_v5_base_v03.json"), encoding="utf-8"))["walp_router"]
    for k in ("tool_ok", "wrong_execution", "rej_ok", "arg_ok"):
        ok(c5[k] == rec5[k], f"v5 {k} {c5[k]} == 기록 {rec5[k]}")
    ok(c5["wrong_execution"] <= base5["wrong_execution"], f"v5 잘못 실행이 v0.3 보다 안 늘었다 ({c5['wrong_execution']} ≤ {base5['wrong_execution']})")
    # 모양만으로는 실행하지 않는다(모양 점수 < 문턱) — 모양 하나 + 다른 칸 하나, 독립 신호 둘이어야 문턱을 넘는다
    ok(se_router.route("module m(input a, output b); assign b = a; endmodule", dic)["status"] != "TOOL",
       "모양만으로는 실행 안 함: Verilog 한 덩어리")
    # 예외 하나는 v0.3 부터 있다: 사전에 손으로 적은 @arxiv~1.5 가 문턱(1.5)을 혼자 넘는다. D 는 그것을 바꾸지도 더하지도 않는다.
    t = "arXiv 2412.18579"
    ok(se_router.route(t, dic)["status"] == se_router.route(t, dic, use_shape=False)["status"],
       "D 는 논문 번호만 있는 요청의 판정을 바꾸지 않는다(v0.3 손무게 예외 그대로)")
    r = se_router.route('Put "done" into public answer file status.txt', dic)
    ok(r.get("tool") == "write_public_answer" and r.get("args", {}).get("content") == "done", f"남은 따옴표로 필수 칸 채우기 ({r.get('tool')} {r.get('args')})")
    r = se_router.route('`bash scripts/deploy.sh` 가 "Permission denied" 로 죽어. 고쳐질 때까지 자동으로 수리 루프 돌려.', dic)
    ok(r.get("tool") != "edit_file", f"백틱 안 경로는 파일 모양이 아니다 ({r.get('tool')})")
    ok(se_router.route("scripts/tests.sh 파일 좀 보여줘", dic).get("candidates") != ["read_image", "read_pdf"],
       "확장자로 가른다: .sh 에 read_pdf·read_image 가 모양 점수를 받지 않는다")

    print("[4d] 틈 넷(사용자가 코드로 찾음 2026-09-29)")
    from walp import mcp_server
    os.environ.pop("WALP_MCP_ALLOW_TEACH", None)
    ok("닫혀" in mcp_server.call("walp_teach", {"word": "cerulean", "category": "color", "concept": "blue"}),
       "MCP walp_teach 는 기본으로 닫혀 있다")
    seen = {}
    real_run = se_router.subprocess.run

    def spy(*a, **kw):
        seen["input"] = kw.get("input", "")
        raise se_router.subprocess.TimeoutExpired("x", 1)
    se_router.subprocess.run = spy
    try:
        se_router.execute("run_shell", {"command": "echo"}, timeout=1, allow_write=True)
    finally:
        se_router.subprocess.run = real_run
    ok(json.loads(seen.get("input") or "{}").get("allow_write") is True, "allow_write 가 자식 프로세스에 넘어간다")
    from walp import usability
    import hashlib as _h
    ok(usability.누구("12345") != _h.sha256(b"walp:12345").hexdigest()[:12], "호출자 해시에 소금이 쳐져 있다")
    salt = os.path.join(tmp, ".salt")
    ok(os.path.exists(salt) and (os.stat(salt).st_mode & 0o077) == 0, "소금 파일은 원장 옆에 0600 으로")
    ok("도구 9" in open(os.path.join(REPO, "walp", "MCP.md"), encoding="utf-8").read(), "MCP.md 도구 수가 실제(9)와 같다")

    print("[4e] 게스트 차단이 !walp 도구 로 새지 않는다(실측 2026-09-29: 막힌 게스트가 read_file 결과를 받았다)")
    import agent_context
    real_blocked = agent_context.BLOCKED_USER_IDS
    agent_context.BLOCKED_USER_IDS = frozenset(set(real_blocked) | {"guest-999"})
    real_who2 = dc._누구
    dc._누구 = lambda: "guest-999"
    old_env = os.environ.get("GUEST_BLOCKED_USER_IDS")
    os.environ["GUEST_BLOCKED_USER_IDS"] = ",".join(agent_context.BLOCKED_USER_IDS)   # 자식 프로세스도 같은 목록
    try:
        out = dc.run("!walp 도구 walp/README.md 파일 보여줘", allow_write=False) or ""
        ok("Weight-free" not in out and "게스트" in out, f"막힌 게스트는 read_file 을 못 쓴다 ({out[:80]!r})")
        dc._누구 = lambda: "someone-ok"
        out2 = dc.run("!walp 도구 walp/README.md 파일 보여줘", allow_write=False) or ""
        ok("Weight-free" in out2, "막히지 않은 사람은 그대로 읽는다(음성 대조)")
    finally:
        agent_context.BLOCKED_USER_IDS = real_blocked
        dc._누구 = real_who2
        if old_env is None:
            os.environ.pop("GUEST_BLOCKED_USER_IDS", None)
        else:
            os.environ["GUEST_BLOCKED_USER_IDS"] = old_env

    print("[4f] 비밀이 든 상태 파일은 저장소 밖에(실측 2026-09-29: 공개 채널에서 pending.json 의 set_key 값이 읽혔다)")
    from pathlib import Path as _P
    saved = {k: os.environ.pop(k, None) for k in ("SE_LEDGER_ROOT", "WALP_STATE_DIR")}
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = tempfile.mkdtemp(prefix="walp-home-")
    try:
        옛 = _P(REPO) / "walp" / "usability" / "pending.json"
        옛.parent.mkdir(parents=True, exist_ok=True)
        남긴것 = 옛.exists()
        if not 남긴것:
            옛.write_text('{"x": {"steps": [{"args": {"value": "OLD-SECRET"}}]}}', encoding="utf-8")
        pend, salt = _P(front._pending_path()).resolve(), _P(usability._소금경로()).resolve()
        ok(not 옛.exists(), "첫 판 자리의 pending.json 은 지운다")
        ok(REPO not in (str(pend), *map(str, pend.parents)), f"pending 은 저장소 밖 ({pend})")
        ok(REPO not in (str(salt), *map(str, salt.parents)), f"소금은 저장소 밖 ({salt})")
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
        os.environ["HOME"] = old_home or ""

    print("[5] 흔적")
    ok(_status() == before, "추적 파일 변화 없음")
    if fails:
        print(f"\n실패 {len(fails)}: " + " · ".join(fails))
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
