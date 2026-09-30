#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP 대화로 자라기 네 가지(사용자 2026-09-30 "네 가지 다 진행해") — 실제로 돌려 본다.

기대는 먼저 적는다:
  1. 사례 기억: 권한 있는 사람이 `행위 작별` 로 고치면 **같은 말은 곧바로** 작별로 답한다 — 손 규칙(인사)보다 앞선다.
     비슷한 말(글자조각 자카드 ≥0.75)도. 권한 없는 한 사람의 고침은 모두의 답을 안 바꾸고, 서로 다른 둘이면 바꾼다.
  2. 덮기 모드: 승격된 XCS 가 '덮기' 이고 아주 확신하면 손 규칙을 덮는다. '채움' 이면 손 규칙이 고른 말은 안 건드린다.
  3. 저절로 진화: 새 신호(고침 · 다음 턴 감사/불만)가 AUTO_N 개면 배경 진화를 **한 번** 띄운다(돌고 있으면 안 띄움).
     관문 결과는 사람마다 **한 번만** 알린다.
  4b. 같은 봉인 모음을 되풀이해 보면 유의수준이 α_k=0.05·(6/π²)/k² 로 줄어든다(거짓 승격 합 ≤ 0.05)
  4. 사용자 관문: 사람이 고친 말의 1/3 은 학습에서 빠지고 관문용으로 간다(결정적). 관문은 거기서 손만보다 나빠지면 승격을 막는다.
  5. 흔적 없음
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

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
    tmp = tempfile.mkdtemp(prefix="walp-grow-")
    os.environ.update(WALP_AUTO_EVOLVE="0", SE_LEDGER_ROOT=tmp, WALP_LEARNED=os.path.join(tmp, "learned.csv"), WALP_BUILD=tmp)
    from walp import chat, dialog, front, usability, search_path
    from walp.xcs import XCS, Params
    search_path._기본받기json = lambda u: ""
    if not front.ensure_built()[0]:
        print("    건너뜀: WALP 빌드 불가")
        return 0

    def 말(t, who="a", w=True):
        return chat.한마디(t, who=who, via="test", allow_write=w)

    print("[1] 사례 기억")
    작별 = "이만 가볼게요 안녕히 계세요"
    ok("안녕하세요 — WALP" in 말(작별), "고치기 전: 손 규칙은 인사로 읽는다")
    o = 말("행위 작별")
    ok("지금부터" in o, f"권한 있는 고침 → 곧바로 ({o[:50]!r})")
    ok("안녕히 가세요" in 말(작별, who="z"), "같은 말 → 작별(다른 사람에게도)")
    ok(dialog.고르기("이만 가볼게요! 안녕히 계세요~")[0] == "bye", "비슷한 말도 작별(자카드)")
    ok(dialog.고르기("안녕")[0] == "greet", "짧은 다른 말은 안 건드린다")
    말("ㅂ2ㅂ2", who="n1", w=False)
    o = 말("행위 작별", who="n1", w=False)
    ok("다른 한 분이" in o and dialog.고르기("ㅂ2ㅂ2")[1] != "memory", "권한 없는 한 사람 → 아직 안 바뀐다")
    말("ㅂ2ㅂ2", who="n2", w=False)
    말("행위 작별", who="n2", w=False)
    ok(dialog.고르기("ㅂ2ㅂ2") == ("bye", "memory"), "서로 다른 둘 → 바뀐다")

    print("[2] 덮기 · 채움")
    글 = "안녕 난 이제 퇴근한다"                            # 손 규칙: 인사
    ok(dialog.손규칙(글, dialog._파스(글)) == "greet", "시험 말은 손 규칙이 인사로 고른다")
    xs = XCS(len(dialog.ACTS), Params(N=300), seed=3)
    xs.어휘 = []
    b = dialog.입력(글, dialog._파스(글), [])
    for _ in range(300):
        xs.step_label_full(b, dialog.ACTS.index("bye"))
    ok(dialog.xcs_예측(xs, 글)[1] >= dialog.CONF_OVR, "XCS 가 아주 확신한다")
    p = dialog._상태()
    dialog.ORDER = "손먼저"                                   # 이 칸은 손먼저에서 채움 · 덮기를 가른다(학습기먼저는 [9])
    for i, (모드, 기대) in enumerate((("채움", ("greet", "rule")), ("덮기", ("bye", "xcs-override")))):
        p.write_text(json.dumps({"xcs": xs.to_json(), "어휘": [], "승격": True, "모드": 모드}), encoding="utf-8")
        os.utime(p, (2e9 + i, 2e9 + i))
        ok(dialog.고르기(글) == 기대, f"{모드} → {기대} ({dialog.고르기(글)})")
    p.unlink()
    dialog.ORDER = "학습기먼저"

    print("[3] 저절로 진화 · 알림")
    띄움 = []
    def 가짜띄우기():
        띄움.append(1)
        return os.getpid()                                     # 살아 있는 PID — 잠금이 '도는 중' 으로 읽힌다
    줄 = [{"ts": 1, "kind": "xcs_gate"}] + [{"ts": 10 + i, "kind": "act_fix", "act": "bye", "text": f"t{i}"}
                                           for i in range(dialog.AUTO_N - 1)]
    ok(dialog.자동확인(줄, 가짜띄우기) is None and not 띄움, f"신호 {dialog.AUTO_N - 1}개 → 안 띄운다")
    줄.append({"ts": 99, "kind": "dialog", "act": "complaint", "text": "틀렸잖아"})
    ok(dialog.자동확인(줄, 가짜띄우기) == os.getpid() and len(띄움) == 1, f"{dialog.AUTO_N}개 → 한 번 띄운다")
    ok(dialog.자동확인(줄, 가짜띄우기) is None and len(띄움) == 1, "돌고 있으면(잠금 PID 살아 있음) 또 안 띄운다")
    dialog._잠금().unlink()
    ok(dialog.새신호(줄 + [{"ts": 200, "kind": "xcs_gate"}]) == 0, "관문 뒤에는 새 신호가 0 으로 돌아간다")
    usability.적기({"who": "system", "via": "evolve", "kind": "xcs_gate", "승격": False, "모드": None,
                    "정확도": {"손만": 0.6, "채움": 0.62, "덮기": 0.61}})
    ok("진화를 돌렸습니다" in dialog.알림("h1") and dialog.알림("h1") == "", "관문 결과는 사람마다 한 번만 알린다")
    ok("진화를 돌렸습니다" in 말("안녕", who="h2"), "대화 답 끝에 붙는다")

    print("[4] 사용자 관문")
    고침들 = [{"ts": i, "kind": "act_fix", "act": "bye", "text": f"잘 있어라 {i}번"} for i in range(30)]
    라벨, _, 사용자 = dialog.재생표본(고침들)
    떼 = {t for _, t in 사용자}
    ok(0 < len(사용자) < 30 and not (떼 & {t for t, _ in 라벨}), f"고침 30 → 관문용 {len(사용자)} · 학습과 안 겹친다")
    ok(떼 == {t for _, t in dialog.재생표본(고침들)[2]}, "결정적이다")

    class 늘인사:
        어휘: list = []
        def predict(self, b):
            pa = [None] * len(dialog.ACTS)
            pa[dialog.ACTS.index("greet")] = 1000.0
            return dialog.ACTS.index("greet"), pa
    시험 = [("greet", "퓨퓨퓨")] * 12                          # 손 빈자리를 XCS 가 맞히는 봉인 모음 → 채움이 유의하게 이긴다
    g = dialog.관문(늘인사(), 시험, "task", [])
    ok(g["채움승격"] and g["모드"] in ("채움", "덮기"), f"봉인에서 이기면 승격 ({g['모드']})")
    u = [("bye", "잘 가 퓨퓨")] * 6                             # 사용자 관문: 손만(작별?) vs XCS(인사)
    sh = dialog.손규칙("잘 가 퓨퓨", dialog._파스("잘 가 퓨퓨"))
    g2 = dialog.관문(늘인사(), 시험, "task", u)
    ok(sh == "bye" and g2["모드"] != "덮기", f"사용자 관문에서 손만보다 나빠지는 덮기는 막는다 ({g2['모드']}, 사용자={g2['사용자관문_통과']})")

    print("[4b] 되풀이해 보는 관문 — α 소비")
    ok(sum(dialog.α(k) for k in range(1, 100000)) < 0.05 and dialog.α(3) < dialog.α(2) < dialog.α(1), "α_k 합 < 0.05, 볼수록 엄격")
    적은 = [("greet", "퓨퓨퓨")] * 6                            # 6승 0패: p=0.0156 — 첫 관문(α_1=0.030)은 통과, 셋째(α_3=0.0034)는 못 통과
    ok(dialog.관문(늘인사(), 적은, "task", [], 유의=dialog.α(1))["채움승격"], "첫 관문 α 로는 통과")
    ok(not dialog.관문(늘인사(), 적은, "task", [], 유의=dialog.α(dialog.BASE_LOOKS + 1))["채움승격"],
       "저자가 이미 두 번 본 모음의 셋째 관문에서는 같은 증거로 통과 못 한다")

    print("[6] 학습기 셋(XCS · 성장망 · NB) — 저장·불러오기 · 채움 자리")
    표본 = [(t, a) for a, t in dialog.모음(dialog.TRAINS[0])][:60]
    for kind in ("grow", "nb"):
        m = dialog.학습기_기르기(표본, [], seed=3, kind=kind)
        m2 = (dialog.성장모형 if kind == "grow" else dialog.NB모형).from_json(json.loads(json.dumps(m.to_json())))
        같음 = all(m.예측(t)[0] == m2.예측(t)[0] and abs(m.예측(t)[1] - m2.예측(t)[1]) < 1e-9 for t, _ in 표본[:20])
        ok(같음, f"{kind}: 저장했다 불러와도 같은 답")
        p = dialog._상태()
        p.write_text(json.dumps({"학습기": kind, "xcs": m.to_json(), "어휘": m.어휘, "승격": True, "모드": "채움"}), encoding="utf-8")
        os.utime(p, (3e9 + len(kind), 3e9 + len(kind)))
        x, 모드 = dialog.승격된집단()
        ok(getattr(x, "kind", "") == kind and 모드 == "채움", f"{kind}: 승격 상태를 읽는다")
        빈 = "퓨퓨퓨 뀨"
        a, c = dialog.학습기_예측(x, 빈)
        기대 = (a, "xcs") if a and c >= dialog.CONF / 1000 else (None, "none")
        ok(dialog.고르기(빈) == 기대, f"{kind}: 손 규칙 빈자리를 확신 ≥0.5 일 때만 채운다 ({dialog.고르기(빈)}, c={c:.2f})")
        p.unlink()
    g = dialog.성장모형.만들기(표본, [], seed=3)
    ok(all(isinstance(e, str) for e in g.설명()), f"성장망 단위는 사람이 읽는 조건으로 보인다 ({g.설명()[:3]})")

    print("[7] 실행 관문의 누수 — 학습과 같은 봉인 문장은 뺀다")
    import inspect
    src = inspect.getsource(dialog.진화)
    ok("학습알" in src and "봉인_누수_뺌" in src, "진화() 가 봉인에서 학습 글을 뺀다")
    원 = (dialog.TRAINS, dialog.TEST, dialog.TEST_SHA, dialog.LEARNER)
    import hashlib
    tr = os.path.join(tmp, "tr.tsv")
    te = os.path.join(tmp, "te.tsv")
    open(tr, "w", encoding="utf-8").write("greet\t안녕하십니까\nbye\t다음에봐요\n" * 1)
    open(te, "w", encoding="utf-8").write("greet\t안녕하십니까\nbye\t잘 있어 친구\n")
    dialog.TRAINS, dialog.TEST = [__import__("pathlib").Path(tr)], __import__("pathlib").Path(te)
    dialog.TEST_SHA = hashlib.sha256(open(te, "rb").read()).hexdigest()
    dialog.LEARNER = "nb"
    g = dialog.진화(줄들=[], 저장=False)
    ok(g.get("봉인_누수_뺌") == 1 and g["n"] == 1, f"겹친 한 문장을 빼고 잰다 ({g.get('봉인_누수_뺌')}, n={g.get('n')})")
    dialog.TRAINS, dialog.TEST, dialog.TEST_SHA, dialog.LEARNER = 원

    print("[8] 검사는 배경 진화를 남기지 않는다")
    불림 = []
    원래 = dialog.자동확인
    dialog.자동확인 = lambda *a, **k: 불림.append(1)
    os.environ.pop("WALP_AUTO_EVOLVE", None)
    front._자동진화()
    ok(not 불림, "SE_LEDGER_ROOT 가 서 있으면 기본으로 안 띄운다")
    os.environ["WALP_AUTO_EVOLVE"] = "1"
    front._자동진화()
    ok(불림 == [1], "WALP_AUTO_EVOLVE=1 이면 켠다")
    os.environ["WALP_AUTO_EVOLVE"] = "0"
    dialog.자동확인 = 원래

    print("[9] 층 순서 · ESN")
    class 늘작별:
        kind = "stub"
        어휘: list = []
        def 예측(self, text, r=None):
            return "bye", 0.8
    p = dialog._상태()
    p.write_text("{}", encoding="utf-8")
    원ORDER = dialog.ORDER
    dialog._실행집단.update(mtime=p.stat().st_mtime, x=늘작별(), 모드="채움")
    dialog.ORDER = "손먼저"
    ok(dialog.고르기("안녕") == ("greet", "rule"), "손먼저: 손 규칙이 고른 말은 손 규칙")
    dialog.ORDER = "학습기먼저"
    ok(dialog.고르기("안녕") == ("bye", "xcs"), "학습기먼저: 학습기(확신 ≥0.5)가 먼저")
    ok(dialog.고르기("빨간 컵 찾아줘", {"status": "ok"}) == ("task", "parser"), "학습기먼저라도 파서가 받아들인 말은 찾기")
    dialog.ORDER = 원ORDER
    p.unlink()
    dialog._실행집단.update(mtime=None, x=None, 모드=None)
    em = dialog.성장모형.만들기(표본, [], seed=3, esn=True)
    em2 = dialog.성장모형.from_json(json.loads(json.dumps(em.to_json())))
    ok(em.esn is not None and all(em.예측(t) == em2.예측(t) for t, _ in 표본[:15]), "ESN 곁들인 성장망: 저장·불러오기(저수지는 씨앗으로 다시 짓는다)")

    print("[10] 래칫 — 관문에서 떨어지거나 지금 것보다 못하면 승격본을 지킨다")
    class 고정:
        kind = "stub"
        어휘: list = []
        def __init__(self, 답):
            self.답 = 답
        def 예측(self, text, r=None):
            return self.답.get(text, "task"), 0.9
    봉 = [("greet", "퓨퓨 하나"), ("bye", "퓨퓨 둘"), ("thanks", "퓨퓨 셋")]
    좋은 = 고정({"퓨퓨 하나": "greet", "퓨퓨 둘": "bye", "퓨퓨 셋": "thanks"})
    나쁜 = 고정({"퓨퓨 하나": "greet"})
    ok(dialog.교체할까({"승격": False}, 좋은, None, None, 봉, "task")[0] is False, "관문 미통과 → 안 바꾼다")
    ok(dialog.교체할까({"승격": True, "모드": "채움"}, 좋은, None, None, 봉, "task")[0] is True, "처음 승격 → 바꾼다")
    r = dialog.교체할까({"승격": True, "모드": "채움"}, 나쁜, 좋은, "채움", 봉, "task")
    ok(r[0] is False and r[2] == [0, 2], f"관문은 지났어도 지금 것보다 못하면 → 안 바꾼다 ({r})")
    ok(dialog.교체할까({"승격": True, "모드": "채움"}, 좋은, 나쁜, "채움", 봉, "task")[0] is True, "지금 것보다 나으면 → 바꾼다")
    # 진화() 저장 길: 승격본이 있는데 새 후보가 관문에서 떨어진다 → 상태 파일이 바이트 그대로
    nbm = dialog.학습기_기르기(표본, [], seed=3, kind="nb")
    p = dialog._상태()
    p.write_text(json.dumps({"학습기": "nb", "xcs": nbm.to_json(), "어휘": nbm.어휘, "승격": True, "모드": "채움"}), encoding="utf-8")
    전 = p.read_bytes()
    원 = (dialog.TRAINS, dialog.TEST, dialog.TEST_SHA, dialog.LEARNER)
    tr = os.path.join(tmp, "tr10.tsv")
    te = os.path.join(tmp, "te10.tsv")
    open(tr, "w", encoding="utf-8").write("greet\t안녕하십니까\nbye\t다음에봐요\n")
    open(te, "w", encoding="utf-8").write("greet\t좋은 저녁입니다\nbye\t잘 있어 친구\n")
    dialog.TRAINS, dialog.TEST = [__import__("pathlib").Path(tr)], __import__("pathlib").Path(te)
    dialog.TEST_SHA = hashlib.sha256(open(te, "rb").read()).hexdigest()
    dialog.LEARNER = "nb"
    g = dialog.진화(줄들=[], 저장=True)
    ok(not g["승격"] and g["교체"] is False and p.read_bytes() == 전, f"떨어진 후보 → 승격본 바이트 그대로 ({g.get('래칫')})")
    ok(dialog.승격된집단()[0] is not None, "승격본이 계속 쓰인다")
    끝 = [z for z in usability.읽기() if z.get("kind") == "xcs_gate"][-1]
    ok(끝.get("교체") is False and "그대로" in 끝.get("래칫", ""), "원장에 떨어진 후보의 관문 결과만 남긴다")
    ok("그대로" in dialog.알림("h10"), f"알림도 사실대로 ({dialog.알림('h11')[:60]!r})")
    dialog.TRAINS, dialog.TEST, dialog.TEST_SHA, dialog.LEARNER = 원
    p.unlink()

    print("[11] 래칫 사용자 기준 — 떼어 둔 사람 고침 ≥5 면 그것이 주 기준(PREREG_래칫_사용자기준.md)")
    사 = [("greet", f"퓨퓨 사람 {i}") for i in range(6)]
    사람좋은 = 고정({t: a for a, t in 사 + 봉})
    옛것 = 고정({t: a for a, t in 봉})                       # 봉인은 맞히고 사람 고침은 못 맞힌다
    미 = {"승격": False, "모드": None}                          # 관문(α 유의)은 못 지났다
    r = dialog.교체할까(미, 사람좋은, 옛것, "덮기", 봉, "task", 사)
    ok(r[0] is True and r[3] == "덮기", f"관문 못 지나도 사람 고침에서 이기고 봉인에서 안 지면 → 바꾼다 ({r[1]})")
    r = dialog.교체할까(미, 옛것, 옛것, "덮기", 봉, "task", 사)
    ok(r[0] is False and "이기지 못함" in r[1], "R1: 사람 고침에서 비기면 → 안 바꾼다")
    봉인만틀림 = 고정({t: a for a, t in 사})
    r = dialog.교체할까(미, 봉인만틀림, 옛것, "덮기", 봉, "task", 사)
    ok(r[0] is False and "1%p" in r[1], f"R2: 사람 고침은 이겨도 봉인에서 여유(⌈0.03⌉=1) 넘게 지면 → 안 바꾼다 ({r[1]})")
    손말 = "안녕하세요"
    손답 = dialog.손규칙(손말, dialog._파스(손말))
    ok(손답 == "greet", f"R3 준비: 손 규칙이 {손말!r} 를 맞힌다 ({손답})")
    봉3 = [(손답, 손말)]
    틀림 = 고정({**{t: a for a, t in 사}, 손말: "bye"})
    옛3 = 고정({손말: "bye"})
    r = dialog.교체할까(미, 틀림, 옛3, "덮기", 봉3, "task", 사)
    ok(r[0] is False and "손 규칙보다 못함" in r[1], f"R3: 옛것과 비겨도 손만보다 못하면 → 안 바꾼다 ({r[1]})")
    r = dialog.교체할까(미, 사람좋은, 옛것, "덮기", 봉, "task", 사[:4])
    ok(r[0] is False and "< 5" in r[1], "사람 고침 4개(<5) → 예전 규칙(관문 필요)")
    ok(dialog.교체할까(미, 사람좋은, None, None, 봉, "task", 사)[0] is False, "승격본이 없으면 사람 고침만으로 처음 승격하지 않는다")
    # 진화() 저장 길 — 상태 파일이 실제로 승격 true 로 바뀌는가
    held, i = [], 0
    while len(held) < 6:
        t = f"퓨퓨 고침 {i}"
        if dialog.사용자봉인(t):
            held.append(t)
        i += 1
    줄 = [{"ts": 100 + k, "who": "u", "kind": "act_fix", "act": "greet", "text": t} for k, t in enumerate(held)]
    te_말 = [("greet", "좋은 저녁입니다"), ("bye", "잘 있어 친구")]
    class 저장되는(고정):
        규칙수 = 0
        def to_json(self):
            return {"stub": True}
    새것 = 저장되는({**{t: "greet" for t in held}, **{t: a for a, t in te_말}})
    원 = (dialog.TRAINS, dialog.TEST, dialog.TEST_SHA, dialog.학습기_기르기, dialog.승격된집단)
    dialog.TRAINS, dialog.TEST = [__import__("pathlib").Path(tr)], __import__("pathlib").Path(te)
    dialog.TEST_SHA = hashlib.sha256(open(te, "rb").read()).hexdigest()
    dialog.학습기_기르기 = lambda *a, **k: 새것
    dialog.승격된집단 = lambda: (고정({}), "덮기")
    g = dialog.진화(줄들=줄, 저장=True)
    d = json.loads(p.read_text(encoding="utf-8"))
    ok(g["교체"] is True and d["승격"] is True and d["모드"] == "덮기" and not g["승격"],
       f"관문 미통과여도 사용자 기준으로 상태 파일이 승격 true 로 ({g['래칫']})")
    끝 = [z for z in usability.읽기() if z.get("kind") == "xcs_gate"][-1]
    ok(끝.get("교체") is True and 끝.get("쓰는_모드") == "덮기" and "바꿈" in dialog.알림("h12"), "원장·알림이 바꿨다고 말한다")
    dialog.TRAINS, dialog.TEST, dialog.TEST_SHA, dialog.학습기_기르기, dialog.승격된집단 = 원
    p.unlink()

    print("[5] 흔적")
    ok(status() == before, "추적 파일 변화 없음")
    if fails:
        print(f"\n실패 {len(fails)}: " + " · ".join(fails))
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
