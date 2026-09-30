#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fw/ (LLM 없는 bare-metal 결정 executive)를 sar 검증환경으로 V&V.

**실제 C 코드**를 잰다: libfw.so(ctypes)로 fw_agent_step 을 호출해, sar reference 가 낸 관측을
먹이고 fw 가 낸 확인 탐지(belief)를 sar evaluator 로 채점한다(파이썬 재구현 아님). 지표는 정책
비교와 동일: 탐지율·오경보·위치RMSE·평균센서비용/스텝. 비교 맥락으로 Baseline·NASA-rule·RL·
RL+SoftVote 도 같은 held-out 시나리오(지리산)에서 같이 채점한다.

정직: fw 는 매 스텝 present 센서 전부를 융합(full fusion)한다 → 비용은 그 센서들로 계상. sar 는
심판(숨은 truth·독립 물리·evaluator)이며 fw 는 선수다.
"""
from __future__ import annotations
import ctypes
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
REPO = os.path.dirname(os.path.dirname(HERE))
import selector_train as st
import policies as _pol
from ctrl.model import mamba_selector as _ms

# fw 센서 순서(bridge.c 와 동일): RGB, THERMAL, LIDAR, SAR, AUDIO
FW_SENSORS = ["RGB", "THERMAL", "LIDAR", "SAR", "AUDIO"]
FW_OBSKEY = ["rgb", "thermal", "lidar", "sar", "audio"]
FW_COSTKEY = {"RGB": "RGB", "THERMAL": "Thermal", "LIDAR": "LiDAR", "SAR": "SAR", "AUDIO": "Audio"}
FW_VOTE_W = [1.0, 0.7, 0.8, 0.5, 0.35]


def load_lib():
    """libfw.so 를 (필요하면 빌드해서) ctypes 로 로드."""
    so = os.path.join(REPO, "fw", "libfw.so")
    if not os.path.exists(so):
        subprocess.run(["make", "-C", os.path.join(REPO, "fw"), "lib"], check=True,
                       capture_output=True, text=True)
    lib = ctypes.CDLL(so)
    lib.fw_bridge_new.restype = ctypes.c_void_p
    lib.fw_bridge_free.argtypes = [ctypes.c_void_p]
    lib.fw_bridge_set_confirm.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_float]
    lib.fw_bridge_set_nisgate.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.fw_bridge_set_cmpc.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    fp = ctypes.POINTER(ctypes.c_float); ip = ctypes.POINTER(ctypes.c_int)
    lib.fw_bridge_step.argtypes = [ctypes.c_void_p, fp, fp, fp, ip, fp,
                                   ctypes.c_float, ctypes.c_float, ctypes.c_int, ctypes.c_int, ctypes.c_float,
                                   ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                   fp, fp, ip, fp, fp]
    lib.fw_bridge_step.restype = ctypes.c_int
    return lib


class FwBridgePolicy(_pol._SelectPolicy):
    """실제 fw C 결정 executive 를 sar 안에서 구동. 항법은 공통 골격, claim 은 fw 의 confirmed belief."""
    def __init__(self, lib, confirm_n=3, confirm_th=0.6, nis_gate=0.0, cmpc_min=0, require_live=False,
                 nav_by_action=False):
        super().__init__()
        self.fwlib = lib
        self.h = lib.fw_bridge_new()
        lib.fw_bridge_set_confirm(self.h, int(confirm_n), ctypes.c_float(confirm_th))
        lib.fw_bridge_set_nisgate(self.h, ctypes.c_float(nis_gate))
        lib.fw_bridge_set_cmpc(self.h, int(cmpc_min), 1 if require_live else 0)
        self._claim = []
        self.last_nis = 0.0
        self.last_px = self.last_py = 0.0
        # nav_by_action=False → 항법은 공통 골격(_SelectPolicy) 그대로. V&V 채점 경로(run_policy)는
        # 이 기본값을 써서 옛 거동 불변. True 면 **fw 의 Action 이 항법을 직접 몬다**(3D 데모용).
        self.nav_by_action = bool(nav_by_action)
        self._home = None
        # 외부 세계상태(참조세계가 모델 안 하는 것 — 배터리·센서고장·충돌). 미션 러너가 스텝마다
        # 세팅한다. 기본값(가득·정상·무충돌)이면 fw_bridge_step 입력이 옛것과 동일 → V&V 채점 불변.
        self.ext_battery = 1.0
        self.ext_collision = 0.0
        self.ext_health = [1.0] * 5
        # 다중표적 미션: 확인 표적을 inspect_dwell 스텝 정밀관측 후 '기록'하고 다음 표적 탐색으로 복귀.
        # None(기본)=끝까지 그 표적에 loiter(단일표적 확인 arc 그대로 — 기존 검사 불변). 미션 러너가 세팅.
        self.inspect_dwell = None
        self._dwell = 0
        self._retired = []                        # 이미 확인·기록했거나 거부한 belief 위치(다시 안 붙잡음)
        # 후보에 접근해 reject_after 스텝 hover 해도 확인(liveness+CMPC) 안 되면 거부(FP)하고 탐색 복귀.
        # None(기본)=거부 안 함(단일표적 arc 그대로). 미션 러너가 세팅.
        self.reject_after = None
        self._appr = 0
        self._invest = None                       # 지금 조사(접근·hover) 중인 후보 자리(끈적: 확인/거부까지 유지)
        self._prevdets = []                       # 직전 스텝 센서 탐지 위치(지속성 필터 — 순간 clutter 걸러냄)

    def __del__(self):
        try:
            self.fwlib.fw_bridge_free(self.h)
        except Exception:      # noqa: BLE001
            pass

    def choose(self, obs, feat):
        ev = [0.0] * 5; xs = [0.0] * 5; ys = [0.0] * 5; pres = [0] * 5
        health = [float(h) for h in self.ext_health]     # 외부 세계상태(기본 [1]*5)
        for i, key in enumerate(FW_OBSKEY):
            dets = obs.get(key, {}).get("detections", [])
            if dets:
                dx, dy, c = max(dets, key=lambda d: d[2])   # 최고신뢰 탐지
                ev[i] = float(c); xs[i] = float(dx); ys[i] = float(dy); pres[i] = 1
        imu_ok = 1 if obs["imu"]["ok"] else 0
        gps_valid = 0 if obs["gps"]["uncertain"] else 1
        pos_err = 0.0 if imu_ok else 5.0
        ld = obs.get("live", {}).get("detections", [])
        live_p, live_x, live_y = (1, float(ld[0][0]), float(ld[0][1])) if ld else (0, 0.0, 0.0)
        cf = (ctypes.c_float * 5)
        ci = (ctypes.c_int * 5)
        px = ctypes.c_float(); py = ctypes.c_float(); conf = ctypes.c_int(); tconf = ctypes.c_float()
        nis = ctypes.c_float()
        act = self.fwlib.fw_bridge_step(
            self.h, cf(*ev), cf(*xs), cf(*ys), ci(*pres), cf(*health),
            ctypes.c_float(self.ext_battery), ctypes.c_float(self.ext_collision),
            ctypes.c_int(imu_ok), ctypes.c_int(gps_valid),
            ctypes.c_float(pos_err),
            ctypes.c_int(live_p), ctypes.c_float(live_x), ctypes.c_float(live_y),
            ctypes.byref(px), ctypes.byref(py), ctypes.byref(conf), ctypes.byref(tconf), ctypes.byref(nis))
        self.last_action = int(act)            # C 결정(안전필터 뒤 최종 Action enum) — trace 용
        self.last_conf = int(conf.value); self.last_tconf = float(tconf.value)
        self.last_nis = float(nis.value)
        self.last_px = float(px.value); self.last_py = float(py.value)   # fw belief 위치(격자) — Action 항법용
        # 비용: 이번 스텝 present 센서 전부(full fusion) — 정직 계상
        self.consulted = [FW_COSTKEY[FW_SENSORS[i]] for i in range(5) if pres[i]]
        # claim: fw 가 시간적으로 확인한 표적만
        self._claim = [(px.value, py.value, tconf.value)] if conf.value else []
        # telemetry primary = 가중 최강 present 센서(없으면 RGB)
        best_i, best_w = -1, -1.0
        for i in range(5):
            if pres[i] and FW_VOTE_W[i] * ev[i] > best_w:
                best_w = FW_VOTE_W[i] * ev[i]; best_i = i
        return FW_COSTKEY[FW_SENSORS[best_i]] if best_i >= 0 else "RGB"

    def claim_from(self, obs, primary):
        return list(self._claim)

    # fw C 결정 executive의 근거를 trace 로 내보낸다 — render3d 애니메이션 로그가 그대로 보여준다.
    _ACT = ["NONE", "SEARCH", "APPROACH", "INSPECT", "RETURN", "AVOID", "RELOCALIZE", "EMERGENCY", "ABSTAIN"]

    def _trace(self, out):
        """C 결정(Action)·target_conf·확인여부·NIS 를 애니메이션 로그가 읽는 trace 로 붙인다."""
        act = getattr(self, "last_action", 0)
        name = self._ACT[act] if 0 <= act < len(self._ACT) else "NONE"
        rule = "fw C executive: 행동=%s · target_conf=%.2f · %s · NIS=%.1f" % (
            name, getattr(self, "last_tconf", 0.0),
            ("확인됨(CMPC≥2+liveness·시간확인)" if getattr(self, "last_conf", 0) else "미확인"),
            getattr(self, "last_nis", 0.0))
        out["trace"] = {"rule": rule, "action": name, "confirmed": int(getattr(self, "last_conf", 0)),
                        "nis": round(getattr(self, "last_nis", 0.0), 2)}
        return out

    def step(self, obs):
        if not self.nav_by_action:
            return self._trace(super().step(obs))          # 공통 항법(V&V 채점 경로 불변)
        return self._trace(self._step_by_action(obs))      # fw Action 이 항법을 몬다(3D 데모)

    def _toward(self, tx, ty, step=3.0):
        """veh 에서 (tx,ty) 로 최대 step 칸 이동(공통 골격 rmax=3 과 같은 속도). 격자 안으로 clip."""
        x, y = self.veh
        dx, dy = tx - x, ty - y; n = math.hypot(dx, dy)
        if n > step:
            tx, ty = x + dx * step / n, y + dy * step / n
        return [float(np.clip(tx, 0, self.GW - 1)), float(np.clip(ty, 0, self.GH - 1))]

    def _retire_loc(self, x, y):
        """확인·기록했거나 거부한 표적 자리를 은퇴시킨다: 다시 안 붙잡고(_retired), **믿음도 눌러**
        커버리지 항법이 그 자리로 다시 끌려가지 않게 한다(안 그러면 찾은 표적에 영영 캠핑)."""
        self._retired.append((float(x), float(y)))
        GW, GH = self.GW, self.GH
        for gy in range(GH):
            for gx in range(GW):
                if (gx - x) ** 2 + (gy - y) ** 2 <= 9:       # 반경 3칸
                    self.covered[gy, gx] = True
                    self.bel[gy * GW + gx] *= 0.001
        s = self.bel.sum(); self.bel /= (s if s > 0 else 1)

    def _valid_pt(self, px, py):
        """격자 안이고 이미 기록/거부(_retired)한 자리가 아니면 참."""
        return (0.5 <= px <= self.GW - 1 and 0.5 <= py <= self.GH - 1
                and not any((px - rx) ** 2 + (py - ry) ** 2 <= 9 for rx, ry in self._retired))

    @staticmethod
    def _detpts(obs):
        return [(float(dd[0]), float(dd[1])) for k in FW_OBSKEY for dd in obs.get(k, {}).get("detections", [])]

    def _nearest_cue(self, curdets, rng=6.0):
        """은퇴 안 됐고 **지속적인**(직전 스텝에도 근처에 뜬) 가장 가까운 센서 탐지. 없으면 None.
        지속성 필터로 순간 clutter(persist=1)를 빼고 실표적·decoy(매 스텝 뜸)만 조사한다 — 안 그러면
        끈적한 조사가 clutter 를 좇다 시간을 다 쓴다(실측: clutter 0.18 에서 0/5)."""
        x, y = self.veh; best, bd = None, rng
        for (cx, cy) in curdets:
            if not self._valid_pt(cx, cy):
                continue
            if not any((cx - px) ** 2 + (cy - py) ** 2 <= 1.5 ** 2 for px, py in self._prevdets):
                continue                                    # 직전 스텝에 근처 탐지 없음 → 순간 clutter, 조사 안 함
            d = math.hypot(cx - x, cy - y)
            if d < bd:
                bd = d; best = (cx, cy)
        return best

    def _step_by_action(self, obs):
        """fw Action 이 항법을 모는 스텝. C 브리지는 **한 번만** 부른다(연속확인 계수 보존).
        후보(확인 belief 또는 가장 가까운 센서 큐)를 조사(접근·hover)하고, liveness 없으면 거부(FP),
        후보 없으면 커버리지 탐색. 확인 생존자 기록·재탐색은 미션 러너가 _retire_loc 로 한다."""
        GW, GH = self.GW, self.GH
        if self._home is None:
            self._home = [float(self.veh[0]), float(self.veh[1])]
        self.consulted = None
        feat = _pol.feature(obs); self.feat_hist.append(feat)
        sig = obs["imu"]["sigma"]
        self.primary = self.choose(obs, feat)               # C 브리지 1회 → last_action·belief·_claim
        act = getattr(self, "last_action", 0)
        aname = self._ACT[act] if 0 <= act < len(self._ACT) else "NONE"
        vis = obs["rgb"]["vis"]
        state = "SEARCHING" if vis >= 0.5 else ("DEGRADED" if vis >= 0.25 else "LOW-INFO")

        # 조사 후보(끈적): 확인 belief 최우선 → 조사 중이던 후보 유지 → 미확인 belief → 가장 가까운 큐.
        # 끈적하게 붙들지 않으면 열화상이 한 스텝 안 떠도(≈55%) 딴 큐로 새서 확인을 못 쌓는다(실측).
        curdets = self._detpts(obs)
        cand = None
        if aname not in ("RETURN", "EMERGENCY", "RELOCALIZE", "NONE"):
            if self._valid_pt(self.last_px, self.last_py) and self.last_conf:
                cand = (self.last_px, self.last_py)
            elif self._invest is not None and self._valid_pt(*self._invest):
                cand = self._invest
            elif self._valid_pt(self.last_px, self.last_py) and aname in ("APPROACH", "INSPECT"):
                cand = (self.last_px, self.last_py)
            else:
                cand = self._nearest_cue(curdets)
        self._invest = cand
        self._prevdets = curdets
        # hover/reject 회계: 확인 안 된 후보에 오래 붙으면(liveness 없음) 거부(FP)
        if cand is not None and math.hypot(cand[0] - self.veh[0], cand[1] - self.veh[1]) <= 1.5:
            if self.last_conf:
                self._appr = 0
            else:
                self._appr += 1
                if self.reject_after and self._appr >= self.reject_after:
                    self._retire_loc(cand[0], cand[1]); self._appr = 0; cand = None; self._invest = None
        else:
            self._appr = 0

        # 웨이포인트
        self.prev = self.veh[:]
        if aname in ("RETURN", "EMERGENCY"):
            self.veh = self._toward(self._home[0], self._home[1])
        elif aname in ("RELOCALIZE", "NONE"):
            self.veh = self.veh[:]                          # 정지(호버)
        elif cand is not None:
            self.veh = self.veh[:] if math.hypot(cand[0] - self.veh[0], cand[1] - self.veh[1]) <= 1.2 \
                else self._toward(cand[0], cand[1])
        else:                                               # 후보 없음 → 커버리지 탐색
            uncov = 1.0 - self.covered.astype(np.float32)
            navb = self.bel + 0.7 * (uncov.reshape(-1) / (uncov.sum() + 1e-6))
            self.veh = list(self._pnext(navb / (navb.sum() + 1e-9)))
        if abs(self.veh[0] - self.prev[0]) + abs(self.veh[1] - self.prev[1]) > 0.1:
            self.heading = math.degrees(math.atan2(self.veh[1] - self.prev[1], self.veh[0] - self.prev[0]))
        for gy in range(GH):
            for gx in range(GW):
                if (gx - self.veh[0]) ** 2 + (gy - self.veh[1]) ** 2 <= 9:
                    self.covered[gy, gx] = True
        src = self.claim_from(obs, self.primary)            # claim = fw 확인 belief
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


def run(n_ep=16, seed=9999, clutter=0.0, persist=1, dem=None, lib=None):
    """clutter: 헛 탐지율. persist: 헛 탐지가 같은 위치에 머무는 스텝(1=transient). 전 정책 동일 시나리오."""
    lib = lib or load_lib()
    if dem is None:
        dem, te_src = st._dem_for(st.TEST_LOC)
        print("held-out 지리산 DEM=%s%s (학습에 안 쓴 곳)" % (dem.shape, te_src))
    W_rl = dict(np.load(os.path.join(REPO, "ctrl", "model", "mamba_rl_5sensor.npz")))
    cand = {
        "fw C (확인창 N=3)": lambda: FwBridgePolicy(lib, confirm_n=3),
        "fw C (확인창 N=2)": lambda: FwBridgePolicy(lib, confirm_n=2),
        "fw C (확인창 N=1)": lambda: FwBridgePolicy(lib, confirm_n=1),
        "Baseline(RGB)": lambda: _pol.BaselinePolicy(),
        "NASA-rule(5센서)": lambda: _pol.NASARulePolicy(),
        "Mamba-RL(보상)": lambda: _pol.MambaSensorPolicy(W_rl, _ms),
        "RL+SoftVote(t0.9)": lambda: _pol.VotingPolicy(_pol.MambaSensorPolicy(W_rl, _ms), mode="soft", tau=0.9),
    }
    rng = np.random.default_rng(seed)
    agg = {k: [] for k in cand}
    for _ in range(n_ep):
        scn = st._rand_scenario(st.TEST_LOC, rng.integers(1, 10_000_000), rng)
        scn["clutter"] = clutter                       # 헛 탐지 주입(전 정책 동일 시나리오)
        scn["clutter_persist"] = persist               # 헛 탐지 공간 지속성(스텝)
        for name, mk in cand.items():
            agg[name].append(st.run_policy(mk, scn, dem, budget=32))
    import evaluator as _eval
    print("\n### clutter=%.2f persist=%d" % (clutter, persist))
    print("| 정책 | 탐지율 | 위치RMSE | 오경보 | 평균센서비용/스텝 |")
    print("|---|---|---|---|---|")
    rows = {}
    for name, lst in agg.items():
        s = _eval.summarize(lst); s["cost"] = float(np.mean([r["cost"] for r in lst]))
        dr = s["detection_rate"][0]; rm = s["loc_rmse_cells"][0]
        print("| %s | %.0f%% | %s | %.2f | %.3f |" % (name, dr, ("%.2f" % rm) if rm == rm else "—",
                                                       s["false_alarms"][0], s["cost"]))
        rows[name] = s
    return rows


def _score_traj(ref, log, eps=2.5):
    """운동 표적을 **시각 맞춰** 채점: 스텝 i 의 claim 을 그 시각 표적 위치와 맞춘다.
    detected=truth 하나라도 근접 claim 이 있었나, FA=어느 시각 표적에도 안 붙은 claim, RMSE=붙은 오차."""
    traj = ref._traj
    n_t = max(1, len(ref._targets))
    detected = set(); fa = 0; errs = []
    for i, out in enumerate(log):
        tg = traj[i] if i < len(traj) else (traj[-1] if traj else [])
        for (cx, cy, *_r) in out.get("detections", []):
            bd = 1e9; bj = -1
            for j, (tx, ty) in enumerate(tg):
                d = ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
                if d < bd:
                    bd = d; bj = j
            if bj >= 0 and bd <= eps:
                detected.add(bj); errs.append(bd)
            else:
                fa += 1
    dr = 100.0 * len(detected) / n_t
    rmse = (sum(e * e for e in errs) / len(errs)) ** 0.5 if errs else float("nan")
    return dr, rmse, fa


def run_motion(mk, dem, motion, persist, clutter, n_ep=16, seed=9999, budget=32):
    import reference as _ref
    rng = np.random.default_rng(seed)
    drs = []; rmses = []; fas = []; niss = []
    for _ in range(n_ep):
        scn = st._rand_scenario(st.TEST_LOC, rng.integers(1, 10_000_000), rng)
        scn["target_motion"] = motion; scn["clutter"] = clutter; scn["clutter_persist"] = persist
        ref = _ref.Reference(scn, dem=dem); pol = mk(); log = []; nv = []
        for _ in range(budget):
            obs = ref.observe(pol.veh)
            out = pol.step({k: v for k, v in obs.items() if k != "truth"}); log.append(out)
            if getattr(pol, "last_nis", None) is not None and pol._claim:
                nv.append(pol.last_nis)     # 붙은 스텝의 NIS(운동 일관성)
        dr, rmse, fa = _score_traj(ref, log)
        drs.append(dr); rmses.append(rmse); fas.append(fa)
        if nv:
            niss.append(float(np.mean(nv)))
    rms = [r for r in rmses if r == r]
    return (float(np.mean(drs)), (float(np.mean(rms)) if rms else float("nan")),
            float(np.mean(fas)), (float(np.mean(niss)) if niss else float("nan")))


def motion_ablation(n_ep=16):
    """motion-only ablation (사용자 표 A–F): persistence × target motion, fw N=2 게이트 off vs on.
    핵심 질문: motion consistency(NIS 게이트)가 무엇을 거르고 무엇을 못 거르나."""
    lib = load_lib(); dem, src = st._dem_for(st.TEST_LOC)
    print("held-out 지리산 DEM=%s%s · motion-only ablation (fw N=2)" % (dem.shape, src))
    GATE = 9.0    # chi^2 2-dof ~99% — NIS 이 위면 운동 모순
    conds = [
        ("A 정지·transient clutter",   "static", 1, 0.15),
        ("B 정지·persistent clutter",  "static", 4, 0.15),
        ("C 등속 표적(clutter 0)",      "const",  1, 0.0),
        ("D 가속 표적(clutter 0)",      "accel",  1, 0.0),
        ("E 방향전환 표적(clutter 0)",  "turn",   1, 0.0),
        ("F 등속표적+persistent clutter", "const", 4, 0.15),
    ]
    print("\n| 조건 | gate | 탐지율 | 위치RMSE | 오경보 | 평균NIS |")
    print("|---|---|---|---|---|---|")
    for label, motion, persist, clutter in conds:
        for gate_name, gate in (("off", 0.0), ("NIS", GATE)):
            dr, rmse, fa, nis = run_motion(
                lambda g=gate: FwBridgePolicy(lib, confirm_n=2, nis_gate=g),
                dem, motion, persist, clutter, n_ep=n_ep)
            print("| %s | %s | %.0f%% | %s | %.2f | %s |" % (
                label, gate_name, dr, ("%.2f" % rmse) if rmse == rmse else "—", fa,
                ("%.2f" % nis) if nis == nis else "—"))


def grid(n_ep=12):
    """결합 스윕: 확인창 N × 지속성 persistence × 운동 motion (clutter=0.20 고정). 지금까지의
    경계를 한 화면에. 각 칸=탐지율/오경보(운동 표적은 시각맞춤 채점). fw(N) gate off."""
    lib = load_lib(); dem, src = st._dem_for(st.TEST_LOC)
    print("held-out 지리산 DEM=%s%s · **결합 스윕** N×persistence×motion (clutter=0.20, n_ep=%d)" % (dem.shape, src, n_ep))
    print("각 칸 = 탐지율%% / 오경보\n")
    print("| motion | persist | N=1 | N=2 | N=3 |")
    print("|---|---|---|---|---|")
    for motion in ("static", "const"):
        for persist in (1, 4):
            cells = []
            for N in (1, 2, 3):
                dr, rmse, fa, nis = run_motion(
                    lambda N=N: FwBridgePolicy(lib, confirm_n=N),
                    dem, motion, persist, 0.20, n_ep=n_ep)
                cells.append("%.0f%%/%.1f" % (dr, fa))
            tag = "transient" if persist == 1 else "persistent"
            print("| %s | %d(%s) | %s |" % (motion, persist, tag, " | ".join(cells)))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--ep", type=int, default=16)
    ap.add_argument("--clutter", type=float, default=None, help="단일 clutter율")
    ap.add_argument("--persist", type=int, default=1, help="헛 탐지 공간 지속성(스텝)")
    ap.add_argument("--mode", choices=["rate", "persist", "motion", "grid"], default="rate",
                    help="rate=clutter율 · persist=지속성 · motion=운동 ablation · grid=결합 스윕")
    a, _ = ap.parse_known_args()
    if a.mode == "grid":
        grid(n_ep=a.ep)
    elif a.mode == "motion":
        motion_ablation(n_ep=a.ep)
    else:
        lib = load_lib(); dem, src = st._dem_for(st.TEST_LOC)
        if a.clutter is not None:
            run(n_ep=a.ep, clutter=a.clutter, persist=a.persist, dem=dem, lib=lib)
        elif a.mode == "persist":
            print("held-out 지리산 DEM=%s%s · **지속성 스윕**(clutter=0.20 고정, persist=1/2/4)" % (dem.shape, src))
            for p in (1, 2, 4):
                run(n_ep=a.ep, clutter=0.20, persist=p, dem=dem, lib=lib)
        else:
            print("held-out 지리산 DEM=%s%s · clutter율 스윕(persist=1 transient)" % (dem.shape, src))
            for c in (0.0, 0.15, 0.30):
                run(n_ep=a.ep, clutter=c, persist=1, dem=dem, lib=lib)
