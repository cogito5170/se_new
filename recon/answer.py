"""recon_rover 도구의 본문: 커밋된 결과 요약(results/summary.json)과 spec.py 로 글을 짓는다.
시뮬레이션을 다시 돌리지 않는다(그건 recon_make). 수치는 전부 가상 시험장 출력(실측 아님)."""
from __future__ import annotations

import json

from recon import paths, spec

S = None


def _s():
    global S
    if S is None:
        S = json.loads((paths.RESULTS / "summary.json").read_text(encoding="utf-8"))
    return S


def _pct(x):
    return "-" if x is None else f"{x * 100:.1f}%"


def 사양() -> str:
    M, P = spec.MECH, spec.PARTS
    return "\n".join([
        "RECON-R1 사양 (recon/spec.py, 부품 수치는 검색 조각 [조각], 나머지 가정 [A])",
        f"- 차체 450×350×150 mm, 윤거 {M['track']} m, 축거 {M['wheelbase']} m, 바퀴 Ø{M['wheel_r'] * 200:.0f} mm, {M['mass_kg']} kg, 무게중심 {M['cog_h']} m",
        f"- 전복 한계 {M['max_slope_deg']:.1f}° (앞뒤; 옆 {M['roll_over_deg']:.1f}°), 정책 경사 한계 {M['slope_limit_deg']}°",
        f"- LiDAR Livox Mid-360 뒤집어 장착(시야 -52..+7°), 광학중심 {M['lidar_h']} m, 사각 반경 {M['lidar_blind_r_inverted']:.2f} m (바로 세우면 {M['lidar_blind_r_upright']:.1f} m)",
        "- 계산: Jetson Orin Nano Super(추정·지도·J) + NUCLEO-H753ZI(바퀴 PID·안전·SE fw 결정 커널)",
        "- 센서 최소 세트: Mid-360 + ICM-42688-P 1 kHz + 엔코더 3200 tick/rev + IMX219 · 확장: ZED-F9P RTK",
        f"- 구동: Pololu 37D 50:1 24 V ×4 (14.4 V 구동, 무부하 {spec.DRIVE['v_noload']:.2f} m/s), MDD20A ×2",
        f"- 전원: 4S Li-ion 10 Ah, 가용 {spec.E_WH:.0f} Wh, 평균 {spec.P_AVG:.1f} W → {spec.RUNTIME_H:.2f} h, 최대 {spec.P_PEAK:.0f} W · Jetson 팩 직결(9-20 V 입력)",
        "- 안전: E-stop·433 MHz 하트비트 킬·MCU MOTOR_EN·워치독 → K1 코일 직렬 (모터 버스만 차단, 로직은 산다)",
        f"- 원시 데이터 {spec.DATA['raw_Bps'] / 1e6:.2f} MB/s · 부품비(확인분) ${_s()['bom_usd']['min']:,.0f}–{_s()['bom_usd']['typical']:,.0f}, 미확인 품목 더하면 약 $2,540–2,830",
    ])


def 정책() -> str:
    return "\n".join([
        "결정 구조 (LLM 없음): 상태추정(EKF x,y,θ,b_g + LIO) → 증거(건강 5·슬립·기울기·위험·J 후보 3) → fw C 커널(MCU 10 Hz: guard → BT 우선순위 → precondition+효용 중재 → 안전필터) → 유도(Dijkstra+순수추종, 기동 잠금) → 바퀴 PID(50 Hz) → 모터",
        "목적함수 U(g) = IG(g) − λE·E − λT·T − λR·R  (kbit), J = U/(U+5). IG = Σ K(r)·½log2(max(σ²,σt²)/max(σpost²,σt²)) — 목표 σt(5 cm, 관심구역 2 cm) 아래는 가치 0",
        "BT 우선순위: EMERGENCY(구동계 고장·배터리<5%) > SAFE_STOP(위험>0.92·경사≥한계·항법 전부 사망·σ>1.2 m) > AVOID(위험>0.6·슬립>0.45·경사>0.8) > RETURN(배터리<귀환필요+8% 걸쇠·저장≥98%·링크≥30 s·커버리지≥92%·LiDAR 사망) > RELOCALIZE(σ>0.35 m) > 효용 argmax(EXPLORE·REVISIT·OBSERVE)",
        f"커널: SE fw/ 를 한 줄도 안 고치고 recon/fw/profile_recon.c 하나로 재사용. 호스트 검사 {_s()['kernel']['host_tests']}, freestanding {_s()['kernel']['text_bytes_kernel_plus_profile']} B, Agent RAM {_s()['kernel']['agent_ram_bytes']} B",
    ])


