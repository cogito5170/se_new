#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RGB+IMU baseline 능동탐색 + NHTSA fallback/최소위험(MRC). 물리로만 판단, 거짓 없는 로그.

NHTSA ADS: OEDR(물체·사건 탐지·대응) + fallback/minimal-risk condition. 즉 '센서가 무엇인가'
만큼 '센서가 충분한 정보를 못 줄 때 어떻게 행동하는가'가 안전의 핵심. 이 실험이 바로 그것을 잰다.

센서 baseline = **RGB(지각: 탐지+시각주행계) + IMU(관성항법: 시각 죽을 때 위치 유지, 드리프트)**.
모든 조건(정상/야간/안개/연기/화재/먼지/비/센서고장)은 sensors.py 의 물리로 계산된다 --
로그의 ρ_rgb·T·β·σ_p 는 전부 그 함수의 출력이지 지어낸 값이 아니다('센서 reliability' 먼저).

fallback 상태기계(계산된 물리값 -> 결정):
  IMU 고장           -> MRC: 상태추정 불가, 즉시 체공/착륙
  RGB 고장           -> 탐지 불가, IMU 추측항법으로 복귀(RTL)
  ρ_rgb ≥ 0.60       -> 정상 탐색. RGB 시각고정 -> IMU σ_p 재설정
  0.25 ≤ ρ_rgb <0.60 -> 저하: 감속·체공관측(더 오래 봄), IMU σ_p 서서히 성장
  ρ_rgb < 0.25       -> 정보부족: (안개면 고지대 상승해 역전층 탈출 시도) IMU 추측항법
                        σ_p ≥ σ_safe 되면 -> MRC: 위치 불확실, 복귀/체공
