#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fw fault-injection replay 하네스를 실제로 컴파일·실행(스텁 아님, 네트워크 불필요).

결정성 replay + 센서 dropout·공분산 폭발·planner 오염·actuator 고장 FDIR + stale gap.
gcc/make 없으면 건너뛴다(환경 한정)."""
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


def test_fault():
    if shutil.which("make") is None or (shutil.which("cc") is None and shutil.which("gcc") is None):
        print("    건너뜀: make/cc 없음(환경 한정) — CI 러너에서 돈다")
        return
    b = subprocess.run(["make", "-C", FW, "fault_test"], capture_output=True, text=True)
    ok(b.returncode == 0, "fault_test 컴파일(-Werror)")
    if b.returncode != 0:
        print(b.stdout + b.stderr); return
    r = subprocess.run([os.path.join(FW, "fault_test")], capture_output=True, text=True)
    out = r.stdout + r.stderr
    print(out)
    ok(r.returncode == 0, "fault-injection replay 전부 통과(exit 0)")
    ok("deterministic=1" in out, "기록 장면 재생 → 동일 행동열(결정성)")
    ok("EV_SENSOR_FAIL" in out, "센서 dropout FDIR")
    ok("공분산 성장" in out, "KF 공분산 폭발 가드")
    ok("EV_SENSOR_STALE" in out, "stale 차등 검출(얼어붙은 채널 격리)")
    ok("모두-정지는 stale 로 못 거른다" in out, "모두-정지 잔여 gap 을 정직히 기록(liveness 몫)")
    subprocess.run(["make", "-C", FW, "clean"], capture_output=True, text=True)


if __name__ == "__main__":
    test_fault()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nfw fault-injection 검사 통과")
