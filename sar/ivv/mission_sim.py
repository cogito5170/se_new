#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자연어 시나리오 → 폐루프 미션 시뮬레이션(fw C 결정 executive가 참조세계 안에서 UAV 제어).

미션은 **사건으로 끝난다**(고정 시간 아님): 전원(모든 표적) 확인 OR 운용 불능
(배터리 소진·핵심센서 고장 지속·충돌 파손). 배터리·센서고장·충돌은 참조세계가 모델하지
않으므로(참조세계는 관측만 낸다) 여기서 대본으로 세계상태를 넣어 fw 의 FDIR·안전필터가
실제로 발화하게 한다.

정직:
 · false positive(오인)는 참조세계의 **decoy**(전-서명이지만 liveness 없음 = 따뜻한 바위·동물)와
   **clutter**(순간 헛탐지 = 흔들리는 식생)로 실재한다. fw 는 liveness 로 이를 거른다 — 영상은
   '센서가 후보를 올림 → 접근 → 생체징후 없음 → 거부'를 보인다. 확인까지 샌 오경보는 평가기가 센다.
 · false negative(놓침)는 **수관 은폐 + RGB/열만으로 CMPC≥2 미달**로 실재한다(정지 자체가 아니라
   가림이 원인 — liveness 는 미세도플러라 정지한 사람도 호흡으로 잡힌다).
 · 개수는 여기서 정하지 않는다. 평가기가 truth 로 잰 detected/false_alarms/missed 를 그대로 낸다.

