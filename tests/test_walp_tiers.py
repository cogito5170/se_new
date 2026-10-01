#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP 세 층(Control · Sequencing · Deliberative) — LLM 앞단(사전등록 walp/eval/PREREG_LLM앞단.md). 실제 LLM 은 안 부른다.

기대는 먼저 적는다:
  1. 모른다(되묻기가 흔들림 · 못 하는 행위)면 숙고층에 묻고 그 답을 말한다 — 부류는 라벨(via=llm), 열린 답은 답 캐시로
  2. 같은 말이 다시 오면 답 캐시가 LLM 없이 답한다(호출 수가 안 는다) · 겉이 덜 닮은 말은 다시 묻는다
  3. 다시 쓴 답 뒤 불만 → 그 답의 문턱이 오른다
  4. 숙고층이 틀 행위(인사 등)라고 하면 WALP 의 틀로 답하고 라벨만 남긴다(답 캐시에 안 넣는다)
  5. 숙고층이 없으면(키 없음) 예전처럼 사람에게 되묻는다 · 오류면 아래 층으로
  6. LLM 라벨은 사람의 고침이 아니다 — 기억 층 · 사용자 관문에 안 들어가고 학습 라벨로만
  7. Claude숙고: Anthropic SDK 호출 모양(모형 · 구조화 출력 · 거절 대비)과 토큰 셈 · 거절이면 None
