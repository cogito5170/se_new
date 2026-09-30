#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WALP 터미널 대화(`python3 -m walp.chat`)를 **파이프로 실제로 돌려** 본다.

기대: 접두사 없는 말을 WALP 가 받는다 · `끝` 에서 나간다 · 원장에 via=terminal 로만 적힌다 · 흔적 없음.
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = []


def ok(c, label):
    print(f"    {'OK  ' if c else '실패'} {label}")
    if not c:
        fails.append(label)


def st():
    return subprocess.run(["git", "status", "--porcelain", "-uno"], cwd=REPO, capture_output=True, text=True).stdout


before = st()
tmp = tempfile.mkdtemp(prefix="walp-chat-")
env = {**os.environ, "SE_LEDGER_ROOT": tmp, "WALP_AUTO_EVOLVE": "0"}
r = subprocess.run([sys.executable, "-m", "walp.chat"], cwd=REPO, env=env, capture_output=True, text=True, timeout=600,
                   input="파란 비자카드 찾아줘\n\n도움\n끝\n이건 안 읽힌다\n")
ok(r.returncode == 0, f"끝나고 0 으로 나간다 ({r.returncode} {r.stderr[-200:]!r})")
ok("알아들음" in r.stdout or "빌드" in r.stdout, "접두사 없는 명령을 WALP 가 받았다")
ok("**WALP**" in r.stdout, "`도움` 이 WALP 도움말")
p = os.path.join(tmp, "walp_usability.jsonl")
줄 = [z for z in (json.loads(x) for x in open(p, encoding="utf-8")) if z.get("kind") != "dialog"] if os.path.exists(p) else []
ok(len(줄) == 1 and 줄[0]["via"] == "terminal", f"원장에 via=terminal 한 줄 — `끝` 뒤 말은 안 읽힌다 ({[(z.get('kind'), z.get('via')) for z in 줄]})")
ok(st() == before, "추적 파일 변화 없음")
print("\n전부 통과" if not fails else f"\n실패 {len(fails)}")
sys.exit(1 if fails else 0)