def 시나리오(sid: str = "") -> str:
    sc = _s()["scenarios"]
    if sid and sid.upper() in sc:
        d = sc[sid.upper()]; k = d["kpi"]
        ev = "\n".join(f"  {e['t']:.1f} s {e['kind']}: {e['msg']}" for e in d["events"]) or "  (없음)"
        return (f"{sid.upper()} {d['title']} — {d['what']}\n대응: {d['how']}\n결과: 커버리지 {_pct(k['coverage'])}"
                + (f" · 관심구역 {_pct(k['aoi_cov'])}" if k.get("aoi_cov") is not None else "")
                + f" · 고도 RMSE {k['rmse_m'] * 100:.1f} cm · ATE {k['ate_m'] * 100:.1f} cm · {k['dist_m']} m · {k['energy_Wh']} Wh · 충돌 {k['collisions']} · {k['done']}\n행동 전이: {d['actions']}\n사건:\n{ev}")
    return "\n".join(f"{i} {d['title']}: 커버리지 {_pct(d['kpi']['coverage'])}, 충돌 {d['kpi']['collisions']}" for i, d in sc.items())


def 기준선() -> str:
    m = _s()["baselines_mc"]["stats_mean_sd"]; nm = {"fixed": "고정 웨이포인트", "random": "무작위", "frontier": "프런티어", "proposed": "제안(J+fw)"}
    rows = [f"{nm[k]}: 커버리지 {v['coverage'][0] * 100:.1f}±{v['coverage'][1] * 100:.1f}%, 관심구역 {v['aoi_cov'][0] * 100:.1f}±{v['aoi_cov'][1] * 100:.1f}%, "
            f"{v['dist_m'][0]:.0f} m, {v['energy_Wh'][0]:.2f} Wh, {v['info_per_Wh'][0]:.0f} kbit/Wh" for k, v in m.items()]
    return ("기준선 비교 (같은 세계·안전층·유도·제어, 5 시드 × 240 s):\n" + "\n".join(rows) +
            "\n읽는 법: 제안과 무작위의 전체 커버리지 차이는 표준편차 안팎 — 우위로 말하지 않는다. 제안이 분명한 것은 분산·정보/에너지·관심구역(제안만 목적함수로 안다).")


def 필터() -> str:
    f = _s()["filters_slip_mud"]["mean"]; nm = {"odom": "F1 엔코더만", "odom_gyro": "F2 +자이로", "ekf_lio": "F3 EKF+LIO", "proposed": "F4 제안"}
    return ("진흙(슬립 0.35) 지도 왜곡 — 같은 원시 데이터, 3 시드 평균:\n" + "\n".join(
        f"{nm[k]}: 최종 위치 {v['final_err_m']:.3f} m, 요 {v['yaw_err_deg']:.2f}°, 지도 RMSE {v['map_rmse_m'] * 100:.1f} cm, 유령 셀 {v['ghost_cells']:.0f}" for k, v in f.items())
        + "\nF4 = 자이로 편향 상태 + 슬립 적응 Q + 슬립 관측 불가 시 주행거리 20 % 의심 + NIS 3회 연속 기각 = 발산으로 보고 공분산 팽창. LIO 는 대용 모델(실 FAST-LIO2 아님).")


def 통로() -> str:
    g = _s()["gap_sweep"]; by = {}
    for x in g:
        by.setdefault(x["gap"], []).append(x["passed"])
    return "통로 폭 쓸기 (로버 전폭 0.44 m): " + " · ".join(f"{k:.1f} m {sum(v)}/{len(v)}" for k, v in sorted(by.items())) + " — 0.9↔1.0 m 에서 뒤집힌다. 원인은 계획기 여유가 아니다 — 깨끗한 지도에서는 계획기가 0.8 m 틈도 연다(tests/test_recon.py). 실제 시뮬에서 막은 것은 2.5D 지도의 벽 번짐(수직면 점이 이웃 셀로)과 그 셀을 보는 전방 위험 판정이다."


def 지식() -> str:
    return (paths.PKG / "knowledge.md").read_text(encoding="utf-8")


def 부르기(무엇: str = "요약", 시나리오id: str = "") -> str:
    w = (무엇 or "요약").strip()
    if w in ("사양", "spec"):
        return 사양()
    if w in ("정책", "결정", "policy"):
        return 정책()
    if w in ("시나리오", "scenario"):
        return 시나리오(시나리오id)
    if w in ("기준선", "baseline"):
        return 기준선()
    if w in ("필터", "슬립", "filter"):
        return 필터()
    if w in ("통로", "gap"):
        return 통로()
    if w in ("지식", "knowledge"):
        return 지식()
    if w in ("요약", "전부"):
        return "\n\n".join([사양(), 정책(), 기준선(), 필터(), 통로(), "시나리오 30:\n" + 시나리오(), f"게시물: {_s()['artifact']}", "모든 수치는 가상 시험장 시뮬레이션 출력이다(실측 아님)."])
    return f"모르는 항목 {w!r}. 가능: 요약 · 사양 · 정책 · 시나리오(+ID) · 기준선 · 필터 · 통로 · 지식"