"""
import ctypes, os, math, sys, argparse, subprocess, random
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sensors, scenario, terrain

SIGMA_SAFE = 30.0     # 위치오차 임계[m] -- 넘으면 안전 항법 불가 -> MRC
DT_STEP = 20.0        # 스텝당 경과시간[s] (이동+체공) -- IMU 드리프트 시간축
RHO_OK, RHO_LOW = 0.60, 0.25

# ── C 정책 코어(ctypes). 없으면 빌드. ─────────────────────────────────────
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
def policy_next(bel, vx, vy):
    tx, ty = ctypes.c_float(), ctypes.c_float(); nl = ctypes.c_int()
    lib.sar_next(bel, ctypes.c_float(vx), ctypes.c_float(vy), ctypes.byref(tx), ctypes.byref(ty), ctypes.byref(nl))
    return tx.value, ty.value


def run(nl_text, seed=None, budget=45):
    rng = random.Random(seed)
    sc = scenario.parse(nl_text, rng)
    phys = sensors.sample_scenario(rng, sc["condition"])
    LAT, LON, RADIUS = sc["lat"], sc["lon"], 3000.0
    CELL_M = 2 * RADIUS / GW
    log = []
    def L(s): log.append(s)
    L("[시나리오] %s" % sc["nl"])
    L("[해석] 장소=%s(일대) -> 랜덤 실좌표 (%.5f, %.5f) | 조건=%s | 산불=%s | 조난자 %d명" %
      (sc["place"], LAT, LON, sc["condition"], "예" if sc["fire"] else "아니오", sc["n_surv"]))
    L("[센서] baseline = RGB(지각) + IMU(관성항법).  판단은 물리 reliability 로만.")
    # 실 지형
    dem, ext, meta = terrain.fetch_dem(LAT, LON, RADIUS, zoom=13)
    DH, DW = dem.shape
    def dem_cell(cx, cy):
        px = min(DW - 1, max(0, int(cx / GW * DW))); py = min(DH - 1, max(0, int(cy / GH * DH)))
        return float(dem[py, px])
    TER = np.array([[dem_cell(gx, gy) for gx in range(GW)] for gy in range(GH)])
    inv_h = float(np.percentile(dem, 40))     # 역전층 고도(안개 상한) = 지형 하위 40% 고도
    L("[지형] 실제 DEM 고도 %.0f~%.0f m (AWS Terrarium). 안개 역전층≈%.0f m" % (dem.min(), dem.max(), inv_h))
    if phys.get("고장"):
        L("[조건물리] %s | **%s 센서 고장**" % (phys["설명"], phys["고장"]))
    else:
        beta0 = sensors.beta_from_visibility(phys["V"])
        L("[조건물리] %s | 가시거리 V=%.0f m -> β=%.4f/m, 조도=%.3g lx, 글레어=%.2f" %
          (phys["설명"], phys["V"], beta0, phys["lux"], phys["glare"]))

    # 화점·조난자·prior 배치
    fire = (rng.uniform(GW * .35, GW * .65), rng.uniform(GH * .35, GH * .65)) if sc["fire"] else (GW / 2, GH / 2)
    survs = [(rng.uniform(4, GW - 4), rng.uniform(4, GH - 4)) for _ in range(sc["n_surv"])]
    bel = np.zeros(GW * GH, dtype=np.float32)
    for gy in range(GH):
        for gx in range(GW):
            d2 = (gx - fire[0]) ** 2 + (gy - fire[1]) ** 2
            bel[gy * GW + gx] = 0.0 if d2 < 9 else math.exp(-d2 / (2 * 10.0 ** 2)) + 0.05
    bel /= bel.sum()

    AGL = 120.0; veh = [2.0, 2.0]; t_since_fix = 0.0; confirmed = []; traj = []; states = []
    FOOT_M = 150.0                     # UAV 저고도 카메라의 물리 footprint 반경[m]
    R_SENSE = math.hypot(AGL, FOOT_M)  # 표적까지 대표 슬랜트 거리[m] = reliability 계산 거리(≈192m)
    home = (2.0, 2.0)

    def local_rgb(cx, cy):
        if phys["rgb_failed"]:
            return 0.0, dict(beta=float("nan"), T=0, rho_atmos=0, rho_illum=0, glare=0, failed=True)
        b = sensors.local_beta(sensors.beta_from_visibility(phys["V"]), dem_cell(cx, cy),
                               math.hypot(cx - fire[0], cy - fire[1]), sc["condition"], inv_h)
        rho, det = sensors.rgb_reliability(b, R_SENSE, phys["lux"], phys["glare"])
        det["beta"] = b
        return rho, det

    for step in range(budget):
        # IMU 고장: 상태추정 불가 -> 즉시 MRC
        if phys["imu_failed"]:
            L("[t=%02d] **IMU 고장 -> 상태추정 불가. MINIMAL-RISK: 즉시 제자리 체공/착륙**(NHTSA fallback). 탐색 중단."
              % step); states.append("MRC"); traj.append((veh[0], veh[1])); break
        tx, ty = policy_next(bel, veh[0], veh[1])       # 정책이 고른 다음 셀(의도)
        rho, det = local_rgb(tx, ty)
        sig = sensors.imu_sigma(t_since_fix)
        elev = dem_cell(tx, ty)
        # RGB 고장 -> 탐지 불가, IMU 로 복귀
        if phys["rgb_failed"]:
            state = "RTL"; veh = [veh[0] + (home[0]-veh[0])*.5, veh[1] + (home[1]-veh[1])*.5]
            t_since_fix += DT_STEP; sig = sensors.imu_sigma(t_since_fix)
            L("[t=%02d] **RGB 고장 -> 탐지 불가.** IMU 추측항법 복귀 중 (σ_p=%.1fm). 조난자 탐지는 불가."
              % (step, sig)); traj.append(tuple(veh)); states.append(state)
            if math.hypot(veh[0]-home[0], veh[1]-home[1]) < 1.5:
                L("[t=%02d] 복귀 완료. RGB 없는 baseline 은 탐지 임무 불가 -> 사람에게 이관." % step); break
            continue
        # 물리로 상태 결정
        detail = "대기%.2f·조도%.2f·글레어%.2f" % (det["rho_atmos"], det["rho_illum"], det["glare"])
        moved = True
        if rho >= RHO_OK:
            state = "정상"; t_since_fix = 0.0; sig = sensors.SIGMA_FIX      # RGB 시각고정 -> IMU 리셋
            veh = [tx, ty]
        elif rho >= RHO_LOW:
            state = "저하"; t_since_fix += DT_STEP * 0.5; sig = sensors.imu_sigma(t_since_fix)  # 약한 고정
            veh = [tx, ty]
        else:
            # 정보부족: 안개면 고지대 상승 시도(역전층 탈출), 아니면 추측항법
            t_since_fix += DT_STEP; sig = sensors.imu_sigma(t_since_fix)
            if sig >= SIGMA_SAFE:
                state = "MRC"; veh_home = home
                L("[t=%02d] cell(%.0f,%.0f) elev=%.0fm | cond=%s β=%.4f/m T@%.0fm=%.1e ρ_rgb=%.2f | "
                  "IMU σ_p=%.1fm ≥ 임계%.0fm -> **MINIMAL-RISK: 위치 불확실, 복귀/체공**(NHTSA fallback)"
                  % (step, tx, ty, elev, sc["condition"], det["beta"], R_SENSE, det["T"], rho, sig, SIGMA_SAFE))
                traj.append(tuple(veh)); states.append(state); break
            if sc["condition"] == "안개" and elev < inv_h:
                # 고지대 이웃 셀로(역전층 위로) -- 물리: 안개는 층운, 오르면 벗어난다
                best = None; bestz = elev
                for dx, dy in ((3,0),(0,3),(3,3),(-3,3),(0,4),(4,0)):
                    nx, ny = min(GW-1,max(0,veh[0]+dx)), min(GH-1,max(0,veh[1]+dy))
                    if dem_cell(nx, ny) > bestz: bestz = dem_cell(nx, ny); best = (nx, ny)
                if best:
                    veh = list(best); state = "정보부족→상승"
                    L("[t=%02d] cell(%.0f,%.0f) elev=%.0fm | 안개 β=%.4f/m ρ_rgb=%.2f(정보부족) | "
                      "**고지대 상승(elev %.0f→%.0fm) 역전층 탈출 시도**, IMU σ_p=%.1fm"
                      % (step, tx, ty, elev, det["beta"], rho, elev, bestz, sig))
                    traj.append(tuple(veh)); states.append(state); continue
            state = "정보부족→체공"; veh = [tx, ty]
        traj.append(tuple(veh)); states.append(state)
        # 탐지 (물리 reliability 로만): footprint 내 & 가시거리 내 & ρ 충분
        got = None
        for (sx, sy) in survs:
            r_cells = math.hypot(sx - veh[0], sy - veh[1])
            slant = math.hypot(r_cells * CELL_M, AGL)         # 표적까지 슬랜트 거리
            if (r_cells <= R_MAX) and (slant <= phys["V"]) and rho >= 0.5 \
               and all((sx-c[0])**2+(sy-c[1])**2 > 4 for c in confirmed) and rng.random() < rho:
                got = (sx, sy); break
        if got:
            confirmed.append(got)
            for gy in range(GH):
                for gx in range(GW):
                    bel[gy*GW+gx] *= (math.exp(-((gx-got[0])**2+(gy-got[1])**2)/(2*1.2**2)) + 0.02)
            la = LAT - (got[1]-GH/2)*CELL_M/111320.0; lo = LON + (got[0]-GW/2)*CELL_M/(111320.0*math.cos(math.radians(LAT)))
            L("[t=%02d] cell(%.0f,%.0f) elev=%.0fm | cond=%s β=%.4f/m T@%.0fm=%.2f ρ_rgb=%.2f(%s) σ_p=%.1fm | "
              "★탐지 조난자 @(%.5f,%.5f) [%s]" % (step, veh[0], veh[1], elev, sc["condition"], det["beta"],
              R_SENSE, det["T"], rho, detail, sig, la, lo, state))
        else:
            for gy in range(GH):
                for gx in range(GW):
                    if (gx-veh[0])**2+(gy-veh[1])**2 <= R_MAX**2:
                        bel[gy*GW+gx] *= (1 - 0.5*rho)      # 신뢰도만큼만 감쇠(못 본 곳은 덜 지운다)
            if "상승" not in state:
                L("[t=%02d] cell(%.0f,%.0f) elev=%.0fm | cond=%s β=%.4f/m T@%.0fm=%.1e ρ_rgb=%.2f(%s) σ_p=%.1fm | 상태=%s%s"
                  % (step, veh[0], veh[1], elev, sc["condition"], det["beta"], R_SENSE, det["T"], rho, detail, sig, state,
                     ", RGB 주행계 유효(시각고정)" if state=="정상" else ""))
        for (cx, cy) in confirmed:
            for gy in range(GH):
                for gx in range(GW):
                    if (gx-cx)**2+(gy-cy)**2 <= 4: bel[gy*GW+gx] *= 0.001
        bel /= bel.sum()
        if len(confirmed) >= len(survs):
            L("[t=%02d] 조난자 %d/%d 전원 확인 -- 임무 완료." % (step, len(confirmed), len(survs))); break

    # 요약
    from collections import Counter
    cnt = Counter(states)
    L("")
    L("[요약] 조건=%s | 조난자 %d/%d 확인 | %d 스텝 | 상태분포=%s" %
      (sc["condition"], len(confirmed), len(survs), len(traj), dict(cnt)))
    if phys.get("고장"):
        L("[판정] %s 고장 시나리오 -> baseline(RGB+IMU)의 fallback 이 %s 로 안전하게 이행(NHTSA MRC)."
          % (phys["고장"], "체공/착륙" if phys["고장"]=="IMU" else "IMU 복귀"))
    elif len(confirmed) == len(survs):
        L("[판정] %s 조건에서 RGB+IMU 만으로 탐색 성공. 물리 reliability 가 충분했다." % sc["condition"])
    else:
        L("[판정] %s 조건에서 센서 정보 부족으로 일부 미탐 -> fallback(추측항법/상승/MRC)으로 안전 유지."
          " 열화상 등 보조 센서가 있어야 이 조건서 탐지가 는다(정직한 baseline 한계)." % sc["condition"])
    return sc, phys, log, dict(dem=dem, traj=traj, states=states, survs=survs, fire=fire,
                               confirmed=confirmed, ext=ext, GW=GW, GH=GH)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nl", type=str, default="설악산 일대에서 산불 발생. 비가 오고 있는 상황이며 조난자 2명으로 추정된다. 주변 일대를 탐색하여라.")
    ap.add_argument("--seed", type=int, default=None)
    a, _ = ap.parse_known_args()
    _sc, _phys, _log, _viz = run(a.nl, a.seed)
    print("\n".join(_log))

    # 보고서(마크다운) -> public_agent_memory/ (봇 수신기가 첨부·PDF 화하는 경로)
    import time as _t
    REPO = os.path.dirname(HERE)
    mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    rel = "public_agent_memory/sar_scenario_%s.md" % _t.strftime("%Y%m%d-%H%M%S")
    body = ["# SAR 시나리오 판단 로그 (RGB+IMU baseline, 물리 reliability)", "",
            "> NHTSA ADS: OEDR + fallback/최소위험(MRC). 센서가 충분한 정보를 못 줄 때의 행동을 잰다.",
            "> 모든 수치(β·T·ρ_rgb·σ_p)는 sensors.py 물리의 출력이다 — 지어낸 값이 아니다.", "",
            "```"] + _log + ["```"]
    open(os.path.join(REPO, rel), "w").write("\n".join(body) + "\n")
    print("산출물:", rel)

    # 그림: 실지형 위 궤적을 시스템 상태 색으로 (정상/저하/정보부족/MRC)
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.font_manager as fm
        for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",):
            if os.path.exists(_c):
                fm.fontManager.addfont(_c); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name()
        matplotlib.rcParams["axes.unicode_minus"] = False
        import matplotlib.pyplot as plt
        from matplotlib.colors import LightSource
        dem = _viz["dem"]; DH, DW = dem.shape; GWv, GHv = _viz["GW"], _viz["GH"]
        COL = {"정상": "lime", "저하": "gold", "정보부족→상승": "orange", "정보부족→체공": "darkorange",
               "MRC": "red", "RTL": "red"}
        def cpx(c): return (c[0] / GWv * DW, c[1] / GHv * DH)
        ls = LightSource(315, 45)
        fig, ax = plt.subplots(figsize=(8.6, 7.4))
        ax.imshow(ls.shade(dem, cmap=plt.cm.terrain, blend_mode="soft", vert_exag=2.0))
        tp = [cpx(t) for t in _viz["traj"]]
        for i, (p, st) in enumerate(zip(tp, _viz["states"])):
            ax.plot(p[0], p[1], "o", ms=5, color=COL.get(st, "cyan"), mec="k", mew=0.3)
            if i: ax.plot([tp[i-1][0], p[0]], [tp[i-1][1], p[1]], "-", color="k", lw=0.4, alpha=0.4)
        for (sx, sy) in _viz["survs"]:
            p = cpx((sx, sy)); ok = any((sx-c[0])**2+(sy-c[1])**2 <= 4 for c in _viz["confirmed"])
            ax.plot(*p, "*", ms=16, color="white" if not ok else "cyan", mec="k")
        pf = cpx(_viz["fire"]); (ax.plot(*pf, "^", ms=13, color="red") if _sc["fire"] else None)
        ax.set_title("RGB+IMU 탐색 — 조건=%s | 상태색: 초록=정상·노랑=저하·주황=정보부족·빨강=MRC/RTL\n%s"
                     % (_sc["condition"], _sc["nl"][:46]), fontsize=9)
        ax.axis("off"); fig.tight_layout()
        out = os.path.join(HERE, "out"); os.makedirs(out, exist_ok=True)
        fig.savefig(os.path.join(out, "scenario_run.png"), dpi=110); plt.close(fig)
        print("saved:", os.path.join(out, "scenario_run.png"))
    except Exception as e:   # noqa: BLE001
        print("figure skipped:", type(e).__name__, e)
