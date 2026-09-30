#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""③ 실제 지형 위 3D 능동탐색 -- NL 시나리오("설악산 대청봉 주변 산불, 일대 탐색").

무엇이 진짜인가(정직):
  · 지형    = 실제 DEM (terrain.py, AWS Terrarium). 능선·계곡이 진짜다.
  · LOS 차폐 = DEM 위 실제 가시선 계산. 능선 뒤 생존자는 안 보인다 -> 재접근해야 한다.
  · 정책    = 논문의 policy_core.c (ctypes) 가 다음 관측 셀을 고른다.
  · 센서선택 = 지형 그림자(hillshade)로 illum 이 낮은 셀 -> EO 약함 -> 열화상. 창발.
  · RTA     = 고도 geofence(지형 위 AGL 유지) + 산불 코어 keep-out.
모델(실측 아님): 탐지 확률(설악산 실 항공영상 없음) -- 파이프라인은 (a) 데모의 실 탐지기와 동일.

출력: out/terrain_search_3d.png (3D 지형+궤적+센서), out/terrain_search_map.png (2D),
      out/decision_log.txt (매 스텝 판단 -- Discord 수신기가 게시할 내용).
"""
import ctypes, os, math, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.font_manager as fm
for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",):
    if os.path.exists(_c):
        fm.fontManager.addfont(_c); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from terrain import fetch_dem

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)

# ── 실제 정책 코어 (C, ctypes) ─────────────────────────────────────────────
lib = ctypes.CDLL(os.path.join(HERE, "libsarcore.so"))
f32 = np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags="C_CONTIGUOUS")
lib.sar_grid_w.restype = lib.sar_grid_h.restype = ctypes.c_int
lib.sar_set_rmax.argtypes = [ctypes.c_float]
lib.sar_next.argtypes = [f32, ctypes.c_float, ctypes.c_float,
                         ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_int)]
lib.sar_entropy.argtypes = [f32]; lib.sar_entropy.restype = ctypes.c_float
GW, GH = lib.sar_grid_w(), lib.sar_grid_h()
R_MAX = 3.0; lib.sar_set_rmax(ctypes.c_float(R_MAX))
def policy_next(bel, vx, vy):
    tx, ty = ctypes.c_float(), ctypes.c_float(); nl = ctypes.c_int()
    lib.sar_next(bel, ctypes.c_float(vx), ctypes.c_float(vy), ctypes.byref(tx), ctypes.byref(ty), ctypes.byref(nl))
    return tx.value, ty.value, nl.value

# ── 시나리오: CLI 인자(봇 !search 가 준다) 또는 기본(설악산 산불) ───────────
import argparse
_ap = argparse.ArgumentParser(description="실지형 3D 능동탐색 (SAR)")
_ap.add_argument("--lat", type=float, default=38.1194)
_ap.add_argument("--lon", type=float, default=128.4656)
_ap.add_argument("--radius", type=float, default=3000.0)
_ap.add_argument("--scenario", type=str, default="설악산 대청봉 주변 산불 발생 -> 일대 조난자 탐색")
_args, _ = _ap.parse_known_args()
SCEN = _args.scenario
LAT, LON, RADIUS = _args.lat, _args.lon, _args.radius
CELL_M = 2 * RADIUS / GW
print("[NL 명령] %s" % SCEN)
print("[좌표] (%.4f, %.4f) 반경 %.0fm  -> 격자 %dx%d, 셀 %.0fm" % (LAT, LON, RADIUS, GW, GH, CELL_M))
dem, ext, meta = fetch_dem(LAT, LON, RADIUS, zoom=13)
DH, DW = dem.shape
print("[지형] 실제 DEM %s 고도 %.0f~%.0f m (AWS Terrarium)" % (dem.shape, dem.min(), dem.max()))

def dem_at(cx, cy):                       # 격자셀 -> DEM 고도(쌍선형)
    px = min(DW - 1, max(0, cx / GW * DW)); py = min(DH - 1, max(0, cy / GH * DH))
    x0, y0 = int(px), int(py); x1, y1 = min(DW - 1, x0 + 1), min(DH - 1, y0 + 1)
    fx, fy = px - x0, py - y0
    return float((dem[y0, x0] * (1 - fx) + dem[y0, x1] * fx) * (1 - fy) +
                 (dem[y1, x0] * (1 - fx) + dem[y1, x1] * fx) * fy)

TER = np.array([[dem_at(gx, gy) for gx in range(GW)] for gy in range(GH)])  # 셀 고도

# ── 지형 그림자 -> illum (센서 선택 구동). 해 방위/고도로 hillshade ─────────
gy_, gx_ = np.gradient(dem.astype(float), 2 * RADIUS / DH, 2 * RADIUS / DW)  # m/픽셀(진짜 지상거리)
slope = np.arctan(np.hypot(gx_, gy_)); aspect = np.arctan2(-gx_, gy_)
SUN_AZ, SUN_ALT = math.radians(135), math.radians(45)   # 오후 해 -> 양지/음지 섞임(EO↔열 전환 보임)
zen = math.pi / 2 - SUN_ALT
hill = (np.cos(zen) * np.cos(slope) + np.sin(zen) * np.sin(slope) * np.cos(SUN_AZ - aspect))
hill = np.clip(hill, 0, 1)
def illum_at(cx, cy):
    px = min(DW - 1, int(cx / GW * DW)); py = min(DH - 1, int(cy / GH * DH))
    return float(hill[py, px])
ILL = np.array([[illum_at(gx, gy) for gx in range(GW)] for gy in range(GH)])

# ── LOS: UAV(고도 zuav) -> 지상셀. DEM 따라 능선이 광선 위로 솟으면 차폐 ────
def has_los(ux, uy, zuav, tx, ty, ztgt, n=24):
    for i in range(1, n):
        f = i / n
        cx = ux + (tx - ux) * f; cy = uy + (ty - uy) * f
        ray = zuav + (ztgt - zuav) * f
        if dem_at(cx, cy) > ray + 8.0:    # 8m 여유
            return False
    return True

# ── 센서 (EO / Thermal). p_useful: EO 는 illum 비례, 열화상은 illum 무관 ────
def p_useful(sensor, r_m, illum):
    # EO: 일광 충분하면 고해상으로 열화상보다 낫다. 그늘/저조도면 급락. Thermal: 조명 무관.
    if sensor == "EO":   return max(0.02, 0.95 * math.exp(-(r_m / 900.0) ** 2) * illum)
    else:                return max(0.02, 0.72 * math.exp(-(r_m / 1000.0) ** 2))   # Thermal
def pick_sensor(illum):
    return ("EO", "일광 충분") if p_useful("EO", 0, illum) >= p_useful("Thermal", 0, illum) else ("Thermal", "지형그림자/저조도")

# ── 시나리오 배치: 산불 코어(keep-out) + 조난자(일부 능선 뒤) ───────────────
rng = np.random.default_rng(7)
fire = (GW * 0.5, GH * 0.42)              # 산불 코어(중앙 근처)
KEEPOUT = 3.0                            # 산불 반경(셀) -- RTA 진입금지
# 조난자: 산불서 떨어진 곳, 일부는 능선 뒤(occlusion 유도)
survivors = [(GW*0.72, GH*0.30), (GW*0.28, GH*0.68), (GW*0.80, GH*0.75)]
# red spot(운용자 표시) = 산불 위치. 조난자는 불에서 '달아나' 일대에 흩어진다 ->
# prior 는 산불 주변으로 넓게(coverage 탐색), 산불 코어(keep-out)는 비운다.
bel = np.zeros(GW * GH, dtype=np.float32)
for gy in range(GH):
    for gx in range(GW):
        d2 = (gx - fire[0]) ** 2 + (gy - fire[1]) ** 2
        if d2 < KEEPOUT ** 2:
            bel[gy * GW + gx] = 0.0                        # 불 속엔 조난자 없다
        else:
            bel[gy * GW + gx] = math.exp(-d2 / (2 * 10.0 ** 2)) + 0.05   # 넓은 사전 + floor
bel /= bel.sum()

AGL = 120.0                              # UAV 지형위 고도[m] (min AGL 안전)
ALT_MAX = dem.max() + 250.0              # 공역 상한
VEH = [2.0, 2.0]; traj = []; confirmed = []; log = []
def L(s): log.append(s); print(s)
L("[이륙] UAV @ 격자(%.0f,%.0f), 목표: %s" % (VEH[0], VEH[1], SCEN))
L("[안전] RTA: 산불 keep-out r=%.0f셀, 고도 AGL=%.0fm 유지, 공역상한 %.0fm" % (KEEPOUT, AGL, ALT_MAX))

BUDGET = 55
for step in range(BUDGET):
    tx, ty, nl = policy_next(bel, VEH[0], VEH[1])
    # RTA(1): 산불 코어 침범 목표는 가장 가까운 안전 셀로 대체
    rta = ""
    if (tx - fire[0]) ** 2 + (ty - fire[1]) ** 2 < KEEPOUT ** 2:
        ang = math.atan2(ty - fire[0], tx - fire[1])
        tx = fire[0] + math.cos(ang) * (KEEPOUT + 0.5); ty = fire[1] + math.sin(ang) * (KEEPOUT + 0.5)
        rta = " [RTA:산불 keep-out 회피]"
    tx = min(GW - 1, max(0, tx)); ty = min(GH - 1, max(0, ty))
    VEH = [tx, ty]
    zt = dem_at(tx, ty); zuav = min(ALT_MAX, zt + AGL)   # RTA(2): 고도 geofence
    traj.append((tx, ty, zuav))
    illum = illum_at(tx, ty); sensor, why = pick_sensor(illum)
    # 관측: footprint 내 LOS 있는 셀만. 조난자 탐지?
    seen = []; hit = None
    for (sx, sy) in survivors:
        r_cells = math.hypot(sx - tx, sy - ty)
        if r_cells <= R_MAX:
            los = has_los(tx, ty, zuav, sx, sy, dem_at(sx, sy))
            if not los:
                L("[step %2d] (%.0f,%.0f) z=%.0fm 센서=%s(%s) | 조난자 후보 능선 뒤 차폐 -> 관측불가, 재접근 필요%s"
                  % (step, tx, ty, zuav, sensor, why, rta)); continue
            pu = p_useful(sensor, r_cells * CELL_M, illum)
            det = rng.random() < pu
            seen.append((sx, sy))
            if det and all((sx - c[0]) ** 2 + (sy - c[1]) ** 2 > 4 for c in confirmed):
                hit = (sx, sy, pu)
    if hit is not None:
        sx, sy, pu = hit; confirmed.append((sx, sy))
        # belief 갱신(탐지): 측정 근처 blob (LOS-aware; pc_belief_update 우도 형태)
        for gy in range(GH):
            for gx in range(GW):
                d2 = (gx - sx) ** 2 + (gy - sy) ** 2
                bel[gy * GW + gx] *= (math.exp(-d2 / (2 * 1.2 ** 2)) + 0.02)
        la = LAT - (sy - GH / 2) * CELL_M / 111320.0; lo = LON + (sx - GW / 2) * CELL_M / (111320.0 * math.cos(math.radians(LAT)))
        L("[step %2d] (%.0f,%.0f) z=%.0fm 센서=%s(%s) | ★탐지 조난자 @(%.5f,%.5f) conf=%.2f%s"
          % (step, tx, ty, zuav, sensor, why, la, lo, pu, rta))
    else:
        # 미탐: 관측한(LOS 있는) footprint 셀만 감쇠 -- 능선 뒤는 안 건드림(지형 인지 belief)
        for gy in range(GH):
            for gx in range(GW):
                if (gx - tx) ** 2 + (gy - ty) ** 2 <= R_MAX ** 2 and has_los(tx, ty, zuav, gx, gy, dem_at(gx, gy)):
                    bel[gy * GW + gx] *= (1 - 0.7 * p_useful(sensor, math.hypot(gx - tx, gy - ty) * CELL_M, illum))
        if not any("차폐" in s for s in log[-1:]):
            L("[step %2d] (%.0f,%.0f) z=%.0fm 센서=%s(%s) | 미탐, footprint 감쇠%s" % (step, tx, ty, zuav, sensor, why, rta))
    # 찾은 조난자 억제 -> 다표적 탐색 계속
    for (cx, cy) in confirmed:
        for gy in range(GH):
            for gx in range(GW):
                if (gx - cx) ** 2 + (gy - cy) ** 2 <= 4: bel[gy * GW + gx] *= 0.001
    bel /= bel.sum()
    if len(confirmed) >= len(survivors):
        L("[임무완료] 조난자 %d명 전원 확인 (step %d)" % (len(confirmed), step)); break
L("[요약] 확인 %d/%d, 스텝 %d, 엔트로피 %.2f" % (len(confirmed), len(survivors), len(traj), lib.sar_entropy(bel)))

open(os.path.join(OUT, "decision_log.txt"), "w").write("\n".join(log) + "\n")
print("saved:", os.path.join(OUT, "decision_log.txt"))

# ── 렌더 ───────────────────────────────────────────────────────────────────
def cellpx(cx, cy): return (cx / GW * DW, cy / GH * DH)
ls = LightSource(azdeg=math.degrees(SUN_AZ), altdeg=math.degrees(SUN_ALT))
# 2D 지도
fig, ax = plt.subplots(figsize=(8.5, 7))
ax.imshow(ls.shade(dem, cmap=plt.cm.terrain, blend_mode="soft", vert_exag=2.0))
tp = np.array([cellpx(t[0], t[1]) for t in traj])
seg_col = ["gold" if pick_sensor(illum_at(t[0], t[1]))[0] == "EO" else "deepskyblue" for t in traj]
for i in range(len(tp) - 1):
    ax.plot(tp[i:i+2, 0], tp[i:i+2, 1], "-", color=seg_col[i], lw=2)
ax.scatter(tp[:, 0], tp[:, 1], c=seg_col, s=14, zorder=3, edgecolors="k", linewidths=0.3)
fp = cellpx(*fire); ax.add_patch(plt.Circle(fp, KEEPOUT / GW * DW, color="red", alpha=0.25))
ax.plot(*fp, "^", color="red", ms=13); ax.annotate("산불(keep-out)", fp, color="red", fontsize=9)
for (sx, sy) in survivors:
    p = cellpx(sx, sy); ok = any((sx-c[0])**2+(sy-c[1])**2<=4 for c in confirmed)
    ax.plot(*p, "*", color="lime" if ok else "white", ms=16, mec="k")
ax.plot(*cellpx(*traj[0][:2]) if traj else cellpx(2,2), "s", color="yellow", ms=9)
ax.set_title("실제 지형 탐색 (금=EO · 하늘=열화상 | ★=조난자 초록=확인)\n%s" % SCEN, fontsize=10)
ax.axis("off"); fig.tight_layout(); fig.savefig(os.path.join(OUT, "terrain_search_map.png"), dpi=110); plt.close(fig)
print("saved:", os.path.join(OUT, "terrain_search_map.png"))
# 3D
fig = plt.figure(figsize=(11, 7)); ax = fig.add_subplot(111, projection="3d")
st = max(1, DH // 130); Z = dem[::st, ::st]; X, Y = np.meshgrid(np.arange(Z.shape[1]), np.arange(Z.shape[0]))
ax.plot_surface(X, Y, Z, cmap="terrain", alpha=0.82, linewidth=0, antialiased=True)
sx3 = tp[:, 0] / DW * Z.shape[1]; sy3 = tp[:, 1] / DH * Z.shape[0]; zz = [t[2] for t in traj]
for i in range(len(sx3) - 1):
    ax.plot(sx3[i:i+2], sy3[i:i+2], zz[i:i+2], color=seg_col[i], lw=2.5)
for (sx, sy) in survivors:
    p = cellpx(sx, sy); ax.scatter(p[0]/DW*Z.shape[1], p[1]/DH*Z.shape[0], dem_at(sx, sy)+30,
                                   c="lime", s=80, marker="*", edgecolors="k")
pf = cellpx(*fire); ax.scatter(pf[0]/DW*Z.shape[1], pf[1]/DH*Z.shape[0], dem_at(*fire)+40, c="red", s=90, marker="^")
ax.set_title("3D 실지형 비행 (설악산, 고도 %.0f~%.0fm) — UAV AGL 유지, 능선 LOS 차폐 반영" % (dem.min(), dem.max()), fontsize=10)
ax.view_init(elev=52, azim=-58); fig.tight_layout(); fig.savefig(os.path.join(OUT, "terrain_search_3d.png"), dpi=110); plt.close(fig)
print("saved:", os.path.join(OUT, "terrain_search_3d.png"))

# ── 임무 보고서(마크다운) -> public_agent_memory/ (봇 수신기가 첨부·PDF 화하는 경로) ──
import time as _t
REPO = os.path.dirname(HERE)
mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
ts = _t.strftime("%Y%m%d-%H%M%S")
rel = "public_agent_memory/sar_mission_%s.md" % ts
sensors = {}
for s in log:
    if "센서=EO" in s: sensors["EO"] = sensors.get("EO", 0) + 1
    elif "센서=Thermal" in s: sensors["Thermal"] = sensors.get("Thermal", 0) + 1
rep = ["# SAR 임무 보고 — %s" % SCEN, "",
       "- **좌표**: (%.4f, %.4f) 반경 %.0f m | 격자 %dx%d, 셀 %.0f m" % (LAT, LON, RADIUS, GW, GH, CELL_M),
       "- **지형**: 실제 DEM 고도 %.0f~%.0f m (AWS Terrarium)" % (dem.min(), dem.max()),
       "- **결과**: 조난자 %d/%d 확인, %d 스텝" % (len(confirmed), len(survivors), len(traj)),
       "- **센서 사용**: EO %d · Thermal %d (지형 그림자로 창발 전환)" % (sensors.get("EO", 0), sensors.get("Thermal", 0)),
       "- **안전**: 산불 keep-out 회피 + 고도 geofence(AGL) 유지", "",
       "## 확인된 조난자 (georef)"]
for (cx, cy) in confirmed:
    la = LAT - (cy - GH / 2) * CELL_M / 111320.0
    lo = LON + (cx - GW / 2) * CELL_M / (111320.0 * math.cos(math.radians(LAT)))
    rep.append("- @ (%.5f, %.5f)  격자셀 (%.0f, %.0f)" % (la, lo, cx, cy))
rep += ["", "## 판단 로그 (매 스텝)", "```"] + log + ["```", "",
        "그림: `sar/out/terrain_search_map.png`, `sar/out/terrain_search_3d.png` (저장소)",
        "", "> 정직: 지형·LOS·정책코어는 실제, 탐지확률은 모델(실 항공영상 없음). 실기는 항공+열화상+SAR학습 탐지기."]
open(os.path.join(REPO, rel), "w").write("\n".join(rep) + "\n")
print("산출물:", rel)   # 봇의 산출물찾기(public_agent_memory/*.md)가 이 경로를 붙인다