산출: 프레임별 상태 JSON(veh·action·belief·센서 탐지·확인 claim(FP/참 분류)·배터리·센서건강·
truth 오버레이) → mission_video.py 가 두 mp4(온보드 RGB+센서 / 상공 샷)로 그린다.
"""
from __future__ import annotations
import ctypes
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import reference as _ref
import evaluator as _eval
import fw_vv as _fw

FRAME_S = 20.0                       # 결정 간격(초) — harness 와 동일
SENS = _fw.FW_SENSORS                # [RGB, THERMAL, LIDAR, SAR, AUDIO]
OBSKEY = _fw.FW_OBSKEY               # [rgb, thermal, lidar, sar, audio]
EPS = 2.5                            # 평가기 매칭 게이트(칸) — evaluator.evaluate 와 동일


def _found_target(truth_targets, claim_xy, eps=EPS):
    """확인 claim 이 어느 truth 표적과 eps 안이면 그 index, 아니면 -1(= false positive)."""
    best, bd = -1, eps
    for i, (tx, ty) in enumerate(truth_targets):
        d = math.hypot(claim_xy[0] - tx, claim_xy[1] - ty)
        if d <= bd:
            bd = d; best = i
    return best


def run(scenario, dem=None, lib=None, battery_life_steps=150, obstacle=None,
        thermal_fault=None, max_steps=400, out=None, real_dem=False, return_ref=False):
    """scenario(자연어 파서 산출) → 미션 실행. 반환 (data, summary).

    battery_life_steps: 만충에서 0까지 걸리는 스텝(≈ battery_life_steps*20s 비행). fw 는 0.25 에서
      RETURN, 0.10 에서 EMERGENCY. obstacle: (gx,gy) 회피 대상(없으면 그리드 중앙 근처). thermal_fault:
      열화상 고장 창 [a,b)(FDIR 격리 시연). max_steps: 렌더 폭주 방지 상한."""
    lib = lib or _fw.load_lib()
    if dem is None and real_dem and scenario.get("place"):
        try:                                     # 실 DEM(AWS Terrarium) — 지명 실좌표의 실제 지형
            from sar import terrain as _t
            dem, _ext, _meta = _t.fetch_dem(scenario["lat"], scenario["lon"], radius_m=3000.0, zoom=12)
        except Exception as _e:                  # noqa: BLE001 — 네트워크 실패 시 합성으로 강등(정직히 표기)
            print("실 DEM 조회 실패(%s) → 합성 DEM 강등" % type(_e).__name__)
            scenario = dict(scenario, place=None, fidelity="L1 합성 DEM(실 DEM 조회 실패)")
            dem = None
    if dem is None:                              # 오프라인: 합성 DEM(네트워크 DEM 조회 안 함)
        from render3d import sar_bridge as _B
        dem = _B.synthetic_dem(96, seed=scenario.get("seed", 2))
    ref = _ref.Reference(scenario, dem=dem)
    GW, GH = ref.GW, ref.GH
    pol = _fw.FwBridgePolicy(lib, confirm_n=2, confirm_th=0.6, nis_gate=24.0,
                             cmpc_min=2, require_live=True, nav_by_action=True)
    pol.reject_after = 8                            # 후보에 8스텝 접근·hover 해도 확인 안 되면 거부(FP)·탐색 복귀
    LOG_DWELL = 4                                    # 확인 생존자 georef 를 4스텝 정밀관측 후 기록·재탐색(지상국 몫)
    pending = []                                     # [(x, y, 남은스텝)] 확인됐고 곧 기록할 자리
    truth = ref.truth()
    tt = [(float(x), float(y)) for x, y in truth["targets"]]
    canopy = list(truth.get("canopy", [False] * len(tt)))
    decoys = [(float(d["gx"]), float(d["gy"])) for d in ref._decoys]
    obstacle = obstacle or (GW * 0.5, GH * 0.42)
    thf = tuple(thermal_fault) if thermal_fault else (10 ** 9, 10 ** 9)

    found = [False] * len(tt)                     # 각 표적 확인 여부(누적)
    found_step = [None] * len(tt)
    sut_log = []
    frames = []
    end_reason = "상한 도달"
    steps_run = 0
    for t in range(max_steps):
        steps_run = t + 1
        # ── 대본 세계상태(참조세계 밖) ──
        battery = max(0.0, 1.0 - t / float(battery_life_steps))
        health = [1.0] * 5
        if thf[0] <= t < thf[1]:
            health[1] = 0.05                       # THERMAL 고장 창 → FDIR 격리
        dob = math.hypot(pol.veh[0] - obstacle[0], pol.veh[1] - obstacle[1])
        collision = max(0.0, 1.0 - dob / 2.5) if t < battery_life_steps * 0.55 else 0.0
        pol.ext_battery = battery
        pol.ext_health = health
        pol.ext_collision = collision

        obs = ref.observe(pol.veh)                 # 참조 관측(truth 없음)
        if thf[0] <= t < thf[1]:                   # 열화상 고장: 실제로 그 센서 데이터가 끊긴다(health 만이 아니라)
            obs["thermal"] = {"detections": []}
        so = pol.step(obs)                         # fw C 결정 → 항법
        sut_log.append(so)

        # 확인 claim 을 truth 로 분류(관찰자 몫 — SUT 는 못 봄)
        claims = []
        for (cx, cy, *rest) in so["detections"]:
            ti = _found_target(tt, (cx, cy))
            if ti >= 0 and not found[ti]:
                found[ti] = True; found_step[ti] = t
            claims.append({"xy": [round(cx, 2), round(cy, 2)],
                           "conf": round(float(rest[0]) if rest else 0.0, 2),
                           "target": ti})          # -1 이면 false positive(확인까지 샌 오경보)
        # 지상국: 새 확인 georef 를 LOG_DWELL 스텝 정밀관측 후 기록·재탐색(다중표적). SUT 출력만 씀(truth 아님).
        for c in claims:
            cx, cy = c["xy"]
            if not any((cx - rx) ** 2 + (cy - ry) ** 2 <= 9 for rx, ry in pol._retired) and \
               not any((cx - px) ** 2 + (cy - py) ** 2 <= 4 for px, py, _ in pending):
                pending.append([cx, cy, LOG_DWELL])
        for p in pending:
            p[2] -= 1
            if p[2] <= 0:
                pol._retire_loc(p[0], p[1])
        pending[:] = [p for p in pending if p[2] > 0]

        # 센서별 후보(관찰자 뷰): 원 탐지 블립(참·decoy·clutter 섞임 — '오인 후보')
        sd = {}
        for k in OBSKEY:
            sd[k] = [[round(float(d[0]), 2), round(float(d[1]), 2)] for d in obs.get(k, {}).get("detections", [])]
        live = [[round(float(d[0]), 2), round(float(d[1]), 2)] for d in obs.get("live", {}).get("detections", [])]

        act = pol._ACT[pol.last_action] if 0 <= pol.last_action < len(pol._ACT) else "NONE"
        frames.append({
            "t": t, "veh": [round(pol.veh[0], 2), round(pol.veh[1], 2)],
            "act": act, "belief": [round(pol.last_px, 2), round(pol.last_py, 2),
                                   int(pol.last_conf), round(pol.last_tconf, 2), round(pol.last_nis, 1)],
            "battery": round(battery, 3), "collision": round(collision, 2),
            "health": [round(h, 2) for h in health],
            "imu_ok": 1 if obs["imu"]["ok"] else 0, "imu_sigma": round(obs["imu"]["sigma"], 2),
            "rgb_vis": round(obs["rgb"]["vis"], 3),
            "sensors": sd, "live": live, "claims": claims,
            "found": [1 if f else 0 for f in found],
            "coverage": round(float(so["telemetry"]["coverage"]), 1),
        })

        # ── 종료 판정 ──
        if all(found):
            end_reason = "임무 완수(전원 확인)"; break
        if battery <= 0.02:
            end_reason = "운용 불능(배터리 소진)"; break
        if act == "EMERGENCY" and battery <= 0.10 and math.hypot(pol.veh[0] - pol._home[0], pol.veh[1] - pol._home[1]) < 1.5:
            end_reason = "운용 불능(비상 귀환 착륙)"; break

    # 상공 뷰 배경용 저해상 DEM(정규화). 관찰자 뷰 — SUT 는 안 씀.
    demq = dem[::max(1, dem.shape[0] // 48), ::max(1, dem.shape[1] // 48)]
    demn = ((demq - demq.min()) / (np.ptp(demq) + 1e-9)).round(3).tolist()

    m = _eval.evaluate({"targets": [tuple(x) for x in tt]}, sut_log)
    n_fp_sensor = sum(1 for fr in frames for k in OBSKEY for _ in fr["sensors"][k])  # 센서레벨 후보 총수(참+오인)
    n_fp_confirmed = m["false_alarms"]                                               # 확인까지 샌 오경보
    data = {
        "GW": GW, "GH": GH, "cell_m": float(ref.PATCH_M / GW), "steps": steps_run, "dem": demn,
        "scenario": {k: scenario.get(k) for k in ("fidelity", "V", "illum", "agl", "sensors", "n_target")},
        "nl": scenario.get("_nl", {}),
        "targets": [[round(x, 2), round(y, 2)] for x, y in tt], "canopy": [int(c) for c in canopy],
        "found": [1 if f else 0 for f in found], "found_step": found_step,
        "decoys": [[round(x, 2), round(y, 2)] for x, y in decoys],
        "obstacle": [round(obstacle[0], 2), round(obstacle[1], 2)],
        "home": [round(pol._home[0], 2), round(pol._home[1], 2)] if pol._home else [2.0, 2.0],
        "end_reason": end_reason, "frames": frames,
        "metrics": {"detected": m["detected"], "n_targets": m["n_targets"],
                    "false_alarms_confirmed": n_fp_confirmed, "fp_candidates_sensor": n_fp_sensor,
                    "loc_rmse_cells": (None if m["loc_rmse_cells"] != m["loc_rmse_cells"] else round(m["loc_rmse_cells"], 2)),
                    "coverage_pct": round(m["coverage_pct"], 1), "steps": m["steps"]},
    }
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(data, f)
    if return_ref:
        return data, ref, dem                    # 3D 렌더(mission_3d)용: 실 DEM·world3d(나무)·_g2w
    return data


def summary_line(data):
    m = data["metrics"]
    miss = m["n_targets"] - m["detected"]
    return ("탐지 %d/%d · 놓침(FN) %d · 확인오경보(FP) %d · 센서레벨 오인후보 %d · %d스텝(%.0f분 임무) · %s"
            % (m["detected"], m["n_targets"], miss, m["false_alarms_confirmed"], m["fp_candidates_sensor"],
               data["steps"], data["steps"] * FRAME_S / 60.0, data["end_reason"]))


if __name__ == "__main__":
    import argparse
    sys.path.insert(0, HERE)
    import nl_scenario as _nl
    ap = argparse.ArgumentParser()
    ap.add_argument("--nl", default=None, help="자연어 상황")
    ap.add_argument("--out", default=os.path.join(HERE, "mission_run.json"))
    ap.add_argument("--battery", type=int, default=200)
    ap.add_argument("--seed", type=int, default=4242)
    a, _ = ap.parse_known_args()
    text = a.nl or ("DMZ와 유사한 산림·초지 환경에서 드론이 RGB·열화상·IMU 센서를 이용해 실종 다섯명을 "
                    "탐색하며, 나무·바위·동물·흔들리는 식생을 사람으로 오인하는 false positive와 "
                    "정지·은폐된 사람을 놓치는 false negative를 포함하라.")
    scn = _nl.parse(text, seed=a.seed)
    d = run(scn, battery_life_steps=a.battery, out=a.out)
    print(summary_line(d))
    print("wrote", a.out)
