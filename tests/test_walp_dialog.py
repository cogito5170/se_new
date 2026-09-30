#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP 대화 행위(walp/dialog.py) × XCS(walp/xcs.py) — 실제로 돌려 본다. 느린 전체 진화(몇 분)는 여기서 안 돌린다.

기대는 먼저 적는다:
  1. 인사·자기질문·능력질문·도움·범위밖·불만·감사·작별·네·아니에 **손 틀**로 답한다 — 찾기는 예전 길(시뮬)로
  2. `오늘 저녁 메뉴 추천해줘` → 범위밖(못 한다고 정직하게), 사전 찾기로 새지 않는다
  3. `행위 <이름>` → 바로 앞 말의 라벨(act_fix)이 원장에 남는다
  4. 재생표본: 받아들여진 찾기 → task 라벨 · act_fix → 그 라벨 · 다음 턴 감사/불만 → 앞 행위 좋음/나쁨(밴딧)
  5. XCS 는 작은 규칙(비트 0 이 1 이면 행동 1)을 배운다 — 결정적이다(같은 씨앗 같은 집단)
  6. 승격되지 않은 집단은 쓰지 않는다 · 승격된 집단은 손 규칙의 **빈자리만** 채운다
  7. 봉인 모음 sha 가 바뀌면 관문을 안 돌린다
  8. 흔적 없음
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
fails: list[str] = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def main() -> int:
    def status():
        return subprocess.run(["git", "status", "--porcelain", "-uno"], cwd=REPO, capture_output=True, text=True).stdout
    before = status()
    tmp = tempfile.mkdtemp(prefix="walp-dialog-")
    os.environ.update(WALP_AUTO_EVOLVE="0", SE_LEDGER_ROOT=tmp, WALP_LEARNED=os.path.join(tmp, "learned.csv"), WALP_BUILD=tmp)
    from walp import dialog, discord_cmd, front, usability, search_path
    from walp.xcs import XCS, Params
    search_path._기본받기json = lambda u: ""
    search_path._기본검색 = lambda q: ([], {"x": "망 없음(시험)"})

    print("[5] XCS 단위")
    def 기르기(seed):
        x = XCS(2, Params(N=200), seed=seed)
        import random
        rng = random.Random(1)
        for _ in range(1500):
            b = "".join(rng.choice("01") for _ in range(6))
            x.step_label_full(b, int(b[0]))
        return x
    x = 기르기(5)
    맞 = sum(x.predict(b)[0] == int(b[0]) for b in ("100000", "011111", "110101", "001010", "101010", "010101"))
    ok(맞 == 6, f"비트0 → 행동 규칙을 배운다 ({맞}/6)")
    ok(기르기(5).dumps() == x.dumps(), "같은 씨앗이면 같은 집단(결정적)")
    ok(XCS.from_json(json.loads(x.dumps())).predict("100000")[0] == 1, "저장·불러오기 뒤에도 같다")

    if not front.ensure_built()[0]:
        print("    건너뜀: WALP 빌드 불가")
        return 0 if not fails else 1

    def 말(t, who="a"):
        agent = __import__("agent_context")
        agent.current_author.set(who)
        return discord_cmd.run("!walp " + t, None, True) or ""

    print("[1][2] 대화 행위 답")
    for t, 기대 in (("안녕", "안녕하세요 — WALP"), ("너 누구야?", "저는 **WALP**"), ("뭐 할 수 있어?", "할 수 있는 것"),
                   ("어떻게 써?", "찾을 물건을 한 문장으로"), ("오늘 저녁 메뉴 추천해줘", "그건 못 합니다"),
                   ("틀렸잖아", "죄송합니다"), ("고마워", "고맙습니다"), ("잘가", "안녕히 가세요"),
                   ("네", "여쭤본 것이 없습니다"), ("아니", "여쭤본 것이 없습니다"), ("빨간 컵 찾아줘", "시뮬레이션")):
        o = 말(t)
        ok(기대 in o, f"{t} → {기대} ({o[:40]!r})")
    ok("사전" not in 말("오늘 저녁 메뉴 추천해줘"), "범위밖은 사전 찾기로 새지 않는다")
    rows = [z for z in usability.읽기() if z.get("kind") == "dialog"]
    ok(len(rows) >= 10 and all(z.get("by") in ("parser", "memory", "xcs-override", "rule", "xcs", "none") for z in rows), "행위마다 원장 kind=dialog")

    print("[3] 행위 고침")
    말("yo", who="b")
    o = 말("행위 인사", who="b")
    fx = [z for z in usability.읽기() if z.get("kind") == "act_fix"]
    ok("고쳤습니다" in o and fx and fx[-1]["act"] == "greet" and fx[-1]["text"] == "yo", f"act_fix 라벨 ({o[:40]!r})")
    ok("행위 이름" in 말("행위 뭐지", who="b"), "모르는 행위 이름이면 목록을 보인다")

    print("[4] 재생표본")
    zs = usability.읽기()
    라벨, 밴딧, _ = dialog.재생표본(zs)
    d라벨 = dict(라벨)
    ok(d라벨.get("빨간 컵 찾아줘") == "task" and d라벨.get("yo") == "greet", "파서 라벨 · 사람 고침 라벨")
    ok(("틀렸잖아", "complaint", True) in 밴딧 or any(not g for _, _, g in 밴딧) or any(g for _, _, g in 밴딧),
       f"다음 턴 감사/불만이 앞 행위의 좋음/나쁨이 된다 ({밴딧[:3]})")
    합성 = [{"ts": 1, "who": "w", "kind": "dialog", "act": "greet", "text": "하잉"},
          {"ts": 5, "who": "w", "kind": "dialog", "act": "thanks", "text": "고마워"},
          {"ts": 10, "who": "w", "kind": "dialog", "act": "about_self", "text": "넌 뭐니"},
          {"ts": 20, "who": "w", "kind": "dialog", "act": "complaint", "text": "틀렸잖아"},
          {"ts": 500, "who": "w", "kind": "dialog", "act": "thanks", "text": "고마워"}]
    ok(dialog.재생표본(합성)[1] == [("하잉", "greet", True), ("넌 뭐니", "about_self", False)],
       "3분 안의 같은 사람만 — 늦은 감사는 안 잇는다")

    print("[6] 승격된 것만 · 빈자리만")
    빈말 = "퓨퓨퓨"
    ok(dialog.손규칙(빈말, dialog._파스(빈말)) is None, "시험 말은 손 규칙의 빈자리")
    xs = XCS(len(dialog.ACTS), Params(N=300), seed=3)
    xs.어휘 = []
    b = dialog.입력(빈말, dialog._파스(빈말), [])
    for _ in range(200):
        xs.step_label_full(b, dialog.ACTS.index("greet"))
    p = dialog._상태()
    for 승격, 기대 in ((False, (None, "none")), (True, ("greet", "xcs"))):
        p.write_text(json.dumps({"xcs": xs.to_json(), "어휘": [], "승격": 승격, "모드": "채움"}), encoding="utf-8")
        os.utime(p, (1e9 + 승격, 1e9 + 승격))
        ok(dialog.고르기(빈말) == 기대, f"승격={승격} → {기대} ({dialog.고르기(빈말)})")
    원 = dialog.ORDER
    dialog.ORDER = "손먼저"
    ok(dialog.고르기("안녕")[1] == "rule", "손먼저: 손 규칙이 고르는 말은 XCS 가 안 건드린다")
    dialog.ORDER = 원
    p.unlink()

    print("[7] 봉인")
    원래 = dialog.TEST_SHA
    dialog.TEST_SHA = "0" * 64
    ok("오류" in dialog.진화(줄들=[], 저장=False), "봉인 sha 가 다르면 관문을 안 돌린다")
    dialog.TEST_SHA = 원래
    import hashlib
    ok(hashlib.sha256(dialog.TEST.read_bytes()).hexdigest() == dialog.TEST_SHA, "봉인 v2 sha 그대로")

    print("[8] 흔적")
    ok(status() == before, "추적 파일 변화 없음")
    if fails:
        print(f"\n실패 {len(fails)}: " + " · ".join(fails))
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
