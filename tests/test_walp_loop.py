#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""walp/loop.py — '고리를 도는 것' 이 최상위 행동인가를 **실제로 돌려** 본다(모의 도구, 네트워크 없음).

기대는 먼저 적는다:
  · 정상: 검색(조각) → 읽기(전문)로 칸을 채우고 done. 바퀴 ≤ 4, 호출 ≤ 30
  · 읽기가 전부 막힘(실측 2026-09-29 서브에이전트: WebFetch 가 모든 도메인에서 막혔다):
    모든 칸이 [조각] 에 머물고, 멈추고, 못 채운 칸을 **전부** 적는다. 수준을 올리지 않는다
  · 검색 도구가 '전문' 이라 우겨도 조각으로 자른다(도구 상한)
  · 예산을 절대 넘지 않는다 · 금지 경로 쓰기는 막고, 목표가 그것을 요구하면 REFUSE
  · 기억으로 다 채워지면 ANSWER(도구 0회) · 같은 입력이면 같은 호출열
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from walp.loop import Budget, Evidence, LoopAct, Slot, ToolSpec  # noqa: E402

fails: list[str] = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


SPECS = [ToolSpec("web_search", ("query",), "query", 1), ToolSpec("web_fetch", ("url",), "url", 4, cost=2),
         ToolSpec("write_file", ("path",), "query", 1, writes=True)]


def mock(blocked=False, liar=False):
    calls = []

    def search(a):
        calls.append(("search", a["query"]))
        q = a["query"].replace(" ", "_")
        return {"ok": True, "items": [{"claim": f"snippet {q} {i}", "url": f"https://ex.org/{q}/{i}",
                                       "level": 4 if liar else 1} for i in range(2)]}

    def fetch(a):
        calls.append(("fetch", a["url"]))
        if blocked:
            return {"ok": False, "error": "proxy 403"}
        if a["url"].endswith("/0"):
            return {"ok": False, "error": "404"}       # 첫 URL 은 죽어 있다 — 다음 것을 읽어야 한다
        return {"ok": True, "items": [{"claim": "full text", "url": a["url"], "level": 4}]}

    def write(a):
        calls.append(("write", a["path"]))
        return {"ok": True, "items": []}

    return {"web_search": search, "web_fetch": fetch, "write_file": write}, calls


def slots(n):
    return [Slot(f"s{i}", [f"topic {i}", f"topic {i} review"], 4) for i in range(n)]


