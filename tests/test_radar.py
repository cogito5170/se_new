#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FMCW-SAR 물리 검증 — 측정 초점 스폿을 설계식과 맞춘다(지어낸 해상도 금지).

과장방지: 해상도 수치를 말하려면 **재서** 식과 맞춘다. 단일 점표적을 백프로젝션으로
초점 맺어 -3dB 스폿을 재고, 방위=λR/2L_sa · 지상거리=δr/sinθ 와 같은 규모인지 본다.
또 스와스가 비모호 거리 안이어야 함(넘으면 접힘)을 지킨다.
"""
from __future__ import annotations
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sar"))
import radar                                                          # noqa: E402

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


cfg = radar.RadarCfg()
print("[스펙] 설계식이 스스로 일관되나")
ok(abs(cfg.range_res - 299792458.0 / (2 * cfg.B)) < 1e-6, "δr = c/2B")
ok(abs(cfg.L_sa - cfg.v * cfg.Ti) < 1e-9, "L_sa = v·Ti")
ok(cfg.unambiguous_range > 200, f"비모호 거리 {cfg.unambiguous_range:.0f} m > 200 m")

print("\n[점표적 초점] 측방관측에서 방위·지상거리 해상도가 식과 같은 규모")
alt = 120.0
inc = math.radians(55.0)
Rg = alt * math.tan(inc)
R = math.hypot(Rg, alt)
ok(R < cfg.unambiguous_range, f"스와스 경사거리 {R:.0f} m < 비모호 {cfg.unambiguous_range:.0f} m (안 접힘)")
flight = np.array([0.0, 0.0]); scene = np.array([0.0, Rg])
tgt = np.array([[0.0, Rg]]); rcs = np.array([1.0])
np.random.seed(0)
img_db, ext, meta = radar.sar_image(cfg, tgt, rcs, flight, scene, 0.0, alt, half=6.0, npx=161)
wx, wy = radar._measure_spot(img_db, ext, 161)
da = cfg.az_res(R)                       # 방위 해상도 식
dg = cfg.range_res / math.sin(inc)       # 지상거리 해상도 식
# 해닝창으로 주엽 ~1.6배. 측정이 식의 [0.5, 3]배 안이면 '같은 규모'로 본다(격자·창 감안).
ok(0.5 * da <= wx <= 3.0 * da, f"방위 초점 {wx:.2f} m ~ 식 δa {da:.2f} m (해닝 1.6×)")
ok(0.5 * dg <= wy <= 4.0 * dg, f"지상거리 초점 {wy:.2f} m ~ 식 δr/sinθ {dg:.2f} m")

print("\n[초점의 진짜 위치] 피크가 표적 위치에 온다(엉뚱한 거리 아님)")
H, W = img_db.shape
pk = np.unravel_index(np.argmax(img_db), img_db.shape)
py = ext[2] + (ext[3] - ext[2]) * pk[0] / (H - 1)
px = ext[0] + (ext[1] - ext[0]) * pk[1] / (W - 1)
ok(abs(px - 0.0) < 2.0 and abs(py - Rg) < 3.0, f"초점 피크 ({px:.1f},{py:.1f}) ≈ 표적 (0,{Rg:.1f})")

print("\n[두 점 분해] δa 만큼 떨어진 두 표적이 둘로 보인다")
sep = 1.2                                 # > δa
two = np.array([[-sep / 2, Rg], [sep / 2, Rg]]); rr = np.array([1.0, 1.0])
img2, ext2, _ = radar.sar_image(cfg, two, rr, flight, scene, 0.0, alt, half=6.0, npx=161)
mid = img2.shape[0] // 2
row = img2[mid, :]
# 방위(x)축 중앙행에서 봉우리 2개인지(간단히: 최대 근처와 대칭 위치 둘 다 높은지)
peaks = np.sum((row[1:-1] > row[:-2]) & (row[1:-1] > row[2:]) & (row[1:-1] > row.max() - 6))
ok(peaks >= 2, f"방위로 {sep} m 떨어진 두 표적이 분해된다(봉우리 {peaks}개)")

print("\n[DOA] 배열식이 물리 범위를 준다")
ok(0 < cfg.doa_unambiguous_deg <= 90.0, f"비모호 DOA ±{cfg.doa_unambiguous_deg:.0f}°")
ok(cfg.doa_res_deg > 0, f"DOA 각해상도 {cfg.doa_res_deg:.1f}°")

print()
if fails:
    print("빨강 %d개:" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("초록 — SAR 물리(초점·해상도·위치·분해·DOA) 전부 식과 맞는다")
