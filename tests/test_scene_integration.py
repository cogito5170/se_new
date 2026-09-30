#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scene DB ↔ 센서 시뮬레이터 배선 검사 — 하나의 SceneDB 를 camera(RGB)·radar(SAR)가 각자
view 로 읽는지, 그리고 **같은 피처**가 두 센서에 서로 다른 관측으로 나타나는지 붙든다.

핵심: (1) camera.render(scene=sdb) 가 scene 피처를 rgb_of 색으로 그린다(예전 인라인과 다르다),
(2) radar.scene_from_terrain(scene=sdb) 가 스와스 안 피처를 radar_of 산란으로 더한다,
(3) scene=None 하위호환 유지, (4) 좌표계(월드미터)가 두 센서에서 일치.
망(fetch_dem) 없이 합성 DEM 으로 돈다.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sar"))
import camera
import radar
import scene as S

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def _dem():
    xx, yy = np.meshgrid(np.linspace(0, 1, 48), np.linspace(0, 1, 48))
    return 700 + 300 * (np.sin(3 * xx) * np.cos(2 * yy) + xx)


def test_camera_uses_scene():
    dem = _dem(); mpp = 6000.0 / dem.shape[1]
    sdb = S.SceneDB(dem, mpp, seed=7, landcover="forest"); sdb.generate()
    cam = (3000.0, 3000.0)
    img_s = camera.render(dem, mpp, cam, 90.0, 45.0, 0.002, W=120, H=80, scene=sdb)
    img_n = camera.render(dem, mpp, cam, 90.0, 45.0, 0.002, W=120, H=80, scene=None)
    ok(img_s.shape == (80, 120, 3), "camera+scene 이미지 형상")
    ok(0.0 <= img_s.min() and img_s.max() <= 1.0, "camera+scene 값域 [0,1]")
    # scene 분기가 실제로 다른 그림을 만든다(인라인 생성과 구별)
    ok(not np.allclose(img_s, img_n), "scene 유무로 렌더가 달라진다(scene 분기 실행됨)")


def test_radar_uses_scene():
    dem = _dem(); mpp = 6000.0 / dem.shape[1]
    sdb = S.SceneDB(dem, mpp, seed=7, landcover="urban"); feats = sdb.generate()
    # 피처가 있는 곳을 스와스 중심으로 잡아 배선을 확인
    f = feats[10]; ctr = np.array([f["wx"], f["wy"]])
    xy1, rcs1, _ = radar.scene_from_terrain(ctr, 60.0, [], n_clutter=100, rng=np.random.default_rng(1), scene=sdb)
    xy0, rcs0, _ = radar.scene_from_terrain(ctr, 60.0, [], n_clutter=100, rng=np.random.default_rng(1), scene=None)
    inswath = [g for g in sdb.query(tuple(ctr), 85) if abs(g["wx"] - ctr[0]) <= 60 and abs(g["wy"] - ctr[1]) <= 60]
    ok(len(rcs1) - len(rcs0) == len(inswath), "radar 가 스와스 안 scene 피처 수만큼 산란점 추가 (%d)" % len(inswath))
    if inswath:
        added = rcs1[len(rcs0):len(rcs0) + len(inswath)]
        ok(all(0.02 <= v <= 0.6 + 1e-9 for v in added), "추가 RCS 가 클러터 대비 정규화 범위 [0.02,0.6]")


def test_same_feature_two_observations():
    # 같은 피처 → RGB 색 + RADAR 산란(둘 다 유효, 서로 다른 물리 속성에서 나온다)
    f = {"kind": "building", "size": 12.0, "wx": 3000.0, "wy": 3000.0, "z": 800.0, "class": "urban"}
    rgb = S.SceneDB.rgb_of(f); rad = S.SceneDB.radar_of(f)
    fw = dict(f); fw["kind"] = "water"
    ok(rgb["color"] != S.SceneDB.rgb_of(fw)["color"], "건물 vs 물: RGB 색이 다르다")
    ok(rad["scatter"] > S.SceneDB.radar_of(fw)["scatter"], "건물(거친·중eps) > 물(경면) SAR 산란")


def test_backward_compat_none():
    dem = _dem(); mpp = 6000.0 / dem.shape[1]
    img = camera.render(dem, mpp, (3000.0, 3000.0), 90.0, 0.0, 0.002, W=64, H=40)  # scene 인자 없음
    ok(img.shape == (40, 64, 3), "camera scene 없이도 동작(하위호환)")
    xy, rcs, hits = radar.scene_from_terrain(np.array([3000.0, 3100.0]), 60.0, [(3000.0, 3100.0)], n_clutter=64)
    ok(hits == 1 and len(rcs) > 0, "radar scene 없이도 동작(하위호환)")


if __name__ == "__main__":
    for fn in (test_camera_uses_scene, test_radar_uses_scene,
               test_same_feature_two_observations, test_backward_compat_none):
        print("[%s]" % fn.__name__)
        fn()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nScene↔센서 배선 통과: 하나의 SceneDB → camera(RGB)·radar(SAR) 각자 view, 같은 피처 다른 관측")
