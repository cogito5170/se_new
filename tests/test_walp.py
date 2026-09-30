#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP(무가중치 자율 언어정책)를 **실제로 빌드하고 돌려서** 본다 — 스텁이 아니다.

  1. C++ 코어를 임시 자리에 빌드(-Werror, 코어는 -fno-exceptions -fno-rtti)하고 core_test 를
     끝까지 돌린다: 고장 주입 표·해석 상태·재시작 원자성·재현성·힙 0·한 걸음 이웃·부호 검정·배율 이웃 — 68개 기대.
  2. 봉인한 평가 문장(held-out)의 sha256 이 그대로인가 — 파서에 맞춰 문장을 고치면 held-out 이
     아니게 된다. 그리고 두 모음에서 **거부해야 할 것을 실행한 수**가 기록과 같은가.
  3. MCP 서버가 JSON-RPC 로 도구를 내놓고, 모호한 말에 실행하지 않고 후보를 돌려주는가.
  4. `!walp` 가 dispatch 에 실려 있고, 사용성 원장 집계가 손으로 센 값과 같은가.

흔적을 안 남긴다: 빌드·원장·학습 사전은 전부 임시 자리(WALP_BUILD · SE_LEDGER_ROOT · WALP_LEARNED).
g++/make 가 없으면 건너뛴다(사유를 찍는다 — 거짓 초록 방지)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WALP = os.path.join(REPO, "walp")
fails: list[str] = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


SEALED = {
    "heldout_corpus.tsv": "de451158604f4e9d5265bbb0dc24a75fe2bada27fae1c0f61000fcb363cf0e83",
    "novel_corpus.tsv": "a357054938c5582b00427a63b579698f6c791b71d338c7954e4a4373c69bcfe4",
}


