#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IV&V 하니스 — Reference · SUT · Evaluator 를 **정해진 인터페이스로만** 잇는다.

텔레메트리 버스(machine-to-machine): 매 틱 참조세계가 프레임을 낸다. 버스는 **SUT 에는 센서만**
(truth 제거) 주고, viewer·evaluator 에는 truth 까지 준다 — 구조적으로 SUT 가 정답을 못 본다.
숨은 시나리오 집합(개발자·SUT 가 truth 를 모름)을 돌려 독립 지표를 낸다.

결과는 **independent simulation-based evidence** 이고, 유효 validation domain 을 명시한다
(현장 validation 아님 — 참조세계도 모델이다. 다만 SUT 와 다른 formulation 이라 공통가정 오류를 잡는다).
"""
import os
import sys
import math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reference as _ref
import sut as _sut
import evaluator as _eval


# 시나리오 발생기 — SUT·개발자와 분리(숨은 truth). 지명 대신 좌표+대기만 준다.
_SITES = [(38.12, 128.47), (35.34, 127.73), (46.41, 11.84), (37.75, -119.59), (40.63, 14.49)]


def gen_scenarios(n=6, master_seed=20260927):
    rng = np.random.default_rng(master_seed)
    out = []
    for i in range(n):
        la, lo = _SITES[i % len(_SITES)]
        la += rng.uniform(-1, 1) * 0.02; lo += rng.uniform(-1, 1) * 0.02
        out.append(dict(seed=int(rng.integers(1, 1_000_000)), lat=float(la), lon=float(lo),
                        V=float(rng.choice([120, 300, 800, 3000])),       # 시정[m] (안개~맑음)
                        illum=float(rng.choice([50, 2000, 20000])),        # 조도[lux] (야간~주간)
                        n_target=int(rng.integers(1, 4))))
    return out


def _sut_view(frame):
    """버스 필터: SUT 에게는 센서 패킷만 — truth 는 절대 안 준다(구조적 분리)."""
    return {k: v for k, v in frame.items() if k != "truth"}


def run_one(scenario, budget=40, record_frames=False, dem=None):
    """One hidden scenario: reference <-> SUT <-> evaluator. Returns (metrics, frames (for the viewer, includes truth)|None).
    dem: a pre-computed DEM (no network; render3d scene3d A/B). None = fetch as before."""
    ref = _ref.Reference(scenario, dem=dem)
    sut = _sut.SUT()
    sut_log = []; frames = []
    truth = ref.truth()                                    # evaluator·viewer 만. SUT 엔 안 감.
    for step in range(budget):
        obs = ref.observe(sut.veh)                         # 참조가 낸 센서 패킷(truth 없음)
        out = sut.step(_sut_view(obs))                     # 버스가 걸러 SUT 에 전달
        sut_log.append(out)
        if record_frames:
            frames.append({"t": obs["t"], "sut_pose": out["waypoint"][:], "sut": out,
                           "sensors": {k: obs[k] for k in ("rgb", "sar", "imu", "gps")},
                           "truth": truth})               # viewer 전용: 정답 포함
        if out["state"] == "MRC":
            break
    metrics = _eval.evaluate(truth, sut_log)
    n_t = scenario.get("n_target", len(scenario.get("targets_spec", []) or truth["targets"]))
    metrics["scenario"] = {"V": scenario["V"], "illum": scenario["illum"], "n_target": n_t}
    return metrics, (frames if record_frames else None)


def run(n=6, budget=40):
    scns = gen_scenarios(n)
    rows = [run_one(s, budget)[0] for s in scns]
    return rows, _eval.summarize(rows)


def _report_md(rows, summ, gif_rel):
    L = ["# IV&V 독립검증 보고 — SUT·참조·평가기 분리 (자기채점 제거)", ""]
    L.append("> **구조**: 독립 참조세계(다른 물리 formulation)가 센서만 SUT 에 주고(truth 제거), "
             "독립 평가기가 숨은 truth 로 SUT 출력을 채점한다. SUT 는 정답을 못 본다 — 자기채점이 "
             "구조적으로 불가능. **independent simulation-based evidence** 이며 현장 validation 아님"
             "(참조세계도 모델. 단 SUT 와 다른 가정이라 공통가정 오류를 잡는다).")
    L.append("")
    L.append("## 실시간 3D 뷰 (관찰자는 TRUTH 를, SUT 는 센서만)")
    L.append("![ivv](%s)" % gif_rel)
    L.append("")
    L.append("## 독립 평가 결과 — 숨은 시나리오 %d개" % summ["n_scenarios"])
    L.append("| V(시정) | 조도 | 표적 | 탐지 | 탐지율 | 위치RMSE(셀) | 오경보 | 커버 | 안전 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        sc = r["scenario"]; rm = "%.2f" % r["loc_rmse_cells"] if r["loc_rmse_cells"] == r["loc_rmse_cells"] else "—"
        L.append("| %.0fm | %.0f | %d | %d/%d | %.0f%% | %s | %d | %.0f%% | %s |" %
                 (sc["V"], sc["illum"], sc["n_target"], r["detected"], r["n_targets"], r["detection_rate"],
                  rm, r["false_alarms"], r["coverage_pct"], "O" if r["safe"] else "X"))
    dr = summ["detection_rate"]; rm = summ["loc_rmse_cells"]; fa = summ["false_alarms"]
    L.append("")
    L.append("- **종합**: 탐지율 %.0f±%.0f%% · 위치 RMSE %.2f±%.2f셀 · 오경보 %.1f±%.1f · 안전 %.0f%%"
             % (dr[0], dr[1], rm[0], rm[1], fa[0], fa[1], summ["safe_frac"]))
    L.append("- 탐지율이 조건(안개·야간)에 따라 정직하게 갈린다 — 참조가 SUT 와 다른 물리로 관측을 냈고, "
             "SUT 는 truth 없이 탐색, 평가기가 truth 로 채점한 결과다.")
    L.append("")
    L.append("---")
    # 참조모델도 모델이다 → 물리 referent 대조 + 4계층 배치 + 조직독립 정직(refval)
    import refval as _rv
    rv_md, _ = _rv.report_md()
    L.append(rv_md)
    return "\n".join(L) + "\n"


# 명시 시험 케이스 — 시나리오는 **임무(objective·영역·시작·제약·탑재체)**만 준다.
# '10분 안에 찾아라'·'이 센서만 써라' 같은 **행동 명령을 SUT 에 주지 않는다**(시험자가 SUT 를
# 과도 규정하는 것). 제한시간은 임무 요구사항(평가기가 검사), 센서목록은 '장착된 탑재체'(사실)일 뿐.
CASE_TAEBAEK = dict(
    name="태백산 동쪽 계곡 · 짙은 안개 · 소나무-암석 혼재 구역 조난자 자율탐색",
    seed=780, lat=37.0966, lon=128.9156 + 0.03, V=40.0, illum=2000.0, agl=150.0,
    payload=["RGB", "X-band SAR", "IMU"],     # 장착된 탑재체(사실). '이것만 써라'가 아니다
    sensors=["RGB", "SAR", "IMU"],            # reference 가 관측을 낼 때 쓰는 탑재체 집합
    targets_spec=[dict(bearing_deg=45.0, range_m=180.0, canopy=True)],   # 북동 180m, 소나무 수관 아래
    req_time_min=10,                          # 임무 요구사항(평가기가 '이내 확보?'로 검사) — SUT 명령 아님
    budget_min=10,                            # 시뮬 창(월드가 여기서 멈춘다) = 요구시간
)


FRAME_S = 20.0    # SUT 결정 1회가 대표하는 실시간 창[s] (case budget 계산과 일치)


def run_case(spec, record_frames=False):
    budget = int(round(spec.get("budget_min", 10) * 60 / FRAME_S))       # 프레임당 20s
    return run_one(spec, budget=budget, record_frames=record_frames)


def run_case_telemetry(spec, dem=None, decisions=None, sut=None):
    """SUT 자율 결정 사이를 **10 Hz 로 보간**해 3계층 스트림을 낸다:
      · 10 Hz  기계 상태(state)  — 버스에 흐르는 원자료
      · 1 Hz   운용 보고(report) — 버스가 자동 데시메이트(사람용)
      · event  결정/경보(즉시)   — WAYPOINT·DETECT·MRC·NAV_DEGRADED
    '보고'(1 Hz/사람) 와 '데이터 전송'(10 Hz/기계) 을 분리한다. 반환 (bus, metrics, ref).
    """
    import telemetry as _tel
    # dem: a pre-computed DEM (no network). decisions: if a list is given, append the observation summary and SUT output
    # (including trace) for each decision -- for the render3d mission animation. Existing telemetry output is unchanged.
    # sut=None -> default Python SUT. A caller can inject another player (e.g. the fw C decision executive via
    # fw_vv.FwBridgePolicy) so the same telemetry/animation shows a different policy. The player only needs the
    # _SelectPolicy interface (.veh, .step()->{waypoint,detections,state,telemetry[,trace]}). Everything else is unchanged.
    ref = _ref.Reference(spec, dem=dem); sut = sut if sut is not None else _sut.SUT(); bus = _tel.TelemetryBus()
    truth = ref.truth()
    cellm = ref.PATCH_M / ref.GW
    budget = int(round(spec.get("budget_min", 10) * 60 / FRAME_S))
    nsub = max(1, int(round(_tel.STATE_HZ * FRAME_S)))    # 결정당 10Hz 서브프레임 수 (=200)
    dt = 1.0 / _tel.STATE_HZ
    t = 0.0; sut_log = []; prev_state = None
    for step in range(budget):
        obs = ref.observe(sut.veh)                        # 참조 관측(truth 없음)
        p0 = sut.veh[:]                                   # 결정 전 위치
        out = sut.step(_sut_view(obs)); sut_log.append(out)
        p1 = out["waypoint"][:]                           # 결정한 다음 웨이포인트
        tele = out["telemetry"]; st = out["state"]
        speed = math.hypot((p1[0]-p0[0])*cellm, (p1[1]-p0[1])*cellm) / FRAME_S   # m/s (격자 유도)
        sens = {"rgb": ("BLIND" if obs["rgb"]["vis"] < 0.25 else ("DEGRADED" if obs["rgb"]["vis"] < 0.5 else "OK")),
                "sar": ("OK" if "SAR" in ref.sensors else "OFF"),
                "imu": ("OK" if obs["imu"]["ok"] else "DRIFT")}
        # 즉시 이벤트: 결정 순간에 기록
        bus.emit_event(t, "WAYPOINT", "→ 격자(%.1f, %.1f) 방위 %03d°" % (p1[0], p1[1], int(tele["heading"]) % 360))
        for (dx, dy, conf) in out["detections"]:
            bus.emit_event(t, "DETECT", "RGB 주장 (%.1f, %.1f) conf=%.2f" % (dx, dy, conf))
        if st == "MRC":
            bus.emit_event(t, "MRC", "IMU σ=%.1fm·GPS불확실 → 최소위험(안전강등)" % tele["sigma"])
        elif st != prev_state and st in ("DEGRADED", "LOW-INFO"):
            bus.emit_event(t, "NAV_DEGRADED", "정책 %s (RGB vis 저하)" % st)
        prev_state = st
        if decisions is not None:
            decisions.append({"t": round(t, 3), "from": p0, "to": p1, "state": st, "detections": out["detections"],
                              "trace": out.get("trace", {}),
                              "obs": {"rgb_vis": obs["rgb"]["vis"], "rgb_n": len(obs["rgb"]["detections"]), "sar_hits": obs["sar"]["hits"],
                                      "thermal_n": len(obs["thermal"]["detections"]), "lidar_n": len(obs["lidar"]["detections"]),
                                      "live_n": len(obs["live"]["detections"]), "imu_sigma": obs["imu"]["sigma"],
                                      "gps_uncertain": obs["gps"]["uncertain"]}})
        # 10 Hz 기계 상태: 결정 사이를 선형 보간
        for k in range(nsub):
            a = (k + 1) / nsub
            gx = p0[0] + (p1[0]-p0[0]) * a; gy = p0[1] + (p1[1]-p0[1]) * a
            bus.publish_state({
                "t": round(t, 6), "pos": (round(gx, 3), round(gy, 3)),
                "alt": float(spec.get("agl", 90.0)), "vel": round(speed, 2),
                "heading": tele["heading"], "imu_sigma": round(_ref.ref_imu_sigma(t), 3),
                "coverage": round(tele["coverage"], 2), "policy": st,
                "sensors": sens, "target": "UNKNOWN",
                # 관측 필드(SUT view 필터가 남길 것) — 나머지는 truth 아님
                "rgb": {"vis": round(obs["rgb"]["vis"], 4)}, "sar": {"hits": obs["sar"]["hits"]},
                "imu": {"sigma": round(obs["imu"]["sigma"], 3)}, "gps": {"uncertain": obs["gps"]["uncertain"]},
            })
            t += dt
        if st == "MRC":
            break
    metrics = _eval.evaluate(truth, sut_log)
    n_t = spec.get("n_target", len(spec.get("targets_spec", []) or truth["targets"]))
    metrics["scenario"] = {"V": spec["V"], "illum": spec["illum"], "n_target": n_t}
    return bus, metrics, ref


def _실사렌더(ref, frames, REPO, stem):
    """render3d 로 **같은 임무를** 실사 3D(three.js PBR)·2D 지도로도 낸다. 탑재 카메라 시점에는 sar/camera.py 와
    같은 Beer-Lambert 안개(β=3.912/V)가 걸린다(render3d/vv.py 가 그 일치를 잰다).

    **시각화 계층이다** -- 실패해도 IV&V 결과(평가기 지표)는 바뀌지 않는다. 그래서 예외를 삼키고 한 줄만 남긴다."""
    try:
        if REPO not in sys.path:
            sys.path.insert(0, REPO)
        from render3d import sar_bridge as _r3
        for p in _r3.render_mission(ref, frames, os.path.join(REPO, "public_agent_memory", "render3d"), stem, repo=REPO):
            print("산출물:", p)
    except Exception as e:                                   # noqa: BLE001
        print("render3d 건너뜀(IV&V 결과와 무관): %s: %s" % (type(e).__name__, str(e)[:120]))


def case_demo(spec=CASE_TAEBAEK):
    """명시 시험 케이스 1건을 Reference→SUT→Evaluator 로 돌리고 3D 뷰+보고서를 낸다."""
    import datetime
    import viewer as _vw
    REPO = os.path.dirname(os.path.dirname(HERE)); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    metrics, frames = run_case(spec, record_frames=True)
    ref = _ref.Reference(spec)
    gif_rel = "public_agent_memory/ivv_case_%s.gif" % ts
    _vw.render(ref.dem, frames, os.path.join(REPO, gif_rel))
    _실사렌더(ref, frames, REPO, "ivv_case_%s" % ts)
    found = metrics["detected"]; nt = metrics["n_targets"]
    canopy = ref.truth()["canopy"]
    within = (metrics["latency_steps"] is not None)
    L = ["# IV&V 시험 케이스 — %s" % spec["name"], ""]
    L.append("> 세 층을 분리한다: **시나리오**(임무만 준다) · **시험 인프라**(Reference 가 hidden truth 로 "
             "월드를 진행) · **평가**(사후 비교). 시나리오도 Reference 도 SUT 에게 '어떻게/무엇이 정답'을 말하지 않는다.")
    L.append("")
    L.append("## A. 임무 시나리오 — 외부가 주는 것 (행동 명령 아님)")
    L.append("- 임무 목적: **조난자를 탐색하라** (방법은 안 정해 준다)")
    L.append("- 운용 영역: 태백산 동쪽 계곡, 실 DEM %.0f~%.0f m" % (ref.dem.min(), ref.dem.max()))
    L.append("- 시작 조건: UAV 초기 위치(격자 출발점), %.0f m AGL" % spec["agl"])
    L.append("- 안전 제약: geofence·최대고도(설계상 RTA/MRC)")
    L.append("- **장착 탑재체(사실)**: %s — '이것만 써라'가 아니라 가용 센서다" % " · ".join(spec.get("payload", spec["sensors"])))
    L.append("- 임무 요구사항: 제한시간 %d분(=%d프레임). **평가기가 '이내 확보?'로 검사** — SUT 에 준 명령이 아니다" %
             (spec.get("req_time_min", spec["budget_min"]), len(frames)))
    L.append("")
    L.append("## B. 시험 인프라 — Reference World (정답을 알려주지 않는다)")
    L.append("- hidden ground truth: 조난자 = 북동 %.0f m, **소나무 수관 아래**(canopy=%s), 지형·기상·센서 실상태" %
             (spec["targets_spec"][0]["range_m"], canopy[0]))
    L.append("- 기상: 짙은 안개 V=%.0f m (β=3.912/V=%.3f /m). SUT 의 결정(어디로·어느 센서)에 따라 **다음 관측만** 생성" %
             (spec["V"], 3.912/spec["V"]))
    L.append("")
    L.append("## C. SUT — 스스로 판단한다 (관측만 받는다)")
    L.append("- 경로·고도·언제 어느 센서·SAR 해석·재탐색·탐지판단·계속/철수·MRC 전환을 **자율 결정**. truth 못 봄.")
    L.append("")
    L.append("## D. 독립 평가 — 사후 비교")
    L.append("- **조난자 확보: %d/%d** · 위치RMSE %s · 오경보 %d · 커버리지 %.0f%% · 안전 %s · 소요 %d프레임 · 요구시간내 확보: %s" %
             (found, nt, ("%.2f셀" % metrics["loc_rmse_cells"]) if metrics["loc_rmse_cells"] == metrics["loc_rmse_cells"] else "—(미탐)",
              metrics["false_alarms"], metrics["coverage_pct"], "O" if metrics["safe"] else "X", metrics["steps"], "예" if within else "아니오"))
    L.append("")
    L.append("## 정직한 해석 — 왜 이 결과인가 (센서 물리)")
    if found < nt:
        L.append("- **RGB**: 40m 안개 투과율 ≈ exp(−%.3f·경사거리) ≈ 0 → 실명. 게다가 조난자가 **소나무 수관 아래**라 "
                 "안개가 걷혀도 광학이 못 뚫는다(수관 투과 ~5%%)." % (3.912/spec["V"]))
        L.append("- **X-band SAR**: 전천후(안개 무관)지만 X-대역(λ=3cm)은 **수관 위를 본다** — 수관 아래 사람은 약한 산란체라 "
                 "반사 확률 급감. 능선·바위 클러터에 묻힌다.")
        L.append("- **결론**: RGB+X-SAR+IMU 만으로 **40m 안개 + 수관 아래 사람**은 **탐지 불가에 가깝다**(이 케이스 미탐). "
                 "정책은 탐지를 꾸미지 않고 안전강등했다.")
        L.append("- **필요**: 열화상(LWIR, 수관 틈으로 체온) · FOPEN(L/P-band SAR, 엽면투과) · 조난자 폰 RF. "
                 "이것이 sensor-agnostic 정책이 다중센서를 융합해야 하는 정량 근거다.")
    else:
        L.append("- 이 실행에서는 확보. 단 수관·안개 조건상 RGB+X-SAR 만으로는 반복성이 낮다(운에 가깝다) — "
                 "열화상·FOPEN 보강이 신뢰성을 준다.")
    L.append("")
    L.append("![case](%s)" % gif_rel)
    md_rel = "public_agent_memory/ivv_case_%s.md" % ts
    open(os.path.join(REPO, md_rel), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("케이스: %s → 조난자 %d/%d, 안전 %s" % (spec["name"][:24], found, nt, "O" if metrics["safe"] else "X"))
    print("산출물:", md_rel)
    print("산출물:", gif_rel)
    return metrics


def telemetry_demo(spec=CASE_TAEBAEK):
    """3계층 rate-stratified 텔레메트리를 돌리고, 실측 주기 + 1Hz 보고발췌 + 이벤트 전부를 낸다."""
    import datetime
    import json
    import telemetry as _tel
    REPO = os.path.dirname(os.path.dirname(HERE)); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bus, metrics, ref = run_case_telemetry(spec)
    rates = bus.rates()
    # 10 Hz 원자료는 검증 가능하도록 jsonl 로 (rate 주장을 남이 재현)
    jsonl_rel = "public_agent_memory/telemetry_state_%s.jsonl" % ts
    with open(os.path.join(REPO, jsonl_rel), "w", encoding="utf-8") as f:
        for s in bus.state_log:
            f.write(json.dumps(bus.sut_view(s), ensure_ascii=False) + "\n")   # SUT view: 관측만
    L = ["# Rate-stratified 텔레메트리 — 하나의 주기로 다 보내지 않는다", ""]
    L.append("> 야전 실시간성은 '모두 같은 주기 보고'가 아니다. **10 Hz 기계 상태 · 1 Hz 운용 보고 · "
             "즉시 이벤트** 세 계층으로 나눈다. '보고'(사람/1 Hz)와 '데이터 전송'(기계/10 Hz)을 분리한다.")
    L.append("")
    L.append("## 실측 주기 (로그 간격 중앙값의 역수 — '정말 그 주기인가')")
    L.append("| 계층 | 목표 | 실측 | 로그 수 |")
    L.append("|---|---|---|---|")
    L.append("| 기계 상태(state) | %.0f Hz | **%.1f Hz** | %d |" % (_tel.STATE_HZ, rates["state_hz"], len(bus.state_log)))
    L.append("| 운용 보고(report) | %.0f Hz | **%.1f Hz** | %d |" % (_tel.REPORT_HZ, rates["report_hz"], len(bus.reports)))
    L.append("| 결정/경보(event) | 즉시 | 발생 순간 | %d |" % rates["events"])
    L.append("")
    L.append("## 결정/경보 이벤트 (즉시 — 일어난 순간)")
    L.append("```")
    for e in bus.events:
        L.append(_tel.format_event(e))
    L.append("```")
    L.append("")
    L.append("## 운용 보고 발췌 (1 Hz 대시보드 — 사람용, 처음 20초)")
    L.append("```")
    for r in bus.reports[:20]:
        L.append(_tel.format_report(r))
    L.append("```")
    L.append("- 10 Hz 원자료 전체(관측만, truth 제거): `%s`" % jsonl_rel)
    L.append("")
    L.append("## 왜 이 세 주기인가 — 정직한 근거")
    L.append("- **10 Hz 는 NASA 표준이 아니다.** 연구용 중간 설계점: 1 Hz 보다 자세·상태를 촘촘히 남기되, "
             "15~20 Hz 유인항공 CNPC 보다 가볍다. [출처:조각]")
    L.append("- 근거 대역(NASA NTRS): UAS CNPC 15~20 Hz · AirSTAR 200 Hz+ · 어떤 UAS 는 5 s(0.2 Hz)가 느려 "
             "≥1 Hz 로 상향 · JPL 텔레메트리 1~100 Hz 이질 채널. [출처:조각]")
    L.append("- **이 로그는 시뮬레이션이다** — 실 링크 지연·손실·대역은 반영 안 됨(field validation 아님).")
    L.append("- 속도는 격자(셀=%.0f m)·결정창(%.0fs)에서 유도한 값 — 실 비행 프로파일 아님." % (ref.PATCH_M/ref.GW, FRAME_S))
    md_rel = "public_agent_memory/telemetry_%s.md" % ts
    open(os.path.join(REPO, md_rel), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("텔레메트리 실측: state %.1fHz · report %.1fHz · event %d" % (rates["state_hz"], rates["report_hz"], rates["events"]))
    print("산출물:", md_rel)
    print("산출물:", jsonl_rel)
    return bus, metrics


def demo(n=6, budget=36):
    """숨은 시나리오 n개 평가 + 한 개는 3D 뷰어로 그려 public_agent_memory 에 보고를 낸다."""
    import datetime
    import viewer as _vw
    REPO = os.path.dirname(os.path.dirname(HERE)); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    scns = gen_scenarios(n)
    rows = [run_one(s, budget)[0] for s in scns]
    summ = _eval.summarize(rows)
    # 뷰어용: 표적 여럿·중간 조건 하나를 프레임 기록해 렌더
    pick = max(range(len(scns)), key=lambda k: scns[k]["n_target"])
    _m, frames = run_one(scns[pick], budget, record_frames=True)
    ref = _ref.Reference(scns[pick])
    gif_rel = "public_agent_memory/ivv_3dview_%s.gif" % ts
    _vw.render(ref.dem, frames, os.path.join(REPO, gif_rel))
    _실사렌더(ref, frames, REPO, "ivv_3dview_%s" % ts)
    md_rel = "public_agent_memory/ivv_%s.md" % ts
    open(os.path.join(REPO, md_rel), "w", encoding="utf-8").write(_report_md(rows, summ, gif_rel))
    print("산출물:", md_rel)
    print("산출물:", gif_rel)
    return rows, summ


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=6); ap.add_argument("--budget", type=int, default=40)
    ap.add_argument("--demo", action="store_true"); ap.add_argument("--case", action="store_true")
    ap.add_argument("--telemetry", action="store_true")
    a, _ = ap.parse_known_args()
    if a.telemetry:
        telemetry_demo(); sys.exit(0)
    elif a.case:
        case_demo(); sys.exit(0)
    elif a.demo:
        rows, summ = demo(a.n, a.budget)
    else:
        rows, summ = run(a.n, a.budget)
    print("=== IV&V: 숨은 시나리오 %d개, 독립 평가 ===" % summ["n_scenarios"])
    for r in rows:
        sc = r["scenario"]
        print("  V=%5.0fm illum=%6.0f 표적%d → 탐지 %d/%d(%.0f%%) RMSE=%.2f셀 오경보%d 커버%.0f%% 안전%s" %
              (sc["V"], sc["illum"], sc["n_target"], r["detected"], r["n_targets"], r["detection_rate"],
               r["loc_rmse_cells"], r["false_alarms"], r["coverage_pct"], "O" if r["safe"] else "X"))
    dr = summ["detection_rate"]; rm = summ["loc_rmse_cells"]; fa = summ["false_alarms"]
    print("종합: 탐지율 %.0f±%.0f%% · 위치RMSE %.2f±%.2f셀 · 오경보 %.1f±%.1f · 안전 %.0f%%" %
          (dr[0], dr[1], rm[0], rm[1], fa[0], fa[1], summ["safe_frac"]))
    print("※ independent simulation-based evidence. 참조세계도 모델(SUT 와 다른 formulation) — 현장 validation 아님.")
