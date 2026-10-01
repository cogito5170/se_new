"""agentic 6단계 -- 도구 실행을 sandbox 안에서 · 회로 차단기 · repair 연결. 정책 K 의 '컨테이너 실행과 검증' ·
'기존 클론 격리' 줄(정책 C 의 '컨테이너' 는 이 저장소에서 sandbox/ -- 사용자 결정 2026-10-01).

  · 진짜 sandbox 로 등록된 도구를 돌린다 -- 결과 · 끝값 · 판이 원장에
  · 기존 클론 격리: 작업 트리에만 있는 파일은 sandbox 안에서 안 보이고, sandbox 안의 쓰기는 작업 트리에 안 닿는다
  · 회로 차단기: 도구 탓 실패만 세고(인프라는 안 센다), 문턱에서 격리 + 수리 요청(모델 없는 진단 · 재현 명령)
  · 수리: --apply 없이는 아무것도 안 바꾼다. --apply 면 repair 에 **고정 모델** 제안기를 끼운다

모델·repair 는 가짜로, sandbox 는 진짜로(도구 실행 · 격리 확인).

    python3 tests/test_agentic_phase6.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestrator"))

from agentic import breaker as BR                       # noqa: E402
from agentic import config as C                         # noqa: E402
from agentic import gate01 as G                         # noqa: E402
from agentic import repair_queue as RQ                  # noqa: E402
from agentic import tools as TL                         # noqa: E402
from agentic.ledger import read_events                  # noqa: E402
from agentic.run import run                             # noqa: E402
from sandbox.run import 실행                             # noqa: E402

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


MODEL = "gemini-3.1-flash-lite"


def cfg_at(d, trip=2):
    base = {"model": MODEL, "model_fallback": False,
            "budgets": {"model_calls": 10, "forgery_retries": 1, "wall_seconds": 180, "tasks": 20,
                        "sandbox_seconds": 120, "react_turns": 6, "tool_output_chars": 4000},
            "sandbox": "sandbox/", "mandatory_checks": ["sandbox"], "allowed_kinds": ["read", "compute"],
            "front": {"walp": False}, "loop": {"same_action": 2, "same_failure": 2, "no_progress": 3},
            "rag": {"k": 3, "repo_graph": False, "record": False}, "repair": {"trip_after": trip}}
    p = Path(d) / f"cfg{len(list(Path(d).glob('cfg*')))}.json"
    p.write_text(json.dumps(base))
    return C.load(p)


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=ROOT, capture_output=True, text=True).stdout


class Fac:
    def __init__(self):
        self.seen = []

    def __call__(self, model, key):
        fac = self

        class _C:
            def invoke(self, p):
                fac.seen.append(model)

                class R:
                    content, model_version = "{\"꼴\": \"사람\", \"사람이_할_것\": \"x\"}", MODEL
                return R()
        return _C()


SB = {"sandbox": lambda s, c, k: (G.TRUE, "fake")}

with tempfile.TemporaryDirectory() as tmp:
    T = Path(tmp)
    cfg = cfg_at(T)

    print("[C.1 · D.4] 등록된 도구는 sandbox 안에서 돈다 (진짜)")
    before = git_status()
    st, rd, txt = run("agentic/config.json 파일 읽어줘", cfg, root=T / "real", keys=[("K", "k")],
                      client_factory=Fac(), run_id="s1")
    es = read_events(rd)
    sx = [e for e in es if e["type"] == "SANDBOX_EXEC"]
    ok(st == "DONE" and "gemini-3.1-flash-lite" in txt, f"DONE · 진짜 파일 내용 ({st})")
    ok(sx and sx[0]["data"]["ran"] and sx[0]["data"]["exit"] == 0 and sx[0]["data"]["tree"].startswith("HEAD "),
       f"SANDBOX_EXEC: 판 HEAD · 끝값 0 ({sx[0]['data'] if sx else None})")
    ok("sandbox: 도구 실행 1번 · 판 HEAD" in txt, "화면 sandbox 줄")
    ok(git_status() == before, "작업 트리가 그대로다")

    print("[B.4 · B.5] 기존 클론 격리")
    probe = ROOT / "agentic" / "_isolation_probe_untracked.txt"
    probe.write_text("작업 트리에만 있는 비밀 문장")
    try:
        out = TL.sandbox_execute("read_file", {"path": "agentic/_isolation_probe_untracked.txt"}, timeout=120)
        ok(out["sandbox"]["ran"] and "작업 트리에만 있는 비밀 문장" not in json.dumps(out, ensure_ascii=False),
           "작업 트리에만 있는 파일은 sandbox(HEAD 판) 안에서 안 보인다")
    finally:
        probe.unlink()
    before = git_status()
    r = 실행(["bash", "-c", "echo 오염 > agentic/_written_in_sandbox.txt && cat agentic/_written_in_sandbox.txt"], 초=60)
    ok(r["끝값"] == 0 and "오염" in r["stdout"], "sandbox 안에서는 쓰기가 됐다")
    ok(not (ROOT / "agentic" / "_written_in_sandbox.txt").exists() and git_status() == before,
       "그 쓰기는 작업 트리에 안 닿았다")
    bad = TL.sandbox_execute("read_file", {"path": "a"}, runner=lambda argv, 초: {"끝값": 3, "돌았나": False, "메모": "판 못 깜"})
    ok(bad["error"].startswith("sandbox_not_run") and TL.broken_reason(bad) is None,
       "판을 못 깔면 sandbox_not_run -- 인프라라 차단기가 안 센다")

    print("[resilience] 회로 차단기 -- 도구 탓 실패만 센다")
    R = {"tools": {"read_file": {"declaration": TL.load_registry()["tools"]["read_file"]["declaration"],
                                 "source_sha": "S1", "kind": "read"}}, "rejected": {}}
    TOOL = {"status": "TOOL", "tool": "read_file", "args": {"path": "agentic/config.json"}}
    calls = []

    def ex_of(out):
        def ex(n, a):
            calls.append(n)
            return dict(out)
        return ex
    broken = {"ok": False, "error": "ValueError: 깨진 도구", "llm_attempts": 0}
    infra = {"ok": False, "error": "timeout 120s", "llm_attempts": 0}
    k = [0]

    def go(executor, root, src="S1", reg=R):
        k[0] += 1
        f = Fac()
        st, rd, txt = run("q", cfg, root=root, keys=[("K", "k")], client_factory=f, run_id=f"b{k[0]}",
                          controller_opts={"registry": reg, "route_fn": lambda t: TOOL, "executor": executor,
                                           "checks": SB, "src_sha": lambda n: src})
        return st, rd, txt, f
    root = T / "br"
    base = root / "agentic" / "runs"
    st, rd, txt, f = go(ex_of(infra), root)
    st, rd, txt, f = go(ex_of(infra), root)
    ok(BR.state(base, "read_file", "S1") == {"open": False, "fails": 0}, "시간 초과 둘은 안 센다")
    st, rd, txt, f = go(ex_of(broken), root)
    ok(st == "RED_RED_STOP" and BR.state(base, "read_file", "S1")["fails"] == 1
       and not any(e["type"] == "TOOL_QUARANTINED" for e in read_events(rd)), "도구 탓 실패 1 -- 아직 격리 안 함")
    st, rd, txt, f = go(ex_of({"ok": True, "result": "x", "llm_attempts": 0}), root)
    ok(st == "DONE" and BR.state(base, "read_file", "S1")["fails"] == 0, "성공 한 번이면 셈이 0 으로")
    go(ex_of(broken), root)
    st, rd, txt, f = go(ex_of(broken), root)
    es = read_events(rd)
    q = [e for e in es if e["type"] == "TOOL_QUARANTINED"]
    rr = [e for e in es if e["type"] == "REPAIR_REQUESTED"]
    ok(q and rr and BR.state(base, "read_file", "S1")["open"], "이어서 2번 -> 격리 + 수리 요청")
    ok("격리: read_file" in txt and "repair_queue --fix 1" in txt, "화면에 격리 · 수리 요청 · 보는 법")
    t = BR.tickets(base)[0]
    ok(t["reproduce"] == "python3 -m agentic.tools --exec read_file '{\"path\": \"agentic/config.json\"}'"
       and t["error"] == "ValueError: 깨진 도구" and "hypotheses" in t["diagnosis"], "요청: 재현 명령 · 증상 · 모델 없는 진단")
    n0 = len(calls)
    st, rd, txt, f = go(ex_of(broken), root)
    ok(len(calls) == n0 and "quarantined:breaker_open" in txt and f.seen == [MODEL],
       "격리된 도구는 돌리지 않고 놓친 것으로 -> 모델로")
    st, rd, txt, f = go(ex_of({"ok": True, "result": "y", "llm_attempts": 0}), root, src="S2",
                        reg={"tools": {"read_file": {**R["tools"]["read_file"], "source_sha": "S2"}}, "rejected": {}})
    ok(st == "DONE", "고쳐서 재등록(새 원문 해시)하면 새 셈 -- 다시 쓰인다")
    go(ex_of({"ok": True, "result": "z", "llm_attempts": 1}), T / "llm")
    ok(BR.state(T / "llm" / "agentic" / "runs", "read_file", "S1")["fails"] == 1, "LLM 을 부르려 한 도구는 도구 탓으로 센다")

    print("[repair] --apply 없이는 아무것도 안 바꾼다 · --apply 면 고정 모델 제안기")
    used = []

    def fixer(cmd, symptom, proposer):
        used.append((cmd, symptom))
        proposer("수리 제안을 내라")            # 제안기가 실제로 모델을 부르는지
        return {"해결": True, "바퀴": 1, "남은것": ""}
    code, text = RQ.fix(1, apply=False, cfg=cfg, root=root, fixer=fixer)
    ok(code == 0 and used == [] and "아무것도 바꾸지 않았다" in text and "제안기: gemini-3.1-flash-lite (폴백 없음)" in text,
       "--apply 없으면 계획만 -- fixer 안 불림")
    fac = Fac()
    code, text = RQ.fix(1, apply=True, cfg=cfg, root=root, keys=[("K", "k")], client_factory=fac, fixer=fixer)
    ok(code == 0 and used and used[0][0].startswith("python3 -m agentic.tools --exec read_file"),
       "--apply 면 재현 명령 · 증상으로 repair 를 돌렸다")
    ok(fac.seen == [MODEL], f"제안기는 설정의 모델 하나만 불렀다 ({fac.seen})")
    ok("--register" in text and BR.tickets(base)[0]["status"] == "fixed_pending_register",
       "고쳐도 재등록 전까지 격리 -- 상태 fixed_pending_register")
    code, text = RQ.fix(1, apply=True, cfg=cfg, root=root, keys=[("K", "k")], client_factory=Fac(),
                        fixer=lambda c, s, p: {"해결": False, "남은것": "재현이 계속 실패"})
    ok(code == 1 and BR.tickets(base)[0]["status"] == "unfixed" and "못 고쳤다" in text, "못 고치면 unfixed 로 남는다")
    ok(RQ.fix(99, apply=False, cfg=cfg, root=root)[0] == 1, "없는 요청 번호는 1")

    print("[설정] 차단 문턱")
    try:
        cfg_at(T, trip=0)
        ok(False, "trip_after 0 은 거절")
    except C.ConfigError as e:
        ok(str(e) == "repair_invalid", "trip_after 0 은 거절")

print()
if fails:
    print(f"agentic 6단계: {len(fails)}개 실패 -- {fails}")
    sys.exit(1)
print("agentic 6단계: sandbox 실행 · 기존 클론 격리 · 회로 차단기 · 수리 요청 · 고정 모델 수리 -- 통과")
