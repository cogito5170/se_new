#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자연어 → 폐루프 미션 시뮬(mission_sim) + 자연어 파서(nl_scenario) + Discord 배선(!시뮬영상).

이 저장소 규율: 글자만 보지 않고 **실제로 돌려** 본다. 미션이 사건으로 종료되는지, liveness 로
decoy 를 걸러 확인 오경보(FP)를 0 으로 유지하는지, 수관 표적이 놓침(FN)으로 남는지, 봇 명령이
가볍게 임포트돼(G012) mission_make 를 배경으로 띄우는지 — 값을 세어 본다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, os.path.join(ROOT, "sar"), os.path.join(ROOT, "sar", "ivv")):
    if p not in sys.path:
        sys.path.insert(0, p)

DEMO = ("DMZ와 유사한 산림·초지 환경에서 드론이 RGB·열화상·IMU 센서를 이용해 실종 다섯명을 "
        "탐색하며, 나무·바위·동물·흔들리는 식생을 사람으로 오인하는 false positive와 "
        "정지·은폐된 사람을 놓치는 false negative를 포함하라.")


def test_nl_parser_extracts_scenario():
    import nl_scenario as NL
    scn = NL.parse(DEMO, seed=31337)
    assert scn["n_target"] == 5, "다섯명 → 표적 5"
    assert len(scn["targets_spec"]) == 5
    assert "RGB" in scn["sensors"] and "Thermal" in scn["sensors"] and "IMU" in scn["sensors"], scn["sensors"]
    assert sum(1 for t in scn["targets_spec"] if t["canopy"]) == 2, "수관 은폐(FN 후보) 2"
    assert len(scn["decoys_spec"]) >= 2, "바위·동물 decoy(FP 원인)"
    assert scn["clutter"] > 0.1 and scn["clutter_persist"] == 1, "흔들리는 식생 = 순간 clutter"
    assert scn["_nl"]["want_fp"] and scn["_nl"]["want_fn"]


def test_mission_terminates_and_liveness_rejects_decoys():
    import nl_scenario as NL
    import mission_sim as MS
    scn = NL.parse(DEMO, seed=31337)
    d = MS.run(scn, battery_life_steps=60, max_steps=90)
    m = d["metrics"]
    assert d["end_reason"] and "운용 불능" in d["end_reason"], d["end_reason"]      # 사건 종료(배터리)
    assert m["n_targets"] == 5 and len(d["frames"]) == d["steps"] >= 1
    assert m["detected"] >= 1, "노출 표적을 하나도 확인 못 함"
    # liveness 게이트: decoy·clutter 는 생체징후가 없어 **확인**까지 못 샌다 → 확인 오경보 0
    assert m["false_alarms_confirmed"] == 0, "liveness 없는 후보가 확인까지 샜다(FP)"
    assert m["fp_candidates_sensor"] > 0, "센서레벨 오인후보(바위·동물·식생)가 떠야 한다"
    # 놓침(FN)은 수관 은폐에서 온다 — 확인 못 한 표적 중 수관이 있어야 한다
    missed = [i for i in range(5) if not d["found"][i]]
    assert any(d["canopy"][i] for i in missed), "놓침이 수관 은폐 표적을 포함해야(FN 근거)"
    # 확인된 claim 은 truth 표적과 매칭됨(target>=0)
    for fr in d["frames"]:
        for c in fr["claims"]:
            if c["target"] == -1:
                assert False, "확인 claim 이 어느 표적과도 안 맞음(FP) — liveness 게이트 위반"


def test_discord_cmd_light_import_and_dispatch():
    # G012: 무거운 것(numpy/matplotlib)을 import 시점에 끌어오면 안 된다 — 깨끗한 프로세스에서 확인
    import subprocess
    chk = subprocess.run([sys.executable, "-c",
                          "import sys; sys.path.insert(0,%r); import sar.discord_cmd; "
                          "assert 'numpy' not in sys.modules and 'matplotlib' not in sys.modules" % ROOT],
                         capture_output=True, text=True)
    assert chk.returncode == 0, "discord_cmd 가 무겁게 임포트된다(G012): %s" % chk.stderr
    import sar.discord_cmd as DC
    assert DC.run("!시뮬영상") is not None and "온보드" in DC.run("!시뮬영상"), "빈 명령 → 도움말"
    assert DC.run("!시뮬영상기 x") is None, "붙여 쓴 말은 명령이 아니다"
    seen = {}

    def fake(argv, log, findword):
        seen["argv"] = argv; seen["find"] = findword
        return "[배경 등록됨]"
    out = DC.run('!시뮬영상 "DMZ 산림 초지 RGB 열화상 IMU 실종 5명 오인 놓침"', runner=fake)
    assert out and "미션 시뮬 영상 실행" in out
    assert seen.get("find") == "mission_make" and "mission_make.py" in " ".join(seen["argv"]), seen


def test_place_detection_real_coords():
    import nl_scenario as NL
    assert NL._place("강원도 산맥에서 실종 5명", 0, 0)[0] == "설악산", "강원도→대표 실산"
    assert NL._place("강원도 고성 DMZ 수색", 0, 0)[0].startswith("고성"), "고성 DMZ"
    assert NL._place("파주 DMZ 산림", 0, 0)[0].startswith("파주"), "파주 DMZ"
    p, la, lo = NL._place("37.79,128.54 조난 2명", 0, 0)      # 좌표가 지명보다 우선
    assert "좌표" in p and abs(la - 37.79) < 0.01 and abs(lo - 128.54) < 0.01
    # 좌표를 지어내지 않는다: 고성/파주는 실 DMZ 접경 범위
    assert 38.0 < NL._DMZ["고성 DMZ"][0] < 38.6 and 128.2 < NL._DMZ["고성 DMZ"][1] < 128.7
    assert 37.7 < NL._DMZ["파주 DMZ"][0] < 38.1 and 126.5 < NL._DMZ["파주 DMZ"][1] < 127.0


def test_mission_3d_scene_valid():
    """mission_sim → render3d 3D 장면이 scene.check 를 통과하고 anim 규격을 지키는지(브라우저 불필요)."""
    import tempfile
    import nl_scenario as NL
    import mission_sim as MS
    import mission_3d as M3
    from render3d import html as H
    scn = NL.parse("설악산 산림에서 실종 3명 탐색, 바위·동물 오인, 은폐 놓침", seed=7)
    scn["place"] = None                                       # 오프라인 검사: 합성 DEM 강제(네트워크 안 씀)
    scn["n_target"] = 3; scn["targets_spec"] = scn["targets_spec"][:3]
    data, ref, dem = MS.run(scn, battery_life_steps=40, max_steps=50, return_ref=True)
    sc = M3.build_scene(ref, dem, data, name="검사")
    assert sc["heightfield"].get("colors"), "실 지형 색·음영(고도 기반)"
    assert sc["anim"]["truth"] and len(sc["anim"]["states"][0]) == 11, "anim states 11필드 규격"
    p = tempfile.mktemp(suffix=".html")
    H.write(sc, p)                                            # scene.check 통과해야 함(아니면 ValueError)
    assert os.path.getsize(p) > 2000
    os.remove(p)


if __name__ == "__main__":
    test_nl_parser_extracts_scenario()
    test_mission_terminates_and_liveness_rejects_decoys()
    test_discord_cmd_light_import_and_dispatch()
    test_place_detection_real_coords()
    test_mission_3d_scene_valid()
    print("OK test_mission_sim")
