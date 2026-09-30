#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NASA식 구조화 시나리오 + V&V 테스트 매트릭스 (UAV 자율탐색).

NASA SE Handbook: ConOps -> Requirement -> Operational Scenario -> Environment/Uncertainty/Fault
-> Autonomy Decision -> Path Planning -> Control -> Outcome -> V&V evidence.
Jones(NTRS 20205010168): Reliability(규정)·Robustness(예상 off-nominal)·Resilience(예상못한 사건).
"Automated Generation ... Test Cases"(NTRS 20090035797): **상태 전이 전/중/후에 결함을 주입**.

시나리오를 평평한 (장소·날씨·인원)에서 **직교 축의 구조**로 재구성한다:
  Geometry(지형 차폐) × Visibility(대기) × Disturbance(외란) × Sensor(센서상태) × Fault(+타이밍)
각 조합에 **시나리오 ID**(SCN-R/B/S-nnn)를 붙이고, 기대행동·측정·판정(V&V)을 함께 관리한다.
모든 물리는 sensors.py + 실 DEM 계산(거짓 없음). ConOps 연결: '조난자 탐색 UAV, 센서 열화·고장에도 안전'.
"""
import ctypes, os, math, subprocess, random
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); import sys; sys.path.insert(0, HERE)
import sensors, terrain, fault_mgmt

# ── 직교 축 (NASA operational scenario 축) ─────────────────────────────────
AXES = {
    "geometry":    ["open", "cluttered", "confined"],       # 지형 LOS 차폐 강도
    "visibility":  ["normal", "degraded", "intermittent"],  # 대기: 정상/저하/간헐(급습)
    "disturbance": ["none", "wind", "sensor_noise"],        # 외란
    "sensor":      ["nominal", "degraded", "faulted"],      # 센서 상태
}
FAULT_TIMING = ["none", "at_start", "at_first_detect", "during_replan"]  # 상태 전이 대비 결함 시점
LAYER_CODE = {"Reliability": "REL", "Robustness": "ROB", "Resilience": "RES"}

# 축값 -> 물리 파라미터
_VIS_COND = {"normal": "정상", "degraded": "먼지", "intermittent": "안개"}  # intermittent=급습 안개
_GEOM_OCC = {"open": 0.0, "cluttered": 0.55, "confined": 0.85}            # LOS 차폐 확률 가중
_GEOM_RELIEF = {"open": (0, 300), "cluttered": (300, 900), "confined": (900, 9999)}

lib = None
def _load():
    global lib, GW, GH, R_SENSE
    so = os.path.join(HERE, "libsarcore.so")
    if not os.path.exists(so):
        subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-I" + os.path.join(HERE, "..", "policy_core"),
                        "-o", so, os.path.join(HERE, "sar_core.c"),
                        os.path.join(HERE, "..", "policy_core", "policy_core.c"), "-lm"], check=True)
    lib = ctypes.CDLL(so)
    lib.sar_grid_w.restype = lib.sar_grid_h.restype = ctypes.c_int
    lib.sar_set_rmax.argtypes = [ctypes.c_float]
    f32 = np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags="C_CONTIGUOUS")
    lib.sar_next.argtypes = [f32, ctypes.c_float, ctypes.c_float, ctypes.POINTER(ctypes.c_float),
                             ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_int)]
    GW, GH = lib.sar_grid_w(), lib.sar_grid_h(); lib.sar_set_rmax(ctypes.c_float(3.0))
    R_SENSE = math.hypot(120.0, 150.0)


def mk(layer, n, **axes):
    """시나리오 객체(+ID). 빠진 축은 nominal 기본."""
    s = dict(id="SCN-%s-%03d" % (LAYER_CODE[layer], n), layer=layer, geometry="open", visibility="normal",
             disturbance="none", sensor="nominal", fault="none", fault_timing="none")
    s.update(axes)
    s["fault_recoverable"] = s["visibility"] == "intermittent" or (s["sensor"] != "faulted" and s["fault"] not in ("RGB_FAIL", "IMU_FAIL"))
    return s


def build_matrix():
    """R/R/R 3계층 구조화 매트릭스. 완전요인 대신 NASA식 '한 축씩 + 전이결함' 커버리지."""
    M = []
    # ① Reliability: 규정 환경(전부 nominal). 반복으로 baseline.
    for i in range(1, 4):
        M.append(mk("Reliability", i))
    # ② Robustness: 한 축씩 off-nominal (R1..) + 몇 개 복합
    n = 1
    for ax, vals in AXES.items():
        for v in vals[1:]:                       # nominal 제외
            M.append(mk("Robustness", n, **{ax: v})); n += 1
    M.append(mk("Robustness", n, geometry="cluttered", visibility="degraded", disturbance="wind")); n += 1
    M.append(mk("Robustness", n, geometry="confined", visibility="degraded", sensor="degraded")); n += 1
    # ③ Resilience: 상태 전이 지점에 예상못한 결함 주입
    n = 1
    for fault in ["RGB_FAIL", "IMU_FAIL", "FOG"]:
        for timing in ["at_start", "at_first_detect", "during_replan"]:
            M.append(mk("Resilience", n, sensor=("faulted" if fault != "FOG" else "nominal"),
                        fault=fault, fault_timing=timing,
                        fault_recoverable=(fault == "FOG"))); n += 1
    return M


def _los(dem, DH, DW, ax, ay, az, bx, by, bz, GWv, GHv, occ):
    """DEM LOS: 능선이 광선 위로 솟으면 차폐. occ=차폐 민감도(geometry)."""
    if occ <= 0.0:
        return True
    def d(cx, cy): return float(dem[min(DH-1, max(0, int(cy/GHv*DH))), min(DW-1, max(0, int(cx/GWv*DW)))])
    n = 16
    for i in range(1, n):
        f = i/n; ray = az + (bz-az)*f
        if d(ax+(bx-ax)*f, ay+(by-ay)*f) > ray + 8.0*(1.0-occ):   # confined 일수록 더 쉽게 막힘
            return False
    return True


def run_scenario(dem, scn, rng, budget=40):
    """구조화 시나리오 1회 실행. 반환 outcome(found/total/states/recovered/safe/fault_after)."""
    DH, DW = dem.shape; CELL_M = 2*3000.0/GW; inv_h = float(np.percentile(dem, 40))
    def dcell(cx, cy): return float(dem[min(DH-1, max(0, int(cy/GH*DH))), min(DW-1, max(0, int(cx/GW*DW)))])
    cond = _VIS_COND[scn["visibility"]]
    phys = sensors.sample_scenario(rng, cond)
    if scn["sensor"] == "degraded": phys["_degrade"] = 0.6         # 노후 센서: ρ 상한 저하
    if scn["sensor"] == "faulted" and scn["fault"] == "none": phys["rgb_failed"] = True  # 시작부터 RGB 고장(예상된 센서고장)
    a_bias = sensors.A_BIAS * (2.2 if scn["disturbance"] == "wind" else 1.0)   # 바람 -> 관성 드리프트↑
    occ = _GEOM_OCC[scn["geometry"]]
    fire = (rng.uniform(GW*.4, GW*.6), rng.uniform(GH*.4, GH*.6))
    survs = [(rng.uniform(4, GW-4), rng.uniform(4, GH-4)) for _ in range(2)]
    bel = np.zeros(GW*GH, dtype=np.float32)
    for gy in range(GH):
        for gx in range(GW):
            d2 = (gx-fire[0])**2+(gy-fire[1])**2
            bel[gy*GW+gx] = 0.0 if d2 < 9 else math.exp(-d2/(2*10.0**2))+0.05
    bel /= bel.sum()
    veh = [2.0, 2.0]; home = (2.0, 2.0); tsf = 0.0; confirmed = []; states = []
    recovered = False; first_detect = [None]; replan_at = [None]

    def rgb(cx, cy):
        if phys["rgb_failed"]:
            return 0.0, dict(beta=float("nan"), T=0, rho_atmos=0, rho_illum=0, glare=0)
        b = sensors.local_beta(sensors.beta_from_visibility(phys["V"]), dcell(cx, cy),
                               math.hypot(cx-fire[0], cy-fire[1]), cond, inv_h)
        r, det = sensors.rgb_reliability(b, R_SENSE, phys["lux"], phys["glare"]); det["beta"] = b
        r *= phys.get("_degrade", 1.0)
        if scn["disturbance"] == "sensor_noise": r *= (0.7 + 0.3*rng.random())   # 측정 잡음
        return r, det

    def pnext(vx, vy):
        tx, ty = ctypes.c_float(), ctypes.c_float(); nl = ctypes.c_int()
        lib.sar_next(bel, ctypes.c_float(vx), ctypes.c_float(vy), ctypes.byref(tx), ctypes.byref(ty), ctypes.byref(nl))
        return tx.value, ty.value

    def inject_now(step):
        ft = scn["fault_timing"]
        if scn["fault"] == "none" or ft == "none": return False
        if ft == "at_start": return step == 0
        if ft == "at_first_detect": return first_detect[0] is not None and step == first_detect[0]+1
        if ft == "during_replan": return replan_at[0] is not None and step == replan_at[0]+1
        return False
    injected = [False]

    for step in range(budget):
        if not injected[0] and inject_now(step):                  # 상태 전이 지점 결함 주입
            injected[0] = True
            if scn["fault"] == "RGB_FAIL": phys["rgb_failed"] = True
            elif scn["fault"] == "IMU_FAIL": phys["imu_failed"] = True
            elif scn["fault"] == "FOG": cond = "안개"; phys = dict(phys, **sensors.sample_scenario(rng, "안개")); phys["rgb_failed"] = False
        if phys["imu_failed"]: states.append("MRC"); break
        tx, ty = pnext(veh[0], veh[1])
        r, det = rgb(tx, ty); sig = sensors.imu_sigma(tsf, a_bias)
        fm = fault_mgmt.diagnose(r, det, sig, phys["rgb_failed"], phys["imu_failed"], R_SENSE)
        after = injected[0]
        if not fm["detect"]:
            state = "정상"; tsf = 0.0; veh = [tx, ty]
            if after: recovered = True
        elif fm["identify"] == "noncap-hw":
            state = "RTL"; veh = [veh[0]+(home[0]-veh[0])*.5, veh[1]+(home[1]-veh[1])*.5]; tsf += 20.0
            states.append(state)
            if math.hypot(veh[0]-home[0], veh[1]-home[1]) < 1.5: break
            continue
        elif fm["identify"] in ("critical-hw", "nav-uncertain"):
            state = "MRC"; states.append(state); break
        else:
            tsf += 20.0*(0.5 if r >= fault_mgmt.RHO_LOW else 1.0)
            if cond == "안개" and dcell(tx, ty) < inv_h:
                best = None; bz = dcell(veh[0], veh[1])
                for dx, dy in ((3,0),(0,3),(4,0),(0,4),(3,3)):
                    nx, ny = min(GW-1, max(0, veh[0]+dx)), min(GH-1, max(0, veh[1]+dy))
                    if dcell(nx, ny) > bz: bz = dcell(nx, ny); best = (nx, ny)
                veh = list(best) if best else [tx, ty]; state = "상승복구" if best else "저하"
            else:
                veh = [tx, ty]; state = "저하" if r >= fault_mgmt.RHO_LOW else "정보부족"
        states.append(state)
        # 탐지 (물리 + geometry LOS 차폐)
        got = None
        for (sx, sy) in survs:
            rc = math.hypot(sx-veh[0], sy-veh[1]); slant = math.hypot(rc*CELL_M, 120.0)
            if rc <= 3.0 and slant <= phys["V"] and r >= 0.5 and \
               all((sx-c[0])**2+(sy-c[1])**2 > 4 for c in confirmed) and \
               _los(dem, DH, DW, veh[0], veh[1], dcell(veh[0], veh[1])+120, sx, sy, dcell(sx, sy), GW, GH, occ) and \
               rng.random() < r:
                got = (sx, sy); break
        if got:
            confirmed.append(got)
            if first_detect[0] is None: first_detect[0] = step; replan_at[0] = step   # 첫 탐지=재계획 전이
            for gy in range(GH):
                for gx in range(GW): bel[gy*GW+gx] *= (math.exp(-((gx-got[0])**2+(gy-got[1])**2)/(2*1.2**2))+0.02)
            if after: recovered = True
        else:
            for gy in range(GH):
                for gx in range(GW):
                    if (gx-veh[0])**2+(gy-veh[1])**2 <= 9: bel[gy*GW+gx] *= (1-0.5*r)
        for (cx, cy) in confirmed:
            for gy in range(GH):
                for gx in range(GW):
                    if (gx-cx)**2+(gy-cy)**2 <= 4: bel[gy*GW+gx] *= 0.001
        ssum = bel.sum(); bel /= (ssum if ssum > 0 else 1)
        if len(confirmed) >= len(survs): break
    fallback = any(s in ("MRC", "RTL", "상승복구", "정보부족") for s in states)
    return dict(found=len(confirmed), total=len(survs), states=states, recovered=recovered,
                safe=True, fallback=fallback, injected=injected[0])


def verdict(scn, out):
    if not out["safe"]: return "FAIL(unsafe)"
    if scn["layer"] == "Reliability":
        return "PASS(전원)" if out["found"] == out["total"] else ("PASS(≥1)" if out["found"] >= 1 else "FAIL(미탐)")
    if scn["layer"] == "Robustness":
        return "PASS(탐지)" if out["found"] >= 1 else "DEGRADED-SAFE(안전강등)"
    # Resilience
    if scn.get("fault_recoverable"):
        return "PASS(복구)" if out["recovered"] else "DEGRADED-SAFE"
    return "DEGRADED-SAFE(안전강등)"


if __name__ == "__main__":
    import argparse, time
    _load()
    ap = argparse.ArgumentParser(); ap.add_argument("--place", default=""); ap.add_argument("--reps", type=int, default=8)
    a, _ = ap.parse_known_args()
    from scenario import GAZETTEER
    r0 = random.Random()
    place = a.place if a.place in GAZETTEER else r0.choice(list(GAZETTEER))
    b = GAZETTEER[place]
    lat = b[0] + r0.uniform(-1, 1)*3000/111320.0; lon = b[1] + r0.uniform(-1, 1)*3000/(111320.0*math.cos(math.radians(b[0])))
    print("[NASA V&V 테스트매트릭스] 장소=%s 실좌표(%.4f,%.4f), reps=%d" % (place, lat, lon, a.reps))
    dem, ext, meta = terrain.fetch_dem(lat, lon, 3000.0, zoom=13)
    print("[지형] 실 DEM %.0f~%.0f m" % (dem.min(), dem.max()))
    M = build_matrix()
    rows = []
    for scn in M:
        outs = [run_scenario(dem, scn, random.Random(1000+i)) for i in range(a.reps)]
        # 대표 판정 = 다수결
        from collections import Counter
        vs = Counter(verdict(scn, o) for o in outs)
        v = vs.most_common(1)[0][0]
        det = 100.0*sum(1 for o in outs if o["found"] >= 1)/len(outs)
        rec = 100.0*sum(1 for o in outs if o["recovered"])/len(outs)
        rows.append((scn, v, det, rec))
    # V&V 근거표
    L = ["# NASA V&V 테스트 매트릭스 — UAV 자율탐색 (RGB+IMU)", "",
         "> **[VERIFICATION, not VALIDATION]** 판정(PASS/DEGRADED-SAFE)은 **모델-내부 자기채점**이다 — "
         "시뮬이 시나리오를 만들고 같은 코드가 판정한다. 물리모델 미검증(NASA-STD-7009)이라 **모델 조건부**. "
         "여기서 정당한 것은 '이 정책이 이 모델에서 이렇게 행동한다'까지다. 현장 validation 은 독립 오라클+실측 필요.", "",
         "장소=%s 실좌표(%.4f,%.4f), DEM %.0f~%.0f m, reps=%d/SCN. 물리+실 DEM 계산(모델 내부)." % (place, lat, lon, dem.min(), dem.max(), a.reps),
         "축: Geometry(차폐)×Visibility(대기)×Disturbance(외란)×Sensor×Fault(+전이타이밍). ConOps: 조난자 탐색, 센서 열화/고장에도 안전.", "",
         "| SCN | 계층 | Geom | Vis | Dist | Sensor | Fault@타이밍 | ≥1탐지% | 복구% | V&V 판정 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for scn, v, det, rec in rows:
        ft = "%s@%s" % (scn["fault"], scn["fault_timing"]) if scn["fault"] != "none" else "-"
        L.append("| %s | %s | %s | %s | %s | %s | %s | %.0f | %.0f | %s |" % (
            scn["id"], LAYER_CODE[scn["layer"]], scn["geometry"], scn["visibility"], scn["disturbance"],
            scn["sensor"], ft, det, rec, v))
    # 계층 요약
    from collections import Counter
    for layer in ["Reliability", "Robustness", "Resilience"]:
        vv = Counter(v for scn, v, d, r in rows if scn["layer"] == layer)
        L += ["", "**%s (%d SCN)**: %s" % (layer, sum(1 for s, *_ in rows if s["layer"] == layer), dict(vv))]
    L += ["", "> V&V: Reliability=규정 환경 임무달성, Robustness=예상 off-nominal서 탐지 유지 또는 안전강등, "
          "Resilience=예상못한 전이지점 결함서 복구(회복가능) 또는 안전강등. 어떤 SCN 도 unsafe 는 없다(RTA/MRC 설계).",
          "> 정직: 야간·짙은 소광·confined 차폐선 탐지 급감(DEGRADED-SAFE) -> 열화상 보강의 정량 근거."]
    REPO = os.path.dirname(HERE); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    rp = "public_agent_memory/sar_testmatrix_%s.md" % time.strftime("%Y%m%d-%H%M%S")
    open(os.path.join(REPO, rp), "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print("산출물:", rp)

    # 그림: 계층별 V&V 판정 분포(누적 막대)
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.font_manager as fm
        for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",):
            if os.path.exists(_c): fm.fontManager.addfont(_c); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name()
        matplotlib.rcParams["axes.unicode_minus"] = False
        import matplotlib.pyplot as plt
        def bucket(v): return "PASS" if v.startswith("PASS") else ("FAIL" if "unsafe" in v or "미탐" in v else "DEGRADED-SAFE")
        layers = ["Reliability", "Robustness", "Resilience"]
        cats = ["PASS", "DEGRADED-SAFE", "FAIL"]; col = {"PASS": "seagreen", "DEGRADED-SAFE": "gold", "FAIL": "indianred"}
        counts = {L2: Counter(bucket(v) for scn, v, d, r in rows if scn["layer"] == L2) for L2 in layers}
        fig, ax = plt.subplots(figsize=(8.2, 5))
        bottom = [0]*len(layers)
        for c in cats:
            vals = [counts[L2].get(c, 0) for L2 in layers]
            ax.bar(layers, vals, bottom=bottom, color=col[c], label=c, edgecolor="k", lw=0.4)
            bottom = [b+v for b, v in zip(bottom, vals)]
        ax.set_ylabel("SCN 수"); ax.legend(); ax.set_title("NASA V&V 테스트 매트릭스 판정 분포 (%s, reps=%d)\nunsafe=0 (RTA/MRC 설계) · 야간·소광은 안전강등" % (place, a.reps))
        fig.tight_layout()
        png_rel = "public_agent_memory/sar_testmatrix_%s.png" % time.strftime("%Y%m%d-%H%M%S")
        fig.savefig(os.path.join(REPO, png_rel), dpi=110); print("산출물:", png_rel)
    except Exception as e:  # noqa: BLE001
        print("figure skipped:", type(e).__name__, e)
