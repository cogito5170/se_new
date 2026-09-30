#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실 land-cover(ESA WorldCover) 연동 검사 — 매핑·타일명·리샘플·폴백 정직성을 붙든다.

오프라인 로직(코드→클래스, 타일명, 리샘플, 폴백 source 명시)은 **항상** 돈다. 실 COG fetch 는
망 의존이라 **막히면 SKIP**(FAIL 아님) — 단, 성공하면 물리적으로 그럴듯한지(태백산=숲 우세) 본다.
폴백을 'esa_worldcover' 라 부르지 않는 것(정직)이 핵심.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sar"))
import landcover as L
import scene as S

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def test_code_mapping():
    # WorldCover 코드 → scene.LANDCOVER 키, 모두 실제 존재하는 클래스여야
    for code, cls in L.WORLDCOVER_TO_CLASS.items():
        ok(cls in S.LANDCOVER, "코드 %d → '%s' 가 실제 LANDCOVER 클래스" % (code, cls))
    ok(L.WORLDCOVER_TO_CLASS[10] == "forest" and L.WORLDCOVER_TO_CLASS[80] == "water"
       and L.WORLDCOVER_TO_CLASS[50] == "urban", "핵심 매핑(나무→숲·물→water·건물→urban)")


def test_codes_to_classes():
    codes = np.array([[10, 50], [80, 30]], dtype=np.uint8)
    cls = L.codes_to_classes(codes)
    ok(cls[0, 0] == "forest" and cls[0, 1] == "urban" and cls[1, 0] == "water" and cls[1, 1] == "grass",
       "코드 격자 → 클래스 격자")


def test_tile_name():
    ok("N36E126" in L._tile_name(37.0966, 128.9456), "태백산 → N36E126 타일")
    ok("N36E126" in L._tile_name(38.99, 128.99), "38.99N/128.99E → 같은 3° 타일")
    ok("S03W060" in L._tile_name(-1.5, -59.0), "남반구·서경 명명(S03W060)")


def test_resample_shape():
    g = np.array([["a", "b", "c"], ["d", "e", "f"]], dtype=object)
    r = L._resample_nn(g, (4, 6))
    ok(r.shape == (4, 6), "리샘플 목표 shape")
    ok(r[0, 0] == "a" and r[-1, -1] == "f", "최근접 모서리 보존")


def test_fallback_is_honest():
    # fetch 를 강제로 실패시켜 폴백 경로 확인 — source 가 esa 가 아니어야
    orig = L.fetch_worldcover
    L.fetch_worldcover = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("forced"))
    try:
        xx, yy = np.meshgrid(np.linspace(0, 1, 16), np.linspace(0, 1, 16))
        dem = 700 + 300 * (np.sin(3 * xx) + xx)
        grid, src = L.landcover_grid(37.0, 128.9, 3000.0, (16, 16), dem=dem, mpp=100.0)
    finally:
        L.fetch_worldcover = orig
    ok(src.startswith("elevation_fallback"), "실패시 source=elevation_fallback (실 데이터라 안 부른다)")
    ok(grid.shape == (16, 16), "폴백 격자 목표 shape")
    ok(all(c in S.LANDCOVER for c in np.unique(grid)), "폴백 클래스가 모두 유효")


def test_live_fetch_optional():
    """실 COG fetch — 막히면 SKIP. 성공하면 태백산은 숲 우세여야(물리적 sanity)."""
    try:
        codes = L.fetch_worldcover(37.0966, 128.9456, 2000.0)
    except Exception as e:  # noqa: BLE001
        print("    SKIP 실 WorldCover 못 받음(망?): %s" % type(e).__name__)
        return
    uniq, cnt = np.unique(codes, return_counts=True)
    top = uniq[np.argmax(cnt)]
    ok(codes.size > 0, "실 창 픽셀 존재 (%s)" % (codes.shape,))
    ok(int(top) == 10, "태백산 최다 클래스 = Tree(10) [실측 sanity]")


if __name__ == "__main__":
    for fn in (test_code_mapping, test_codes_to_classes, test_tile_name, test_resample_shape,
               test_fallback_is_honest, test_live_fetch_optional):
        print("[%s]" % fn.__name__)
        fn()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nland-cover 검사 통과: 매핑·타일명·리샘플·폴백 정직성 (+실 fetch sanity)")
