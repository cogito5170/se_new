#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자연어 상황 → 폐루프 미션 시뮬 → 두 mp4(온보드 RGB+센서 / 상공 샷). Discord `!시뮬영상` 배경 엔트리.

무거운 것(numpy/matplotlib/ctypes)은 이 프로세스 안에서만 돈다(G012). 산출 mp4 경로를 stdout 에
`산출물:` 꼴로 찍어 봇이 붙인다(relay.산출물꼴 이 .mp4 를 잡는다).

정직: L2 대표 렌더(실사 아님). false+/false- 개수는 물리·평가기가 낸 것을 그대로 보고한다.
"""
from __future__ import annotations
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.dirname(HERE), REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT = os.path.join(REPO, "public_agent_memory", "mission")


def _rel(p):
    try:
        return os.path.relpath(p, REPO)
    except ValueError:
        return p


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mission_make")
    ap.add_argument("--nl", default=None, help="자연어 상황")
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--battery", type=int, default=200, help="만충→0 스텝(≈*20s 비행). 소진 시 운용 불능 종료")
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--interp", type=int, default=2)
    ap.add_argument("--fault", action="store_true", help="열화상 고장 창을 넣어 FDIR 시연(2모달이라 확인율↓)")
    a = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    text = a.nl or ("DMZ와 유사한 산림·초지 환경에서 드론이 RGB·열화상·IMU 센서를 이용해 실종 다섯명을 "
                    "탐색하며, 나무·바위·동물·흔들리는 식생을 사람으로 오인하는 false positive와 "
                    "정지·은폐된 사람을 놓치는 false negative를 포함하라.")
    import nl_scenario as _nl
    import mission_sim as _ms
    import mission_video as _mv

    scn = _nl.parse(text, seed=a.seed)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = os.path.join(OUT, "mission_%s" % ts)
    jpath = stem + ".json"
    # 실 지명이면 실 DEM(강원 고성·파주 DMZ 등)로 3D 렌더. 아니면 합성 지형 2D.
    d, ref, dem = _ms.run(scn, battery_life_steps=a.battery, thermal_fault=((48, 66) if a.fault else None),
                          out=jpath, real_dem=True, return_ref=True)
    outs = []
    made_3d = False
    if scn.get("place"):                            # 실 지형 → three.js 3D(webm → mp4 로 변환해 첨부)
        try:
            import mission_3d as _m3
            o3, _ = _m3.render(ref, dem, d, stem + "_3d",
                               name="임무 3D · %s" % scn["place"], speed=max(a.fps * 3.0, 30.0), webm=True)
            webm = next((p for p in o3 if p.endswith(".webm")), None)
            if webm:                                # webm 은 크다(>7MB 가능) → 작은 mp4 로 변환해 붙인다
                import imageio.v2 as _iio
                fr = [f for f in _iio.get_reader(webm)]
                if fr:
                    h, w = fr[0].shape[:2]; fr = [f[:h - (h % 2), :w - (w % 2)] for f in fr]
                    mp4 = stem + "_3d.mp4"
                    _iio.mimsave(mp4, fr, fps=24, codec="libx264", quality=7,
                                 macro_block_size=None, output_params=["-pix_fmt", "yuv420p"])
                    outs.append(mp4); made_3d = True
        except Exception as _e:                     # noqa: BLE001 — 브라우저/three 없으면 2D 로 강등
            print("3D 렌더 실패(%s) → 2D 로만 낸다" % type(_e).__name__)
    _mv.render_both(jpath, stem, fps=a.fps, interp=a.interp)  # 2D 상공/온보드 도식(FP/FN 주석)
    outs += [stem + "_onboard.mp4", stem + "_aerial.mp4"]

    for p in outs:
        print("산출물:", _rel(p))
    m = d["metrics"]; nl = d.get("nl", {})
    miss = m["n_targets"] - m["detected"]
    print("=== 보고 ===")
    print("상황: %s" % text)
    print("해석: 표적 %d명(수관 은폐 %d) · 센서 %s · decoy %d(바위·동물) · 흔들리는 식생 clutter"
          % (scn["n_target"], nl.get("n_canopy", 0), "·".join(scn["sensors"]), nl.get("n_decoy", 0)))
    print(_ms.summary_line(d))
    print("· 확인 %d/%d · 놓침(FN) %d(대부분 수관 은폐 — 정지 자체가 아니라 가림) · 확인까지 샌 오경보(FP) %d"
          % (m["detected"], m["n_targets"], miss, m["false_alarms_confirmed"]))
    print("· 센서레벨 오인후보 %d건(바위·동물 decoy·순간 식생)은 liveness 로 걸러 사람으로 확정 안 함"
          % m["fp_candidates_sensor"])
    if made_3d:
        print("장소: %s · %s (실 고도 DEM·AWS Terrarium — 위성 사진 텍스처 아님, 고도 기반 음영)"
              % (scn["place"], d["scenario"]["fidelity"]))
        print("영상: **3D**(실 지형 relief·나무·탑재/조감 카메라, three.js webm) + 2D 도식(상공/온보드, FP/FN 주석).")
    else:
        print("영상: 온보드(RGB 청·열화상 주·liveness ★) + 상공 샷(관찰자 truth·SUT 는 센서만). L2 대표 렌더 — 실사 아님.")
    print("주의: 확인율은 배치(seed)에 따라 노출표적 1~3/3 편차(2모달 CMPC+liveness 확인이 까다로움). 이 실행 seed=%d." % a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
