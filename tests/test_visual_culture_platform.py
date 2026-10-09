"""visual_culture_platform/ 의 자체 검사를 저장소 검사 경로(scripts/tests.sh · CI)에 묶는다.

    python3 tests/test_visual_culture_platform.py

그 프로젝트는 따로 떼어 Antigravity 로 넘기는 독립 파이썬 프로젝트라 검사도 제 폴더에
있다(`visual_culture_platform/tests/run_tests.py`, pytest 없이 돈다). 여기서는 그것을
**실제로 돌려** 종료 코드와 마지막 요약 줄을 본다 -- 파일이 있는지만 보면 안 도는 검사도
초록이 된다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "visual_culture_platform" / "tests" / "run_tests.py"

proc = subprocess.run([sys.executable, str(RUNNER)], capture_output=True, text=True, timeout=600)
lines = [l for l in proc.stdout.splitlines() if l.strip()]
summary = next((l for l in reversed(lines) if " passed, " in l and " failed" in l), "")
failed = [l for l in lines if l.startswith("FAIL") or l.startswith("ERROR")]

if proc.returncode != 0 or not summary or " 0 failed" not in summary:
    print("\n".join(lines[-40:]))
    print(proc.stderr[-2000:])
    print(f"visual_culture_platform: 실패 -- {summary or '요약 줄 없음'} {failed[:5]}")
    sys.exit(1)
print(f"visual_culture_platform: {summary.strip()} -- 통과")
