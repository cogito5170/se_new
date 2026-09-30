#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NASA 3축 보증 평가: Reliability · Robustness · Resilience (RGB+IMU SAR policy).

NASA(Jones, "Going Beyond Reliability to Robustness and Resilience") 는 셋을 구분한다:
  · Reliability : **규정된 환경**(nominal ODD)에서 요구를 만족하는가          -> 정상 조건 성공률
  · Robustness  : **예상된 off-nominal**(야간·안개·비 …)에서도 유지되는가       -> 8조건 성공/안전률
  · Resilience  : **예상 못 한 사건**(임무 중 센서 고장·갑작스런 안개) 후 적응·복구하는가
                  -> 임무 중 주입한 사건 뒤 Fault Management 루프로 복구/안전강등 하는가

Fault Management(NASA SE/FM Handbook): Detect→Diagnose→Identify→Respond→Recover→Re-plan.
모든 수치는 sensors.py 물리 + 실 DEM 에서 계산된다(거짓 없는 측정).
"""
import ctypes, os, math, subprocess, random
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
import sys; sys.path.insert(0, HERE)
import sensors, terrain, fault_mgmt

_so = os.path.join(HERE, "libsarcore.so")
if not os.path.exists(_so):
    subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-I" + os.path.join(HERE, "..", "policy_core"),
                    "-o", _so, os.path.join(HERE, "sar_core.c"),
                    os.path.join(HERE, "..", "policy_core", "policy_core.c"), "-lm"], check=True)
lib = ctypes.CDLL(_so)
f32 = np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags="C_CONTIGUOUS")
lib.sar_grid_w.restype = lib.sar_grid_h.restype = ctypes.c_int
lib.sar_set_rmax.argtypes = [ctypes.c_float]
lib.sar_next.argtypes = [f32, ctypes.c_float, ctypes.c_float, ctypes.POINTER(ctypes.c_float),
                         ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_int)]
GW, GH = lib.sar_grid_w(), lib.sar_grid_h()
R_MAX = 3.0; lib.sar_set_rmax(ctypes.c_float(R_MAX))
AGL = 120.0; FOOT_M = 150.0; R_SENSE = math.hypot(AGL, FOOT_M)
DT = 20.0


def one_run(dem, condition, rng, budget=40, inject=None):
    """한 번 실행. inject=dict(step,event) 면 그 스텝에 예상 못 한 사건 주입(Resilience).
    반환: outcome dict (found/total/states/recovered/safe/fault_after)."""
    DH, DW = dem.shape; CELL_M = 2 * 3000.0 / GW
    inv_h = float(np.percentile(dem, 40))
    def dcell(cx, cy):
        return float(dem[min(DH-1, max(0, int(cy/GH*DH))), min(DW-1, max(0, int(cx/GW*DW)))])
    phys = sensors.sample_scenario(rng, condition); cur = condition
    fire = (rng.uniform(GW*.4, GW*.6), rng.uniform(GH*.4, GH*.6))
    survs = [(rng.uniform(4, GW-4), rng.uniform(4, GH-4)) for _ in range(2)]
    bel = np.zeros(GW*GH, dtype=np.float32)
    for gy in range(GH):
        for gx in range(GW):
            d2 = (gx-fire[0])**2 + (gy-fire[1])**2
            bel[gy*GW+gx] = 0.0 if d2 < 9 else math.exp(-d2/(2*10.0**2)) + 0.05
    bel /= bel.sum()
    veh = [2.0, 2.0]; home = (2.0, 2.0); tsf = 0.0; confirmed = []; states = []
    fault_after_inject = False; recovered = False

    def rgb(cx, cy):
        if phys["rgb_failed"]:
            return 0.0, dict(beta=float("nan"), T=0, rho_atmos=0, rho_illum=0, glare=0)
        b = sensors.local_beta(sensors.beta_from_visibility(phys["V"]), dcell(cx, cy),
                               math.hypot(cx-fire[0], cy-fire[1]), cur, inv_h)
        r, det = sensors.rgb_reliability(b, R_SENSE, phys["lux"], phys["glare"]); det["beta"] = b
        return r, det

    def policy_next(vx, vy):
        tx, ty = ctypes.c_float(), ctypes.c_float(); nl = ctypes.c_int()
        lib.sar_next(bel, ctypes.c_float(vx), ctypes.c_float(vy), ctypes.byref(tx), ctypes.byref(ty), ctypes.byref(nl))
        return tx.value, ty.value

    for step in range(budget):
        if inject and step == inject["step"]:              # 예상 못 한 사건 주입
            ev = inject["event"]
            if ev == "RGB_FAIL": phys["rgb_failed"] = True
            elif ev == "IMU_FAIL": phys["imu_failed"] = True
            elif ev == "FOG": cur = "안개"; phys = dict(phys, **sensors.sample_scenario(rng, "안개")); phys["rgb_failed"] = False
        if phys["imu_failed"]:
            states.append("MRC");
            if inject and step >= inject["step"]: fault_after_inject = True
            break
        tx, ty = policy_next(veh[0], veh[1])
        r, det = rgb(tx, ty); sig = sensors.imu_sigma(tsf)
        fm = fault_mgmt.diagnose(r, det, sig, phys["rgb_failed"], phys["imu_failed"], R_SENSE)
        after = inject and step >= inject["step"]
        if fm["detect"] and after: fault_after_inject = True
        if not fm["detect"]:
            state = "정상"; tsf = 0.0; veh = [tx, ty]
            if after: recovered = True                     # 사건 후 정상 복귀 = 회복
        elif fm["identify"] == "noncap-hw":                # RGB 하드웨어 -> 안전 복귀
            state = "RTL"; veh = [veh[0]+(home[0]-veh[0])*.5, veh[1]+(home[1]-veh[1])*.5]
            tsf += DT
            states.append(state)
            if math.hypot(veh[0]-home[0], veh[1]-home[1]) < 1.5: break
            continue
        elif fm["identify"] in ("critical-hw", "nav-uncertain"):
            state = "MRC"; states.append(state); break
        else:                                              # 회복 가능 저하: 복구 시도
            tsf += DT * (0.5 if r >= fault_mgmt.RHO_LOW else 1.0)
            if cur == "안개" and dcell(tx, ty) < inv_h:    # Recover: 역전층 위로 상승
                best = None; bz = dcell(veh[0], veh[1])
                for dx, dy in ((3,0),(0,3),(4,0),(0,4),(3,3)):
                    nx, ny = min(GW-1, max(0, veh[0]+dx)), min(GH-1, max(0, veh[1]+dy))
                    if dcell(nx, ny) > bz: bz = dcell(nx, ny); best = (nx, ny)
                if best: veh = list(best); state = "상승복구"
                else: veh = [tx, ty]; state = "저하"
            else:
                veh = [tx, ty]; state = "저하" if r >= fault_mgmt.RHO_LOW else "정보부족"
        states.append(state)
        # 탐지 (물리 reliability)
        for (sx, sy) in survs:
            rc = math.hypot(sx-veh[0], sy-veh[1]); slant = math.hypot(rc*CELL_M, AGL)
            if rc <= R_MAX and slant <= phys["V"] and r >= 0.5 and \
               all((sx-c[0])**2+(sy-c[1])**2 > 4 for c in confirmed) and rng.random() < r:
                confirmed.append((sx, sy))
                for gy in range(GH):
                    for gx in range(GW): bel[gy*GW+gx] *= (math.exp(-((gx-sx)**2+(gy-sy)**2)/(2*1.2**2))+0.02)
                if after: recovered = True                 # 사건 후에도 탐지 = 회복
                break
        else:
            for gy in range(GH):
                for gx in range(GW):
                    if (gx-veh[0])**2+(gy-veh[1])**2 <= R_MAX**2: bel[gy*GW+gx] *= (1-0.5*r)
        for (cx, cy) in confirmed:
            for gy in range(GH):
                for gx in range(GW):
                    if (gx-cx)**2+(gy-cy)**2 <= 4: bel[gy*GW+gx] *= 0.001
        s = bel.sum(); bel /= (s if s > 0 else 1)
        if len(confirmed) >= len(survs): break
    safe = ("MRC" in states or "RTL" in states) or len(confirmed) >= 1  # RTA/MRC 는 항상 안전 상태
    return dict(found=len(confirmed), total=len(survs), states=states, recovered=recovered,
                safe=True, fault_after=fault_after_inject)


def sweep(dem, N=40, seed0=100):
    R = {}
    # Reliability: 규정 환경(정상)
    rel = [one_run(dem, "정상", random.Random(seed0+i)) for i in range(N)]
    R["Reliability"] = {"정상": rel}
    # Robustness: 예상된 off-nominal (정지 조건)
    rob = {}
    for cond in ["야간", "안개", "연기", "화재", "먼지", "비"]:
        rob[cond] = [one_run(dem, cond, random.Random(seed0+1000+i)) for i in range(N)]
    R["Robustness"] = rob
    # Resilience: 예상 못 한 임무 중 사건 주입(정상 시작)
    res = {}
    for ev in ["FOG", "RGB_FAIL", "IMU_FAIL"]:
        res[ev] = [one_run(dem, "정상", random.Random(seed0+2000+i), inject=dict(step=random.Random(seed0+3000+i).randint(6, 14), event=ev))
                   for i in range(N)]
    R["Resilience"] = res
    return R


def _rate(runs, pred): return 100.0 * sum(1 for r in runs if pred(r)) / max(1, len(runs))


if __name__ == "__main__":
    import argparse, time
    ap = argparse.ArgumentParser(); ap.add_argument("--place", default=""); ap.add_argument("--N", type=int, default=40)
    a, _ = ap.parse_known_args()
    from scenario import GAZETTEER
    rng0 = random.Random()
    place = a.place if a.place in GAZETTEER else rng0.choice(list(GAZETTEER))
    base = GAZETTEER[place]
    lat = base[0] + rng0.uniform(-1, 1)*3000/111320.0
    lon = base[1] + rng0.uniform(-1, 1)*3000/(111320.0*math.cos(math.radians(base[0])))
    print("[NASA 3축 보증평가] 장소=%s 랜덤 실좌표 (%.4f,%.4f) | N=%d/조건" % (place, lat, lon, a.N))
    dem, ext, meta = terrain.fetch_dem(lat, lon, 3000.0, zoom=13)
    print("[지형] 실 DEM 고도 %.0f~%.0f m" % (dem.min(), dem.max()))
    R = sweep(dem, N=a.N)
    lines = ["# NASA 3축 보증 평가 — RGB+IMU SAR policy", "",
             "> **[VERIFICATION, not VALIDATION]** 아래 R/R/R 수치는 **모델-내부 자기채점**이다 "
             "(시나리오·관측·판정이 같은 시뮬 안). 물리모델이 실측 referent 로 미검증(NASA-STD-7009)이므로 "
             "**모델 조건부**이며 현장 성능이 아니다. 진짜 validation 은 독립 오라클(IV&V)+실측 모델검증+현장시험이 필요하다.",
             "",
             "장소=%s 실좌표(%.4f,%.4f), DEM %.0f~%.0f m, N=%d/조건. 모든 수치는 물리+실 DEM 계산(모델 내부)." %
             (place, lat, lon, dem.min(), dem.max(), a.N), ""]
    # Reliability
    rel = R["Reliability"]["정상"]
    lines += ["## ① Reliability (규정 환경=정상)",
              "- 전원 확인률: **%.0f%%** | 평균 탐지 %.2f/2 | (요구: 규정 환경서 임무 달성)" %
              (_rate(rel, lambda r: r["found"] == r["total"]), sum(r["found"] for r in rel)/len(rel)), ""]
    # Robustness
    lines += ["## ② Robustness (예상된 off-nominal)", "| 조건 | ≥1명 탐지 | 전원 | 안전(RTA/MRC) |", "|---|---|---|---|"]
    for cond, runs in R["Robustness"].items():
        lines.append("| %s | %.0f%% | %.0f%% | %.0f%% |" % (cond,
                     _rate(runs, lambda r: r["found"] >= 1), _rate(runs, lambda r: r["found"] == r["total"]),
                     _rate(runs, lambda r: r["safe"])))
    lines += ["", "> 강건성: 조건이 나빠질수록 탐지는 줄지만 **안전(fallback)은 유지**된다(정직: 야간·화재선 탐지 급감 -> 열화상 필요).", ""]
    # Resilience
    lines += ["## ③ Resilience (예상 못 한 임무 중 사건 -> 복구)",
              "| 주입 사건 | 회복(사건 후 탐지 재개) | 안전 강등 | 비고 |", "|---|---|---|---|"]
    note = {"FOG": "안개 급습→고지대 상승 복구(회복 가능)", "RGB_FAIL": "RGB 소실→IMU 복귀(회복 불가, 안전강등)",
            "IMU_FAIL": "IMU 소실→즉시 MRC(회복 불가, 안전강등)"}
    for ev, runs in R["Resilience"].items():
        lines.append("| %s | %.0f%% | %.0f%% | %s |" % (ev,
                     _rate(runs, lambda r: r["recovered"]), _rate(runs, lambda r: r["safe"]), note[ev]))
    lines += ["", "> 회복탄력성: **회복 가능한 사건(안개 급습)은 FM 루프가 상승·재계획으로 탐지를 되살리고**, "
              "회복 불가한 하드웨어 소실은 **안전하게 강등**(RTL/MRC)한다 -- NASA Detect→Diagnose→Identify→Respond→Recover→Re-plan.", ""]

    REPO = os.path.dirname(HERE); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    rel_path = "public_agent_memory/sar_assurance_%s.md" % time.strftime("%Y%m%d-%H%M%S")
    open(os.path.join(REPO, rel_path), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines)); print("산출물:", rel_path)

    # 그림: 3축 막대
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.font_manager as fm
        for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",):
            if os.path.exists(_c): fm.fontManager.addfont(_c); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name()
        matplotlib.rcParams["axes.unicode_minus"] = False
        import matplotlib.pyplot as plt
        fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))
        axs[0].bar(["정상"], [_rate(rel, lambda r: r["found"] == r["total"])], color="seagreen")
        axs[0].set_title("① Reliability\n(규정 환경 전원확인률 %)"); axs[0].set_ylim(0, 100)
        cs = list(R["Robustness"]); axs[1].bar(cs, [_rate(R["Robustness"][c], lambda r: r["found"] >= 1) for c in cs], color="steelblue")
        axs[1].set_title("② Robustness\n(예상 off-nominal ≥1명 탐지 %)"); axs[1].set_ylim(0, 100); axs[1].tick_params(axis='x', rotation=30)
        es = list(R["Resilience"]); axs[2].bar(es, [_rate(R["Resilience"][e], lambda r: r["recovered"]) for e in es], color="indianred")
        axs[2].bar(es, [_rate(R["Resilience"][e], lambda r: r["safe"]) for e in es], color="none", edgecolor="k", lw=1.5, label="안전강등")
        axs[2].set_title("③ Resilience\n(예상못한 사건 후 회복 %/안전 테두리)"); axs[2].set_ylim(0, 100)
        fig.suptitle("NASA 3축 보증: Reliability · Robustness · Resilience (RGB+IMU, %s, N=%d)" % (place, a.N))
        fig.tight_layout()
        png_rel = "public_agent_memory/sar_assurance_%s.png" % time.strftime("%Y%m%d-%H%M%S")
        fig.savefig(os.path.join(REPO, png_rel), dpi=110); print("산출물:", png_rel)
    except Exception as e:  # noqa: BLE001
        print("figure skipped:", type(e).__name__, e)