def test_all():
    for name, sha in SEALED.items():
        with open(os.path.join(WALP, "eval", name), "rb") as f:
            ok(hashlib.sha256(f.read()).hexdigest() == sha, f"봉인 문장 {name} 가 커밋 때와 같다")

    if shutil.which("make") is None or shutil.which("g++") is None:
        print("    건너뜀: make/g++ 없음(환경 한정) — 빌드·실행 검사는 CI 러너에서 돈다")
        return
    tmp = tempfile.mkdtemp(prefix="walp-test-")
    env = dict(os.environ, WALP_BUILD=tmp, SE_LEDGER_ROOT=tmp, WALP_LEARNED=os.path.join(tmp, "learned.csv"))
    try:
        r = subprocess.run(["make", "-C", WALP, f"BUILD={tmp}", "-j2", "all", "test"], capture_output=True, text=True,
                           timeout=600, env=env)
        out = r.stdout + r.stderr
        print("\n".join(l for l in out.splitlines() if l.startswith(("OK", "FAIL", "PASS", "     "))))
        ok(r.returncode == 0, "core_test 통과(exit 0)")
        ok(sum(1 for l in out.splitlines() if l.startswith("OK   ")) >= 68, "core_test 기대 68개가 실제로 돌았다")
        ok("음성 대조: 안전층을 빼면 위반이 실제로 난다" in out, "안전층 시험이 비어 있지 않다(음성 대조가 돌았다)")

        cli = os.path.join(tmp, "walp_cli")
        # 봉인 문장: 채점한 결과가 기록(walp/eval/results)과 같은가 — 파서가 조용히 바뀌면 여기서 걸린다
        for name in ("heldout", "novel"):
            got = json.loads(subprocess.run([cli, "corpus", os.path.join(WALP, "eval", f"{name}_corpus.tsv")],
                                            capture_output=True, text=True, env=env).stdout)
            # v0.4: 구절 틀을 들이며 이 둘은 개발 모음이 됐다(실패 문장을 읽었다) — 기록은 lang_*_v04.json(v0.3 은 *_full.json)
            with open(os.path.join(WALP, "eval", "results", f"lang_{name}_v04.json"), encoding="utf-8") as f:
                rec = json.load(f)
            for k in ("ok_exact", "wrong_execution", "reject_refused", "amb_asked"):
                ok(got[k] == rec[k], f"{name}: {k} = {got[k]} (기록 {rec[k]})")
        # 봉인 v5: 한 번 채점한 v0.4 기록과 같은가 + 잘못 실행이 기준선(v0.3)보다 늘지 않았는가
        v5 = os.path.join(WALP, "eval", "parse_v5.tsv")
        ok(hashlib.sha256(open(v5, "rb").read()).hexdigest().startswith("4cf0a32e6dc9a554"), "봉인 v5 sha 그대로")
        got5 = json.loads(subprocess.run([cli, "corpus", v5], capture_output=True, text=True, env=env).stdout)
        with open(os.path.join(WALP, "eval", "results", "lang_v5_v04.json"), encoding="utf-8") as f:
            rec5 = json.load(f)
        with open(os.path.join(WALP, "eval", "results", "lang_v5_base_v03.json"), encoding="utf-8") as f:
            base5 = json.load(f)
        for k in ("ok_exact", "wrong_execution", "reject_refused", "amb_asked"):
            ok(got5[k] == rec5[k], f"v5: {k} = {got5[k]} (기록 {rec5[k]})")
        ok(got5["wrong_execution"] <= base5["wrong_execution"], f"v5 잘못 실행이 v0.3 보다 안 늘었다 ({got5['wrong_execution']} ≤ {base5['wrong_execution']})")
        dev = json.loads(subprocess.run([cli, "corpus", os.path.join(WALP, "eval", "dev_corpus.tsv")],
                                        capture_output=True, text=True, env=env).stdout)
        ok(dev["wrong_execution"] == 0 and dev["ok_exact"] == dev["n_ok"], "개발 문장 전부 맞음(순환 — 동작 확인일 뿐)")

        # v0.3 자기개선 고리(짧게): 환경 B 한 흐름. 짝지은 검정 고리가 '막힘 → 대기' 를 증명하고 승격하는가 ·
        # 안전 위반 0 · 예산을 안 넘는가. (기대는 먼저 적었다 — 전체 실행 5흐름 중 5흐름이 이것을 승격했다)
        si = subprocess.run([cli, "selfimprove", "--quick", "--no-mutation", "--train", "60", "--streams", "1"],
                            capture_output=True, text=True, env=env, timeout=300)
        try:
            sj = json.loads(si.stdout)
        except ValueError:
            sj = {"domains": []}
        rows = [r for d in sj["domains"] for r in d["rows"]]
        se2 = [r for d in sj["domains"][:1] for r in d["rows"] if r["system"] == "se2_paired"]
        ok(bool(se2) and "change=13" in " ".join(e for e in se2[0]["events"] if "PROMOTE" in e),
           "자기개선 고리(se2)가 환경 B 에서 '막힘 → 대기' 를 검정으로 승격")
        se_rows = [r for r in rows if r["system"].startswith("se")]
        ok(bool(se_rows) and all(0 < r["episodes_used"] <= r["budget"] for r in se_rows),
           "SE 고리가 예산(v0.2 와 같은 에피소드 수)을 안 넘는다")
        ok(bool(rows) and all(r["D_after"]["violations"] == 0 and r["A_after"]["violations"] == 0 for r in rows), "자기개선 뒤 안전 위반 0")

        # v3 고리(배율 이웃 + 패턴 이동 + 무익 정지)가 대기 평탄부(≥16)까지 가는가 — 환경 B 한 흐름, 예산 3배.
        # 기대는 먼저 적었다: 전체 실행(평가 대역 80000)에서 5흐름 중 4흐름이 대기 20 에 닿았고, v2 는 3배 예산에서도
        # 5흐름 모두 8 에서 멈췄다(walp/eval/results/selfimprove_v3_*.json)
        s3 = subprocess.run([cli, "selfimprove", "--quick", "--no-mutation", "--train", "60", "--streams", "1",
                             "--budget-mult", "3", "--domain", "B", "--only", "se3"],
                            capture_output=True, text=True, env=env, timeout=600)
        try:
            r3 = [r for r in json.loads(s3.stdout)["domains"][0]["rows"] if r["system"] == "se3"]
        except (ValueError, IndexError, KeyError):
            r3 = []
        ok(bool(r3) and r3[0]["params"]["rules"]["blocked"] == "hold" and r3[0]["params"]["blocked_wait"] >= 16,
           f"v3 고리가 막힘→대기 + 대기 ≥16 에 닿는다 ({r3[0]['params']['blocked_wait'] if r3 else '실행 실패'})")

        # MCP: 초기화 → 도구 목록 → 모호한 말은 실행하지 않고 후보 → 모르는 말은 거부
        reqs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "walp_interpret", "arguments": {"text": "find the container"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "walp_run", "arguments": {"text": "파란 비자카드 찾아줘", "seed": 3}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "walp_interpret", "arguments": {"text": "find a yellow cup"}}},
        ]
        p = subprocess.run([sys.executable, os.path.join(WALP, "mcp_server.py")], input="\n".join(json.dumps(x) for x in reqs) + "\n",
                           capture_output=True, text=True, timeout=300, env=env)
        outs = {d["id"]: d for d in (json.loads(l) for l in p.stdout.splitlines() if l.strip())}
        ok(outs.get(1, {}).get("result", {}).get("serverInfo", {}).get("name") == "walp", "MCP initialize")
        ok(2 not in outs or len(outs[2]["result"]["tools"]) == 9, "MCP 도구 아홉")
        ok(set(outs) == {1, 2, 3, 4, 5}, "알림에는 답하지 않고 요청 다섯에는 답한다")
        t3 = outs[3]["result"]["content"][0]["text"]
        ok("1) 컵 찾기" in t3 and "2) 상자 찾기" in t3, "모호한 말 → 실행 없이 후보 둘")
        t4 = outs[4]["result"]["content"][0]["text"]
        ok("파란 비자 카드 찾기" in t4 and "시뮬레이션" in t4, "run → 해석 + 시뮬 결과")
        ok("'yellow' 는 모르는 말" in outs[5]["result"]["content"][0]["text"], "모르는 말은 추측 없이 거부")
        with open(os.path.join(tmp, "walp_usability.jsonl"), encoding="utf-8") as f:
            ledger = [json.loads(l) for l in f if l.strip()]
        명령줄 = [z for z in ledger if z.get("kind") != "dialog"]     # 2026-09-30: run 마다 대화 행위 줄(kind=dialog)도 하나씩 붙는다
        ok(len(명령줄) == 3 and all(len(z["who"]) == 12 for z in ledger), "사용성 원장에 명령 세 줄(+대화 행위 줄), 호출자는 해시")

        # 원장 집계를 손으로 센 값과 대조
        sys.path.insert(0, REPO)
        os.environ["SE_LEDGER_ROOT"] = tmp
        from walp import usability
        ok(usability.sus_score([5, 1, 5, 1, 5, 1, 5, 1, 5, 1]) == 100.0 and usability.sus_score([3] * 10) == 50.0,
           "SUS 점수 공식(Brooke 1996): 최고 100, 전부 3 이면 50")
        t0 = 1_000_000.0
        fake = [
            {"ts": t0, "who": "a", "kind": "run", "status": "unsupported", "reason": "unknown_word", "token": "zz"},
            {"ts": t0 + 5, "who": "a", "kind": "run", "status": "ok", "outcome": "success"},
            {"ts": t0 + 10, "who": "b", "kind": "interpret", "status": "ambiguous"},
            {"ts": t0 + 20, "who": "b", "kind": "interpret", "status": "ok"},
            {"ts": t0 + 5000, "who": "b", "kind": "run", "status": "unsupported", "reason": "negation"},   # 30분 넘어 새 세션
        ]
        s = usability.집계(fake)
        ok(s["세션"] == 3 and s["첫시도_성공"] == [0, 3], "세션 셋(30분 규칙), 첫 시도 성공 0")
        ok(s["포기한_세션"] == [1, 3] and s["되묻기_뒤_회복"] == [1, 1], "포기 1 · 되묻기 뒤 회복 1/1")
        ok(s["모르는_낱말_상위"] == [("zz", 1)] and s["임무_성공"] == [1, 1], "모르는 낱말 · 임무 성공 집계")

        # dispatch 에 실렸나(LLM 앞)
        import dispatch
        ok(any(getattr(m, "PREFIX", "") == "!walp" for m in dispatch.명령들), "!walp 가 dispatch 명령들에 있다")
        ok(dispatch.run("!walp 도움") and "WALP" in dispatch.run("!walp 도움"), "!walp 도움 이 답한다")
        ok(dispatch.run("!walpish 아무거나") is None, "붙여 쓴 !walpish 는 명령이 아니다")
        ok("관리 채널" in dispatch.run("!walp 가르치기 a color blue", allow_write=False), "가르치기는 관리 채널에서만")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_all()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nWALP 검사 통과(빌드·코어 시험·봉인 문장·MCP·사용성 원장·dispatch)")
