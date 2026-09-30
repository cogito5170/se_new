#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파이프라인 4계층 실측 검사 — 수가 **실측**이고 과장방지 4검사가 실제로 걸리는지 붙든다.

핵심: (1) 지연은 벽시계로 재고 양수·유한(추정치 아님), (2) 데이터율은 실 nbytes 이고 계산값과
일치(독립 대조), (3) 동작점이 성함(렌더 유효), (4) 정확도를 오프라인에서 **지어내지 않는다**
(render_md 가 대리수 거부 문구를 낸다). 망 없이 합성 DEM 으로 돈다.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sar"))
import measure as M

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def test_measures_are_real():
    r = M.measure_environment("forest", k=2)
    la = r["latency"]; d = r["drate"]; w = r["world"]
    ok(la["rgb_ms"] > 0 and la["sar_ms"] > 0, "지연이 양수(벽시계 실측)")
    import math
    ok(all(math.isfinite(v) for v in (la["rgb_ms"], la["sar_ms"], la["rgb_cpu_ms"], la["sar_cpu_ms"])), "지연 유한")
    ok(w["mpp_m"] > 0 and w["n_features"] > 0, "세계해상도·피처수 실측")
    ok(d["rgb_frame_B"] > 0 and d["sar_raw_frame_B"] > 0, "데이터율 실 바이트")


def test_datarate_crosscheck():
    r = M.measure_environment("urban", k=2)
    ok(r["drate"]["rgb_calc_matches"], "RGB nbytes = H·W·3·itemsize (독립 대조 일치)")


def test_operating_point_sound():
    r = M.measure_environment("alpine", k=2)
    ok(r["sound"] and r["rgb_valid"] and r["sar_valid"], "동작점 성함(RGB∈[0,1]·SAR raw 유한)")


def test_no_fabricated_accuracy():
    r = M.measure_environment("desert", k=2)
    md = M.render_md([r], accuracy=None)
    ok("정확도라 부르지 않는다" in md, "오프라인 정확도 대리수 거부 문구(검사 4)")
    ok("임베디드 HW 아님" in md, "임베디드 아님 한계 명시")
    ok("[출처:조각]" in md, "대표값 인용을 조각으로 표시")
    # 정확도를 주면 표가 생긴다
    md2 = M.render_md([r], accuracy=[dict(env="desert", V=3000.0, detection_rate=50.0, loc_rmse_cells=1.2)])
    ok("탐지율" in md2 and "50%" in md2, "정확도 주면 ④ 표 채워짐")


def test_environments_differ():
    # land-cover 로 피처 수가 갈린다(다양한 공간) — 같은 seed, 다른 환경
    a = M.measure_environment("forest", k=1)["world"]["n_features"]
    b = M.measure_environment("coast", k=1)["world"]["n_features"]
    ok(a != b, "환경별로 피처 수가 다르다 (forest %d vs coast %d)" % (a, b))


if __name__ == "__main__":
    for fn in (test_measures_are_real, test_datarate_crosscheck, test_operating_point_sound,
               test_no_fabricated_accuracy, test_environments_differ):
        print("[%s]" % fn.__name__)
        fn()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\n측정 검사 통과: 벽시계 실측·데이터율 대조·동작점·정확도 대리수 거부")
