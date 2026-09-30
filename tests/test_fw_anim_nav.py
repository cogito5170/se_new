#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fw C 결정 executive가 render3d 3D 임무 애니메이션의 항법을 **직접 몬다**(nav_by_action=True).

왜 있나: 처음 배선(nav_by_action=False)에서는 fw 의 Action(SEARCH/APPROACH/INSPECT)이 로그로만
찍히고 UAV 는 공통 골격 항법으로 움직였다. 그래서 확인이 안 됐다 -- UAV 가 표적 곁에 loiter 하지
않아 연속 liveness 가 안 쌓였다(실측: 10분·30분 창 모두 확인 0). fw Action 이 항법을 몰면
APPROACH 로 접근·INSPECT 로 loiter 해 CMPC≥2+liveness 확인 arc 가 완성된다.

이 검사는 그 arc 가 실제로 닫히는지 본다. 글자만 보지 않고 **결정 로그와 지표를 세어** 본다.
또 기본 경로(nav_by_action=False)가 V&V 채점과 바이트 동일한 항법을 쓰는지도 지킨다."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, os.path.join(ROOT, "sar"), os.path.join(ROOT, "sar", "ivv")):
    if p not in sys.path:
        sys.path.insert(0, p)


def _build(nav_by_action, close=False, budget_min=10):
    from render3d import mission_anim as MA, sar_bridge as B
    import fw_vv as F
    spec = MA.default_spec(V=6000.0, canyon=False)
    spec["budget_min"] = budget_min
    if close:
        spec["targets_spec"] = [{"bearing_deg": 60, "range_m": 300, "canopy": False}]
        spec["n_target"] = 1
    dem = B.synthetic_dem(96, seed=2)
    player = F.FwBridgePolicy(F.load_lib(), confirm_n=2, nis_gate=24.0, cmpc_min=2,
                              require_live=True, nav_by_action=nav_by_action)
    return MA.build(spec, dem, speed=20.0, name="검사", sut=player)


def test_action_drives_nav_completes_confirm_arc():
    """fw Action 항법: 근거리 단일표적에서 SEARCH→APPROACH→liveness 확인→INSPECT arc 가 닫힌다."""
    sc, summ = _build(nav_by_action=True, close=True, budget_min=10)
    decs = sc["anim"]["decisions"]
    approach = sum(1 for d in decs if "행동=APPROACH" in d[2])
    inspect = sum(1 for d in decs if "행동=INSPECT" in d[2])
    confirmed = sum(1 for d in decs if "확인됨" in d[2])
    assert approach >= 1, "APPROACH 가 한 번도 안 나옴 -- belief 로 접근을 안 한다"
    assert inspect >= 1, "INSPECT(loiter)가 한 번도 안 나옴 -- 확인 뒤 정밀관측 상태로 못 간다"
    assert confirmed >= 1, "확인이 한 번도 안 됨 -- 연속 liveness+CMPC arc 가 안 닫힌다"
    assert summ["metrics"]["detected"] >= 1, "표적을 하나도 확인 못 함(detected=0)"
    # trace 는 실제 C 결정을 담는다(로그가 지어낸 것이 아님)
    assert all("fw C executive" in d[2] for d in decs), "결정 로그가 fw C executive 근거가 아님"


def test_default_nav_unchanged_is_coverage_search():
    """기본 경로(nav_by_action=False)는 공통 골격 항법 그대로 -- V&V 채점 경로 불변.
    같은 시나리오·같은 씨앗에서 super().step() 궤적과 웨이포인트가 바이트 동일해야 한다."""
    import fw_vv as F
    import sut as _sut
    import policies as _pol
    import reference as _ref
    from render3d import mission_anim as MA, sar_bridge as B

    spec = MA.default_spec(V=6000.0, canyon=False)
    spec["budget_min"] = 4
    dem = B.synthetic_dem(96, seed=2)
    lib = F.load_lib()

    # fw 기본 경로(nav_by_action=False)의 웨이포인트
    ref1 = _ref.Reference(spec, dem=dem)
    p1 = F.FwBridgePolicy(lib, confirm_n=2, nis_gate=24.0, cmpc_min=2, require_live=True)  # 기본 False
    wp_default = []
    for _ in range(8):
        obs = ref1.observe(p1.veh)
        out = p1.step({k: v for k, v in obs.items() if k != "truth"})
        wp_default.append(tuple(round(v, 6) for v in out["waypoint"]))

    # 같은 관측열에서 _SelectPolicy.step() 을 직접 부른 웨이포인트(공통 골격)와 같은지
    # (같은 참조세계·같은 C 브리지 순서 → 항법 결정은 동일 골격이어야)
    ref2 = _ref.Reference(spec, dem=dem)
    p2 = F.FwBridgePolicy(lib, confirm_n=2, nis_gate=24.0, cmpc_min=2, require_live=True)
    wp_super = []
    for _ in range(8):
        obs = ref2.observe(p2.veh)
        out = _pol._SelectPolicy.step(p2, {k: v for k, v in obs.items() if k != "truth"})
        wp_super.append(tuple(round(v, 6) for v in out["waypoint"]))

    assert wp_default == wp_super, "기본 경로가 공통 골격 항법과 어긋난다:\n  fw=%s\n  base=%s" % (wp_default, wp_super)


if __name__ == "__main__":
    test_action_drives_nav_completes_confirm_arc()
    test_default_nav_unchanged_is_coverage_search()
    print("OK test_fw_anim_nav")
