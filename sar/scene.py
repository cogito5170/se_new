#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scene Database — 하나의 거대한 3D mesh 가 아니라 **다중해상도·다중속성 세계 데이터베이스**.

NASA/JPL 접근(SimScape·WorldWind·DUST·IDEAS)의 핵심 발상을 이 저장소 규모로 옮긴다:
지구 전체를 나무 하나하나 mesh 로 만들지 않는다. 대신
  · **Geometry**: 지형(DEM) + land-cover(숲/사막/물/풀/암반/도시) + 피처(나무·바위·건물)
  · **Material**: 센서마다 **다른 속성** — RGB(분광반사), Radar/SAR(유전율·거칠기·산란), LiDAR(반사도)
  · **State**: 기상·조도·시각(여기선 인터페이스만)
로 나눠 관리하고, **피처는 land-cover 분포에서 절차적으로 생성**한다(밀도·크기·분포만 저장,
수만 그루를 낱개로 저장하지 않는다). 그리고 **LOD**: 먼 곳은 저해상도, 센서가 보는 근거리만
자세히 — 그래서 **센서 데이터량도 같이 제어**된다.

이렇게 하면 **장소(숲→사막→도시)가 바뀌어도 sensor simulator 는 그대로**고, 바뀌는 건
scene database 뿐이다(camera.py 는 RGB view, radar.py 는 radar view 를 이 DB 에서 읽으면 된다).

