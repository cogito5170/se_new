#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실시간 지휘 화면(재생) — 지휘자가 1~3초에 판단하게. raw 가 아니라 '상황정보'.

설계 우선순위(사용자): ① top-down 커버리지 지도(어디 봤나/현재/다음) ② RGB 검출 오버레이
(거리·방위·신뢰도) ③ 3D 고도 ④ 미션 상태(탐색/커버리지%/표적/위험/통신) ⑤ 이벤트+SAR 무전.
raw IMU 숫자 대신 자세계·플래그(GPS 불확실↑)로 '상황화'. 물리는 sensors.py, 보고는 report.py.

실시간 = "지금 무슨 일?"  vs  사후보고 = "무슨 일이 있었고 정책이 왜 반응했고 복구했나"(시간축) -- 분리.
"""
import ctypes, os, math, subprocess, random, argparse
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); import sys; sys.path.insert(0, HERE)
import sensors, terrain, fault_mgmt, report, scenario, camera, radar
import scene as scene_mod
import landcover as landcover_mod
import matplotlib; matplotlib.use("Agg")
import matplotlib.font_manager as fm
for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",):
    if os.path.exists(_c): fm.fontManager.addfont(_c); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.colors import LightSource
from matplotlib.patches import Rectangle, Circle, FancyArrow

_so = os.path.join(HERE, "libsarcore.so")
if not os.path.exists(_so):
    subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-I"+os.path.join(HERE, "..", "policy_core"),
                    "-o", _so, os.path.join(HERE, "sar_core.c"), os.path.join(HERE, "..", "policy_core", "policy_core.c"), "-lm"], check=True)
lib = ctypes.CDLL(_so)
f32 = np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags="C_CONTIGUOUS")
lib.sar_grid_w.restype = lib.sar_grid_h.restype = ctypes.c_int
lib.sar_set_rmax.argtypes = [ctypes.c_float]
lib.sar_next.argtypes = [f32, ctypes.c_float, ctypes.c_float, ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_int)]
GW, GH = lib.sar_grid_w(), lib.sar_grid_h(); lib.sar_set_rmax(ctypes.c_float(3.0))
R_SENSE = math.hypot(120.0, 150.0)
CELL_M = 2*3000.0/GW


def _sector(cx, cy): return "%s-%d" % ("ABCDEF"[min(5, int(cx/GW*6))], min(6, int(cy/GH*6))+1)


def simulate(nl, seed=None, budget=48):
    rng = random.Random(seed); sc = scenario.parse(nl, rng); phys = sensors.sample_scenario(rng, sc["condition"])
    LAT, LON = sc["lat"], sc["lon"]; cond = sc["condition"]
    dem, ext, meta = terrain.fetch_dem(LAT, LON, 3000.0, zoom=13); DH, DW = dem.shape
    inv_h = float(np.percentile(dem, 40))
    def dcell(cx, cy): return float(dem[min(DH-1, max(0, int(cy/GH*DH))), min(DW-1, max(0, int(cx/GW*DW)))])
    fire = (rng.uniform(GW*.4, GW*.6), rng.uniform(GH*.4, GH*.6)) if sc["fire"] else (GW/2, GH/2)
    survs = [(rng.uniform(4, GW-4), rng.uniform(4, GH-4)) for _ in range(sc["n_surv"])]
    bel = np.zeros(GW*GH, dtype=np.float32)
    for gy in range(GH):
        for gx in range(GW):
            d2 = (gx-fire[0])**2+(gy-fire[1])**2; bel[gy*GW+gx] = 0.0 if d2 < 9 else math.exp(-d2/(2*10.0**2))+0.05
    bel /= bel.sum()
    covered = np.zeros((GH, GW), dtype=bool)
    veh = [2.0, 2.0]; prev = [2.0, 2.0]; heading = 0.0; tsf = 0.0; confirmed = []; frames = []; radio = []
    bb = sensors.beta_from_visibility(phys["V"])          # 대기 소광계수(카메라 haze·SAR 무관)
    radio.append(report.radio(report.on_start("탐색구역 (%.4f,%.4f)" % (LAT, LON), sc["nl"][:26])))
    def pnext(vx, vy, b=None):
        if b is None: b = bel
        tx, ty = ctypes.c_float(), ctypes.c_float(); nn = ctypes.c_int()
        lib.sar_next(b, ctypes.c_float(vx), ctypes.c_float(vy), ctypes.byref(tx), ctypes.byref(ty), ctypes.byref(nn)); return tx.value, ty.value
    for step in range(budget):
        event = None
        # 덜 greedy: 항법 belief 에 **미탐색 커버리지 보너스**를 섞어 능선 너머·구석까지 쓴다
        # (탐지 belief 는 그대로 두고 이동 목표만 탐사쪽으로 — 순수 탐욕은 봉우리만 찍고 끝난다)
        uncov = 1.0 - covered.astype(np.float32)
        navb = bel + 0.7 * (uncov.reshape(-1) / (uncov.sum() + 1e-6))
        navb = np.ascontiguousarray(navb / (navb.sum() + 1e-9), dtype=np.float32)
        if phys["imu_failed"]:
            radio.append(report.radio(report.on_mrc("IMU 소실")))
            frames.append(dict(veh=veh[:], heading=heading, cov=covered.copy(), sig=99, rho=0, state="MRC",
                               cond=cond, elev=dcell(*veh), det=None, radio=radio[-2:], event="IMU 고장", fire=fire, found=len(confirmed), beta=bb)); break
        tx, ty = pnext(veh[0], veh[1], navb)
        if phys["rgb_failed"]:
            r, det = 0.0, dict(beta=float("nan"), T=0, rho_atmos=0, rho_illum=0, glare=0)
        else:
            b = sensors.local_beta(sensors.beta_from_visibility(phys["V"]), dcell(tx, ty), math.hypot(tx-fire[0], ty-fire[1]), cond, inv_h)
            r, det = sensors.rgb_reliability(b, R_SENSE, phys["lux"], phys["glare"]); det["beta"] = b
        sig = sensors.imu_sigma(tsf); fmr = fault_mgmt.diagnose(r, det, sig, phys["rgb_failed"], phys["imu_failed"], R_SENSE)
        if not fmr["detect"]:
            state = "SEARCHING"; tsf = 0.0; prev = veh[:]; veh = [tx, ty]
        elif fmr["identify"] == "noncap-hw":
            state = "RTL"; prev = veh[:]; veh = [veh[0]*.6, veh[1]*.6]; tsf += 20; event = "RGB 고장→복귀"
            radio.append(report.radio(report.on_fault("RGB 소실", "IMU 추측항법 복귀")))
        elif fmr["identify"] in ("critical-hw", "nav-uncertain"):
            state = "MRC"; event = "위치 불확실→최소위험"; radio.append(report.radio(report.on_mrc(fmr["diagnose"][:18])))
            frames.append(dict(veh=veh[:], heading=heading, cov=covered.copy(), sig=sig, rho=r, state=state,
                               cond=cond, elev=dcell(*veh), det=None, radio=radio[-2:], event=event, fire=fire, found=len(confirmed), beta=bb)); break
        else:
            tsf += 20*(0.5 if r >= fault_mgmt.RHO_LOW else 1.0)
            if cond == "안개" and dcell(tx, ty) < inv_h:
                best = None; bz = dcell(veh[0], veh[1])
                for dx, dy in ((3,0),(0,3),(4,0),(0,4)):
                    nx, ny = min(GW-1, max(0, veh[0]+dx)), min(GH-1, max(0, veh[1]+dy))
                    if dcell(nx, ny) > bz: bz = dcell(nx, ny); best = (nx, ny)
                prev = veh[:]; veh = list(best) if best else [tx, ty]; state = "RECOVER↑"; event = "안개-역전층 상승"
            else:
                prev = veh[:]; veh = [tx, ty]; state = "DEGRADED" if r >= fault_mgmt.RHO_LOW else "LOW-INFO"
        if abs(veh[0]-prev[0]) + abs(veh[1]-prev[1]) > 0.1: heading = math.degrees(math.atan2(veh[1]-prev[1], veh[0]-prev[0]))
        # 커버리지: footprint 내 & 신뢰도 충분 셀을 '봤다'
        if r >= 0.4:
            for gy in range(GH):
                for gx in range(GW):
                    if (gx-veh[0])**2+(gy-veh[1])**2 <= 9: covered[gy, gx] = True
        # ── 상세 무전: 상태 전이·주기 보고 (야전 무전처럼 자주·구체적으로) ──
        covpct_now = 100.0 * covered.sum() / (GW * GH)
        sar_hits_now = sum(1 for (sx, sy) in survs
                           if math.hypot(sx-veh[0], sy-veh[1]) <= 3.2 and all((sx-c[0])**2+(sy-c[1])**2 > 4 for c in confirmed))
        vis_txt = "양호" if r >= 0.6 else ("저하" if r >= 0.25 else "불량")
        if state in ("DEGRADED", "LOW-INFO"):
            radio.append(report.radio(report.on_verify(_sector(*veh), r)))
        elif state == "RECOVER↑":
            radio.append(report.radio(report.on_replan("안개 역전층 회피 상승")))
        elif step % 5 == 0:
            radio.append(report.radio(report.on_coverage(covpct_now, len(confirmed), len(survs)) if step % 10 == 0
                                       else report.on_sensor(vis_txt, sig, sar_hits_now)))
        elif step % 4 == 2:
            radio.append(report.radio(report.on_waypoint(_sector(*veh), dcell(*veh), covpct_now)))
        # 탐지
        detrec = None
        for (sx, sy) in survs:
            rc = math.hypot(sx-veh[0], sy-veh[1]); slant = math.hypot(rc*CELL_M, 120.0)
            if rc <= 3.0 and slant <= phys["V"] and r >= 0.5 and all((sx-c[0])**2+(sy-c[1])**2 > 4 for c in confirmed) and rng.random() < r:
                confirmed.append((sx, sy))
                brg = (math.degrees(math.atan2(sy-veh[1], sx-veh[0])) - heading + 540) % 360 - 180
                la = LAT-(sy-GH/2)*CELL_M/111320.0; lo = LON+(sx-GW/2)*CELL_M/(111320.0*math.cos(math.radians(LAT)))
                detrec = dict(sx=sx, sy=sy, dist=slant, bearing=brg, conf=r, sector=_sector(sx, sy), latlon="%.5f,%.5f" % (la, lo))
                event = "표적 발견"; radio.append(report.radio(report.on_detect(detrec["latlon"], detrec["sector"])))
                for gy in range(GH):
                    for gx in range(GW): bel[gy*GW+gx] *= (math.exp(-((gx-sx)**2+(gy-sy)**2)/(2*1.2**2))+0.02)
                break
        else:
            for gy in range(GH):
                for gx in range(GW):
                    if (gx-veh[0])**2+(gy-veh[1])**2 <= 9: bel[gy*GW+gx] *= (1-0.5*r)
        for (cx, cy) in confirmed:
            for gy in range(GH):
                for gx in range(GW):
                    if (gx-cx)**2+(gy-cy)**2 <= 4: bel[gy*GW+gx] *= 0.001
        ssum = bel.sum(); bel /= (ssum if ssum > 0 else 1)
        frames.append(dict(veh=veh[:], heading=heading, cov=covered.copy(), sig=sig, rho=r, state=state,
                           cond=cond, elev=dcell(*veh), det=detrec, radio=radio[-2:], event=event, fire=fire, found=len(confirmed), beta=bb))
        if len(confirmed) >= len(survs):
            radio.append("탐색 완료. 조난자 %d명 전원 확인. 이상." % len(confirmed)); break
    return dict(sc=sc, phys=phys, dem=dem, DH=DH, DW=DW, fire=fire, survs=survs, frames=frames, confirmed=confirmed, LAT=LAT, LON=LON, radio=radio)


MPP_PATCH = 6000.0                                    # DEM 패치 한 변(2·RADIUS) [m]
AGL = 90.0                                            # 지형 위 비행고도 [m]


def _world(c):                                        # 격자(0..GW) → 지상 미터
    return (c[0] / GW * MPP_PATCH, c[1] / GH * MPP_PATCH)


def render_gif(V, path, fps=2, on_frame=None):
    dem, DH, DW, sc = V["dem"], V["DH"], V["DW"], V["sc"]; frames = V["frames"]
    ls = LightSource(315, 45); hs = ls.hillshade(dem, vert_exag=2.0)
    mpp = MPP_PATCH / DW
    survivors_world = [_world(s) for s in V["survs"]]
    cfg = radar.RadarCfg()
    # 하나의 scene DB — RGB(camera)·SAR(radar)가 **같은 피처**를 각자 view 로 본다.
    # land-cover 는 실 ESA WorldCover(무키 COG) 를 받고, 못 받으면 고도규칙 폴백(source 로 명시).
    lc_grid, lc_source = landcover_mod.landcover_grid(V["LAT"], V["LON"], MPP_PATCH / 2, dem.shape, dem=dem, mpp=mpp)
    sdb = scene_mod.SceneDB(dem, mpp, seed=int(abs(V["LAT"]) * 1000) ^ int(abs(V["LON"]) * 1000), landcover=lc_grid)
    sdb.generate()
    lc_tag = "ESA WorldCover(실측)" if lc_source == "esa_worldcover" else "고도근사(폴백)"
    _hf = camera._terrain_sampler(dem, mpp)                     # SAR 클러터를 실 지형에서 뽑는다
    def _backscatter(xs, ys):                                   # 지형 구조 × land-cover 변조
        xs = np.asarray(xs); ys = np.asarray(ys)
        grad = np.abs(_hf(xs + mpp, ys) - _hf(xs, ys)) + np.abs(_hf(xs, ys + mpp) - _hf(xs, ys))
        gsc = sdb.ground_scatter(xs, ys)                        # land-cover 지면 산란(물=경면 약, 암반=강)
        return (0.3 + grad) * (0.15 + gsc)                      # 능선 밝게 + 물/평활면 어둡게
    def cpx(c): return (c[0]/GW*DW, c[1]/GH*DH)
    fig = plt.figure(figsize=(13.5, 7.8)); gs = fig.add_gridspec(3, 3, height_ratios=[1, 1, 1])
    axm = fig.add_subplot(gs[:, 0:2])          # ① top-down 지도(최우선, 크게)
    axc = fig.add_subplot(gs[0, 2])            # ② RGB 카메라 실제 시야(FPV)
    axr = fig.add_subplot(gs[1, 2])            # ③ SAR 레이더 영상
    axs = fig.add_subplot(gs[2, 2]); axs.axis("off")  # ④⑤ 상태+무전
    NF = len(frames)

    def draw(i):
        fr = frames[i]
        for a in (axm, axc, axr): a.clear()
        axs.clear(); axs.axis("off")
        vw = _world(fr["veh"]); hd = fr["heading"]; hdr = math.radians(hd)
        # ── ① TOP-DOWN 지도 ──
        axm.imshow(hs, cmap="gray", alpha=0.9)
        cov = np.zeros((*hs.shape, 4)); c = fr["cov"]
        covbig = np.kron(c, np.ones((DH//GH+1, DW//GW+1)))[:hs.shape[0], :hs.shape[1]]
        cov[covbig > 0] = (0.1, 0.8, 0.3, 0.28)
        axm.imshow(cov)
        tp = [cpx(f["veh"]) for f in frames[:i+1]]
        axm.plot([p[0] for p in tp], [p[1] for p in tp], "-", color="cyan", lw=1.6, alpha=0.9)
        ux, uy = cpx(fr["veh"])
        axm.add_patch(FancyArrow(ux, uy, math.cos(hdr)*DW*0.05, math.sin(hdr)*DH*0.05, width=DW*0.006, color="red", zorder=6))
        axm.plot(ux, uy, "o", color="red", ms=9, zorder=6)
        if sc["fire"]:
            fp = cpx(fr["fire"]); axm.add_patch(Circle(fp, DW*0.11, color="red", alpha=0.18)); axm.plot(*fp, "^", color="red", ms=12)
        for (sx, sy) in V["survs"]:
            p = cpx((sx, sy)); okd = any((sx-c2[0])**2+(sy-c2[1])**2 <= 4 for c2 in V["confirmed"])
            axm.plot(*p, "*", ms=17, color="lime" if okd else "white", mec="k", zorder=5)
        covpct = 100.0*fr["cov"].sum()/(GW*GH)
        axm.set_title("TOP-DOWN — 초록=탐색완료(%.0f%%) · 빨강점=UAV(화살표=방위) · 별=표적 · 삼각=화재" % covpct, fontsize=9)
        axm.set_xlim(0, DW); axm.set_ylim(DH, 0); axm.axis("off")
        # ── ② RGB 카메라 실제 시야(FPV): 실 DEM 원근투영 + 물리 haze + 조난자 반점 ──
        img = camera.render(dem, mpp, vw, AGL, hd, fr["beta"], survivor_xy=survivors_world,
                            rho=fr["rho"], W=176, H=104, scene=sdb)
        axc.imshow(img); axc.axis("off")
        if fr["det"] is not None:
            d = fr["det"]
            axc.text(0.03, 0.10, "PERSON %.0f%%  %.0fm %+.0f°" % (d["conf"]*100, d["dist"], d["bearing"]),
                     transform=axc.transAxes, color="lime", fontsize=7.5, weight="bold")
        vis = "GOOD" if fr["rho"] >= .6 else ("DEGRADED" if fr["rho"] >= .25 else "POOR")
        axc.set_title("RGB CAM 실시야(FPV) 가시도:%s ρ=%.2f" % (vis, fr["rho"]), fontsize=9)
        # ── ③ SAR 레이더 영상: raw 합성 → 백프로젝션 (안개 뚫는 측방 SAR) ──
        # 스와스 중심 = 사거리 안 가장 가까운 조난자(측방기하) 아니면 전방 80 m
        best = None; bestd = 1e9
        for (sw, s2) in zip(survivors_world, V["survs"]):
            d2 = math.hypot(sw[0]-vw[0], sw[1]-vw[1])
            if 60 <= d2 <= 400 and d2 < bestd: bestd = d2; best = sw
        scene = np.array(best) if best is not None else np.array([vw[0]+math.cos(hdr)*80, vw[1]+math.sin(hdr)*80])
        scat, rcs, hits = radar.scene_from_terrain(scene, 60.0, survivors_world, n_clutter=256,
                                                   rng=np.random.default_rng(1000+i), rcs_fn=_backscatter, scene=sdb)
        img_db, ext, meta = radar.sar_image(cfg, scat, rcs, np.array(vw), scene, hd, AGL, half=60.0, npx=72)
        axr.imshow(img_db, extent=ext, cmap="gist_heat", vmin=-20, vmax=0, origin="lower", aspect="auto")
        if hits:
            axr.plot(scene[0], scene[1], "s", mfc="none", mec="cyan", ms=15, mew=1.6)
            axr.text(scene[0], scene[1]+9, "TGT", color="cyan", fontsize=8, weight="bold", ha="center")
            axr.text(0.03, 0.06, "표적 반사 %d (안개 관통)" % hits, transform=axr.transAxes, color="cyan", fontsize=7.5, weight="bold")
        axr.set_title("SAR X-대역 FMCW %.0fGHz  δr=%.1fm δa=%.1fm" %
                      (cfg.fc/1e9, cfg.range_res, meta["az_res_m"]), fontsize=8)
        axr.set_xticks([]); axr.set_yticks([])
        # ── ④⑤ 상태 + 무전 (상황정보, raw 아님) ──
        colmap = {"SEARCHING": "green", "DEGRADED": "orange", "LOW-INFO": "darkorange", "RECOVER↑": "royalblue", "RTL": "red", "MRC": "red"}
        st = fr["state"]; axs.text(0, 1.0, "STATUS: %s" % st, color=colmap.get(st, "gray"), fontsize=12, weight="bold", va="top")
        gps = "불확실↑" if fr["sig"] >= 15 else "정상"
        haz = "HIGH" if (sc["fire"] and math.hypot(fr["veh"][0]-fr["fire"][0], fr["veh"][1]-fr["fire"][1]) < 4) else "LOW"
        axs.text(0, 0.86, "커버리지 %.0f%%  표적 %d/%d  위험 %s" % (100.0*fr["cov"].sum()/(GW*GH), fr["found"], len(V["survs"]), haz), fontsize=9, va="top")
        axs.text(0, 0.75, "IMU %s  GPS %s  통신 GOOD  방위 %03d°  고도 %.0fm" % ("정상" if fr["sig"] < 99 else "고장", gps, int(hd) % 360, AGL), fontsize=8.5, va="top")
        axs.text(0, 0.64, "SAR 레이더: 안개 무관(전천후) · 표적반사 %d" % hits, fontsize=8.5, color="saddlebrown", va="top")
        axs.text(0, 0.58, "지표피복: %s" % lc_tag, fontsize=7.5, color="darkgreen", va="top")
        if fr["event"]:
            axs.text(0, 0.52, "[!] %s" % fr["event"], color="crimson", fontsize=10, weight="bold", va="top")
        axs.text(0, 0.40, "─ SAR 무전 ─", fontsize=8.5, color="navy", va="top")
        for k, msg in enumerate(fr["radio"]):
            axs.text(0, 0.32-k*0.15, "> " + msg[:72], fontsize=6.6, va="top")
        return []

    fig.suptitle("UAV-01  SAR MISSION  |  %s  조건=%s  t=%02d/%02d" % (sc["place"], sc["condition"], 0, NF), fontsize=11)
    def upd(i):
        fig.suptitle("UAV-01  SAR MISSION  |  %s  조건=%s  t=%02d/%02d" % (sc["place"], sc["condition"], i, NF), fontsize=11)
        if on_frame is not None:
            try: on_frame(i, NF)
            except Exception: pass
        return draw(i)
    anim = FuncAnimation(fig, upd, frames=NF, interval=500, blit=False)
    anim.save(path, writer=PillowWriter(fps=fps), dpi=80); plt.close(fig)   # dpi 로 GIF 용량<7MB(첨부 상한)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--nl", default="설악산 일대 산불, 안개, 조난자 2명 탐색"); ap.add_argument("--seed", type=int, default=None)
    a, _ = ap.parse_known_args()
    V = simulate(a.nl, a.seed)
    print("장소=%s 조건=%s 조난자 %d/%d, %d프레임" % (V["sc"]["place"], V["sc"]["condition"], len(V["confirmed"]), len(V["survs"]), len(V["frames"])))
    print("─ SAR 무전 로그 ─"); [print("  ▸", m) for m in V["radio"]]
    out = os.path.join(HERE, "out"); os.makedirs(out, exist_ok=True)
    render_gif(V, os.path.join(out, "playback.gif")); print("saved:", os.path.join(out, "playback.gif"))
