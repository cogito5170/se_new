#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""행동 기반 WALP(walp/behavior.py) — 구조 검증 V1–V5 를 끄고 켜기로 붙든다(사전등록 walp/eval/PREREG_행동기반.md).

기대는 먼저 적는다:
  V1 행동이 직접 행위를 고른다 — 옛 사슬(dialog.고르기)이 불리면 터지게 해도 버스가 답한다 · L0 의 행위를 바꾸면 말이 바뀐다
  V2 보상이 그 행동의 가치만 바꾼다 — L1 에 보상 → L1 만 변함(L0 바이트 그대로), 반대도
  V3 억제가 실제로 일한다 — 선 이음 → 상위 출력 · 선 끊음 → 하위 출력
  V4 새 행동을 더해도 센서 · L0 을 다시 기르지 않는다 — 더한 뒤 직렬화 바이트 그대로 · 새 행동이 제 조건에서 행한다
  V5 숙고 · 기억을 빼도 L0 이 모든 말에 답한다
  +  저장·불러오기 · 흔적 없음
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
    tmp = tempfile.mkdtemp(prefix="walp-behavior-")
    os.environ.update(WALP_AUTO_EVOLVE="0", SE_LEDGER_ROOT=tmp, WALP_LEARNED=os.path.join(tmp, "learned.csv"), WALP_BUILD=tmp)
    from walp import behavior as B, dialog as D, front
    if not front.ensure_built()[0]:
        print("    건너뜀: WALP 빌드 불가")
        return 0
    표본 = [("안녕", "greet"), ("안녕하세요", "greet"), ("잘가", "bye"), ("고마워", "thanks"), ("너 누구야", "about_self"),
          ("빨간 컵 찾아줘", "task"), ("파란 카드 찾아", "task"), ("뭐 할 수 있어", "capability"), ("틀렸잖아", "complaint"),
          ("네", "yes"), ("아니", "no"), ("오늘 저녁 메뉴 추천해줘", "out_of_scope")]
    센 = B.센서(None, D.어휘기르기([(t, a) for t, a in 표본]))
    l0 = B._L0기르기([(센.읽기(t), a) for t, a in 표본], seed=3, epochs=15)
    # L1: '퓨' 로 시작하는 말에서 L0 이 틀린다는 에피소드 → 묻기를 배운다
    ep = [(B.불확실비트(센.읽기(t), l0.행(센.읽기(t), {})), not t.startswith("퓨")) for t in ["퓨퓨", "퓨웅", "퓨"] * 4 + [t for t, _ in 표본]]
    l1 = B.L1기르기(ep, c=0.3, seed=3, epochs=30)
    체 = {"센서": 센, "반응": l0, "되묻기": l1}

    print("[V1] 행동이 직접 행위를 고른다")
    원 = D.고르기
    D.고르기 = lambda *a, **k: (_ for _ in ()).throw(AssertionError("옛 사슬이 불렸다"))
    bus = B.버스짓기(체)
    try:
        결과 = [bus.돌기(t) for t, _ in 표본]
        ok(all(r["행한것"] for r in 결과), "옛 사슬 없이 모든 말에 답한다")
    except AssertionError as e:
        ok(False, f"옛 사슬이 불렸다: {e}")
    D.고르기 = 원
    r = bus.돌기("잘가")
    ok(r["승자"] == "반응" and B.말(r) == ("틀", D.틀["bye"]), f"L0 이 고른 행위가 곧 말이 된다 ({r['행한것']})")
    class 늘감사:
        def predict(self, x):
            return D.ACTS.index("thanks"), [0] * 12
    진짜 = l0.x
    l0.x = 늘감사()
    r = bus.돌기("잘가")
    ok(B.말(r) == ("틀", D.틀["thanks"]), "L0 의 행위를 바꾸면 말이 바뀐다(뒤에 다른 분류기가 없다)")
    l0.x = 진짜

    print("[V2] 보상이 그 행동의 가치만 바꾼다")
    상 = 센.읽기("안녕")
    o0 = l0.행(상, {})
    a0, a1 = l0.x.dumps(), l1.x.dumps()
    l1.결과(상, o0, True, 0.7)
    ok(l1.x.dumps() != a1 and l0.x.dumps() == a0, "L1 보상 → L1 만 변한다")
    a1 = l1.x.dumps()
    l0.결과(상, "greet", True)
    ok(l0.x.dumps() != a0 and l1.x.dumps() == a1, "L0 보상 → L0 만 변한다")

    print("[V3] 억제")
    r = bus.돌기("퓨퓨")
    ok(r["출력"]["되묻기"] is not None and r["승자"] == "되묻기" and B.말(r)[0] == "되물음", f"선 이음 → 되묻기가 L0 을 대체 ({r['승자']})")
    ok(r["출력"]["반응"] is not None, "억제되어도 L0 은 이 턴에 계산했다(병렬)")
    bus.끊기("되묻기", "반응")
    r = bus.돌기("퓨퓨")
    ok(r["출력"]["되묻기"] is not None and r["승자"] == "반응", f"선 끊음 → L1 이 켜져 있어도 L0 이 말한다 ({r['승자']})")
    bus = B.버스짓기(체)
    r = bus.돌기("선반은 피해서 파란 카드랑 열쇠 찾고, 없으면 검은 컵")
    ok(r["승자"] == "숙고" and B.말(r)[0] == "계획", "숙고가 켜지면 아래 셋을 억제")

    print("[V4] 새 행동을 더해도 다시 기르지 않는다")
    전 = (l0.x.dumps(), json.dumps(센.어휘))
    class 인사층(B.행동):
        이름, 층 = "반가움", 4
        def 행(self, 상태, 아래):
            return {"행위": "greet"} if "반가" in 상태["text"] else None
    bus.더하기(인사층(), 억제={"반응", "되묻기"})
    r = bus.돌기("반가워요 친구")
    ok(r["승자"] == "반가움" and r["행한것"] == {"행위": "greet"}, f"새 행동이 제 조건에서 행한다 ({r['승자']})")
    ok((l0.x.dumps(), json.dumps(센.어휘)) == 전, "센서 · L0 직렬화가 바이트 그대로")
    ok(bus.돌기("잘가")["승자"] == "반응", "새 행동이 꺼져 있으면 아래가 그대로 말한다")

    print("[V5] 숙고·기억 없이도")
    bare = B.버스짓기(체, 숙고켜기=False, 기억켜기=False)
    ok(all(bare.돌기(t)["행한것"] for t in [t for t, _ in 표본] + ["선반은 피해서 파란 카드랑 열쇠 찾고", "아무말"]),
       "L0(+L1) 만으로 모든 말에 답한다")

    print("[+] 저장·불러오기")
    d = B.from_json(json.loads(B.dumps(체)))
    ok(B.dumps(d) == B.dumps(체) and B.버스짓기(d).돌기("잘가")["행한것"] == B.버스짓기(체).돌기("잘가")["행한것"], "같다")

    print("[해석] 자연어 대답 → 선택지")
    for 대답, 선, l0행위, 기대 in (("저에 대한 거요", ["about_self", "greet"], None, "about_self"),
                              ("인사한거야", ["about_self", "greet"], "complaint", "greet"),
                              ("아니 뒤에꺼", ["help", "task"], "no", "task"), ("응 그거", ["help", "task"], "yes", "help"),
                              ("몰라", ["help", "task"], "task", None)):
        ok(B.고른것(대답, 선, l0행위) == 기대, f"{대답!r} ({l0행위}) → {기대}")

    print("[대화] 형식 없이 — 되물음은 자연어 선택지, 대답·불만도 자연어로(실제 대화 길 chat.한마디 로)")
    from walp import chat, usability
    모형 = B.행동모형(체)
    st = D._상태()
    st.parent.mkdir(parents=True, exist_ok=True)
    st.write_text(json.dumps({"학습기": "behavior", "xcs": 모형.to_json(), "어휘": 모형.어휘, "승격": True, "모드": "채움"}),
                  encoding="utf-8")
    D._실행집단["mtime"] = None
    ok(getattr(D.승격된집단()[0], "kind", "") == "behavior", "승격된 행동 모형을 읽는다")
    o = chat.한마디("퓨퓨", who="n")
    ok("어느 쪽이신가요" in o or "이신가요" in o, f"흔들리면 자연어 선택지로 되묻는다 ({o[:70]!r})")
    ok("행위 <이름>" not in o and "`네`" not in o, "형식을 요구하지 않는다")
    선 = [z for z in usability.읽기() if z.get("kind") == "behavior"][-1]["선택지"]
    o = chat.한마디("네", who="n")          # 작은 시험 L0 이 배운 꼴(학습 12문장) — 실제 L0 은 모음 1300여 문장의 네·아니 꼴로 읽는다
    fx = [z for z in usability.읽기() if z.get("kind") == "act_fix"]
    ok(fx and fx[-1]["text"] == "퓨퓨" and fx[-1]["act"] == 선[0] and fx[-1].get("via") == "natural",
       f"'네' → 첫째 선택지({선[0]})를 원래 말의 라벨로 남긴다")
    ok("이신가요" not in o, f"풀렸으면 그 행위로 답한다 ({o[:50]!r})")
    D._기억캐시["key"] = None
    r = B.버스짓기(체).돌기("퓨퓨")
    ok(r["승자"] == "기억" and r["행한것"]["행위"] == 선[0], f"같은 말은 다음부터 기억 층이 억제하고 답한다 ({r['승자']})")
    chat.한마디("잘가", who="m")
    o = chat.한마디("틀렸잖아", who="m")
    ok("잘못 알아들었나 봐요" in o, f"답한 뒤 자연어 불만 → 다음 후보로 다시 묻는다 ({o[:60]!r})")
    끝 = [z for z in usability.읽기() if z.get("kind") == "behavior"][-1]
    ok(끝.get("글") == "잘가" and "bye" not in 끝.get("선택지", []), "틀렸던 행위는 빼고 묻는다")
    print("[가르침] 선택지에 없는 뜻 → 가르쳐 달라 → 그 말을 답으로 배운다(행동 하나가 는다)")
    전 = (l0.x.dumps(), l1.x.dumps())
    o = chat.한마디("퓨웅", who="t")
    ok("이신가요" in o, f"흔들리면 되묻는다 ({o[:40]!r})")
    o = chat.한마디("둘 다 아니야, 심심하다는 거였어", who="t")
    ok("처음 듣는 뜻" in o, f"둘 다 아니면 가르쳐 달라고 한다 ({o[:50]!r})")
    o = chat.한마디("심심하면 저랑 물건 찾기 놀이 해요", who="t")
    새 = [z for z in usability.읽기() if z.get("kind") == "act_new"]
    ok("배웠습니다" in o and 새 and 새[-1]["text"] == "퓨웅" and 새[-1]["답"] == "심심하면 저랑 물건 찾기 놀이 해요",
       f"가르친 말을 새 행위의 답으로 남긴다 ({o[:40]!r})")
    o = chat.한마디("퓨웅~", who="t")
    ok("물건 찾기 놀이" in o, f"같은 꼴의 말에 배운 답을 한다 ({o[:40]!r})")
    ok((l0.x.dumps(), l1.x.dumps()) == 전, "V4: 새 행위가 늘어도 L0 · L1 은 바이트 그대로")
    ok("물건 찾기 놀이" not in chat.한마디("잘가", who="t"), "닮지 않은 말은 가로채지 않는다")
    o1 = chat.한마디("퓨웅!", who="t")
    o2 = chat.한마디("틀렸잖아", who="t")
    ok("물건 찾기 놀이" in o1, f"답한 뒤라도 배운 뜻의 말은 불만으로 가로채지 않는다 ({o1[:30]!r})")
    뜻 = B.뜻들읽기(usability.읽기(), usability.누구("t") if hasattr(usability, "누구") else "t")
    ok(뜻 and 뜻[-1].θ > B.TEACH_θ, f"배운 답 뒤 불만 → 그 행위의 문턱을 올린다 ({[f.θ for f in 뜻]})")
    합성 = [{"ts": 1, "who": "p1", "kind": "act_new", "id": "x1", "text": "퓨퓨퓨", "답": "안", "w": False}]
    ok(B.뜻들읽기(합성, "p1") and not B.뜻들읽기(합성, "p2"), "쓰기 권한 없이 가르친 것은 가르친 사람에게만")
    ok(B.포함률("퓨웅~", "퓨웅") == 1.0 and B.포함률("잘가", "퓨웅") == 0.0, "포함률")

    st.unlink()
    D._실행집단["mtime"] = None

    print("[+] 흔적")
    ok(status() == before, "추적 파일 변화 없음")
    if fails:
        print(f"\n실패 {len(fails)}: " + " · ".join(fails))
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