**정직**: 여기 material 값은 문헌 **대표값**(representative)이지 측정값이 아니다 [출처:조각].
현장 validation 안 됨. LOD 는 거리대역 컬링(진짜 기하 mesh LOD 아님). 이것은 **아키텍처의
최소 구현**이다 — SimScape/DUST 재현이 아니다.
"""
from __future__ import annotations
import math
import numpy as np


# ── Material: 센서마다 다른 속성 (하나의 객체, 여러 관측) ──
# 값은 문헌 대표값 [출처:조각]. rgb=반사색(0..1), eps=상대유전율(실수부), rough=표면 rms 거칠기[m],
# lidar=근적외 반사도(0..1). 정확한 스펙트럼/편파 의존은 미구현(대표 스칼라).
MATERIAL = {
    #                 rgb(0..1)                 eps(상대유전율)  rough[m]  lidar  emis(LWIR 방사율)
    "tree":     dict(rgb=(0.18, 0.31, 0.16), eps=12.0,        rough=0.35, lidar=0.45, emis=0.98),  # 초목: 수분 많아 eps 큼
    "rock":     dict(rgb=(0.46, 0.43, 0.39), eps=5.5,         rough=0.12, lidar=0.30, emis=0.95),  # 건조 암반
    "building": dict(rgb=(0.62, 0.60, 0.57), eps=6.0,         rough=0.02, lidar=0.55, emis=0.92),  # 콘크리트(평활→정반사)
    "sand":     dict(rgb=(0.76, 0.70, 0.52), eps=2.8,         rough=0.01, lidar=0.35, emis=0.92),  # 건조 모래(eps 작음)
    "grass":    dict(rgb=(0.34, 0.45, 0.24), eps=8.0,         rough=0.05, lidar=0.40, emis=0.97),
    "water":    dict(rgb=(0.16, 0.26, 0.38), eps=80.0,        rough=0.001, lidar=0.05, emis=0.99), # 물: eps 매우 큼, 경면
    "snow":     dict(rgb=(0.86, 0.88, 0.92), eps=1.6,         rough=0.02, lidar=0.85, emis=0.99),
    "soil":     dict(rgb=(0.40, 0.33, 0.24), eps=4.5,         rough=0.03, lidar=0.32, emis=0.95),
}

# ── Land-cover: 절차적 생성 분포(밀도·크기). 낱개 저장 안 함 — 클래스+분포만. ──
LANDCOVER = {
    "forest": dict(ground="soil", feature="tree", density=0.9, size=(4.0, 12.0), rock_density=0.05),
    "desert": dict(ground="sand", feature="rock", density=0.15, size=(0.3, 2.0), rock_density=0.15),
    "urban":  dict(ground="soil", feature="building", density=0.6, size=(6.0, 30.0), rock_density=0.0),
    "coast":  dict(ground="sand", feature="rock", density=0.1, size=(0.2, 1.5), rock_density=0.1),
    "grass":  dict(ground="grass", feature="tree", density=0.2, size=(2.0, 6.0), rock_density=0.03),
    "alpine": dict(ground="rock", feature="rock", density=0.3, size=(0.5, 4.0), rock_density=0.3),
    "water":  dict(ground="water", feature="rock", density=0.0, size=(0.2, 1.0), rock_density=0.0),
}

# ── LOD: 거리대역별 (표현 최소 피처크기[m], 텍스처 해상도[m/px]) ──
# 멀리 있는 세계는 대충(큰 것만·거친 텍스처), 센서가 보는 근거리만 자세히.
LOD_BANDS = [
    (150.0,   0.2,  0.2),    # 근거리(<150m): 20cm 텍스처, 0.2m 이상 피처
    (600.0,   1.0,  1.0),    # 중거리
    (2000.0,  5.0,  5.0),    # 원거리
    (float("inf"), 30.0, 30.0),  # far-field: 30m DEM 만
]


def _surface_scatter(material, wavelength_m=0.031):
    """지면(표면) 상대 후방산란 — 유전 대비 × 거칠기(Rayleigh). 크기항 없음(면이라). [출처:조각]
    물(경면·고eps)은 매끈해 약하고, 암반·모래(거침)는 강하다 — SAR 클러터가 land-cover 를 닮는다."""
    eps = material["eps"]; rough = material["rough"]
    gamma = abs((math.sqrt(eps) - 1) / (math.sqrt(eps) + 1))
    k = 2 * math.pi / wavelength_m
    rough_factor = 1.0 - math.exp(-(k * rough) ** 2)
    return gamma * (0.05 + rough_factor)


def lod_for(dist_m):
    """거리 → (최소피처크기[m], 텍스처해상도[m/px], 대역인덱스)."""
    for i, (dmax, minsize, texres) in enumerate(LOD_BANDS):
        if dist_m < dmax:
            return minsize, texres, i
    return LOD_BANDS[-1][1], LOD_BANDS[-1][2], len(LOD_BANDS) - 1


def classify(elev, slope_m, dmin, drng):
    """DEM 셀 → land-cover 클래스(고도·경사 기반, WorldWind 식 규칙 근사)."""
    if elev > dmin + 0.86 * drng:
        return "alpine"                       # 설선 위
    if slope_m > 0.9:
        return "alpine"                       # 급경사=암반
    if elev < dmin + 0.05 * drng:
        return "coast"                        # 최저지대
    if elev < dmin + 0.58 * drng:
        return "forest"                       # 수목한계 아래
    return "grass"


class SceneDB:
    """다중해상도·다중속성 scene DB. 지형+절차적 피처를 쥐고, 센서별 view 를 낸다."""

    def __init__(self, dem, mpp, seed=0, landcover=None):
        self.dem = np.asarray(dem, dtype=float)
        self.mpp = float(mpp)
        self.DH, self.DW = self.dem.shape
        self.rng = np.random.default_rng(seed)
        self.dmin = float(self.dem.min()); self.drng = float(np.ptp(self.dem)) or 1.0
        # land-cover 맵: 주어지면 쓰고, 없으면 지형에서 분류
        gy, gx = np.gradient(self.dem)
        self.slope = np.hypot(gx, gy) / self.mpp
        if landcover is None:
            self.landcover = np.empty((self.DH, self.DW), dtype=object)
            for j in range(self.DH):
                for i in range(self.DW):
                    self.landcover[j, i] = classify(self.dem[j, i], self.slope[j, i], self.dmin, self.drng)
        elif isinstance(landcover, str):
            self.landcover = np.full((self.DH, self.DW), landcover, dtype=object)
        else:
            self.landcover = np.asarray(landcover, dtype=object)
        self._features = None                 # 지연 생성(procedural)
        self._build_ground_maps()             # 지면(표면) material: land-cover → 색·산란

    def _build_ground_maps(self):
        """셀별 지면 material 맵 — 피처뿐 아니라 **지면 자체도** land-cover 로 색·SAR 산란이 갈린다.
        (클래스 ≤6 개이므로 마스크로 벡터화 — 셀 루프 없음.)"""
        self.ground_rgb_map = np.zeros((self.DH, self.DW, 3))
        self.ground_scat_map = np.zeros((self.DH, self.DW))
        for cls in np.unique(self.landcover):
            lc = LANDCOVER.get(cls)
            gm = MATERIAL[lc["ground"]] if lc else MATERIAL["soil"]
            mask = (self.landcover == cls)
            self.ground_rgb_map[mask] = gm["rgb"]
            self.ground_scat_map[mask] = _surface_scatter(gm)

    def _cells(self, wx, wy):
        wx = np.asarray(wx, dtype=float); wy = np.asarray(wy, dtype=float)
        i = np.clip((wx / self.mpp).astype(int), 0, self.DW - 1)
        j = np.clip((wy / self.mpp).astype(int), 0, self.DH - 1)
        return j, i

    def ground_rgb(self, wx, wy):
        """월드(wx,wy)[m] 지면의 **RGB view(분광반사색)** — land-cover 기반. 반환 (...,3)."""
        j, i = self._cells(wx, wy)
        return self.ground_rgb_map[j, i]

    def ground_scatter(self, wx, wy):
        """월드(wx,wy)[m] 지면의 **radar view(상대 후방산란)** — land-cover 기반. 물=경면 약, 암반=강."""
        j, i = self._cells(wx, wy)
        return self.ground_scat_map[j, i]

    # ── 절차적 생성: 밀도·크기 분포에서 피처 인스턴스 ──
    def generate(self, max_features=4000):
        """land-cover 분포에서 피처를 절차적으로 인스턴스화(밀도×셀면적). 결정적(seed)."""
        feats = []
        cell_area = self.mpp * self.mpp
        for j in range(self.DH):
            for i in range(self.DW):
                lc = LANDCOVER.get(self.landcover[j, i])
                if not lc:
                    continue
                # 기대 피처 수 = 밀도 × 셀면적(스케일 보정). 포아송으로 뽑는다.
                lam = lc["density"] * cell_area / 3000.0
                for kind_key, dens in (("feature", lam), ("rock", lc["rock_density"] * cell_area / 3000.0)):
                    n = self.rng.poisson(dens)
                    ftype = lc["feature"] if kind_key == "feature" else "rock"
                    for _ in range(int(n)):
                        wx = (i + self.rng.random()) * self.mpp
                        wy = (j + self.rng.random()) * self.mpp
                        smin, smax = lc["size"] if kind_key == "feature" else (0.2, 1.5)
                        feats.append({
                            "kind": ftype, "wx": float(wx), "wy": float(wy),
                            "z": float(self.dem[j, i]),
                            "size": float(self.rng.uniform(smin, smax)),
                            "class": self.landcover[j, i],
                        })
                        if len(feats) >= max_features:
                            self._features = feats
                            return feats
        self._features = feats
        return feats

    def features(self):
        return self._features if self._features is not None else self.generate()

    # ── LOD 쿼리: 센서가 보는 근거리만 자세히, 먼 것은 큰 것만 ──
    def query(self, cam_xy, radius_m, max_out=2000):
        """카메라 위치 기준 radius 안 피처를, **거리별 LOD 로 컬링**해 반환.
        먼 대역은 최소피처크기 미만을 버린다(=데이터량 제어). 반환 리스트에 dist·lod 부착."""
        cx, cy = cam_xy
        out = []
        for f in self.features():
            d = math.hypot(f["wx"] - cx, f["wy"] - cy)
            if d > radius_m:
                continue
            minsize, texres, band = lod_for(d)
            if f["size"] < minsize:            # LOD 컬링: 먼 곳의 작은 것은 안 그린다
                continue
            g = dict(f); g["dist"] = d; g["lod"] = band; g["texres"] = texres
            out.append(g)
        out.sort(key=lambda g: g["dist"])
        return out[:max_out]

    # ── 센서별 view: 같은 피처 → 다른 관측 속성 ──
    @staticmethod
    def rgb_of(feat):
        """RGB view: 분광반사(색). 조명응답은 렌더러(camera.py)가 씌운다."""
        m = MATERIAL[feat["kind"]]
        return {"color": m["rgb"], "size": feat["size"]}

    @staticmethod
    def radar_of(feat, wavelength_m=0.031):
        """Radar/SAR view: 유전율·거칠기 → **상대 산란강도**(RCS 아님, 대표 무차원).
        Rayleigh 거칠기 기준 kσ 와 유전율 대비를 곱한 정성 모델 [출처:조각]."""
        m = MATERIAL[feat["kind"]]
        eps = m["eps"]; rough = m["rough"]
        gamma = abs((math.sqrt(eps) - 1) / (math.sqrt(eps) + 1))    # 유전 대비(수직입사 반사계수 근사)
        k = 2 * math.pi / wavelength_m
        rough_factor = 1.0 - math.exp(-(k * rough) ** 2)            # 거칠수록 후방산란↑ (경면=0)
        strength = gamma * (0.1 + rough_factor) * (feat["size"] ** 2)
        return {"scatter": float(strength), "eps": eps, "rough": rough}

    @staticmethod
    def lidar_of(feat):
        """LiDAR view: 기하면 + 근적외 반사도."""
        m = MATERIAL[feat["kind"]]
        return {"reflectivity": m["lidar"], "size": feat["size"]}


def data_rate(scene, cam_xy, radius_m):
    """LOD 가 센서 데이터량을 어떻게 제어하나 — 대역별 피처 수 + 근사 텍스처 샘플 수."""
    q = scene.query(cam_xy, radius_m)
    per_band = {}
    for g in q:
        b = per_band.setdefault(g["lod"], {"features": 0, "tex_samples": 0.0})
        b["features"] += 1
        # 그 대역 텍스처 해상도로 피처를 덮는 샘플 수 ~ (size/texres)^2
        b["tex_samples"] += (g["size"] / max(g["texres"], 1e-3)) ** 2
    return {"total_features": len(q), "per_band": per_band}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    a, _ = ap.parse_known_args()
    # 합성 지형(외부망 없이도 도는 데모). 실제로는 terrain.fetch_dem(DEM) 를 넣는다.
    xx, yy = np.meshgrid(np.linspace(0, 1, 24), np.linspace(0, 1, 24))
    dem = 700 + 300 * (np.sin(3 * xx) * np.cos(2 * yy) + xx)
    print("=== Scene DB: 하나의 세계 → 센서마다 다른 관측 ===")
    for lc in ("forest", "desert", "urban"):
        sc = SceneDB(dem, mpp=250.0, seed=7, landcover=lc)
        feats = sc.generate()
        cam = (dem.shape[1] * 250.0 / 2, dem.shape[0] * 250.0 / 2)
        dr = data_rate(sc, cam, 1500.0)
        # 같은 피처 하나를 세 센서로
        f0 = feats[0] if feats else {"kind": "rock", "size": 1.0, "wx": 0, "wy": 0, "z": 0, "class": lc}
        rgb = SceneDB.rgb_of(f0); rad = SceneDB.radar_of(f0); lid = SceneDB.lidar_of(f0)
        print("\n[%s] 피처 %d개(절차생성), 쿼리내 %d개" % (lc, len(feats), dr["total_features"]))
        print("  피처 kind=%s size=%.1fm →" % (f0["kind"], f0["size"]))
        print("    RGB   반사색=%s" % (tuple(round(c, 2) for c in rgb["color"]),))
        print("    RADAR 산란강도=%.2f (eps=%.1f rough=%.3fm)" % (rad["scatter"], rad["eps"], rad["rough"]))
        print("    LiDAR 반사도=%.2f" % lid["reflectivity"])
        print("  LOD 데이터량(대역별 피처수):", {b: v["features"] for b, v in sorted(dr["per_band"].items())})
    print("\n※ 장소가 바뀌어도 센서 시뮬레이터는 그대로 — scene DB 만 바뀐다.")
    print("※ material=문헌 대표값(측정 아님) · 현장 validation 안 됨 · LOD=거리대역 컬링(정성).")
