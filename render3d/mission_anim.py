# -*- coding: utf-8 -*-
"""Mission animation -- a UAV flying through the scene3d reference world in 3D, plus a live log of how the autonomy policy was applied.

Data comes straight from the IV&V telemetry bus (sar/ivv/harness.run_case_telemetry) -- nothing new is invented:
  10 Hz  machine state  : position, speed, heading, policy state, RGB vis, IMU sigma, coverage   (telemetry.STATE_HZ)
   1 Hz  ops report     : decimated by the bus automatically                                    (telemetry.REPORT_HZ)
   now   events         : WAYPOINT, DETECT, MRC, NAV_DEGRADED
   20 s  SUT decision   : trace.rule (the decision rationale the SUT emits itself -- thresholds are not re-copied here)
**Spec: 10 Hz, not 10 GHz** -- an update rate, not a bandwidth. The code says so itself: "10 Hz is not a NASA
standard; it is a research design point" (sar/ivv/harness.py telemetry_demo).

The observer view (chase, aerial) may show truth (targets) -- the sar/ivv/viewer.py rule. The SUT never sees it.
Output: interactive HTML (camera switch, play/pause) + a webm video recorded headless (if a browser is available).
"""
from __future__ import annotations

import math
import os
import sys


def _paths():
    here = os.path.dirname(os.path.abspath(__file__)); root = os.path.dirname(here)
    for p in (root, os.path.join(root, "sar"), os.path.join(root, "sar", "ivv")):
        if p not in sys.path:
            sys.path.insert(0, p)


def build(spec: dict, dem, speed: float = 20.0, name: str = "임무 재생", sut=None) -> "tuple[dict, dict]":
    """spec (IV&V scenario, scene3d recommended) + DEM -> (scene with an anim block, summary). spec["budget_min"] sets the length.
    sut=None -> default Python SUT. Pass a player (e.g. the fw C decision executive) to animate that policy instead."""
    _paths()
    import harness as Hn
    import telemetry as Tl
    from render3d import sar_bridge as B
    from render3d.visibility import CAMERAS
    decisions = []
    bus, metrics, ref = Hn.run_case_telemetry(spec, dem=dem, decisions=decisions, sut=sut)
    s = B.reference_scene(ref, (ref.GW / 2.0, ref.GH / 2.0), 0, name=name) if getattr(ref, "scene3d", False) else \
        B.terrain_scene(ref.dem, float(ref.mpp), name=name, V_m=float(ref.V), fidelity=ref.fidelity)
    if not getattr(ref, "scene3d", False):
        for tg in ref._targets:
            x, y = ref._g2w(tg["gx"], tg["gy"])
            s["props"].append({"kind": "person", "x": x, "y": y, "z": float(B._h(ref.dem, ref.mpp, x, y)), "size": 1.0, "yaw_deg": 0.0})
    g = lambda x, y: float(B._h(ref.dem, ref.mpp, x, y))
    states = []
    for st in bus.state_log:
        x, y = ref._g2w(*st["pos"])
        states.append([round(st["t"], 2), round(x, 1), round(y, 1), round(g(x, y) + float(st["alt"]), 1), round(float(st["heading"]), 1),
                       st["policy"], round(st["rgb"]["vis"], 3), round(st["imu_sigma"], 2), round(st["coverage"], 1), round(st["vel"], 2), round(float(st["alt"]), 1)])
    reports = [[round(r["t"], 2), Tl.format_report(r)] for r in bus.reports]
    events = [[round(e["t"], 2), e["kind"], e["detail"]] for e in bus.events]
    decs = []
    for d in decisions:
        o = d["obs"]
        decs.append([d["t"], d["state"], d["trace"].get("rule", ""),
                     "관측: RGB vis %.2f·탐지 %d · SAR hits %d · 열 %d · LiDAR %d · live %d · IMU σ %.1fm · GPS %s"
                     % (o["rgb_vis"], o["rgb_n"], o["sar_hits"], o["thermal_n"], o["lidar_n"], o["live_n"], o["imu_sigma"],
                        "불확실" if o["gps_uncertain"] else "정상")])
    truth = [ref._g2w(*t) for t in ref.truth()["targets"]]
    hf = CAMERAS["rgb"]["hfov_deg"]
    s["anim"] = {"states": states, "reports": reports, "events": events, "decisions": decs, "speed": speed,
                 "state_hz": Tl.STATE_HZ, "report_hz": Tl.REPORT_HZ, "decision_s": Hn.FRAME_S,
                 "rgb_fov_v": 2 * math.degrees(math.atan(math.tan(math.radians(hf / 2)) * 9 / 16)), "rgb_pitch_deg": -30.0,
                 "truth": [[x, y, g(x, y)] for x, y in truth]}
    if s.get("fog"):
        s["fog"]["views"] = ["onboard"]
    rates = bus.rates()
    summ = {"metrics": {k: metrics[k] for k in ("detected", "n_targets", "false_alarms", "steps") if k in metrics},
            "rates_measured": rates, "n_states": len(states), "n_reports": len(reports), "n_events": len(events),
            "n_decisions": len(decs), "decision_s": Hn.FRAME_S, "sim_seconds": states[-1][0] if states else 0.0, "fidelity": ref.fidelity,
            "scene3d": getattr(ref, "scene3d", False)}
    return s, summ


def default_spec(V: float = 800.0, seed: int = 4242, canyon: bool = False) -> dict:
    """Demo scenario: 2 targets (one under canopy), RGB·SAR·IMU·thermal·LiDAR, 3D visibility on, 10 min (30 decisions)."""
    return dict(seed=seed, lat=37.0, lon=128.0, V=V, illum=20000.0, agl=60.0 if canyon else 90.0, n_target=2, scene3d=True,
                fidelity="L1 합성 %s DEM + SceneDB" % ("협곡" if canyon else "언덕"), budget_min=10,
                sensors=["RGB", "SAR", "IMU", "Thermal", "LiDAR"],
                targets_spec=[{"bearing_deg": 60, "range_m": 900, "canopy": True}, {"bearing_deg": 140, "range_m": 1300, "canopy": False}])
