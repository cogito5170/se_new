#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph/digest.py -- '지은 때' 만 바뀐 것은 바뀐 것이 아니다.

실측 2026-09-29: precheck 에서 test_night_돌리기 가 '새것이 없으면 원격이 안 움직인다' 에 한 번 걸렸다
(8번 중 1번). 요지문에 분 단위 시각이 박혀 있어, 두 번째 night.sh 가 **다른 분**에 돌면 내용이 같아도 파일이
바뀌고 -> 커밋 -> 밀기가 났다. VM 의 밤 작업도 새것 없이 시각만 바뀐 커밋을 낼 수 있었다.

진짜 저장소를 흉내 낸 임시 자리에서 **시각을 한 분 옮겨** 두 번 쓰고, 파일이 그대로인지 본다.
음성 대조: 내용이 바뀌면 파일도 바뀌어야 한다.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from graph import digest  # noqa: E402

fails = []


def ok(c, m):
    print(("  통과  " if c else "  실패  ") + m)
    if not c:
        fails.append(m)


판 = Path(tempfile.mkdtemp(prefix="digest-"))
진짜 = time.gmtime
try:
    time.gmtime = lambda *a: time.struct_time((2026, 9, 29, 17, 1, 0, 1, 272, 0))
    p = digest.쓰기(판)
    첫 = p.read_text(encoding="utf-8")
    time.gmtime = lambda *a: time.struct_time((2026, 9, 29, 17, 2, 0, 1, 272, 0))
    digest.쓰기(판)
    ok(p.read_text(encoding="utf-8") == 첫, "시각만 한 분 옮겨 다시 지으면 파일이 그대로다")
    원래짓기 = digest.짓기
    digest.짓기 = lambda repo=None: 원래짓기(repo) + "\n- 새 줄\n"
    digest.쓰기(판)
    ok(p.read_text(encoding="utf-8") != 첫, "내용이 바뀌면 파일도 바뀐다(음성 대조)")
    digest.짓기 = 원래짓기
finally:
    time.gmtime = 진짜
print("\ndigest: 시각만 바뀐 것은 안 쓴다 --", "통과" if not fails else f"실패 {len(fails)}")
sys.exit(1 if fails else 0)