def test_loop():
    impl, calls = mock()
    R = LoopAct(SPECS, impl).run(slots(5))
    ok(R.act == "LOOP" and R.stop == "done", f"정상: LOOP 로 돌아 done ({R.stop})")
    ok(R.turns <= 4 and R.calls <= 30, f"바퀴 {R.turns} ≤ 4 · 호출 {R.calls} ≤ 30")
    ok(all(lv == 4 for lv, _ in R.slots.values()) and not R.unverified, "모든 칸 [전문], 못 채운 것 없음")
    ok(any(t[4] == "404" for t in R.trace) and any(u.endswith("/1") for _, us in R.slots.values() for u in us),
       "죽은 URL 뒤에 다음 URL 을 읽었다(같은 URL 을 다시 두드리지 않고)")

    impl, calls = mock(blocked=True)
    R = LoopAct(SPECS, impl).run(slots(5))
    ok(R.stop in ("stalled", "exhausted", "budget_turns"), f"읽기가 막힘: 멈췄다({R.stop})")
    ok(all(lv == 1 for lv, _ in R.slots.values()), "읽기가 막히면 모든 칸이 [조각] 에 머문다 — 올리지 않는다")
    ok(len(R.unverified) == 5 and all("조각 까지만" in why for _, why in R.unverified), "못 채운 칸 다섯을 전부 적는다")
    ok(R.calls <= 30 and R.turns <= 4, "막혀도 예산 안")

    impl, _ = mock(liar=True)
    impl2 = dict(impl)
    impl2["web_fetch"] = lambda a: {"ok": False, "error": "403"}
    R = LoopAct(SPECS, impl2).run(slots(2))
    ok(all(lv == 1 for lv, _ in R.slots.values()), "검색이 '전문' 이라 우겨도 도구 상한(조각)으로 자른다")

    impl, _ = mock()
    R = LoopAct(SPECS, impl, Budget(turns=4, tools=30, per_turn=8)).run(slots(20))
    ok(R.calls <= 30 and R.turns <= 4, f"칸 20개: 호출 {R.calls} ≤ 30 · 바퀴 {R.turns} ≤ 4 — 예산을 안 넘는다")
    ok(R.stop in ("budget_tools", "budget_turns") and R.unverified, "예산으로 멈추면 못 채운 것을 적는다")
    ok(any(why == "budget_per_turn" for *_, why in R.denied), "한 바퀴 묶음 상한(8)이 실제로 걸렸다")

    impl, calls = mock()
    L = LoopAct(SPECS, impl, forbidden=("/home/user/SE",))  # G019: 기계 경로 — 막혀야 할 인자 문자열일 뿐, 파일을 안 만진다
    R = L.run(slots(1), required_writes=["/home/user/SE/walp/x.md"])  # G019: 기계 경로 — 막혀야 할 인자 문자열일 뿐, 파일을 안 만진다
    ok(R.act == "REFUSE" and R.calls == 0 and not calls, "금지 경로 쓰기를 요구하는 목표 → REFUSE, 호출 0")
    R = L.run([Slot("w", ["/home/user/SE/secret"], 1)])  # G019: 기계 경로 — 막혀야 할 인자 문자열일 뿐, 파일을 안 만진다
    ok(any(why.startswith("forbidden") for *_, why in R.denied) and not any(c[0] == "write" for c in calls),
       "인자에 금지 경로가 든 호출은 감독기가 막는다(실행 안 됨)")

    impl, calls = mock()
    L = LoopAct(SPECS, impl)
    L.run(slots(3))
    n = len(calls)
    R = L.run(slots(3))
    ok(R.act == "ANSWER" and R.calls == 0 and len(calls) == n, "기억으로 다 채워지면 ANSWER — 도구 0회")
    mem = [Evidence("s0", "old", "https://ex.org/old", 1, "web_search", 0)]
    R = LoopAct(SPECS, mock()[0], memory=mem).run(slots(1))
    ok(R.act == "LOOP", "기억이 요구 수준(전문)에 못 미치면 LOOP")

    a = LoopAct(SPECS, mock()[0]).run(slots(6))
    b = LoopAct(SPECS, mock()[0]).run(slots(6))
    ok(a.trace == b.trace and a.registry_hash == b.registry_hash, "같은 입력 → 같은 호출열, 같은 도구목록 해시")
    ok(LoopAct(SPECS[:2], mock()[0]).hash != a.registry_hash, "도구목록이 바뀌면 해시가 바뀐다")


def test_walp_campaign():
    if shutil.which("make") is None or shutil.which("g++") is None:
        print("    건너뜀: make/g++ 없음(환경 한정)")
        return
    tmp = tempfile.mkdtemp(prefix="walp-loop-")
    try:
        code = ("import sys; sys.path.insert(0, %r); from walp.loop import walp_campaign; "
                "print(walp_campaign('find the container', k=2))" % REPO)
        env = dict(os.environ, WALP_BUILD=tmp, SE_LEDGER_ROOT=tmp)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600, env=env)
        out = r.stdout
        print("\n".join("      " + l for l in out.splitlines()[:12]))
        ok(r.returncode == 0, "walp_campaign 이 돈다")
        ok("OK type=cup#1" in out and "OK type=box#2" in out, "모호한 명령 → 후보 둘 × 시드 둘, 칸 넷")
        ok("고르지 않았다" in out, "후보 중 하나를 고르지 않는다(사람 몫)")
        ok(not os.listdir(tmp) or all(n != "walp_usability.jsonl" for n in os.listdir(tmp)),
           "고리 안쪽 호출은 사용성 원장에 안 적는다(사람의 말이 아니다)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_loop()
    test_walp_campaign()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nLoopAct 검사 통과")
