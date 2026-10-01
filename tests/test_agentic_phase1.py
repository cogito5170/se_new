"""agentic 1단계 -- 정책 K 의 셋(고정 모델 정체 · 원시 로그 숨김+구조화 사건 · 로깅 실패)과 H0 위조 게이트.

모델은 전부 **가짜**다(CLAUDE.md: 배선 확인은 예외). 진짜 Gemini 는 여기서 안 부른다 --
키도 없고, 응답이 `modelVersion` 을 실제로 싣는지는 VM 에서 한 번 불러 봐야 안다.

꼴은 `tests/test_논문원장_게이트.py` 를 따른다: 옳은 길 하나를 돌리고, 여러 가지로 망가뜨려
매번 그 망가짐이 화면과 원장에 **그대로** 나오는지 본다. 원장은 임시 자리에 쓴다(나무를 안 더럽힌다).

    python3 tests/test_agentic_phase1.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestrator"))

from agentic import config as C                         # noqa: E402
from agentic import forgery as F                        # noqa: E402
from agentic.ledger import Ledger, read_events          # noqa: E402
from agentic.render import render                       # noqa: E402
from agentic.run import run                             # noqa: E402
import gemini_http as G                                 # noqa: E402

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


MODEL = "gemini-3.1-flash-lite"
# 사용자가 붙여 준 실제 답(2026-10-01) -- 이것이 이 단계가 막아야 할 바로 그것이다
FORGED = ("Log: NO_LOOP_DETECTED. Status: Gate01 evaluation (A_TO_B: TRUE). MCP version: 0.46.0.\n\n"
          "Story Transition: Industrial Gallery to Fashion\n"
          "[Next]: Generate design tokens based on this architectural-fashion transition.")
CLEAN = "Concrete texture maps to structured heavy wool.\n[Next]: list the three tokens as JSON"


class _Reply:
    def __init__(self, text, mv):
        self.content, self.model_version = text, mv


class FakeFactory:
    """(모델, 키) -> 클라이언트. 무엇을 불렀는지 적는다. 대본은 차례대로 쓴다:
    ("ok", 글, modelVersion) 또는 ("err", 상태, 이름, 본문)."""

    def __init__(self, *script):
        self.script, self.seen = list(script), []

    def __call__(self, model, key):
        self.seen.append((model, key))
        step = self.script.pop(0)
        fac = self

        class _C:
            def invoke(self, prompt):
                fac.last_prompt = prompt
                if step[0] == "err":
                    raise G.GeminiError(step[1], step[2], step[3])
                return _Reply(step[1], step[2])
        return _C()


def cfg_file(d, **over):
    base = {"model": MODEL, "model_fallback": False,
            "budgets": {"model_calls": 4, "forgery_retries": 1, "wall_seconds": 180, "tasks": 20,
                        "sandbox_seconds": 60},
            "sandbox": "sandbox/", "mandatory_checks": ["sandbox"], "allowed_kinds": ["read", "compute"]}
    base.update(over)
    p = Path(d) / f"cfg{len(list(Path(d).glob('cfg*')))}.json"
    p.write_text(json.dumps(base))
    return p


KEYS = [("GEMINI_API_KEY", "k1"), ("GEMINI_API_KEY_FALLBACK", "k2")]

with tempfile.TemporaryDirectory() as tmp:
    T = Path(tmp)
    cfg = C.load(cfg_file(T))

    print("[K] 고정 모델 정체 -- 설정")
    ok(C.load().model == MODEL, f"저장소 설정의 모델이 {MODEL} 이다")
    for bad, why in [({"model_fallback": True}, "model_fallback_must_be_false"),
                     ({"fallback_models": ["gemini-3.5-flash"]}, "forbidden_key:fallback_models"),
                     ({"models": [MODEL, "x"]}, "forbidden_key:models"),
                     ({"model": ""}, "model_missing"),
                     ({"budgets": {"model_calls": True, "forgery_retries": 1, "wall_seconds": 9, "tasks": 1,
                                  "sandbox_seconds": 1}},
                      "budget_invalid:model_calls"),
                     ({"mandatory_checks": []}, "mandatory_checks_must_include_sandbox"),
                     ({"mandatory_checks": ["lint"]}, "mandatory_checks_must_include_sandbox"),
                     ({"allowed_kinds": ["read", "root"]}, "allowed_kinds_invalid")]:
        try:
            C.load(cfg_file(T, **bad))
            ok(False, f"{bad} 를 거절한다")
        except C.ConfigError as e:
            ok(str(e) == why, f"{list(bad)[0]} -> {why}")
    c2 = C.load(cfg_file(T, sandbox="sandbox/ "))
    ok(c2.sha256 != cfg.sha256, "설정 바이트가 다르면 해시가 다르다(다른 실행으로 기록된다)")

    print("[K] 고정 모델 정체 -- 런타임")
    fac = FakeFactory(("ok", CLEAN, MODEL))
    st, rd, txt = run("q", cfg, root=T, keys=KEYS, client_factory=fac, run_id="verified")
    ok(st == "DONE" and "확인됨" in txt, "응답이 같은 모델을 밝히면 DONE · 확인됨")
    ev = read_events(rd)
    ok(ev[0]["type"] == "RUN_START" and ev[0]["data"]["config_sha256"] == cfg.sha256,
       "원장 첫 줄에 설정 해시")

    fac = FakeFactory(("ok", CLEAN, f"{MODEL}-001"))
    st, _, txt = run("q", cfg, root=T, keys=KEYS, client_factory=fac, run_id="rev")
    ok(st == "DONE" and "확인됨" in txt, "같은 모델의 개정(-001)은 확인됨 · 원래 값은 화면에 그대로")
    ok(f"{MODEL}-001" in txt, "개정 꼬리를 지우지 않고 보인다")

    fac = FakeFactory(("ok", CLEAN, None))
    st, _, txt = run("q", cfg, root=T, keys=KEYS, client_factory=fac, run_id="unrep")
    ok(st == "DONE" and "미확인" in txt and "확인됨" not in txt,
       "응답이 모델을 안 밝히면 미확인 -- 부른 이름으로 채우지 않는다")

    fac = FakeFactory(("ok", CLEAN, "gemini-3.5-flash-lite"))
    st, rd, txt = run("q", cfg, root=T, keys=KEYS, client_factory=fac, run_id="mismatch")
    ok(st == "BLOCKED" and "model_mismatch" in txt, "다른 모델이 답하면 BLOCKED(model_mismatch)")
    ok("Concrete" not in txt, "불일치 모델의 답은 화면에 안 나온다")
    ok(not any(e["type"] == "ANSWER_ADOPTED" for e in read_events(rd)), "원장에도 채택 없음")

    fac = FakeFactory(("err", 429, "RESOURCE_EXHAUSTED", "{}"), ("err", 503, "UNAVAILABLE", "{}"))
    st, _, txt = run("q", cfg, root=T, keys=KEYS, client_factory=fac, run_id="unavail")
    ok(st == "BLOCKED" and "model_unavailable" in txt, "키를 다 써도 안 되면 BLOCKED(model_unavailable)")
    ok({m for m, _ in fac.seen} == {MODEL}, f"폴백 없음: 부른 모델이 {MODEL} 하나뿐 ({fac.seen})")
    ok([k for _, k in fac.seen] == ["k1", "k2"], "키만 돌렸다")

    st, _, txt = run("q", cfg, root=T, keys=[], client_factory=FakeFactory(), run_id="nokey")
    ok(st == "BLOCKED" and "no_api_key" in txt, "키가 없으면 BLOCKED(no_api_key) -- 다른 모델로 대신하지 않는다")

    print("[H0] 깃발 위조")
    fac = FakeFactory(("ok", FORGED, MODEL), ("ok", FORGED, MODEL))
    st, rd, txt = run("q", cfg, root=T, keys=KEYS, client_factory=fac, run_id="forged")
    ok(st == "NEEDS_REVIEW", "사용자가 받은 그 답을 두 번 받으면 NEEDS_REVIEW(채택 안 함)")
    for w in ("NO_LOOP_DETECTED", "A_TO_B", "0.46.0", "Industrial"):
        ok(w not in txt, f"화면에 {w!r} 가 안 나온다")
    ok("루프: UNKNOWN" in txt, "루프 칸은 UNKNOWN (탐지기가 없다)")
    ok("Gate01: 평가 안 함" in txt, "Gate01 칸은 '평가 안 함' -- TRUE 가 아니다")
    ok("MCP: protocol 기록 없음 · sdk 기록 없음 · server 기록 없음" in txt, "MCP 칸은 세 갈래 다 기록 없음")
    forg = [e for e in read_events(rd) if e["type"] == "MODEL_FLAG_FORGERY"]
    kinds = {h[0] for e in forg for h in e["data"]["hits"]}
    ok(len(forg) == 2 and {"flag", "gate", "status_line", "version_claim"} <= kinds,
       f"원장에 위조 두 번, 네 종류 다 잡힘 ({sorted(kinds)})")
    ok("previous answer" in fac.last_prompt, "두 번째 물음에는 버렸다는 말이 붙는다")

    fac = FakeFactory(("ok", FORGED, MODEL), ("ok", CLEAN, MODEL))
    st, rd, txt = run("q", cfg, root=T, keys=KEYS, client_factory=fac, run_id="forged_then_clean")
    ok(st == "DONE" and "Concrete" in txt and "깃발 위조: 1회" in txt,
       "위조 뒤 깨끗한 답이면 그것을 채택하고, 위조 1회를 보인다")
    ok("다음 작업 제안(디스패치 안 됨): list the three tokens as JSON" in txt,
       "[Next] 는 제안으로만 -- 디스패치됐다고 안 쓴다")
    ok(not any("[Next]" in l for l in txt.split("답:")[1].splitlines()), "답 본문에서 [Next] 줄은 빠진다")

    fac = FakeFactory(("ok", FORGED, MODEL), ("ok", FORGED, MODEL))
    c_small = C.load(cfg_file(T, budgets={"model_calls": 1, "forgery_retries": 1, "wall_seconds": 180,
                                           "tasks": 20, "sandbox_seconds": 60}))
    st, _, txt = run("q", c_small, root=T, keys=KEYS, client_factory=fac, run_id="budget")
    ok(st == "FAILED" and "budget_model_calls" in txt, "재질문도 예산에서 -- 호출 예산 1 이면 FAILED(budget_model_calls)")

    print("[H0] 거짓 경보 없음 (음성 짝)")
    for s in ("The test failed twice, so we are done when it passes.",
              "Gate the signal through a buffer; the logic is blocked by the clock.",
              "Version control keeps history."):
        ok(F.scan(s) == [], f"산문은 안 걸린다: {s[:40]}")
    ok(F.scan("Protocol version: 2025-06-18") != [], "날짜꼴 버전 주장도 걸린다")
    ok(F.scan("I am Gemini, running fine.") != [], "모델 정체 자칭도 걸린다")

    print("[K] 원시 로그 숨김 + 구조화 사건 보임")
    secret = "AIzaSy" + "FAKE" * 8 + "1234"          # 이어 붙인다 -- 한 덩어리면 G004 가 진짜 키로 본다
    os.environ["GEMINI_API_KEY"] = secret
    try:
        body = json.dumps({"error": {"message": f"RAW-BODY-MARKER key={secret}"}})
        fac = FakeFactory(("err", 400, "INVALID_ARGUMENT", body), ("ok", CLEAN, MODEL))
        st, rd, txt = run("q", cfg, root=T, keys=KEYS, client_factory=fac, run_id="rawlog")
        ok(st == "DONE", "첫 키 오류 뒤 둘째 키로 DONE")
        ok("RAW-BODY-MARKER" not in txt, "오류 본문이 화면에 안 나온다")
        ok("진단 로그:" in txt and "diag.log" in txt, "진단 로그는 경로와 크기만 보인다")
        diag = (rd / "diag.log").read_text()
        ok("RAW-BODY-MARKER" in diag, "원시 본문은 진단 싱크에 남는다")
        ok(secret not in diag, "진단 싱크에서 키는 마스킹된다")
        ok(oct((rd / "diag.log").stat().st_mode & 0o777) == "0o600", "진단 싱크는 600")
        evs = (rd / "events.jsonl").read_text()
        ok("RAW-BODY-MARKER" not in evs and secret not in evs, "사건 원장에는 본문도 키도 없다")
        ends = [e for e in read_events(rd) if e["type"] == "MODEL_CALL_END"]
        ok(ends[0]["data"]["status"] == 400 and ends[0]["data"]["name"] == "INVALID_ARGUMENT",
           "사건에는 상태·이름이 구조화되어 있다")
    finally:
        del os.environ["GEMINI_API_KEY"]

    print("[K] 로깅 실패")
    blocked = T / "agentic" / "runs" / "logfail"
    (blocked / "events.jsonl").mkdir(parents=True)          # 원장 자리가 디렉터리 -> 쓰기 실패 (root 여도)
    st, _, txt = run("q", cfg, root=T, keys=KEYS, client_factory=FakeFactory(("ok", CLEAN, MODEL)),
                     run_id="logfail")
    ok(st == "LOGGING_FAILURE" and "LOGGING_FAILURE" in txt, "원장을 못 쓰면 LOGGING_FAILURE")
    ok("Concrete" not in txt, "로깅이 죽으면 답도 안 낸다")

    sink_bad = T / "agentic" / "runs" / "sinkfail"
    (sink_bad / "diag.log").mkdir(parents=True)
    fac = FakeFactory(("err", 500, "INTERNAL", "boom"), ("ok", CLEAN, MODEL))
    st, _, txt = run("q", cfg, root=T, keys=KEYS, client_factory=fac, run_id="sinkfail")
    ok(st == "LOGGING_FAILURE", "진단 싱크를 못 써도 조용히 넘어가지 않는다")

    print("[원장] 닫힌 목록 · 종료")
    L = Ledger(T / "closed", "closed")
    for f, why in [(lambda: L.emit("SUCCESS", "code"), "모르는 사건 종류"),
                   (lambda: L.emit("RUN_START", "gemini"), "모르는 행위자"),
                   (lambda: L.terminal("OK", "x", ""), "모르는 종료 상태"),
                   (lambda: L.terminal("DONE", "", ""), "사유 없는 종료")]:
        try:
            f()
            ok(False, f"{why} 를 거절한다")
        except ValueError:
            ok(True, f"{why} 를 거절한다")
    L.terminal("DONE", "x", "")
    try:
        L.emit("RUN_START", "code")
        ok(False, "종료 뒤 사건을 거절한다")
    except ValueError:
        ok(True, "종료 뒤 사건을 거절한다")
    L2 = Ledger(T / "noterm", "noterm")
    L2.emit("RUN_START", "code", {"model": MODEL})
    txt = render(read_events(T / "noterm"))
    ok("FAILED (no_terminal_event)" in txt, "종료 사건이 없으면 FAILED(no_terminal_event) 로 그린다")

    print("[gemini_http] 응답의 modelVersion 을 Reply 에 싣는다")
    class _R:
        status_code = 200
        text = ""
        def __init__(self, p): self.p = p
        def json(self): return self.p
    import requests
    real = requests.post
    try:
        payload = {"candidates": [{"content": {"parts": [{"text": "hi"}]}}], "modelVersion": f"{MODEL}-001"}
        requests.post = lambda *a, **k: _R(payload)
        r = G.Client(MODEL, "k").invoke("x")
        ok(r.content == "hi" and r.model_version == f"{MODEL}-001", "modelVersion 이 실린다")
        payload2 = {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}
        requests.post = lambda *a, **k: _R(payload2)
        ok(G.Client(MODEL, "k").invoke("x").model_version is None, "없으면 None -- 부른 이름으로 안 채운다")
    finally:
        requests.post = real

print()
if fails:
    print(f"agentic 1단계: {len(fails)}개 실패 -- {fails}")
    sys.exit(1)
print("agentic 1단계: 고정 모델 · 위조 게이트 · 원시 로그 숨김 · 로깅 실패 · 닫힌 원장 -- 통과")
