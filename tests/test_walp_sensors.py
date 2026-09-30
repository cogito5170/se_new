#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP 센서(반응 이모지 · 메시지 고침) — 모듈과 **봇의 처리기를 실제로 돌려** 본다.

사용자(2026-09-30): "센서부터 늘려라, 반응 이모지랑 메시지 수정 받게."

이 컨테이너에는 discord 패키지가 없어 봇을 import 할 수 없다. 그래서 글자를 grep 하지 않고,
`discord_bot_server.py` 에서 해당 함수들의 **소스를 AST 로 꺼내 가짜 client·payload 와 함께 실행**한다
(on_message 까지 — `!walp` 에 답한 뒤 연결표에 잇는지).

기대는 먼저 적는다:
  1. `!walp` 요청에 답하면 연결표에 (요청 · 답들 · 사람) 이 잇긴다. `!walp` 가 아닌 답은 안 잇는다
  2. WALP 답에 단 반응만 원장에 한 줄(kind=reaction) — 이모지·극성·본인·늦음. 다른 메시지·봇 자신·다른 채널은 0줄
  3. 반응 빼기는 kind=reaction_remove
  4. 요청 글을 고치면 kind=edit(새 글). 글이 안 바뀐 수정(미리보기)·같은 고침 두 번은 한 줄만. 봇 글·남의 메시지는 0줄
  5. 모르는 이모지는 극성 0(추측 안 함), 변이 선택자(FE0F) 유무는 같게
  6. `!walp 결과` 집계에 반응·고침 수가 나온다
  7. 행동을 안 바꾼다 — 처리기는 아무것도 보내지 않는다
  8. 흔적 없음(추적 파일 변화 0)
  9. WALP 전용 서버(사용자 2026-09-30, 1554699881589899334): 그 길드(또는 채널)의 말은 `!walp` 를 안 붙여도
     WALP 가 받는다 · 에이전트로 절대 안 떨어진다 · 길드 필터(GUILD_ID 가 딴 서버)에 안 막힌다 ·
     쓰기는 화이트리스트만 · 그 답에 단 반응도 센다
