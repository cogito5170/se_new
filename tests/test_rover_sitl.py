#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로버 SITL 하네스 — fw(실 libfw.so)의 로버 문맥 응답을 **세어** 잠근다(회귀).

이 저장소 규율: 글자만 보지 않고 실제로 돌려 본다. 하네스가 시나리오별로 fw 의 응답을 **차별화**해
재는지(안 그러면 검증이 아니다), 그리고 알려진 gap(R-03 고착·R-08b 지속 가짜)을 정직히 드러내는지.
고정 seed → 회귀시험.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, os.path.join(ROOT, "rover"), os.path.join(ROOT, "sar", "ivv")):
    if p not in sys.path:
        sys.path.insert(0, p)

import rover_sitl as R


def test_fw_reaches_goal_when_healthy():
    """R-01 평탄·정상: fw 가 목표에 도달(APPROACH/INSPECT 로 접근)."""
    r = R.run_scenario(R.SCENARIOS["R-01 평탄·정상"], seed=7)
    assert r["reached"] is not None, "정상 조건에서 목표 미도달"


def test_fw_relocalizes_on_lost_localization():
    """R-05 GPS 누락: 측위 신뢰 무너지면 fw 가 RELOCALIZE(추측항법 위 전진 금지)."""
    r = R.run_scenario(R.SCENARIOS["R-05 GPS 지연·누락"], seed=7)
    assert r["n_reloc"] > 0, "GPS 상실에도 RELOCALIZE 안 함(오래된 측위로 전진하면 안 됨)"
    assert r["reached"] is None, "측위 잃고도 목표 도달로 보고(정지했어야)"


def test_transient_fake_rejected_persistent_confirmed_gap():
    """R-08: 순간 가짜(센서독립·튐)는 CMPC·시간이 거른다. 지속 가짜(co-locate·고정)는
    생체(UAV 전용) 없이 확정된다 — 경계지도의 알려진 gap 을 정직히 드러낸다."""
    a = R.run_scenario(R.SCENARIOS["R-08a 순간 가짜표적"], seed=7)
    b = R.run_scenario(R.SCENARIOS["R-08b 지속 가짜표적"], seed=7)
    assert a["false_confirm"] is False, "순간 가짜를 확정(시간적 확인이 거르지 못함)"
    assert b["false_confirm"] is True, "지속 가짜가 확정 안 됨 — gap 이 사라졌다면 검사/모델을 재검토"


def test_stuck_encoder_is_undetected_gap():
    """R-03 엔코더 고착: fw 는 고착 센서 판별이 없다(fault_test 의 stale gap 과 동뿌리).
    → 고장 응답(AVOID/RELOCALIZE) 없이 무심코 진행. 이 gap 을 정직히 잠근다."""
    r = R.run_scenario(R.SCENARIOS["R-03 엔코더 고착"], seed=7)
    assert r["n_avoid"] == 0 and r["n_reloc"] == 0, "고착 센서에 fw 가 반응했다면 gap 이 닫힌 것 — 재확인"


def test_motion_layer_does_steering_not_fw():
    """행동 제어(조향·국소 회피)는 모션 어댑터의 일이지 fw 가 아니다. R-06 vs R-06b: 같은 fw 행동인데
    nav_avoid(퍼텐셜필드)가 암석을 더 크게 우회한다 → 조향은 어댑터/항법 몫."""
    r6 = R.run_scenario(R.SCENARIOS["R-06 경로 암석(장애물)"], seed=7)
    r6b = R.run_scenario(R.SCENARIOS["R-06b 암석+모션층 회피"], seed=7)
    assert r6b["min_obst"] > r6["min_obst"] + 0.3, \
        "모션층 회피가 암석을 더 우회 못함: %.1f vs %.1f" % (r6b["min_obst"], r6["min_obst"])


def test_immobilization_recovery_lives_in_motion_layer_not_fw():
    """도랑 빠짐(immobilization): 명령은 전진인데 실제로 못 움직인다(헛돎). fw 는 이걸 모른다
    (fw 입력에 '명령속도↔실제 지면속도' 불일치 신호가 없다) → 계속 전진만 명령해 갇힌다.
    복구(후진·우회)는 **모션 층**의 일이지 fw 가 아니다. R-09(복구 없음) vs R-09b(모션층 복구):
    같은 fw 정책인데 모션 층이 붙으면 탈출·도달한다 → 행동제어·복구는 어댑터/항법 몫."""
    no_rec = R.run_scenario(R.SCENARIOS["R-09 도랑 빠짐(복구 없음)"], seed=7)
    rec = R.run_scenario(R.SCENARIOS["R-09b 도랑+모션층 복구"], seed=7)
    # 복구 없으면: fw 는 immobilization 을 모른다 → 갇힌 채 미도달·저이동
    assert no_rec["reached"] is None, "복구 없이 도랑을 빠져나와 도달 — 물리(도랑 헛돎) 재확인"
    assert no_rec["progress"] < 6.0, "복구 없는데 이동 %.1fm — 도랑에 갇혀야 한다" % no_rec["progress"]
    assert no_rec["n_recover"] == 0, "복구 안 켰는데 복구 발동"
    # 모션 층 복구: 헛돎 검출(VO) → 후진·우회 → 탈출·도달. fw 정책은 불변(같은 우세행동).
    assert rec["n_recover"] > 0, "모션 층이 immobilization 을 검출·복구 못 함"
    assert rec["reached"] is not None, "모션층 복구를 켰는데 도랑을 못 빠져나와 미도달"
    assert rec["progress"] > no_rec["progress"] + 5.0, \
        "복구가 이동을 못 늘림: %.1f vs %.1f" % (rec["progress"], no_rec["progress"])
    assert rec["top"] == no_rec["top"], "fw 정책(우세행동)이 바뀌었다 — 복구는 fw 밖이어야: %s vs %s" % (rec["top"], no_rec["top"])


def test_scenarios_differentiate():
    """하네스가 검증이려면 시나리오별 결과가 실제로 달라야 한다(재려던 걸 쟀나)."""
    rmses = {k: round(R.run_scenario(sc, seed=7)["rmse"], 2) for k, sc in R.SCENARIOS.items()}
    assert len(set(rmses.values())) >= 3, "RMSE 가 시나리오별로 안 갈린다 — 물리·매핑이 차별화 못 함: %s" % rmses


if __name__ == "__main__":
    test_fw_reaches_goal_when_healthy()
    test_fw_relocalizes_on_lost_localization()
    test_transient_fake_rejected_persistent_confirmed_gap()
    test_stuck_encoder_is_undetected_gap()
    test_motion_layer_does_steering_not_fw()
    test_immobilization_recovery_lives_in_motion_layer_not_fw()
    test_scenarios_differentiate()
    print("OK test_rover_sitl")
