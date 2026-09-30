#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP 숙고기(walp/strips.py) — 저자 예문(봉인 계획 모음과 별개)으로 계획을 붙잡고, 대화 길에서 실제로 돌린다.

기대는 먼저 적는다:
  1. 차례(랑·그리고·then) · 우발(없으면·or else) · 공유 피할 곳 · 물건 뒤 색 · 띄어쓰기 없는 말 · 거부(가져와·인사)
  2. 표지를 품은 낱말("파랑" 속 "랑")을 자르지 않는다
  3. 코어가 UTF-8 글자 중간을 자른 출력에도 front.cli 가 죽지 않는다("검정컵없으면파랑컵찾아" — 실측으로 죽던 말)
  4. 대화 길: 여러 걸음 요청 → 계획 → 걸음마다 같은 세계에서 시뮬 → 원장 kind=plan(꼴 포함). 한 걸음 요청은 예전 길 그대로
  5. 우발 가지: 앞 가지가 모두 성공하면 뒤 가지를 안 돌린다 · 실패하면 돌린다
  6. 흔적 없음
"""
from __future__ import annotations

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
    tmp = tempfile.mkdtemp(prefix="walp-strips-")
    os.environ.update(SE_LEDGER_ROOT=tmp, WALP_LEARNED=os.path.join(tmp, "learned.csv"), WALP_BUILD=tmp)
    from walp import chat, front, strips, usability, search_path
    search_path._기본받기json = lambda u: ""

    print("[1][2] 계획")
    for 말, 기대 in (
            ("선반은 피해서 파란 비자카드랑 열쇠 찾고, 없으면 검은 컵",
             "find(card,blue,visa,avoid=shelf) && find(key,avoid=shelf) || find(cup,black,avoid=shelf)"),
            ("빨간 컵 찾아줘", "find(cup,red)"),
            ("컵이랑 열쇠 찾아줘", "find(cup) && find(key)"),
            ("find the blue card, then the red key", "find(card,blue) && find(key,red)"),
            ("카드 파란거 찾아줘", "find(card,blue)"),
            ("초록 컵 없으면 아무 컵이나", "find(cup,green) || find(cup)"),
            ("책상이랑 바닥 피해서 검은 상자 찾고 그다음 마스터 카드",
             "find(box,black,avoid=desk+floor) && find(card,master,avoid=desk+floor)"),
            ("red mug or else a black box, avoid the counter", "find(cup,red,avoid=counter) || find(box,black,avoid=counter)"),
            ("검정컵없으면파랑컵찾아", "find(cup,black) || find(cup,blue)"),
            ("빨간상자랑파란열쇠찾아줘", "find(box,red) && find(key,blue)"),
            ("파랑 컵이랑 빨강 상자", "find(cup,blue) && find(box,red)"),
            ("상자 찾아서 가져와", "REJECT"),
            ("안녕하세요", "REJECT")):
        got = strips.계획(말)
        ok(strips.정규(got) == strips.정규(기대), f"{말} → {got}")
    ok(strips.꼴("find(card,blue,visa,avoid=shelf) && find(key) || find(cup,black)")
       == "find(o,c,b,avoid) && find(o) || find(o,c)", "계획의 꼴(삼각 표처럼 값을 지운 모양)")

    if not front.ensure_built()[0]:
        print("    건너뜀: WALP 빌드 불가")
        return 0 if not fails else 1

    print("[3] UTF-8 중간 자름에 안 죽는다")
    r = front.cli("parse", "검정컵없으면파랑컵찾아")
    ok(isinstance(r, dict) and "status" in r, f"front.cli 가 dict 를 돌려준다 ({str(r)[:60]})")

    print("[4] 대화 길")
    o = chat.한마디("선반은 피해서 파란 비자카드랑 열쇠 찾고, 없으면 검은 컵", who="p")
    ok("여러 걸음으로 알아들음" in o and "1. 파란 비자 카드 찾기" in o, f"계획하고 걸음마다 시뮬 ({o[:60]!r})")
    zs = [z for z in usability.읽기() if z.get("kind") == "plan"]
    ok(zs and zs[-1]["꼴"] == "find(o,c,b,avoid) && find(o,avoid) || find(o,c,avoid)" and zs[-1]["plan"].count("find(") == 3,
       "원장 kind=plan · 꼴")
    o1 = chat.한마디("빨간 컵 찾아줘", who="p")
    ok("여러 걸음" not in o1 and "알아들음: **빨간 컵 찾기" in o1, "한 걸음 요청은 예전 길")

    print("[5] 우발 가지")
    돈 = []
    기록, 성공 = strips.실행("find(cup) || find(box)", lambda 말: (돈.append(말) or 말, True))
    ok(성공 and 돈 == ["컵 찾아줘"], "앞 가지 성공 → 뒤 가지 안 돈다")
    돈.clear()
    기록, 성공 = strips.실행("find(cup) && find(key) || find(box)", lambda 말: (돈.append(말) or 말, "열쇠" not in 말))
    ok(성공 and 돈 == ["컵 찾아줘", "열쇠 찾아줘", "상자 찾아줘"], f"앞 가지 실패 → 뒤 가지 ({돈})")

    print("[6] 흔적")
    ok(status() == before, "추적 파일 변화 없음")
    if fails:
        print(f"\n실패 {len(fails)}: " + " · ".join(fails))
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