"""
from __future__ import annotations

import ast
import asyncio
import os
import subprocess
import sys
import tempfile
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
fails: list[str] = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


ADMIN, PUB, OTHER, BOT_ID = 100, 200, 999, 7
WALP_GUILD = 1554699881589899334


class Msg:
    _n = 1000

    def __init__(self, content, author_id=42, channel_id=ADMIN, bot=False):
        Msg._n += 1
        self.id = Msg._n
        self.content = content
        self.author = types.SimpleNamespace(id=author_id, bot=bot)
        self.channel = Chan(channel_id)
        self.guild = None
        self.attachments = []
        self.sent = []

    async def reply(self, t):
        m = Msg(t, author_id=BOT_ID, channel_id=self.channel.id, bot=True)
        self.sent.append(m)
        return m

    async def delete(self):
        pass


class Chan:
    def __init__(self, cid):
        self.id = cid
        self.sent = []

    async def send(self, t=None, **kw):
        m = Msg(t or "", author_id=BOT_ID, channel_id=self.id, bot=True)
        self.sent.append(m)
        return m


def _봇함수들():
    src = open(os.path.join(REPO, "discord_bot_server.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    want = {"쪼개기", "_길게답하기", "_walp_이어두기", "_센서채널", "_walp_반응", "on_raw_reaction_add",
            "on_raw_reaction_remove", "on_raw_message_edit", "on_message", "_walp전용", "_walp_run", "_walp전용답"}
    body = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in want:
            n.decorator_list = []
            body.append(n)
        elif isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("답한도", "최대쪽") for t in n.targets):
            body.append(n)
    got = {n.name for n in body if hasattr(n, "name")}
    return ast.Module(body=body, type_ignores=[]), want - got


def main() -> int:
    def status():
        return subprocess.run(["git", "status", "--porcelain", "-uno"], cwd=REPO, capture_output=True, text=True).stdout
    before = status()
    os.environ["SE_LEDGER_ROOT"] = tempfile.mkdtemp(prefix="walp-sensors-")
    from walp import sensors, usability

    def 줄들():
        return usability.읽기()

    print("[봇 소스에서 처리기 꺼내기]")
    mod, 없음 = _봇함수들()
    ok(not 없음, f"처리기가 다 있다 (없는 것: {sorted(없음)})")
    if 없음:
        print(f"\n실패 {len(fails)}")
        return 1

    dispatched = []

    def fake_run(text, runner=None, may_write=False):
        dispatched.append(text)
        if text.startswith("!walp"):
            return "WALP 답 " + "x" * 2500          # 두 쪽으로 나뉜다 — 쪽마다 잇는지
        if text.startswith("!다른"):
            return "다른 명령 답"
        return None

    ns = {
        "asyncio": asyncio, "GUILD_ID": 0, "ADMIN_CHANNEL_ID": ADMIN, "ADMIN_ALLOWED_USER_IDS": set(), "WALP_ONLY_IDS": set(),
        "main_public": types.SimpleNamespace(PUBLIC_CHANNEL_IDS={PUB}),
        "client": types.SimpleNamespace(user=types.SimpleNamespace(id=BOT_ID)),
        "dispatch": types.SimpleNamespace(run=fake_run, 앞세울것=lambda t: (None, None)),
        "agent_context": types.SimpleNamespace(current_author=types.SimpleNamespace(set=lambda v: None)),
        "relay": types.SimpleNamespace(배경꺼내기=lambda: []),
        "keys": types.SimpleNamespace(PREFIX="!열쇠"),
        "inbox": None, "print": lambda *a, **k: None,
    }

    async def _no(*a, **k):
        raise AssertionError("에이전트로 떨어졌다")
    ns["_handle_admin_message"] = ns["_handle_public_message"] = _no
    exec(compile(mod, "discord_bot_server.py", "exec"), ns)
    run = asyncio.run

    print("[1] !walp 답을 연결표에 잇는다")
    q = Msg("!walp 파란 비자카드 찾아줘")
    run(ns["on_message"](q))
    답들 = q.sent + q.channel.sent
    d = sensors._읽기()
    ok(len(답들) == 2 and all(str(m.id) in d.get("rep", {}) for m in 답들), f"두 쪽 답이 다 이어졌다 ({len(답들)})")
    ok(str(q.id) in d.get("req", {}), "요청이 표에 있다")
    o = Msg("!다른 명령")
    run(ns["on_message"](o))
    ok(not any(str(m.id) in sensors._읽기().get("rep", {}) for m in o.sent), "!walp 가 아닌 답은 안 잇는다")
    ok(len(줄들()) == 0, "잇기만으로는 원장에 안 쓴다")

    def RP(mid, uid=42, emoji="👍", ch=ADMIN):
        return types.SimpleNamespace(message_id=mid, user_id=uid, emoji=emoji, channel_id=ch, guild_id=None)

    print("[2][3] 반응")
    run(ns["on_raw_reaction_add"](RP(답들[0].id)))
    run(ns["on_raw_reaction_add"](RP(답들[1].id, uid=43, emoji="🤔")))
    run(ns["on_raw_reaction_remove"](RP(답들[0].id)))
    zs = 줄들()
    ok([z["kind"] for z in zs] == ["reaction", "reaction", "reaction_remove"], f"세 줄 ({[z['kind'] for z in zs]})")
    ok(zs[0]["emoji"] == "👍" and zs[0]["극성"] == 1 and zs[0]["본인"] is True, "요청한 사람의 👍 → 극성 +1 · 본인")
    ok(zs[1]["극성"] == 0 and zs[1]["본인"] is False, "남의 🤔 → 극성 0(모름) · 본인 아님")
    ok(all(isinstance(z["늦음_s"], (int, float)) and z["늦음_s"] >= 0 for z in zs), "늦음_s 가 있다")
    ok(all(len(z["who"]) == 12 and z["who"] != "42" for z in zs), "사람은 가명으로만")
    n0 = len(zs)
    run(ns["on_raw_reaction_add"](RP(o.sent[0].id)))                   # WALP 답이 아님
    run(ns["on_raw_reaction_add"](RP(q.id)))                           # 요청 메시지 자체
    run(ns["on_raw_reaction_add"](RP(답들[0].id, uid=BOT_ID)))         # 봇 자신
    run(ns["on_raw_reaction_add"](RP(답들[0].id, ch=OTHER)))           # 다른 채널
    ok(len(줄들()) == n0, "WALP 답이 아닌 것 · 봇 자신 · 다른 채널은 0줄")

    print("[4] 고침")

    def EP(mid, content, uid=42, bot=False, ch=ADMIN):
        data = {"id": str(mid), "author": {"id": str(uid), "bot": bot}}
        if content is not None:
            data["content"] = content
        return types.SimpleNamespace(message_id=mid, channel_id=ch, guild_id=None, data=data)

    run(ns["on_raw_message_edit"](EP(q.id, "!walp 파란 비자카드 찾아줘")))   # 글 그대로(미리보기 붙기)
    run(ns["on_raw_message_edit"](EP(q.id, None)))                        # 글 없는 수정
    ok(len(줄들()) == n0, "글이 안 바뀐 수정은 0줄")
    run(ns["on_raw_message_edit"](EP(q.id, "!walp 파란 비자카드 찾아줘, 선반은 피해서")))
    run(ns["on_raw_message_edit"](EP(q.id, "!walp 파란 비자카드 찾아줘, 선반은 피해서")))
    zs = 줄들()
    ok(len(zs) == n0 + 1 and zs[-1]["kind"] == "edit", "같은 고침 두 번 → 한 줄")
    ok(zs[-1]["text"].endswith("선반은 피해서") and zs[-1]["walp"] is True and zs[-1]["본인"] is True, "새 글 · walp · 본인")
    run(ns["on_raw_message_edit"](EP(o.id, "!다른 명령 고침")))
    run(ns["on_raw_message_edit"](EP(답들[0].id, "봇 글", uid=BOT_ID, bot=True)))
    ok(len(줄들()) == n0 + 1, "WALP 요청이 아닌 메시지 · 봇 글은 0줄")

    print("[5] 극성 표")
    ok(sensors.극성("❤️") == 1 and sensors.극성("❤") == 1 and sensors.극성("👎") == -1 and sensors.극성("<:custom:123>") == 0,
       "FE0F 유무 같게 · 모르는 것(사용자 정의 이모지)은 0")

    print("[6] 집계")
    s = usability.집계(줄들())
    ok(s["반응"]["n"] == 2 and s["반응"]["뺌"] == 1 and s["반응"]["+"] == 1 and s["반응"]["모름"] == 1 and s["고침"]["n"] == 1,
       f"반응·고침이 센다 ({s['반응']}, {s['고침']})")
    ok("답에 단 반응 2" in usability.보고(s), "보고에 나온다")

    print("[7] 행동을 안 바꾼다")
    ok(len(q.sent) + len(q.channel.sent) == 2 and dispatched.count("!walp 파란 비자카드 찾아줘") == 1,
       "처리기는 아무것도 보내지 않고, 고친 요청을 다시 돌리지 않는다")

    print("[9] WALP 전용 서버")
    호출 = []
    ns["_walp_run"] = lambda 본문, w: (호출.append((본문, w)) or "WALP: " + 본문)
    ns["GUILD_ID"] = 555                                   # 딴 서버로 길드 필터가 켜져 있어도
    ns["WALP_ONLY_IDS"] = {WALP_GUILD}
    ns["ADMIN_ALLOWED_USER_IDS"] = {42}
    m = Msg("파란 비자카드 찾아줘", author_id=43, channel_id=31337)
    m.guild = types.SimpleNamespace(id=WALP_GUILD)
    n_disp = len(dispatched)
    run(ns["on_message"](m))
    ok(호출 == [("!walp 파란 비자카드 찾아줘", False)], f"접두사 없이도 WALP · 화이트리스트 밖은 쓰기 불가 ({호출})")
    ok(len(dispatched) == n_disp, "고정 명령 표(dispatch)도 안 거친다 — WALP 만")
    m2 = Msg("!walp 가르치기 vermilion color red", author_id=42, channel_id=31337)
    m2.guild = types.SimpleNamespace(id=WALP_GUILD)
    run(ns["on_message"](m2))
    ok(호출[-1] == ("!walp 가르치기 vermilion color red", True), "이미 붙은 !walp 는 두 번 안 붙이고, 화이트리스트는 쓸 수 있다")
    ns["ADMIN_ALLOWED_USER_IDS"] = set()
    run(ns["on_message"](m2))
    ok(호출[-1][1] is False, "화이트리스트가 비면 아무도 못 쓴다")
    ns["_walp_run"] = lambda 본문, w: None
    m3 = Msg("에이전트: 코드 고쳐줘", channel_id=31337)
    m3.guild = types.SimpleNamespace(id=WALP_GUILD)
    run(ns["on_message"](m3))                               # _handle_* 가 불리면 AssertionError 로 터진다
    ok(not m3.sent, "WALP 가 답을 안 내도 에이전트로 안 떨어진다")
    ns["_walp_run"] = lambda 본문, w: "WALP: " + 본문
    m4 = Msg("안녕", channel_id=WALP_GUILD)                  # 채널 id 로 줘도
    m4.guild = types.SimpleNamespace(id=777)
    run(ns["on_message"](m4))
    ok(bool(m4.sent), "채널 id 로 지정해도 된다")
    n1 = len(줄들())
    run(ns["on_raw_reaction_add"](types.SimpleNamespace(message_id=m.sent[0].id, user_id=43, emoji="👎",
                                                        channel_id=31337, guild_id=WALP_GUILD)))
    ok(len(줄들()) == n1 + 1 and 줄들()[-1]["극성"] == -1, "WALP 전용 서버의 답에 단 반응도 센다(길드 필터에 안 막힌다)")

    src = open(os.path.join(REPO, "discord_bot_server.py"), encoding="utf-8").read()
    asg = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)
           and any(getattr(t, "id", "") == "WALP_ONLY_IDS" for t in n.targets)]
    for env, want in (({}, {WALP_GUILD}), ({"WALP_ONLY_IDS": "11, 22,x"}, {WALP_GUILD, 11, 22})):
        g = {"os": types.SimpleNamespace(getenv=lambda k, d="", e=env: e.get(k, d))}
        exec(compile(ast.Module(body=asg, type_ignores=[]), "bot", "exec"), g)
        ok(g.get("WALP_ONLY_IDS") == want, f"봇의 실제 기본값 · 환경 더하기 ({g.get('WALP_ONLY_IDS')})")
    r = ns["_walp_run"]
    exec(compile(ast.Module(body=[n for n in mod.body if getattr(n, "name", "") == "_walp_run"], type_ignores=[]), "bot", "exec"), ns)
    진짜 = ns["_walp_run"]("!walp 도움", False)
    ns["_walp_run"] = r
    ok("WALP" in (진짜 or ""), "진짜 _walp_run 이 discord_cmd 에 닿는다")

    print("[8] 흔적")
    ok(status() == before, "추적 파일 변화 없음")
    if fails:
        print(f"\n실패 {len(fails)}: " + " · ".join(fails))
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
