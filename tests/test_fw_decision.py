#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fw/ LLM 없는 자율 결정 executive 를 **실제로 컴파일·실행**해 행동을 검증(스텁 아님).

bash -n 같은 표면검사가 아니라 gcc 로 빌드해 host_test 를 끝까지 돌린다 — 외로운 센서 억제·
코로보 확인·안전 override·FDIR·arbiter·건강가중이 실제로 그렇게 동작하는지 본다.
gcc/make 없으면 건너뛴다(환경 한정, 거짓 초록 방지 위해 사유를 찍는다)."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FW = os.path.join(REPO, "fw")
fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def test_build_and_run():
    if shutil.which("make") is None or (shutil.which("cc") is None and shutil.which("gcc") is None):
        print("    건너뜀: make/cc 없음(환경 한정) — CI 러너에서 돈다")
        return
    subprocess.run(["make", "-C", FW, "clean"], capture_output=True, text=True)
    r = subprocess.run(["make", "-C", FW, "test"], capture_output=True, text=True)
    out = r.stdout + r.stderr
    print(out)
    ok(r.returncode == 0, "fw host_test 컴파일·실행 통과(exit 0, -Werror)")
    ok("외로운 Audio 는 확인 안 됨" in out, "오경보 억제(외로운 센서) 검사가 실제로 돌았다")
    ok("확인된 표적 → INSPECT" in out, "코로보 확인 → INSPECT 검사가 실제로 돌았다")
    ok("충돌 임박 → AVOID override" in out, "안전 supervisor override 검사가 실제로 돌았다")
    ok("FDIR 이벤트 2건" in out, "FDIR(센서고장 이벤트) 검사가 실제로 돌았다")
    subprocess.run(["make", "-C", FW, "clean"], capture_output=True, text=True)  # 흔적 안 남긴다


if __name__ == "__main__":
    test_build_and_run()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nfw 결정 executive 검사 통과(컴파일·실행·행동)")
