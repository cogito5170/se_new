#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""독립 참조세계(Reference World) — SUT 와 **다른 물리 formulation** + 숨은 truth.

핵심: SUT(sensors.py)와 같은 식을 쓰면 공통가정에 동조해 systematic error 를 못 잡는다.
그래서 여기서는 일부러 **다른 모델**을 쓴다:
  · 안개: SUT 는 Koschmieder(3.912/V)·SNR 탐지. 여기는 **2항 소광(에어로졸 Angstrom+분자)
    + Blackwell 대비임계** 탐지 — 다른 formulation.
  · IMU: SUT 는 랜덤워크(½b t², 발산). 여기는 **1차 Gauss-Markov(정상상태 수렴)** — 다른 formulation.
두 세계가 어긋나는 지점이 곧 '가정에 기댄 성능'을 드러낸다(robustness).

observe(pose) 는 **관측만** 준다(truth 없음). truth() 는 evaluator·viewer 만 부른다.
"""
import math
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # sar/
import terrain


def ref_transmittance(V, R, wavelength_um=0.55):
    """참조 대기투과 — **검증된 Koschmieder 표준**(βV=3.912 @2% 대비) + 파장의존 + 분자 Rayleigh.

    독립성은 '틀린 상수'가 아니라 아래 **다른 탐지 formulation(Blackwell)·IMU(GM)**에서 온다.
    소광 자체는 SUT 와 같은 검증된 물리를 써야 옳다(refval.py 가 표준과 대조해 domain 을 잰다).
    분자항은 물리값(~1.2e-5/m @550nm, Bodhaine 1999 급) — 짧은 거리서는 무시할 만하다."""
    beta_aer = (3.912 / max(V, 1.0)) * (wavelength_um / 0.55) ** (-1.3)   # Koschmieder 표준 + Angstrom
    beta_mol = 1.2e-5 * (wavelength_um / 0.55) ** (-4.0)                  # Rayleigh(물리값)
    return math.exp(-(beta_aer + beta_mol) * R)


def ref_detect_prob(V, R, illum_lux, target_contrast=0.85):
    """참조 탐지확률 — **Blackwell 대비임계**: 외관대비 C=C0·t 가 임계 ε_th 넘으면 탐지(로지스틱).

    SUT 의 광자한계 SNR 모델과 formulation 이 다르다(대비 대 SNR)."""
    t = ref_transmittance(V, R)
    C = target_contrast * t
    eps_th = 0.02 * (1.0 + 60.0 / max(illum_lux, 1.0))     # 저조도면 임계 상승
    return 1.0 / (1.0 + math.exp(-(C - eps_th) / (0.15 * eps_th + 1e-6)))


def ref_imu_sigma(t, tau=55.0, sigma_ss=9.0):
    """참조 관성 불확실도 — **1차 Gauss-Markov**(정상상태 sigma_ss 로 수렴). SUT 랜덤워크와 다르다."""
    return sigma_ss * math.sqrt(max(0.0, 1.0 - math.exp(-2.0 * t / tau)))


class Reference:
    """독립 참조세계. 숨은 truth 를 쥐고, pose 에 대해 관측만 반환한다."""

    GW = GH = 24
    PATCH_M = 6000.0
    AGL = 90.0

    def __init__(self, scenario, dem=None):
        """scenario: 숨은 시나리오. truth 는 여기서만 생성. AGL·센서집합·표적(임의 or 명시).
        dem: 미리 받은 DEM 을 넣으면 재-fetch 안 함(학습서 한 지역 수천 에피소드 돌릴 때)."""
        self.rng = np.random.default_rng(scenario["seed"])
        self.lat = scenario["lat"]; self.lon = scenario["lon"]
        self.V = scenario["V"]; self.illum = scenario["illum"]
        self.AGL = float(scenario.get("agl", 90.0))
        self.clutter = float(scenario.get("clutter", 0.0))   # 헛 탐지율(0=없음, 기존 동작 불변)
        self.clutter_persist = int(scenario.get("clutter_persist", 1))  # 헛 탐지가 같은 위치에 머무는 스텝(1=매스텝 새위치=transient)
        self._clut = {}                                      # 센서별 지속 clutter 상태 {key:{x,y,ttl}}
        self.sensors = set(scenario.get("sensors", ["RGB", "SAR", "IMU"]))
        if dem is not None:
            self.dem = dem
        else:
            self.dem, _, _ = terrain.fetch_dem(self.lat, self.lon, self.PATCH_M / 2, zoom=13)
        self.DH, self.DW = self.dem.shape
        self.mpp = self.PATCH_M / self.DW
        # 숨은 truth: 표적. 명시(targets_spec: 방위·거리·수관) 우선, 없으면 임의.
        self._targets = []
        if scenario.get("targets_spec"):
            cx, cy = self.GW / 2.0, self.GH / 2.0
            cellm = self.PATCH_M / self.GW
            for ts in scenario["targets_spec"]:
                br = math.radians(ts.get("bearing_deg", 45.0)); rng_m = ts.get("range_m", 180.0)
                gx = cx + (rng_m / cellm) * math.sin(br); gy = cy - (rng_m / cellm) * math.cos(br)  # 방위: N=0,E=90
                self._targets.append({"gx": float(np.clip(gx, 2, self.GW-2)), "gy": float(np.clip(gy, 2, self.GH-2)),
                                      "canopy": bool(ts.get("canopy", False))})
        else:
            for _ in range(scenario.get("n_target", 1)):
                self._targets.append({"gx": float(self.rng.uniform(3, self.GW-3)),
                                      "gy": float(self.rng.uniform(3, self.GH-3)), "canopy": False})
        # 표적 운동(motion 축 V&V): static/const/accel/turn. 초기 속도 방향 임의.
        self.tmotion = scenario.get("target_motion", "static")
        tsp = float(scenario.get("target_speed", 0.35))
        for tg in self._targets:
            ang = self.rng.uniform(0, 2 * math.pi)
            tg["vx"] = tsp * math.cos(ang) if self.tmotion != "static" else 0.0
            tg["vy"] = tsp * math.sin(ang) if self.tmotion != "static" else 0.0
        self._traj = []       # 스텝별 표적 위치(운동 표적을 시각(時刻) 맞춰 채점하려면 필요)
        # Decoy(전-서명 가짜): 실 표적처럼 여러 센서를 트립하지만 truth 아님(claim 하면 오경보).
        # liveness(호흡·심박 미세운동)만 없다 — CMPC 로도 못 가르고 liveness 채널로만 걸린다.
        self._decoys = []
        if scenario.get("decoys_spec"):
            cx, cy = self.GW / 2.0, self.GH / 2.0; cellm = self.PATCH_M / self.GW
            for ds in scenario["decoys_spec"]:
                br = math.radians(ds.get("bearing_deg", 200.0)); rng_m = ds.get("range_m", 200.0)
                dx = cx + (rng_m / cellm) * math.sin(br); dy = cy - (rng_m / cellm) * math.cos(br)
                self._decoys.append({"gx": float(np.clip(dx, 2, self.GW-2)), "gy": float(np.clip(dy, 2, self.GH-2)),
                                     "canopy": False})
        else:
            for _ in range(int(scenario.get("n_decoy", 0))):
                self._decoys.append({"gx": float(self.rng.uniform(3, self.GW-3)),
                                     "gy": float(self.rng.uniform(3, self.GH-3)), "canopy": False})
        self.t = 0.0
        self.cell_m = self.PATCH_M / self.GW                 # size of one grid cell (m) -- the unit of rc
        self.legacy_slant = bool(scenario.get("legacy_slant_units", False))   # True = the old (wrong) range units, for comparing past results
        # ── scene3d (contract: render3d/핸드오프_센서스펙_관측계약.md) ──
        # The reference world computes observations from 3D visibility (terrain line of sight, real tree geometry, pixels on target).
        # **Off by default.** With it off, observations are bit-identical to the old code except for the range-unit fix above
        # (legacy_slant_units=True makes it bit-identical to the old code as well). The SUT gets the same detection-packet schema.
        self.scene3d = bool(scenario.get("scene3d", False))
        self.fidelity = scenario.get("fidelity") or ("L2 실측 DEM + SceneDB" if dem is None else "주어진 DEM(출처 미상)")
        if self.scene3d:
            self._init_scene3d(scenario)

    def _g2w(self, gx, gy):
        """IV&V grid -> world (m). Same as sar/ivv/viewer.py and render3d/sar_bridge: pixel index = g/GW*DW."""
        return (gx / self.GW * self.DW * self.mpp, gy / self.GH * self.DH * self.mpp)

    def _init_scene3d(self, scenario):
        """3D world = DEM + SceneDB trees/buildings + (targets with canopy=True) a real tree over the target.
        Uses its **own RNG stream** -- the main stream (self.rng) is consumed exactly as with scene3d=False, so an A/B
        comparison differs only by geometry."""
        root = os.path.dirname(os.path.dirname(HERE))
        if root not in sys.path:
            sys.path.insert(0, root)
        from render3d.visibility import World
        from sar.scene import SceneDB
        r3 = np.random.default_rng(int(scenario["seed"]) + 7919)
        feats = SceneDB(self.dem, self.mpp, seed=int(scenario["seed"])).generate(max_features=int(scenario.get("scene3d_features", 4000)))
        self.world3d = World(self.dem, self.mpp, feats, lad=float(scenario.get("lad", 1.5)))
        # Tree placement assumption (sensitivity knobs). Default = one tree over the target, offset sigma 0.6 m, size 10-14 m.
        # n>1: the rest of the cluster is scattered uniformly within cluster_r (m) of the target. The default path consumes r3 in the same order as before.
        ct = dict({"sigma": 0.6, "size": (10.0, 14.0), "n": 1, "cluster_r": 0.0}, **scenario.get("canopy_tree", {}))
        for tg in self._targets + self._decoys:
            x, y = self._g2w(tg["gx"], tg["gy"])
            if tg["canopy"]:                          # the canopy flag becomes geometry: a real tree over the target
                self.world3d.add_tree(x + float(r3.normal(0, ct["sigma"])), y + float(r3.normal(0, ct["sigma"])),
                                      float(r3.uniform(*ct["size"])))
                for _ in range(int(ct["n"]) - 1):
                    a = float(r3.uniform(0, 2 * math.pi)); rr = ct["cluster_r"] * math.sqrt(float(r3.uniform(0, 1)))
                    self.world3d.add_tree(x + rr * math.cos(a), y + rr * math.sin(a), float(r3.uniform(*ct["size"])))
            tg["yaw3d"] = float(r3.uniform(0.0, 180.0))
        self.scene3d_parts = set(scenario.get("scene3d_parts", ("los", "canopy", "pixels", "slant", "radar_shadow")))
        self._rng_shadow = np.random.default_rng(int(scenario["seed"]) + 104729)   # radar shadow only (does not touch the main stream)
        self.cams3d = scenario.get("scene3d_cams")          # None = render3d.visibility.CAMERAS (representative-value assumption)

    _OLD_CANOPY = {"rgb": 0.05, "thermal": 0.25, "lidar": 0.1}      # the old constants (kept when a factor is off)

    def _occ3d(self, geo, sensor, canopy):
        """3D factor that replaces the canopy constant. **A factor that is turned off keeps the old treatment** --
        the first version dropped the canopy constant when only los was on, and canopy targets showed up for free
        (fake effect: detection 0.30 -> 0.46). Now, e.g. los only = los_frac x (canopy constant for canopy targets)."""
        los_on, can_on = "los" in self.scene3d_parts, "canopy" in self.scene3d_parts
        if los_on and can_on:
            return geo["canopy_vis"]
        f = geo["foliage_vis"] if can_on else (self._OLD_CANOPY[sensor] if canopy else 1.0)
        return f * (geo["los_frac"] if los_on else 1.0)

    # ── evaluator·viewer 전용(SUT 는 못 부른다) ──
    def truth(self):
        return {"targets": [(t["gx"], t["gy"]) for t in self._targets],
                "canopy": [t["canopy"] for t in self._targets], "V": self.V, "illum": self.illum}

    def world_full(self, pose):
        """viewer 용: 관측 + truth 를 함께(관찰자는 정답을 봐도 된다 — SUT 와 분리돼 있으니)."""
        w = self.observe(pose)
        w["truth"] = self.truth()
        return w

    # ── SUT 로 나가는 인터페이스: 관측만 ──
    def observe(self, pose):
        """pose=(gx,gy) 격자위치 → 센서 패킷. **truth 없음.** 참조 물리로 계산."""
        import sensors_ref as _sr
        gx, gy = pose
        self.t += 1.0
        # 표적 운동 진행(motion 축): const=등속, accel=가속, turn=방향전환. 그 뒤 위치 기록.
        if self.tmotion != "static":
            for tg in self._targets:
                if self.tmotion == "accel":
                    tg["vx"] *= 1.08; tg["vy"] *= 1.08
                elif self.tmotion == "turn":
                    c, s = math.cos(0.5), math.sin(0.5)
                    vx, vy = tg["vx"], tg["vy"]
                    tg["vx"] = c * vx - s * vy; tg["vy"] = s * vx + c * vy
                tg["gx"] = float(np.clip(tg["gx"] + tg["vx"], 1, self.GW - 1))
                tg["gy"] = float(np.clip(tg["gy"] + tg["vy"], 1, self.GH - 1))
        self._traj.append([(t["gx"], t["gy"]) for t in self._targets])
        have_rgb = "RGB" in self.sensors; have_sar = "SAR" in self.sensors; have_imu = "IMU" in self.sensors
        have_thermal = "Thermal" in self.sensors; have_lidar = "LiDAR" in self.sensors; have_audio = "Audio" in self.sensors
        # 조건-유도 온도·풍(부족분): 야간/안개면 배경 서늘, 화재면 뜨겁다(간이). Audio 잡음 바닥.
        night = self.illum < 1.0; fog = self.V < 500.0
        T_amb = 283.0 if (night or fog) else 293.0
        wind_db = 45.0 if self.V < 200.0 else 35.0
        rgb_dets = []; sar_hits = 0; sar_dets = []; thermal_dets = []; lidar_dets = []; audio_dets = []
        live_dets = []

        def _emit(tg, is_real):
            nonlocal sar_hits
            tx, ty, canopy = tg["gx"], tg["gy"], tg["canopy"]
            rc = math.hypot(tx - gx, ty - gy)
            # rc is in **grid cells** (1 cell = PATCH_M/GW = 250 m). Before 2026-09-28 this was hypot(rc*mpp, AGL): grid cells
            # multiplied by DEM pixel size mpp, which shortened horizontal range by DW/GW (x4 on a 96 DEM; a 500 m target -> 154 m).
            # legacy_slant_units=True reproduces the old behaviour (only for comparing past results).
            slant = math.hypot(rc * (self.mpp if self.legacy_slant else self.cell_m), self.AGL)
            if rc > 3.2:
                return
            geo = None
            if self.scene3d:                                     # 3D visibility (inside the reference world only -- the SUT never sees it)
                cx3, cy3 = self._g2w(gx, gy)
                cz3 = float(self.world3d.ground(cx3, cy3)) + self.AGL
                geo = self.world3d.observe_geometry((cx3, cy3, cz3), self._g2w(tx, ty), tg.get("yaw3d", 0.0), cams=self.cams3d)
                if "slant" in self.scene3d_parts:                # 3D slant range: horizontal range plus the terrain height difference
                    slant = geo["slant_m"]                       # (between the ground under the UAV and the target) -- the 2D formula assumes flat ground
                pix = "pixels" in self.scene3d_parts
            # RGB: 참조 물리(안개)로 탐지. **소나무 수관 아래면 광학이 못 뚫는다**(안개와 별개, 곱해짐).
            if have_rgb:
                p = ref_detect_prob(self.V, slant, self.illum)
                if geo is not None:                              # 3D: geometric visibility x Johnson pixels on target
                    p *= self._occ3d(geo, "rgb", canopy) * (geo["p_johnson_rgb"] if pix else 1.0)
                elif canopy:
                    p *= 0.05                                    # 침엽 수관 광학투과 ~5% (거의 실명)
                if self.rng.random() < p:
                    gerr = 0.25 + 1.2 * (1.0 - p) + 0.15 * rc
                    rgb_dets.append((float(tx + self.rng.normal(0, gerr)), float(ty + self.rng.normal(0, gerr)), float(p)))
            # X-band SAR: 전천후(안개 무관)지만 **수관 아래 사람은 약한 산란체**(X-대역은 수관 위를 본다).
            if have_sar:
                p_sar = 0.6 if not canopy else 0.10             # 수관 아래면 반사 확률 급감
                if self.rng.random() < p_sar:
                    # SAR 위치주장: 전천후지만 RGB 보다 **거칠다**(DOA·거리 해상도). 낮은 신뢰.
                    gerr_sar = 0.8 + 0.4 * rc
                    d = (float(tx + self.rng.normal(0, gerr_sar)), float(ty + self.rng.normal(0, gerr_sar)), 0.5)
                    # Radar shadow: if terrain blocks the path from the antenna (at the UAV) to the target, no echo returns.
                    # Same geometric line of sight as optics; X-band canopy attenuation is different physics, so the constant stays.
                    # Decided on a **separate random stream** (_rng_shadow) -- the main stream is consumed exactly as with it off.
                    # The first version multiplied p_sar, the number of normal draws changed with hit/miss, the rest of the
                    # stream shifted, and detection "went up" (0.47->0.53, n=8) even though the SUT does not use SAR -- noise.
                    # Not modelled: layover, multipath, diffraction (GAP).
                    if geo is None or "radar_shadow" not in self.scene3d_parts or self._rng_shadow.random() < geo["los_frac"]:
                        sar_hits += 1
                        sar_dets.append(d)
            # Thermal(LWIR): 야간·연무 유리(열대비), 수관은 대부분 가림(×0.25). RGB 보다 위치 거침.
            if have_thermal:
                tr = _sr.thermal_dn(305.0, T_amb, 0.98, self.V, slant, rng=self.rng)
                if geo is not None:
                    p_th = (0.85 if tr["detectable"] else 0.05) * self._occ3d(geo, "thermal", canopy) * (geo["p_johnson_thermal"] if pix else 1.0)
                else:
                    p_th = (0.85 if tr["detectable"] else 0.05) * (0.25 if canopy else 1.0)
                if self.rng.random() < p_th:
                    gerr = 0.4 + 0.25 * rc
                    thermal_dets.append((float(tx + self.rng.normal(0, gerr)),
                                         float(ty + self.rng.normal(0, gerr)), 0.7))
            # LiDAR: 맑으면 정밀, 안개(왕복 2β)·수관(폐색 ×0.1)엔 급감.
            if have_lidar:
                lr = _sr.lidar_return(slant, 0.3, self.V, rng=self.rng)
                if geo is not None:                              # LiDAR: gap probability (same path both ways -> not squared). No Johnson (GAP)
                    p_li = (0.8 if lr["detectable"] else 0.02) * self._occ3d(geo, "lidar", canopy)
                else:
                    p_li = (0.8 if lr["detectable"] else 0.02) * (0.1 if canopy else 1.0)
                if self.rng.random() < p_li:
                    gerr = 0.2 + 0.1 * rc
                    lidar_dets.append((float(tx + self.rng.normal(0, gerr)),
                                       float(ty + self.rng.normal(0, gerr)), 0.8))
            # Audio: 소리는 안개·수관·야간 통과(광학과 다른 채널)지만 방위만 → 위치 거침, 근거리만.
            if have_audio:
                ar = _sr.audio_detect((slant, 0.0), (0.0, 0.0), source_db=85.0, wind_db=wind_db, rng=self.rng)
                if ar["detectable"] and self.rng.random() < 0.7:
                    gerr = 1.0 + 0.3 * rc
                    audio_dets.append((float(tx + self.rng.normal(0, gerr)),
                                       float(ty + self.rng.normal(0, gerr)), 0.4))
            # Liveness(호흡·심박 미세운동): **실 표적만**. decoy 는 서명은 같아도 이것이 없다.
            # 마이크로파 생체징후(FINDER류)는 수관도 통과 → canopy 무관, 근거리만.
            if is_real and rc <= 3.0 and (geo is None or "los" not in self.scene3d_parts or geo["terrain_los"]) \
                    and self.rng.random() < 0.9:                   # 3D: a ridge blocks RF too (the canopy does not)
                live_dets.append((float(tx + self.rng.normal(0, 0.5)),
                                  float(ty + self.rng.normal(0, 0.5)), 0.9))

        for tg in self._targets:
            _emit(tg, True)
        for dc in self._decoys:                                  # decoy: 전-서명 트립하되 liveness 없음
            _emit(dc, False)
        # ── Clutter(헛 탐지): 실 표적이 아닌 스퍼리어스 관측. 센서 독립, 드론 FOV 안 임의 위치,
        #    표적에서 ≥4셀. 신뢰도는 실 탐지와 같은 분포(신뢰도만으론 못 거르게 — 공정한 시험).
        #    clutter_persist>1 이면 같은 위치에 여러 스텝 머문다(transient 가정을 깨는 worst case:
        #    지속 clutter 는 실 표적처럼 시간적 확인을 통과할 수 있다). ──
        if self.clutter > 0.0:
            cl = self.clutter
            rate = {"rgb": 0.6, "thermal": 0.7, "lidar": 0.3, "sar": 0.5, "audio": 1.0}  # 상대 성향
            havek = {"rgb": have_rgb, "thermal": have_thermal, "lidar": have_lidar,
                     "sar": have_sar, "audio": have_audio}
            detsk = {"rgb": rgb_dets, "thermal": thermal_dets, "lidar": lidar_dets,
                     "sar": sar_dets, "audio": audio_dets}

            def _cconf(k):
                return float(self.rng.uniform(0.5, 0.95)) if k == "rgb" else \
                    {"thermal": 0.7, "lidar": 0.8, "sar": 0.5, "audio": 0.4}[k]

            def _spurious():
                for _ in range(4):
                    ox = float(np.clip(gx + self.rng.uniform(-3, 3), 0, self.GW - 1))
                    oy = float(np.clip(gy + self.rng.uniform(-3, 3), 0, self.GH - 1))
                    if all(math.hypot(ox - t["gx"], oy - t["gy"]) > 4.0 for t in self._targets):
                        return ox, oy
                return None
            for k in ("rgb", "thermal", "lidar", "sar", "audio"):
                if not havek[k]:
                    continue
                stt = self._clut.get(k)
                if stt and stt["ttl"] > 0:                         # 지속 clutter: 같은 위치 + 작은 잡음
                    jx = float(np.clip(stt["x"] + self.rng.normal(0, 0.3), 0, self.GW - 1))
                    jy = float(np.clip(stt["y"] + self.rng.normal(0, 0.3), 0, self.GH - 1))
                    detsk[k].append((jx, jy, _cconf(k)))
                    if k == "sar":
                        sar_hits += 1
                    stt["ttl"] -= 1
                elif self.rng.random() < cl * rate[k]:             # 새 clutter 발생
                    pt = _spurious()
                    if pt:
                        detsk[k].append((pt[0], pt[1], _cconf(k)))
                        if k == "sar":
                            sar_hits += 1
                        self._clut[k] = {"x": pt[0], "y": pt[1], "ttl": self.clutter_persist - 1}
        sig = ref_imu_sigma(self.t) if have_imu else 0.0
        rho = ref_transmittance(self.V, math.hypot(3 * (self.mpp if self.legacy_slant else self.cell_m), self.AGL))  # rough visibility indicator at 3 cells (same unit fix)
        return {
            "t": self.t,
            "rgb": {"detections": rgb_dets if have_rgb else [], "vis": float(rho) if have_rgb else 0.0},
            "sar": {"hits": int(sar_hits), "detections": sar_dets if have_sar else []},
            "thermal": {"detections": thermal_dets if have_thermal else []},
            "lidar": {"detections": lidar_dets if have_lidar else []},
            "audio": {"detections": audio_dets if have_audio else []},
            "live": {"detections": live_dets},   # liveness 채널(호흡·심박) — 실 표적만, decoy 없음
            "imu": {"sigma": float(sig), "ok": (sig < 40.0) if have_imu else False},
            "gps": {"uncertain": (sig >= 15.0) if have_imu else True},
        }
