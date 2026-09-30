#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CMPC(교차모달 물리 일관성) 규칙 검사(네트워크 불필요, 합성 obs).

단일모달 clutter 는 ≥2 로 거르고, 가림-강 채널 단독 진짜는 조건부로 살리며, 전-서명 decoy 는
CMPC 로 통과하되 liveness 로만 걸린다 — #449 관측가능성 경계의 규칙을 못박는다."""
from __future__ import annotations
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "sar", "ivv")); sys.path.insert(0, os.path.join(REPO, "sar"))
import policies as pol

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def _obs(**dets):
    """dets: rgb=[(x,y,c)], sar=..., live=... → obs 딕셔너리."""
    o = {k: {"detections": []} for k in ("rgb", "sar", "thermal", "lidar", "audio", "live")}
    for k, v in dets.items():
        o[k] = {"detections": v}
    return o


def test_cmpc():
    C = pol.cmpc_confirm
    # 단일모달(RGB 만): spatial(≥1) 통과, CMPC(≥2) 기각
    o = _obs(rgb=[(10, 10, 0.9)])
    ok(len(C(o, cmpc_min=1)) == 1, "단일모달 → spatial(≥1) 은 claim")
    ok(len(C(o, cmpc_min=2, conditional=False)) == 0, "단일모달 광학 → CMPC(≥2) 기각(clutter 억제)")
    # 가림-강 채널(SAR) 단독 진짜: strict 는 버리고 conditional 은 살린다
    os_ = _obs(sar=[(10, 10, 0.5)])
    ok(len(C(os_, cmpc_min=2, conditional=False)) == 0, "SAR 단독 → strict 는 기각(진짜 손실 위험)")
    ok(len(C(os_, cmpc_min=2, conditional=True)) == 1, "SAR 단독 → conditional 은 살림(수관 진짜 보존)")
    # 교차모달 일치(RGB+Thermal 같은 자리): CMPC 통과
    o2 = _obs(rgb=[(10, 10, 0.9)], thermal=[(10.2, 9.9, 0.7)])
    ok(len(C(o2, cmpc_min=2)) == 1, "RGB+Thermal 코로보 → CMPC 통과")
    # 전-서명 decoy(RGB+Thermal+LiDAR, liveness 없음): CMPC 통과, liveness 로만 기각
    dec = _obs(rgb=[(10, 10, 0.9)], thermal=[(10.1, 10, 0.7)], lidar=[(10, 10.1, 0.8)])
    ok(len(C(dec, cmpc_min=2)) == 1, "전-서명 decoy → CMPC 는 통과(관측가능성 한계)")
    ok(len(C(dec, cmpc_min=2, require_live=True)) == 0, "decoy → liveness 요구 시 기각(호흡·심박 없음)")
    # 진짜(같은 서명 + liveness): liveness 요구도 통과
    real = _obs(rgb=[(10, 10, 0.9)], thermal=[(10.1, 10, 0.7)], lidar=[(10, 10.1, 0.8)], live=[(10, 10, 0.9)])
    ok(len(C(real, cmpc_min=2, require_live=True)) == 1, "진짜(liveness 있음) → liveness 요구도 통과")


if __name__ == "__main__":
    test_cmpc()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nCMPC 규칙 검사 통과(단일모달 억제·가림채널 조건부 보존·decoy 는 liveness 로만)")
