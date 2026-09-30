#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP 대화로 자라기(walp/evolve.py) — 진짜 파서·시뮬로 **대화를 끝까지 돌려** 본다.

사용자(2026-09-30): "사용자와 대화하면서 스스로 발전하는 형태의 최소항부터 구현하자."

기대는 먼저 적는다:
  1. 모르는 말 → 고쳐 말해 받아들여짐 → WALP 가 뜻을 **묻는다** → `네` → 사전에 넣고 처음 말을 다시 돌려 **알아듣는다**
  2. 배운 뒤에는 **다른 문장**에서도 그 말을 알아듣는다(외운 문장이 아니라 낱말을 배웠다)
  3. `아니` → 배우지 않고, 같은 말이 다시 나와도 알아듣지 않는다(버림)
  4. 고쳐 말한 것이 **다른 요청**이면(다른 자리도 바뀌었으면) 묻지 않는다 — 추측 안 함
  5. 쓰기 권한 없는 사람의 `네` 는 증거 1 — 서로 다른 사람 둘이 모여야 넣는다(한 사람이 두 번은 안 된다)
  6. 물은 것이 없을 때의 `네` 는 가로채지 않는다 · 10분 넘은 거부와는 잇지 않는다
  7. 원장에 kind=evolve 로 후보·물음·네·넣음이 남는다
  8. 흔적 없음(학습 사전·원장은 임시 자리)
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
    tmp = tempfile.mkdtemp(prefix="walp-evolve-")
    os.environ.update(WALP_AUTO_EVOLVE="0", SE_LEDGER_ROOT=tmp, WALP_LEARNED=os.path.join(tmp, "learned.csv"), WALP_BUILD=tmp)
    from walp import evolve, front, usability, search_path
    search_path._기본받기json = lambda u: ""            # 사전 찾기는 망 없이(이 시험은 자라기만 본다)
    if not front.ensure_built()[0]:
        print("    건너뜀: WALP 빌드 불가(g++/make)")
        return 0

    def 말(t, who="a", w=True):
        return front.run(t, who, "terminal", seed=3, allow_write=w)

    print("[1] 고쳐 말하기 → 묻기 → 네 → 배움")
    ok("모르는 말" in 말("주홍 컵 찾아줘"), "처음엔 모른다")
    r = 말("빨간 컵 찾아줘")
    ok("알아들음" in r and "'주홍' 라는 말을 **빨강** 뜻으로" in r, "고쳐 말하면 뜻을 묻는다")
    r = 말("네")
    ok("배웠다: '주홍' → 빨강" in r and "알아들음: **빨간 컵 찾기" in r, "네 → 넣고 처음 말을 다시 돌려 알아듣는다")
    print("[2] 다른 문장에서도")
    ok("알아들음: **빨간 상자 찾기" in 말("주홍 상자 찾아줘"), "배운 낱말이 새 문장에서 쓰인다")

    print("[3] 아니 → 버림")
    말("파란 카드 찾아줘, 벽장은 피해서")
    ok("'벽장' 라는 말을 **선반**" in 말("파란 카드 찾아줘, 선반은 피해서"), "벽장 → 선반 을 묻는다")
    ok("배우지 않는다" in 말("아니"), "아니 → 안 배운다")
    ok("모르는 말" in 말("파란 카드 찾아줘, 벽장은 피해서"), "여전히 모른다")
    ok("라는 말을" not in 말("파란 카드 찾아줘, 선반은 피해서"), "버린 후보는 다시 안 묻는다")

    print("[4] 다른 요청이면 묻지 않는다")
    말("다홍 열쇠 찾아줘", who="b")
    r = 말("파란 상자 찾아줘", who="b")                  # 색도 물체도 바뀌었다 — 대입 하나로 같아지지 않는다
    ok("라는 말을" not in r, "색·물체가 다 바뀐 고쳐 말하기에서는 안 묻는다")
    말("선홍 찾아줘", who="b")
    ok("라는 말을" not in 말("빨간 컵 찾아줘", who="b"), "물체가 빠진 말과는 맞대지 않는다(대입해도 같아지지 않음)")

    print("[5] 권한 없는 사람: 서로 다른 둘")
    말("먹색 컵 찾아줘", who="c", w=False)
    말("검은 컵 찾아줘", who="c", w=False)
    r = 말("네", who="c", w=False)
    ok("사람 1/2" in r, f"한 사람의 네는 증거 1 ({r[:60]!r})")
    말("먹색 컵 찾아줘", who="c", w=False)
    r = 말("검은 컵 찾아줘", who="c", w=False)
    말("네", who="c", w=False)
    ok("모르는 말" in 말("먹색 상자 찾아줘", who="c", w=False), "같은 사람이 두 번 해도 안 넣는다")
    말("먹색 컵 찾아줘", who="d", w=False)
    ok("라는 말을" in 말("검은 컵 찾아줘", who="d", w=False), "다른 사람에게도 묻는다(후보가 있으니)")
    r = 말("네", who="d", w=False)
    ok("배웠다: '먹색' → 검정" in r, f"둘째 사람의 네 → 넣는다 ({r[:60]!r})")

    print("[6] 가로채지 않기 · 창")
    ok("여쭤본 것이 없습니다" in 말("네", who="e"), "물은 것이 없으면 네 는 가로채지 않는다(대화 행위 '네' 로 답한다)")
    d = evolve._읽기()
    d.setdefault("fail", {})[usability.누구("f")] = [{"ts": 0, "text": "고동 컵 찾아줘", "token": "고동"}]
    evolve._쓰기(d)
    ok("라는 말을" not in 말("빨간 컵 찾아줘", who="f"), "10분 넘은 거부와는 잇지 않는다")

    print("[7] 원장")
    zs = [z for z in usability.읽기() if z.get("kind") == "evolve"]
    what = [z["what"] for z in zs]
    ok(all(k in what for k in ("후보", "물음", "네", "넣음", "아니")), f"후보·물음·네·넣음·아니가 남는다 ({sorted(set(what))})")
    ok("대화로 자라기" in front.report() and "주홍→red" in front.report(), "`결과` 에 배운 말이 나온다")
    learned = open(os.environ["WALP_LEARNED"], encoding="utf-8").read()
    ok("주홍,color,red" in learned and "먹색,color,black" in learned and "벽장" not in learned, f"사전: {learned.strip()!r}")

    print("[8] 흔적")
    ok(status() == before, "추적 파일 변화 없음")
    if fails:
        print(f"\n실패 {len(fails)}: " + " · ".join(fails))
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
