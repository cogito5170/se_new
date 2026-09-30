#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scene DB 검사 — '하나의 세계, 센서마다 다른 관측' 과 '절차생성·LOD' 가 실제로 그런지.

핵심: (1) 같은 피처가 RGB·Radar·LiDAR 에서 **다른 속성**을 낸다(하나의 세계 여러 관측),
(2) 절차생성이 결정적(seed), (3) LOD 가 먼 곳 작은 피처를 버려 데이터량을 제어, (4) 장소가
바뀌어도 센서 view 함수는 그대로. 대표값의 물리적 순서(물 eps ≫ 모래)도 자명검사로 붙든다.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sar"))
import scene as S

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def _dem():
    xx, yy = np.meshgrid(np.linspace(0, 1, 24), np.linspace(0, 1, 24))
    return 700 + 300 * (np.sin(3 * xx) * np.cos(2 * yy) + xx)


def test_material_per_sensor_distinct():
    # 모든 kind 가 네 센서 속성을 다 가진다
    for kind, m in S.MATERIAL.items():
        ok(all(k in m for k in ("rgb", "eps", "rough", "lidar")), "material[%s] 4속성 완비" % kind)
    # 물리 대표값 순서: 물 eps ≫ 모래, 초목 eps > 건조암반
    ok(S.MATERIAL["water"]["eps"] > 10 * S.MATERIAL["sand"]["eps"], "물 eps ≫ 모래 eps")
    ok(S.MATERIAL["tree"]["eps"] > S.MATERIAL["rock"]["eps"], "초목(수분) eps > 건조 암반")


def test_one_world_many_observations():
    f = {"kind": "tree", "size": 6.0, "wx": 0.0, "wy": 0.0, "z": 0.0, "class": "forest"}
    rgb = S.SceneDB.rgb_of(f); rad = S.SceneDB.radar_of(f); lid = S.SceneDB.lidar_of(f)
    ok("color" in rgb and "scatter" in rad and "reflectivity" in lid, "센서별 view 키가 다르다")
    # 같은 나무 vs 같은 크기 물(경면·고eps)은 radar 산란이 달라야(속성이 관측을 가른다)
    fw = dict(f); fw["kind"] = "water"
    ok(rad["scatter"] != S.SceneDB.radar_of(fw)["scatter"], "같은 크기라도 kind 로 radar 산란이 갈린다")
    ok(S.SceneDB.rgb_of(f)["color"] != S.SceneDB.rgb_of(fw)["color"], "RGB 색도 kind 로 갈린다")


def test_procedural_deterministic():
    dem = _dem()
    a = S.SceneDB(dem, 250.0, seed=11, landcover="forest").generate()
    b = S.SceneDB(dem, 250.0, seed=11, landcover="forest").generate()
    c = S.SceneDB(dem, 250.0, seed=12, landcover="forest").generate()
    ok(len(a) == len(b) and a[0] == b[0], "같은 seed → 같은 피처(결정적)")
    ok(len(a) > 0, "피처가 절차적으로 생성됨 (%d개)" % len(a))
    ok(not (len(a) == len(c) and a[10] == c[10]), "다른 seed → 다른 피처")


def test_lod_controls_data():
    dem = _dem()
    sc = S.SceneDB(dem, 250.0, seed=5, landcover="desert")
    sc.generate()
    cx = dem.shape[1] * 250.0 / 2; cy = dem.shape[0] * 250.0 / 2
    near = sc.query((cx, cy), 300.0)
    far = sc.query((cx, cy), 1500.0)
    ok(len(far) >= len(near), "반경 넓으면 피처 수 증가 (%d ≥ %d)" % (len(far), len(near)))
    # LOD 컬링: 먼 대역엔 최소크기 미만이 없어야
    for g in far:
        minsize, _tex, band = S.lod_for(g["dist"])
        if g["size"] < minsize:
            fails.append("LOD 컬링 위반: 크기 %.2f < 최소 %.2f @대역 %d" % (g["size"], minsize, band))
            break
    else:
        ok(True, "LOD: 먼 대역의 작은 피처는 컬링됨")
    dr = S.data_rate(sc, (cx, cy), 1500.0)
    ok(dr["total_features"] == len(far), "data_rate 총수 = 쿼리 결과 수")


def test_place_invariant_sensor_views():
    dem = _dem()
    # 같은 view 함수가 숲/사막/도시 피처 모두에 동작(장소 바뀌어도 센서 시뮬 그대로)
    for lc in ("forest", "desert", "urban", "coast", "alpine", "grass"):
        sc = S.SceneDB(dem, 250.0, seed=3, landcover=lc)
        feats = sc.generate(max_features=200)
        if not feats:
            ok(False, "%s 피처 생성" % lc); continue
        f = feats[0]
        r = S.SceneDB.radar_of(f)
        ok(r["scatter"] >= 0 and "color" in S.SceneDB.rgb_of(f), "%s: 동일 센서 view 로 관측 가능" % lc)


def test_ground_material():
    """지면(표면)도 land-cover 로 색·SAR 산란이 갈린다(피처뿐 아니라)."""
    dem = _dem(); mpp = 6000.0 / dem.shape[1]
    lc = np.empty(dem.shape, dtype=object)
    lc[:, :dem.shape[1] // 2] = "forest"    # 지면 soil
    lc[:, dem.shape[1] // 2:] = "alpine"    # 지면 rock
    sdb = S.SceneDB(dem, mpp, seed=7, landcover=lc)
    left = (1000.0, 3000.0); right = (5000.0, 3000.0)
    ok(not np.allclose(sdb.ground_rgb(*left), sdb.ground_rgb(*right)), "지면 RGB 가 land-cover 로 갈린다")
    ok(sdb.ground_scatter(*right) > sdb.ground_scatter(*left), "암반 지면 SAR 산란 > 흙 지면")
    # 표면 산란 물리 순서: 물(경면) ≪ 모래 < 암반
    w = S._surface_scatter(S.MATERIAL["water"]); s = S._surface_scatter(S.MATERIAL["sand"]); r = S._surface_scatter(S.MATERIAL["rock"])
    ok(w < s < r, "표면 산란 물(경면) ≪ 모래 < 암반 (%.3f<%.3f<%.3f)" % (w, s, r))


if __name__ == "__main__":
    for fn in (test_material_per_sensor_distinct, test_one_world_many_observations,
               test_procedural_deterministic, test_lod_controls_data, test_place_invariant_sensor_views,
               test_ground_material):
        print("[%s]" % fn.__name__)
        fn()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nScene DB 검사 통과: 하나의 세계·센서별 다른 관측·절차생성·LOD 데이터량 제어")