"""
from __future__ import annotations

import os
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


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="walp-tiers-")
    os.environ.update(WALP_AUTO_EVOLVE="0", SE_LEDGER_ROOT=tmp, WALP_LEARNED=os.path.join(tmp, "learned.csv"), WALP_BUILD=tmp)
    from walp import behavior as B, deliberate as DL, dialog as D, front
    if not front.ensure_built()[0]:
        print("    건너뜀: WALP 빌드 불가")
        return 0
    표본 = [("안녕", "greet"), ("잘가", "bye"), ("고마워", "thanks"), ("빨간 컵 찾아줘", "task"), ("파란 카드 찾아", "task"),
          ("프랑스 수도가 어디야", "knowledge"), ("오늘 저녁 메뉴 추천해줘", "out_of_scope"), ("네", "yes"), ("아니", "no"), ("틀렸잖아", "complaint"),
          ("일본 수도가 어디야", "knowledge"), ("물 끓는 온도가 몇도야", "knowledge")]
    센 = B.센서(None, D.어휘기르기(표본))
    l0 = B._L0기르기([(센.읽기(t), a) for t, a in 표본], seed=3, epochs=15)
    ep = [(B.불확실비트(센.읽기(t), l0.행(센.읽기(t), {})), not t.startswith("퓨")) for t in ["퓨퓨", "퓨웅", "퓨"] * 4 + [t for t, _ in 표본]]
    체 = {"센서": 센, "반응": l0, "되묻기": B.L1기르기(ep, c=0.3, seed=3, epochs=30)}
    원장: list = []
    t = [1000.0]

    def 턴(말, 숙고, who="u"):
        t[0] += 10
        out = B.대화(B.버스짓기(체, 뜻들=B.뜻들읽기(원장, who), 캐시=B.캐시읽기(원장)), 말, who,
                    [z for z in 원장 if z.get("kind") == "behavior"], t[0], 숙고=숙고)
        for z in out["기록"]:
            원장.append({"ts": t[0], "who": who, **z})
        return out

    print("[1][2] 모름 → 숙고 → 답 캐시")
    신탁 = DL.신탁숙고({"프랑스 수도가 어디야": ("knowledge", "파리입니다."), "독일 수도가 어디야": ("knowledge", "베를린입니다."),
                    "영국 수도가 어디야": ("greet", "안녕하세요!")})   # [4] 용: '모름' 이 확실히 나는 말에 신탁이 틀 행위를 답한다
    ok(B.모름(B.버스짓기(체).돌기("프랑스 수도가 어디야")), "준비: L0 가 바깥지식으로 읽어 '모른다' 가 된다")
    o = 턴("프랑스 수도가 어디야", 신탁)
    ok(o["종류"] == "숙고" and o["내용"] == "파리입니다." and 신탁.통계["호출"] == 1, f"모르면 숙고층에 묻고 그 답을 말한다 ({o['종류']})")
    ok(any(z["kind"] == "llm_answer" for z in 원장) and any(z["kind"] == "act_fix" and z.get("via") == "llm" for z in 원장),
       "배울 것: 열린 답(llm_answer) + 부류 라벨(act_fix via=llm)")
    o = 턴("프랑스 수도가 어디야?", 신탁)
    ok(o["종류"] == "틀" and o["내용"] == "파리입니다." and 신탁.통계["호출"] == 1, f"겉이 닮은 말은 답 캐시가 LLM 없이 답한다 (호출 {신탁.통계['호출']})")
    o = 턴("독일 수도가 어디야", 신탁)
    ok(o["내용"] == "베를린입니다." and 신탁.통계["호출"] == 2, "겉이 덜 닮은 말(포함률 < 0.75)은 다시 묻는다 — 남의 답을 안 준다")

    print("[3] 다시 쓴 답 뒤 불만")
    턴("프랑스 수도가 어디야!", 신탁)
    턴("틀렸잖아", 신탁)
    캐 = {f.예[0]: f.θ for f in B.캐시읽기(원장)}
    ok(캐.get("프랑스 수도가 어디야", 0) > B.CACHE_θ, f"문턱이 오른다 ({캐})")

    print("[4] 틀 행위")
    전 = len([z for z in 원장 if z["kind"] == "llm_answer"])
    o = 턴("영국 수도가 어디야", 신탁)
    ok(o["종류"] == "틀" and o["내용"] == D.틀["greet"], "숙고층이 인사라 하면 WALP 의 틀로 답한다")
    ok(len([z for z in 원장 if z["kind"] == "llm_answer"]) == 전 and ("영국 수도가 어디야", "greet") in
       [(z["text"], z["act"]) for z in 원장 if z["kind"] == "act_fix"], "라벨만 남고 답 캐시에는 안 넣는다")

    print("[5] 숙고층이 없거나 오류")
    ok(턴("퓨퓨퓨", None, who="v")["종류"] == "되물음", "숙고층이 없으면 예전처럼 사람에게 되묻는다")
    class 오류숙고:
        def 묻기(self, text):
            return {"오류": "APIConnectionError"}
    ok(턴("퓨퓨퓨퓨", 오류숙고(), who="w")["종류"] == "되물음", "숙고층 오류면 아래 층(되물음)으로")
    ok(DL.기본숙고() is None, "검사(SE_LEDGER_ROOT)에서는 기본으로 LLM 을 안 부른다")

    r = B.버스짓기(체).돌기("퓨퓨퓨")
    ok(r["승자"] == "되묻기", f"준비: '퓨퓨퓨' 는 되묻기 층이 흔들린다 ({r['승자']})")
    전호출 = 신탁.통계["호출"]
    o = 턴("퓨퓨퓨", 신탁, who="z")
    ok(신탁.통계["호출"] == 전호출 + 1 and o["종류"] == "숙고", f"되묻기가 흔들려도 '모른다' — 사람 대신 숙고층에 묻는다 ({o['종류']})")

    print("[6] LLM 라벨은 사람의 고침이 아니다")
    ok(not D.고침표(원장), "기억 층(고침표)에 안 들어간다")
    라벨, _, 사용자시험 = D.재생표본(원장)
    ok(("프랑스 수도가 어디야", "knowledge") in 라벨 and not 사용자시험, "학습 라벨로는 들어가고 사용자 관문에는 안 들어간다")

    print("[7] Claude숙고 — SDK 호출 모양(가짜 anthropic 모듈)")
    받은: dict = {}
    class 블록:
        def __init__(self, text):
            self.type, self.text = "text", text
    class 응답:
        def __init__(self, stop, text):
            self.stop_reason, self.content, self.model = stop, [블록(text)], "claude-opus-5-5"
            self.usage = types.SimpleNamespace(input_tokens=321, output_tokens=45)
    class 메시지:
        def __init__(self, stop):
            self.stop = stop
        def create(self, **kw):
            받은.update(kw)
            return 응답(self.stop, '{"act": "knowledge", "answer": "파리입니다."}')
    def 가짜(stop):
        m = types.ModuleType("anthropic")
        class APIError(Exception):
            pass
        class Anthropic:
            def __init__(self, default_headers=None):
                self.beta = types.SimpleNamespace(messages=메시지(stop))
        m.Anthropic, m.APIError = Anthropic, APIError
        return m
    sys.modules["anthropic"] = 가짜("end_turn")
    c = DL.Claude숙고()
    d = c.묻기("프랑스 수도?")
    ok(d["행위"] == "knowledge" and d["답"] == "파리입니다." and c.통계["입력토큰"] == 321 and c.통계["출력토큰"] == 45,
       f"JSON 을 읽고 토큰을 센다 ({d})")
    ok(받은.get("model") == "claude-opus-5-5" and 받은["output_config"]["format"]["type"] == "json_schema"
       and 받은.get("fallbacks") == "default" and 받은["output_config"].get("effort") == "low",
       "모형 · 구조화 출력 · 거절 대비 · effort 를 보낸다")
    sys.modules["anthropic"] = 가짜("refusal")
    c2 = DL.Claude숙고()
    ok(c2.묻기("x") is None and c2.통계["거절"] == 1, "거절이면 None(아래 층이 되묻는다)")
    del sys.modules["anthropic"]

    if fails:
        print(f"\n실패 {len(fails)}: " + " · ".join(fails))
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
