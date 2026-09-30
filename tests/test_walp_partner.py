#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP 대화 상대 구동기(walp/partner.py) — 로컬 가짜 Gemini 서버로 **진짜 HTTP 길**을 돌려 본다(밖 망 없이).

기대는 먼저 적는다:
  1. 요청: POST · 키는 `x-goog-api-key` 헤더로만(URL 에 없다) · systemInstruction · JSON 응답 형식
  2. 429(retryDelay 7s) → 그만큼(+2) 쉬고 다시 한다 · 여덟 번 이어진 오류면 멈춘다
  3. 한 턴: 말 → WALP 답 → WALP 가 고른 행위가 의도와 다르면 구동기가 `행위 <의도>` 로 고친다(Gemini 호출 없이)
  4. WALP 가 뜻을 물으면 다음 권함은 yes/no, 모르는 말이면 rephrase
  5. 하루 한도(rpd)를 넘기지 않는다 — 간격 = max(60/rpm, 86400/rpd)
  6. 기록: 턴마다 walp_partner.jsonl 한 줄, 원장에는 via=gemini
  7. 흔적 없음
"""
from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
fails: list[str] = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


받은: list = []
대본: list = []


class 가짜Gemini(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode())
        받은.append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
        code, payload = 대본.pop(0) if 대본 else (200, {"say": "안녕", "act": "greet"})
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if code == 200:
            out = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        else:
            out = payload
        self.wfile.write(json.dumps(out).encode())


def main() -> int:
    def status():
        return subprocess.run(["git", "status", "--porcelain", "-uno"], cwd=REPO, capture_output=True, text=True).stdout
    before = status()
    tmp = tempfile.mkdtemp(prefix="walp-partner-")
    os.environ.update(WALP_AUTO_EVOLVE="0", SE_LEDGER_ROOT=tmp, WALP_LEARNED=os.path.join(tmp, "learned.csv"),
                      WALP_BUILD=tmp, GEMINI_API_KEY="TESTKEY-123", NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")
    for k in ("HTTP_PROXY", "http_proxy"):
        os.environ.pop(k, None)
    from walp import front, partner, usability, search_path
    search_path._기본받기json = lambda u: ""
    if not front.ensure_built()[0]:
        print("    건너뜀: WALP 빌드 불가")
        return 0
    srv = http.server.HTTPServer(("127.0.0.1", 0), 가짜Gemini)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    partner.API = f"http://127.0.0.1:{srv.server_port}/v1beta/models/{{model}}:generateContent"

    시각 = [1_000_000.0]

    def 시계():
        시각[0] += 0.01
        return 시각[0]

    def 민다(목록):
        def 쉬기(s):
            목록.append(s)
            시각[0] += s
        return 쉬기

    print("[1][2][3] 진짜 HTTP 길")
    대본[:] = [(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [{"retryDelay": "7s"}]}}),
              (200, {"say": "이만 가볼게요 안녕히 계세요", "act": "bye"}),      # 손 규칙은 인사 → 구동기가 작별로 고친다
              (200, {"say": "주홍 컵 찾아줘", "act": "task"}),
              (200, {"say": "빨간 컵 찾아줘", "act": "task"})]
    쉼: list = []
    찍음: list = []
    통 = partner.돌리기(시간=1, 턴상한=3, rpm=60, rpd=100000, 페르소나수=1, 쓰기=True, 씨앗=1, 출력=찍음.append,
                     쉬기=민다(쉼), 시계=시계)
    ok(len(받은) == 4 and all(r["key"] == "TESTKEY-123" and "TESTKEY" not in r["path"] for r in 받은),
       "키는 헤더로만 — URL 에 없다")
    b = 받은[0]["body"]
    ok("systemInstruction" in b and b["generationConfig"]["responseMimeType"] == "application/json"
       and "gemini" in 받은[0]["path"], "systemInstruction · JSON 응답 형식 · 모델 경로")
    ok(쉼 and 쉼[0] == 9.0 and 통["429"] == 1, f"429 retryDelay 7s → 9초 쉰다 ({쉼[:2]})")
    ok(통["턴"] == 3 and 통["고침"] == 1, f"세 턴 · 고침 한 번 ({통})")
    zs = usability.읽기()
    fx = [z for z in zs if z.get("kind") == "act_fix"]
    ok(fx and fx[0]["act"] == "bye" and fx[0]["text"] == "이만 가볼게요 안녕히 계세요", "구동기의 고침이 원장에 act_fix 로")
    ok(all(z.get("via") == "gemini" for z in zs if z.get("kind") in ("dialog", "act_fix", "run")), "원장에는 via=gemini")
    기록 = [json.loads(l) for l in open(os.path.join(tmp, "walp_partner.jsonl"), encoding="utf-8")]
    ok(len(기록) == 3 and 기록[0]["의도"] == "bye" and 기록[0]["walp_act"] == "greet" and 기록[0]["고침"], "턴마다 기록 한 줄")
    ok(기록[-1]["권함"] == "rephrase", "모르는 말 다음 턴은 고쳐 말하기를 권한다")
    ok(any("쓰셨나요?" in t for w, t in [("walp", 기록[-1]["답"])]) and "쓰셨나요?" in partner._줄임("x" * 3000 + "쓰셨나요? `네`") and partner.권할행위(__import__("random").Random(0), 기록[-1]["답"]) == "yes/no",
       "WALP 가 뜻을 물으면 다음 권함은 네/아니")

    print("[2] 오류가 이어지면 멈춘다")
    대본[:] = [(500, {"error": {"code": 500}})] * 9
    통2 = partner.돌리기(시간=1, 턴상한=5, rpm=60, rpd=100000, 페르소나수=1, 씨앗=1, 출력=찍음.append, 쉬기=민다([]), 시계=시계)
    ok(통2["오류"] == 8 and 통2["턴"] == 0 and any("여덟 번" in c for c in 찍음), "오류 여덟 번 → 멈춤")

    print("[5] 하루 한도")
    대본[:] = []
    쉼2: list = []
    통3 = partner.돌리기(시간=100, 턴상한=3, rpm=60, rpd=2, 페르소나수=1, 씨앗=1, 출력=찍음.append, 쉬기=민다(쉼2), 시계=시계)
    ok(통3["호출"] >= 3 and any(s > 40000 for s in 쉼2), f"rpd=2 → 세 번째 호출 전에 하루 창이 풀릴 때까지 쉰다 ({[round(s) for s in 쉼2][:4]})")
    ok(쉼2[0] == 86400 / 2, "간격 = max(60/rpm, 86400/rpd)")
    srv.shutdown()

    print("[7] 흔적")
    ok(status() == before, "추적 파일 변화 없음")
    if fails:
        print(f"\n실패 {len(fails)}: " + " · ".join(fails))
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
