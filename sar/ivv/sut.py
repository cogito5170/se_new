#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""System Under Test — 능동탐색 정책. **관측만** 먹고 결정을 낸다.

독립성 계약(NASA IV&V): 이 파일은 reference·evaluator·truth 를 **import 하지 않는다**.
표적의 실제 위치를 절대 받지 않는다 — 오직 센서 패킷(관측)만. 자기 성공을 스스로 판정하지
않는다(그건 evaluator 몫). 계획은 자기 모델(policy_core + 자기 IMU 가정)로 한다 — 참조세계와
다른 가정을 써도 되고, 그 어긋남이 evaluator 에서 드러나는 것이 이 구조의 목적이다.
"""
import ctypes
import math
import os
import subprocess
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_SAR = os.path.dirname(_HERE)
_SO = os.path.join(_SAR, "libsarcore.so")


def _lib():
    if not os.path.exists(_SO):
        subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-I" + os.path.join(_SAR, "..", "policy_core"),
                        "-o", _SO, os.path.join(_SAR, "sar_core.c"),
                        os.path.join(_SAR, "..", "policy_core", "policy_core.c"), "-lm"], check=True)
    lib = ctypes.CDLL(_SO)
    f32 = np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags="C_CONTIGUOUS")
    lib.sar_grid_w.restype = lib.sar_grid_h.restype = ctypes.c_int
    lib.sar_set_rmax.argtypes = [ctypes.c_float]
    lib.sar_next.argtypes = [f32, ctypes.c_float, ctypes.c_float,
                             ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_int)]
    return lib


class SUT:
    def __init__(self):
        self.lib = _lib()
        self.GW = self.lib.sar_grid_w(); self.GH = self.lib.sar_grid_h()
        self.lib.sar_set_rmax(ctypes.c_float(3.0))
        self.bel = np.ones(self.GW * self.GH, dtype=np.float32) / (self.GW * self.GH)
        self.veh = [2.0, 2.0]; self.prev = [2.0, 2.0]; self.heading = 0.0
        self.tsf = 0.0
        self.covered = np.zeros((self.GH, self.GW), dtype=bool)
        self.claims = []                                     # 이 시스템이 '표적'이라 **주장**한 위치(추정)

    def _pnext(self, b):
        tx, ty = ctypes.c_float(), ctypes.c_float(); nn = ctypes.c_int()
        self.lib.sar_next(np.ascontiguousarray(b, dtype=np.float32), ctypes.c_float(self.veh[0]), ctypes.c_float(self.veh[1]),
                          ctypes.byref(tx), ctypes.byref(ty), ctypes.byref(nn))
        return tx.value, ty.value

    def step(self, obs):
        """센서 패킷 → 결정. 반환: {waypoint, detections(주장), state, telemetry}. truth 안 씀."""
        GW, GH = self.GW, self.GH
        # 덜 greedy 항법(미탐색 보너스)
        uncov = 1.0 - self.covered.astype(np.float32)
        navb = self.bel + 0.7 * (uncov.reshape(-1) / (uncov.sum() + 1e-6))
        tx, ty = self._pnext(navb / (navb.sum() + 1e-9))
        sig = obs["imu"]["sigma"]
        # **SUT 자기 가정**: 관성드리프트가 크면(자기 모델로) 위치불확실 → 최소위험(참조와 무관하게)
        if not obs["imu"]["ok"] or sig >= 36.0:
            state = "MRC"
            return {"waypoint": self.veh[:], "detections": [], "state": state,
                    "telemetry": {"coverage": float(100.0*self.covered.sum()/(GW*GH)), "heading": self.heading,
                                  "sigma": sig, "gps_uncertain": obs["gps"]["uncertain"], "sar_hits": obs["sar"]["hits"]},
                    "trace": {"rule": "IMU %s · σ=%.1fm ≥ 36 → MRC(최소위험: 제자리·탐색 중단)" % ("불량" if not obs["imu"]["ok"] else "정상", sig),
                              "vis": obs["rgb"]["vis"], "imu_sigma": sig, "nav_target": None, "belief_peak": float(self.bel.max())}}
        vis = obs["rgb"]["vis"]
        state = "SEARCHING" if vis >= 0.5 else ("DEGRADED" if vis >= 0.25 else "LOW-INFO")
        # Decision rationale (for the live log). Built from the same variables the decision itself uses -- the viewer does not re-copy thresholds (single source).
        rule = ("RGB vis=%.2f %s → %s" % (vis, "≥0.5" if vis >= 0.5 else ("∈[0.25,0.5)" if vis >= 0.25 else "<0.25"), state)
                + " · IMU σ=%.1fm<36 → 비행 계속" % sig
                + " · 다음 웨이포인트 = policy_core(믿음 %.3f + 미탐색 보너스 0.7) 최대" % float(self.bel.max()))
        self.prev = self.veh[:]; self.veh = [tx, ty]
        if abs(self.veh[0]-self.prev[0]) + abs(self.veh[1]-self.prev[1]) > 0.1:
            self.heading = math.degrees(math.atan2(self.veh[1]-self.prev[1], self.veh[0]-self.prev[0]))
        # 커버리지
        for gy in range(GH):
            for gx in range(GW):
                if (gx-self.veh[0])**2 + (gy-self.veh[1])**2 <= 9:
                    self.covered[gy, gx] = True
        # 관측된 RGB 탐지 → **주장**(추정 위치). truth 아님 — 센서가 준 픽셀 위치일 뿐.
        new_claims = []
        for (dx, dy, conf) in obs["rgb"]["detections"]:
            if all((dx-c[0])**2 + (dy-c[1])**2 > 4 for c in self.claims):
                self.claims.append((dx, dy)); new_claims.append((dx, dy, conf))
                for gy in range(GH):
                    for gx in range(GW):
                        self.bel[gy*GW+gx] *= (math.exp(-((gx-dx)**2+(gy-dy)**2)/(2*1.2**2)) + 0.02)
        ssum = self.bel.sum(); self.bel /= (ssum if ssum > 0 else 1)
        if new_claims:
            rule += " · RGB 탐지 %d건 → 표적 주장, 믿음을 그 주변으로 갱신" % len(new_claims)
        elif obs["rgb"]["detections"]:
            rule += " · RGB 탐지 %d건(기존 주장 2칸 안 → 중복, 무시)" % len(obs["rgb"]["detections"])
        return {"waypoint": self.veh[:], "detections": new_claims, "state": state,
                "telemetry": {"coverage": float(100.0*self.covered.sum()/(GW*GH)), "heading": self.heading,
                              "sigma": sig, "gps_uncertain": obs["gps"]["uncertain"], "sar_hits": obs["sar"]["hits"]},
                "trace": {"rule": rule, "vis": vis, "imu_sigma": sig, "nav_target": [float(tx), float(ty)],
                          "belief_peak": float(self.bel.max()), "n_rgb_obs": len(obs["rgb"]["detections"]),
                          "sar_hits": obs["sar"]["hits"]}}
