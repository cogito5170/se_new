#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정책 후보(선수) — sar 검증환경(reference·evaluator)이 채점한다. 정책은 관측만 받는다(truth 못 봄).

세 후보가 **항법은 같고**(policy_core), 다른 것은 **어느 센서의 탐지를 신뢰해 주장하느냐**뿐:
  · Baseline   : RGB 만 신뢰(=기존 SUT). 안개서 RGB 가 무력하면 못 잡는다.
  · NASA-rule  : S4 식 효용 U_i=ΔP_i−α·cost_i (SAR 는 measure.py 실측 15배 느림=비쌈)로 고른다.
  · Selector   : **학습된 selective-SSM(Mamba)** 가 관측 시퀀스를 읽어 고른다(손 규칙 아님, thesis).

관측 특징(truth 없음): [rgb_vis, sar_hit, imu_ok, gps_uncertain]. 학습·선택 공용.
"""
from __future__ import annotations
import ctypes
import math
import numpy as np

import sut as _sut


D_IN = 4


def feature(obs):
    """관측 → 특징 벡터(truth 없음). d_in=4."""
    return np.array([
        float(obs["rgb"]["vis"]),
        1.0 if obs["sar"]["hits"] > 0 else 0.0,
        1.0 if obs["imu"]["ok"] else 0.0,
        1.0 if obs["gps"]["uncertain"] else 0.0,
    ], dtype=float)


# 센서 비용(정규화 0..1): RGB 싸고 빠름 ↔ SAR/LiDAR 느리고 전력 큼. Audio 저렴, Thermal 중간.
COST_NORM = {"RGB": 0.10, "Audio": 0.20, "Thermal": 0.40, "LiDAR": 0.60, "SAR": 0.70}
# 관측 obs 에서 그 센서의 탐지 리스트를 꺼내는 키
SENSOR_KEY = {"RGB": "rgb", "SAR": "sar", "Thermal": "thermal", "LiDAR": "lidar", "Audio": "audio"}


class _SelectPolicy(_sut.SUT):
    """공통 선수 골격 — 항법·MRC·커버리지는 SUT 와 같고, **claim 센서만** choose() 로 고른다."""

    def __init__(self):
        super().__init__()
        self.feat_hist = []
        self.primary = "RGB"
        self.consulted = None      # 이번 스텝에 함께 켠 센서집합(투표용). None=primary 하나만.

    def choose(self, obs, feat):
        """반환 'RGB' | 'SAR'. 하위 클래스가 규칙/학습으로 정한다."""
        return "RGB"

    def claim_from(self, obs, primary):
        """주장할 탐지 리스트를 낸다. 기본: 고른 센서 하나의 탐지를 그대로 믿는다.
        투표 정책이 이 훅을 오버라이드해 **여러 센서 합의**로 거른다(오경보↓·위치↑)."""
        return list(obs.get(SENSOR_KEY.get(primary, "rgb"), {}).get("detections", []))

    def _after_claim(self, new_claims):
        """claim 뒤 훅(직전 탐지 피드백 등). 기본 무동작."""
        pass

    def step(self, obs):
        GW, GH = self.GW, self.GH
        self.consulted = None                       # 매 스텝 초기화(choose 가 투표 시 채운다)
        feat = feature(obs); self.feat_hist.append(feat)
        uncov = 1.0 - self.covered.astype(np.float32)
        navb = self.bel + 0.7 * (uncov.reshape(-1) / (uncov.sum() + 1e-6))
        tx, ty = self._pnext(navb / (navb.sum() + 1e-9))
        sig = obs["imu"]["sigma"]
        if not obs["imu"]["ok"] or sig >= 36.0:
            return {"waypoint": self.veh[:], "detections": [], "state": "MRC",
                    "telemetry": {"coverage": float(100.0 * self.covered.sum() / (GW * GH)), "heading": self.heading,
                                  "sigma": sig, "gps_uncertain": obs["gps"]["uncertain"], "sar_hits": obs["sar"]["hits"],
                                  "primary_sensor": self.primary, "consulted": None}}
        vis = obs["rgb"]["vis"]
        state = "SEARCHING" if vis >= 0.5 else ("DEGRADED" if vis >= 0.25 else "LOW-INFO")
        self.prev = self.veh[:]; self.veh = [tx, ty]
        if abs(self.veh[0] - self.prev[0]) + abs(self.veh[1] - self.prev[1]) > 0.1:
            self.heading = math.degrees(math.atan2(self.veh[1] - self.prev[1], self.veh[0] - self.prev[0]))
        for gy in range(GH):
            for gx in range(GW):
                if (gx - self.veh[0]) ** 2 + (gy - self.veh[1]) ** 2 <= 9:
                    self.covered[gy, gx] = True
        # ── 센서 선택 → 그 센서의 탐지를 주장(claim_from 훅; 투표 정책이 오버라이드) ──
        self.primary = self.choose(obs, feat)
        src = self.claim_from(obs, self.primary)
        new_claims = []
        for (dx, dy, conf) in src:
            if all((dx - c[0]) ** 2 + (dy - c[1]) ** 2 > 4 for c in self.claims):
                self.claims.append((dx, dy)); new_claims.append((dx, dy, conf))
                for gy in range(GH):
                    for gx in range(GW):
                        self.bel[gy * GW + gx] *= (math.exp(-((gx - dx) ** 2 + (gy - dy) ** 2) / (2 * 1.2 ** 2)) + 0.02)
        ssum = self.bel.sum(); self.bel /= (ssum if ssum > 0 else 1)
        self._after_claim(new_claims)
        return {"waypoint": self.veh[:], "detections": new_claims, "state": state,
                "telemetry": {"coverage": float(100.0 * self.covered.sum() / (GW * GH)), "heading": self.heading,
                              "sigma": sig, "gps_uncertain": obs["gps"]["uncertain"], "sar_hits": obs["sar"]["hits"],
                              "primary_sensor": self.primary, "consulted": self.consulted}}


class BaselinePolicy(_SelectPolicy):
    """RGB 만 신뢰(기존 SUT 와 동등)."""
    def choose(self, obs, feat):
        return "RGB"


class NASARulePolicy(_SelectPolicy):
    """NASA S4 식 효용 정책: U_i=ΔP_i−α·cost 로 **가용 센서 전체**에서 고른다(RGB·SAR·Thermal·LiDAR·Audio).

    ΔP 는 S4 처럼 **센서의 조건별 특성(a priori)** + 관측된 가시도로 추정한다. 정직: 정책은 수관을
    직접 관측 못 한다 — 그래서 수관 아래선 열/광학을 골라 놓쳐도 그것이 이 규칙의 한계다."""
    ALPHA = 0.35
    AVAIL = ("RGB", "SAR", "Thermal", "LiDAR", "Audio")

    def _dP(self, name, obs):
        vis = float(obs["rgb"]["vis"])
        if name == "RGB":
            return vis                                          # 관측된 가시도(식별력 높음)
        if name == "SAR":
            return 0.5                                          # 전천후(위치는 거침)
        if name == "Thermal":
            return 0.75                                         # 야간·연무에 강함(열대비)
        if name == "LiDAR":
            return 0.65 * min(1.0, vis / 0.5)                   # 안개(저가시)면 급감
        if name == "Audio":
            return 0.45                                         # 전조건·거칠음(방위)
        return 0.0

    def choose(self, obs, feat):
        avail = [s for s in self.AVAIL if s in ({"RGB", "SAR"} | {"Thermal", "LiDAR", "Audio"})]
        util = {s: self._dP(s, obs) - self.ALPHA * COST_NORM[s] for s in avail
                if SENSOR_KEY[s] in obs}                        # reference 가 낸 센서만
        best = max(util, key=util.get)
        # 히스테리시스: 현재 센서에 소폭 가산(모드 떨림 방지)
        if self.primary in util and util[best] <= util[self.primary] + 0.05:
            return self.primary
        return best


class SelectorPolicy(_SelectPolicy):
    """학습된 selective-SSM(Mamba)이 관측 시퀀스로 센서를 고른다. weights=mamba_selector 파라미터."""
    def __init__(self, weights, model):
        super().__init__()
        self.W = weights; self.model = model

    def choose(self, obs, feat):
        seq = np.array(self.feat_hist, dtype=float)             # (t, d_in) 지금까지 관측
        prob = self.model.predict(self.W, seq)[-1, 0]           # 현재 스텝 P(use SAR)
        return "SAR" if prob > 0.5 else "RGB"


def oracle_label(obs, vis_thresh=0.4):
    """학습용 truth-aware 라벨(배포 시 안 씀): 어느 센서를 신뢰해야 했나. 1=SAR, 0=RGB."""
    rgb = obs["rgb"]["detections"]; sar = obs["sar"]["detections"]
    if rgb:
        return 0.0                                              # RGB 가 잡으면 RGB(정밀)
    if sar:
        return 1.0                                              # RGB 못 잡고 SAR 잡으면 SAR
    return 1.0 if obs["rgb"]["vis"] < vis_thresh else 0.0       # 아무도 못 잡음: 가시 낮으면 SAR 대비


# ── 5센서 cost-aware 학습(cost 규율을 라벨에 심는다) ──
SENSORS_5 = ["RGB", "SAR", "Thermal", "LiDAR", "Audio"]         # 클래스 인덱스 순서
D_IN_MULTI = 3                                                 # [vis, imu_ok, gps] — 순수 관측 문맥


def feature_multi(obs, prev_choice_idx=0, prev_detected=0.0):
    """5센서 선택용 특징 — **관측 문맥만**(가시도·IMU·GPS). prev 피드백을 뺐다: 그걸 넣으면 추론서
    자기강화 covariate shift(RGB→RGB 락인)로 센서를 영영 안 바꾼다(실측). 조건→센서 매핑을 배운다."""
    return np.array([float(obs["rgb"]["vis"]), 1.0 if obs["imu"]["ok"] else 0.0,
                     1.0 if obs["gps"]["uncertain"] else 0.0], dtype=float)


def oracle_label_cost(obs):
    """(구) 탐지-이벤트 라벨 — 탐지 순간의 최저비용 센서. 반응형 정책엔 부적합(미리 켜야 잡는데
    탐지 순간에만 라벨). oracle_label_condition 으로 대체. 검사 호환 위해 남겨둔다."""
    detects = [s for s in SENSORS_5 if obs.get(SENSOR_KEY[s], {}).get("detections")]
    if detects:
        return SENSORS_5.index(min(detects, key=lambda s: COST_NORM[s]))
    return SENSORS_5.index("RGB")


# 센서 에너지(전력/대역) 정규화 — 비용과 별개 축(요청: U=D−λC−μE).
ENERGY_NORM = {"RGB": 0.10, "Audio": 0.20, "Thermal": 0.50, "LiDAR": 0.70, "SAR": 0.60}
LAM_COST = 0.30    # λ (비용 가중)
MU_ENERGY = 0.10   # μ (에너지 가중)


def sensor_utilities(V, illum, canopy, nominal_m=180.0, agl=120.0):
    """조건 s 에서 센서별 **탐지 유틸리티 D(a,s)∈[0,1]** — reference 가 탐지를 생성하는 그 확률과 동형
    (자기일관). ReAct 회귀 타깃이자 oracle 유틸리티의 D 항. truth(V·illum·canopy) 아는 값."""
    import math
    import sensors_ref as _sr
    slant = math.hypot(nominal_m, agl)
    night = illum < 1.0; fog = V < 500.0
    T_amb = 283.0 if (night or fog) else 293.0
    wind_db = 45.0 if V < 200.0 else 35.0
    return {
        "RGB": ref_detect_prob_proxy(V, slant, illum) * (0.05 if canopy else 1.0),
        "SAR": 0.6 if not canopy else 0.10,
        "Thermal": (0.85 if _sr.thermal_dn(305.0, T_amb, 0.98, V, slant)["detectable"] else 0.05) * (0.25 if canopy else 1.0),
        "LiDAR": (0.8 if _sr.lidar_return(slant, 0.3, V)["detectable"] else 0.02) * (0.1 if canopy else 1.0),
        "Audio": 0.7 if _sr.audio_detect((slant, 0.0), (0.0, 0.0), source_db=85.0, wind_db=wind_db)["detectable"] else 0.05,
    }


def utility_scores(D, lam=LAM_COST, mu=MU_ENERGY):
    """U(a|s) = D(a,s) − λ·C(a) − μ·E(a). 조건별 센서 유틸리티(비용·에너지 반영)."""
    return {a: D[a] - lam * COST_NORM[a] - mu * ENERGY_NORM[a] for a in SENSORS_5}


def oracle_label_condition(V, illum, canopy, nominal_m=180.0, agl=120.0):
    """**조건 기반 proactive 라벨 = argmax_a[D(a,s)−λC(a)−μE(a)]** (요청 형식). 하드코딩 rule 이 아니라
    유틸리티 argmax — '무조건 Thermal' 이 아니라 '이 조건서 유틸리티 최대 센서를 미리 켜라'.
    라벨은 detection event 아니라 **관측 전 조건**에서 나온다(causal ordering: 조건→센서→미래탐지)."""
    U = utility_scores(sensor_utilities(V, illum, canopy, nominal_m, agl))
    return SENSORS_5.index(max(U, key=U.get))


def ref_detect_prob_proxy(V, R, illum, C0=0.85):
    """RGB 탐지확률(참조와 동형): Koschmieder 투과 × 조도. reference.ref_detect_prob 축약."""
    import math
    t = math.exp(-(3.912 / max(V, 1.0)) * R)
    C = C0 * t
    eps_th = 0.02 * (1.0 + 60.0 / max(illum, 1.0))
    return 1.0 / (1.0 + math.exp(-(C - eps_th) / (0.15 * eps_th + 1e-6)))


class MambaSensorPolicy(_SelectPolicy):
    """학습된 5센서 Mamba(softmax). 관측 문맥+직전 피드백 시퀀스로 센서 클래스를 고른다."""
    def __init__(self, weights, model):
        super().__init__()
        self.W = weights; self.model = model
        self.mfeat = []; self.prev_choice = 0; self.prev_detected = 0.0

    def choose(self, obs, feat):
        self.mfeat.append(feature_multi(obs, self.prev_choice, self.prev_detected))
        cls = int(self.model.predict_class(self.W, np.array(self.mfeat))[-1])
        self.prev_choice = cls
        return SENSORS_5[cls]

    def _after_claim(self, new_claims):
        self.prev_detected = 1.0 if new_claims else 0.0


# ── 센서 융합(투표) 가중치: 위치 정밀도·신뢰 순. RGB 정밀, Audio 는 방위만(거침) ──
VOTE_W = {"RGB": 1.0, "LiDAR": 0.8, "Thermal": 0.7, "SAR": 0.5, "Audio": 0.35}


class VotingPolicy(_SelectPolicy):
    """센서 융합 확인층(STORM식) — base 정책(예: RL Mamba)이 항법·센서선택을 하고, **claim 은
    여러 센서 합의로만 건다**. 외로운 거친 탐지(방위만 주는 Audio 등)를 걸러 오경보를 줄이고,
    soft 는 신뢰가중 무게중심으로 위치(RMSE)를 개선한다.

    **정직한 대가**: 확인집합(confirm)의 센서를 함께 켜므로 스텝 비용이 오른다(consulted 로 계상).
    또 합의를 요구하므로 **한 센서만 보던 진짜 탐지도 억제**될 수 있다(탐지율↓) — 그 trade-off 를 잰다.

    mode='hard': 한 군집에 **서로 다른 센서 ≥ k** 면 확인(위치=최고신뢰 센서).
    mode='soft': 한 군집의 **Σ VOTE_W ≥ tau** 면 확인, 위치=신뢰가중 무게중심."""
    def __init__(self, base, mode="soft", gate=2.0, k=2, tau=0.9, confirm=None):
        super().__init__()
        self.base = base                                   # choose 를 위임할 정책(RL 등)
        self.mode = mode; self.gate = float(gate); self.k = int(k); self.tau = float(tau)
        self.confirm = list(confirm) if confirm else list(SENSORS_5)   # 함께 켜는 확인 센서집합

    def choose(self, obs, feat):
        return self.base.choose(obs, feat)                 # 센서 선택은 base(RL)가

    def claim_from(self, obs, primary):
        """**앵커드 확인 게이트**: RL 이 고른 primary 센서의 탐지가 후보(anchor)다. 각 후보를 확인집합의
        다른 센서로 코로보레이션해, 합의가 되는 것만 claim 한다. RL 의 제안 자체는 그대로 두고,
        **외로운(코로보 안 되는) 제안만 버려 오경보를 줄인다.** primary 가 아무것도 안 내면 claim 없음."""
        anchors = list(obs.get(SENSOR_KEY.get(primary, "rgb"), {}).get("detections", []))
        # 비용 정직: primary 가 뭔가 제안한 스텝에만 코로보 센서를 켠다(cue→confirm). 아니면 primary 하나.
        self.consulted = list(self.confirm) if anchors else [primary]
        corr = []                                          # 확인집합의 다른 센서 탐지(코로보 후보)
        for s in self.confirm:
            if s == primary:
                continue
            for (dx, dy, conf) in obs.get(SENSOR_KEY[s], {}).get("detections", []):
                corr.append((s, float(dx), float(dy), float(conf)))
        out = []
        wtot = sum(VOTE_W.values())
        for (ax, ay, aconf) in anchors:
            per = {primary: (float(ax), float(ay), float(aconf))}   # primary 는 1표(앵커)
            for (s, dx, dy, conf) in corr:                          # gate 안 다른 센서 → 센서당 최고 conf 1표
                if (dx - ax) ** 2 + (dy - ay) ** 2 <= self.gate ** 2 and (s not in per or conf > per[s][2]):
                    per[s] = (dx, dy, conf)
            if self.mode == "hard":
                if len(per) >= self.k:                              # 서로 다른 센서 ≥ k 면 확인
                    bx, by, _ = max(per.values(), key=lambda v: v[2])   # 위치=최고신뢰 센서
                    out.append((bx, by, min(1.0, len(per) / len(self.confirm))))
            else:                                                   # soft: Σ가중 ≥ tau, 위치=가중 무게중심
                wsum = sum(VOTE_W[s] for s in per)
                if wsum >= self.tau:
                    wx = sum(VOTE_W[s] * per[s][0] for s in per) / wsum
                    wy = sum(VOTE_W[s] * per[s][1] for s in per) / wsum
                    out.append((wx, wy, min(1.0, wsum / wtot)))
        return out


# ── CMPC: 교차모달 물리 일관성. "몇 개 봤나"가 아니라 "사람이라면 함께 나와야 할 채널이 양립하나". ──
CMPC_ALLWEATHER = {"SAR", "Audio"}     # 안개·수관·야간 통과(가림에 강함)
CMPC_BLOCKED = {"RGB", "Thermal", "LiDAR"}   # LOS/광학/열 — 수관·안개에 막힘


def cmpc_confirm(obs, cmpc_min=2, require_live=False, gate=2.5, conditional=True):
    """한 관측(obs)에서 교차모달 일관성으로 확인된 표적 위치들을 낸다(nav 무관·상태없음).
    서로 다른 물리채널 ≥ 요구치(조건부 완화)면 확인, require_live 면 liveness 도 근접해야.
    반환 [(x, y, conf), ...]. 정책과 실험이 공유해 규칙 드리프트를 막는다."""
    cand = []
    for s in SENSORS_5:
        for (dx, dy, conf) in obs.get(SENSOR_KEY[s], {}).get("detections", []):
            cand.append((s, float(dx), float(dy), float(conf)))
    live = [(float(x), float(y)) for (x, y, *_r) in obs.get("live", {}).get("detections", [])]
    clusters = []
    for (s, dx, dy, conf) in cand:
        for cl in clusters:
            if (dx - cl["cx"]) ** 2 + (dy - cl["cy"]) ** 2 <= gate ** 2:
                cl["mem"].append((s, dx, dy, conf))
                xs = [m[1] for m in cl["mem"]]; ys = [m[2] for m in cl["mem"]]
                cl["cx"] = sum(xs) / len(xs); cl["cy"] = sum(ys) / len(ys)
                break
        else:
            clusters.append({"cx": dx, "cy": dy, "mem": [(s, dx, dy, conf)]})
    out = []
    for cl in clusters:
        per = {}
        for (s, dx, dy, conf) in cl["mem"]:
            if s not in per or conf > per[s][2]:
                per[s] = (dx, dy, conf)
        mods = set(per)
        required = cmpc_min
        if conditional and cmpc_min >= 2 and mods.isdisjoint(CMPC_BLOCKED) and mods & CMPC_ALLWEATHER:
            required = 1                                   # 가림-강 채널만 → 수관 진짜 보존
        if len(mods) < required:
            continue
        if require_live and not any((lx - cl["cx"]) ** 2 + (ly - cl["cy"]) ** 2 <= gate ** 2 for (lx, ly) in live):
            continue                                       # liveness 없음(전-서명 decoy) → 기각
        wx = sum(per[s][0] for s in per) / len(per); wy = sum(per[s][1] for s in per) / len(per)
        out.append((wx, wy, min(1.0, len(mods) / 3.0)))
    return out


class CmpcPolicy(_SelectPolicy):
    """교차모달 일관성 정책(정보집합 I1/I2 실험용). claim 을 **서로 다른 물리채널 ≥ N** 합의로만
    건다(spatial voting 이 아니라 modal signature 일치). 조건부: 가림에 강한 SAR/Audio 만 있는
    군집(수관·SAR-dominant)은 ≥1 로 완화(진짜를 안 버리려). require_live 면 liveness 채널(호흡·심박)
    이 같이 있어야 확인 — 전-서명 decoy 를 거르는 유일한 정보.

    cmpc_min=1 → 기존 spatial voting(I0 기준선). =2 → CMPC(I1). +require_live → I2."""
    def __init__(self, cmpc_min=2, require_live=False, gate=2.5, conditional=True):
        super().__init__()
        self.cmpc_min = int(cmpc_min); self.require_live = bool(require_live); self.gate = float(gate)
        self.conditional = bool(conditional)   # 가림-강 채널만인 군집을 ≥1 로 완화(수관 진짜 보존)
        self._claim = []

    def choose(self, obs, feat):
        # claim 은 공유 규칙 cmpc_confirm 으로(정책·실험 드리프트 방지).
        self._claim = cmpc_confirm(obs, self.cmpc_min, self.require_live, self.gate, self.conditional)
        present = [s for s in SENSORS_5 if obs.get(SENSOR_KEY[s], {}).get("detections")]
        self.consulted = present or None
        best, bc = "RGB", -1.0
        for s in present:
            c = max(d[2] for d in obs[SENSOR_KEY[s]]["detections"])
            if c > bc:
                bc = c; best = s
        return best

    def claim_from(self, obs, primary):
        return list(self._claim)


class ForcedSensorPolicy(_SelectPolicy):
    """외부가 정한 센서를 그대로 쓰는 정책 — RL 롤아웃용(항법·claim·belief 는 공통 골격 그대로)."""
    def __init__(self):
        super().__init__()
        self.forced = "RGB"

    def choose(self, obs, feat):
        return self.forced


class ReActMambaPolicy(_SelectPolicy):
    """ReAct(Option B, 수치형): Mamba 가 관측시퀀스로 **센서별 유틸리티 D̂ 를 추론(reason)**,
    정책은 **argmax_a[D̂_a − λC_a − μE_a] 로 행동(act)**. 새 관측이 다시 Mamba 로(closed loop).
    비용/에너지 trade-off(λ,μ)를 **재학습 없이 결정시점에** 적용한다."""
    def __init__(self, weights, model, lam=LAM_COST, mu=MU_ENERGY):
        super().__init__()
        self.W = weights; self.model = model; self.lam = lam; self.mu = mu
        self.mfeat = []

    def choose(self, obs, feat):
        self.mfeat.append(feature_multi(obs))
        dhat = self.model.predict_reg(self.W, np.array(self.mfeat))[-1]      # reason: D̂ 벡터
        D = {a: float(dhat[i]) for i, a in enumerate(SENSORS_5)}
        U = utility_scores(D, self.lam, self.mu)                            # act: argmax(D̂−λC−μE)
        return max(U, key=U.get)


class OraclePolicy(_SelectPolicy):
    """cost-aware oracle 행동정책(학습 데이터 생성용) — 매 스텝 feature_multi 와 라벨을 기록한다.
    truth 를 보는 oracle 이므로 **학습에만** 쓰고 배포엔 안 쓴다."""
    def __init__(self):
        super().__init__()
        self.mfeat = []; self.labels = []; self.prev_choice = 0; self.prev_detected = 0.0

    def choose(self, obs, feat):
        # oracle 특권: 모든 센서 탐지를 동시에 보고 **가장 싼 탐지 센서**를 라벨로(cost 규율).
        # Mamba 는 이 라벨을 문맥특징(feature_multi, 미활성 센서의 이번 탐지 안 봄)으로만 모방한다.
        self.mfeat.append(feature_multi(obs, self.prev_choice, self.prev_detected))
        lab = oracle_label_cost(obs)
        self.labels.append(lab); self.prev_choice = lab
        return SENSORS_5[lab]

    def _after_claim(self, new_claims):
        self.prev_detected = 1.0 if new_claims else 0.0
