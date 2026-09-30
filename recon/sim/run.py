"""폐루프 한 판: 센서 → 추정 → 지도 → 증거 → fw 결정(C) → 유도 → 제어 → 모터 → 물리.
python3 run.py <시나리오ID> [--method proposed|frontier|random|fixed] [--seed N] [--no-record]"""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
from recon import paths  # noqa: E402
import argparse
import json
import math
import struct
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from estimation import Estimator, LIOModel, wrap  # noqa: E402
from fwpolicy import Policy  # noqa: E402
from mapping import ElevationMap, TileCoder, SIG_TARGET, compression_table  # noqa: E402
from planning import Planner, pure_pursuit, V_NOM  # noqa: E402
from rover import (B, GNSS, IMU, K_E, R_M, I0, R_W, Encoders, Faults, Lidar, Rover, P_BASE)  # noqa: E402
import spec  # noqa: E402

OUT = paths.RUNS
DT = 0.02
E_USABLE = spec.E_WH
REAL_PTS_PER_FRAME = 20000


class Truth:
    def __init__(self, w, mres=0.1):
        f = int(round(mres / w.res)); n = w.n // f
        a = w.h[: n * f, : n * f].reshape(n, f, n, f)
        self.h = a.mean((1, 3)); self.spread = a.max((1, 3)) - a.min((1, 3))
        k = w.kind[: n * f, : n * f].reshape(n, f, n, f)
        self.kind = k.max((1, 3))
        c = (np.arange(n) + 0.5) * mres
        X, Y = np.meshgrid(c, c, indexing="ij")
        x0, y0, x1, y1 = w.region
        self.inreg = (X > x0) & (X < x1) & (Y > y0) & (Y < y1)
        self.target = self.inreg & (self.kind != 2)
        from scipy.ndimage import binary_dilation
        self.edge = binary_dilation(self.spread > 0.10, iterations=2)     # 수직 구조 ±0.2 m: 2.5D 격자의 '벽 번짐' 구역


def kpis(mp, tr, est_err, t, rover, coder, info0, aoi=None):
    known = mp.var < 0.01
    good = known & ~tr.edge & tr.inreg
    rmse = float(np.sqrt(np.mean((mp.h[good] - tr.h[good]) ** 2))) if good.any() else float("nan")
    ge = known & tr.edge & tr.inreg & (tr.kind != 2)
    edge_rmse = float(np.sqrt(np.mean((mp.h[ge] - tr.h[ge]) ** 2))) if ge.any() else float("nan")
    cov = float(((mp.var < SIG_TARGET ** 2) & tr.target).sum() / tr.target.sum())
    ent = mp.entropy_bits(tr.inreg)
    ate = float(np.sqrt(np.mean(np.square(est_err)))) if est_err else 0.0
    aoi_cov = None
    if aoi:
        x0, y0, x1, y1, sg = aoi; r = mp.res
        A = (mp.var[int(x0 / r):int(x1 / r), int(y0 / r):int(y1 / r)] < sg ** 2)
        T_ = tr.target[int(x0 / r):int(x1 / r), int(y0 / r):int(y1 / r)]
        aoi_cov = round(float((A & T_).sum() / max(T_.sum(), 1)), 4)
    return dict(t=round(t, 1), coverage=round(cov, 4), aoi_cov=aoi_cov, rmse_m=round(rmse, 4), edge_rmse_m=round(edge_rmse, 4), ate_m=round(ate, 3),
                info_kbit=round((info0 - ent) / 1000, 1), energy_Wh=round(rover.bat.Wh_used, 2),
                dist_m=round(rover.dist, 1), collisions=rover.collisions,
                down_kB=round(coder.bytes_total / 1000, 1))


def run(sc, method="proposed", seed=0, record=True, t_max=None, compare_filters=False, quiet=False):
    rng = np.random.default_rng(seed)
    np.random.seed(seed)
    w = sc["world"](seed)
    t_max = t_max or sc.get("t_max", 180.0)
    faults = Faults(**sc.get("faults", {}))
    gnss_equipped = sc.get("gnss", False)
    bx, by = w.base
    rv = Rover(w, bx, by, w.start_yaw, soc=sc.get("soc", 1.0))
    enc, imu, lid, gnss = Encoders(), IMU(rng), Lidar(rng), GNSS(rng)
    lio = LIOModel(rng)
    kinds = ["proposed"] + (["odom", "odom_gyro", "ekf_lio"] if compare_filters else [])
    ests = {k: Estimator(k, bx, by, w.start_yaw) for k in kinds}
    est = ests["proposed"]
    maps = {k: ElevationMap(w.size) for k in kinds}
    mp = maps["proposed"]
    tr = Truth(w)
    pl = Planner(mp, w.region)
    aoi = sc.get("aoi")
    if aoi:
        pl.set_aoi(*aoi)
    pol = Policy()
    coder = TileCoder(mp.n)
    storage_cap = sc.get("storage_B", 512e9)
    stored = 0.0
    info0 = mp.entropy_bits(tr.inreg)

    last_ticks = enc.read(rv, faults, 0.0)
    wheel_i = np.zeros(4)
    t = 0.0
    act = "HOLD"; dec = {}
    goal = None; path = []; dwell = 0.0; avoid_left = 0.0; avoid_dir = -1
    breadcrumbs = [(bx, by)]
    last_lidar_t = 0.0; last_scan = None; prev_lio_t = None
    cand = {}
    lidar_h = cam_h = gnss_h = 1.0; imu_h = 1.0; enc_ok = np.ones(4, bool); enc_bad_t = np.zeros(4)
    slip = 0.0; tilt = 0.0; risk = 0.0; link_age = 0.0; bat_need = 0.0; bw, lat = 4e6, 0.05; kp_cov = 0.0; kp = {}
    health = (1.0, 1.0, 1.0, 1.0, 1.0); stop_static = 0; trav = None; slip_hold = 0.0; last_avoid_why = ''; dust_filter_on = False; done_cnt = 0; avoid_t = 0.0; escape = 0.0; n_break = 0
    comm_q = []           # (도착시각, bytes)
    rate_raw = rate_down = 0.0
    events = []; timeline = []
    est_err = []
    frames = []; snaps = []
    n_frames = sc.get("frames", 480)
    t_frame = t_max / n_frames; next_frame = 0.0; next_snap = 0.0
    fixed_wp = sc.get("fixed_wp") or lawnmower(w.region)
    fixed_i = 0
    rand_goal = None
    done_reason = None
    mission_done = False
    wall0 = time.time()
    k_step = 0
    health_prev = None
    voxels = set()

    def log(kind, msg):
        events.append(dict(t=round(t, 1), kind=kind, msg=msg))
        if not quiet:
            print(f"[{t:6.1f}] {kind}: {msg}")

    while t < t_max:
        k_step += 1
        # ------------------------------------------------ 10 Hz: 인지·추정·지도·결정
        if k_step % 5 == 0:
            sc_ = lid.scan(w, rv, faults, t)
            if sc_ is not None:
                pts_s, Rw, o, tag = sc_
                last_lidar_t = t
                P_true = pts_s @ Rw.T + o                     # 참 세계좌표 (LIO 정보행렬용)
                # 추정 자세로 세계에 올린다 (z·roll·pitch 는 IMU 기울기, yaw·x·y 는 추정기)
                down = int((pts_s[:, 2] < -0.05).sum())
                near_air = float(tag.mean()) if len(tag) else 0.0          # 센서가 '잡음' 으로 태그한 점의 비율
                h_ret = float(np.clip(down / (0.35 * lid.expected_ground_rays()), 0, 1))
                h_air = float(np.clip(1 - 6 * near_air, 0.55, 1.0)) if near_air > 0.005 else 1.0   # 먼지: 살아 있지만 열화(0.55 하한)
                h_now = min(h_ret, h_air)
                lidar_h = h_now if lidar_h == 0.0 else lidar_h + 0.3 * (h_now - lidar_h)      # 지수 평활: 한 프레임 요동으로 안 뒤집힌다
                degraded = lidar_h < 0.8
                if degraded:                                   # 성능저하 모드: 먼지가 몰리는 2 m 안쪽 되돌림을 버린다(가까운 곳은 안 보인다 → 감속)
                    keep = (np.linalg.norm(pts_s, axis=1) >= 2.0) & ~tag
                    if not dust_filter_on:
                        log("degrade", f"LiDAR 건강 {lidar_h:.2f}: 2 m 안쪽 점 폐기(먼지 필터), 측정분산 ×9, 속도 ½")
                        dust_filter_on = True
                    pts_s = pts_s[keep]
                elif dust_filter_on and lidar_h > 0.9:
                    dust_filter_on = False; log("recover", f"LiDAR 건강 {lidar_h:.2f} 회복 -> 먼지 필터 해제")
                z = lio.measure(rv, w, P_true, degraded)
                for k, e in ests.items():
                    if z is not None:
                        e.update_lio(z[0], z[1], (t - prev_lio_t) if prev_lio_t else 0.1)
                prev_lio_t = t
                rng_s = np.linalg.norm(pts_s, axis=1)
                for k, e in ests.items():
                    cy, sy = math.cos(e.s[2]), math.sin(e.s[2])
                    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
                    da, db = rng.normal(0, math.radians(0.2), 2)   # 이 프레임의 자세각 추정 오차 (IMU 기울기 0.2°)
                    Ea = np.array([[1, 0, db], [0, 1, -da], [-db, da, 1]])
                    Rp = Rz @ (Rz_T(rv.yaw) @ Rw) @ Ea
                    oe = np.array([e.s[0] + spec.MECH["lidar_x"] * cy, e.s[1] + spec.MECH["lidar_x"] * sy, o[2] + 0.01 * rng.standard_normal()])
                    Pw = pts_s @ Rp.T + oe
                    maps[k].integrate(np.column_stack([Pw, rng_s]), math.radians(0.2), e.P, lid.sig * (3 if degraded else 1), t)
                    if k == "proposed":
                        last_scan = Pw
                        vk = np.floor(Pw[:: 7] / 0.1).astype(np.int64)
                        voxels.update((vk[:, 0] * 1000003 + vk[:, 1] * 1009 + vk[:, 2]).tolist())
                raw_B = REAL_PTS_PER_FRAME * 26 + 1000 * 32 / 10 + 100 * 24 / 10 + (spec.DATA["cam_Bps"] / 10 if cam_h > 0.5 else 0)
                if stored < storage_cap:
                    stored += raw_B
                rate_raw = 0.9 * rate_raw + 0.1 * raw_B * 10
            else:
                if t - last_lidar_t > 0.3:
                    lidar_h = 0.0
                rate_raw *= 0.9
            g = gnss.read(w, rv, faults, t) if gnss_equipped and k_step % 10 == 0 else None
            if g is not None:
                est.update_gnss(g[:2], g[2])
            if gnss_equipped:
                i_, j_ = w.idx(rv.x, rv.y)
                gnss_h = 0.0 if (faults.on("gnss_loss", t) or w.gnss_block[i_, j_]) else 1.0
            cam_h = 0.0 if faults.on("cam_fail", t) else 1.0
            # IMU 건강: 추정 편향 크기
            b = abs(math.degrees(est.s[3]))
            imu_h = 1.0 if b < 0.6 else (0.3 if b < 2 else 0.0)
            if imu_h < 0.5 and est.use_gyro:
                est.use_gyro = False; log("isolate", f"IMU 자이로 편향 {b:.2f}°/s -> 자이로 배제, 엔코더 요율로 전환")
            # 엔코더 건강: 같은 쪽 짝 바퀴와 비교
            ticks = enc.read(rv, faults, t)
            for kk, pp in ((0, 1), (1, 0), (2, 3), (3, 2)):
                wk = abs(ticks[kk] - enc_prev_ticks[kk]) if k_step > 5 else 1
                wp = abs(ticks[pp] - enc_prev_ticks[pp]) if k_step > 5 else 1
                if wp > 40 and wk < 0.2 * wp:
                    enc_bad_t[kk] += 0.1
                else:
                    enc_bad_t[kk] = max(0, enc_bad_t[kk] - 0.1)
                if enc_bad_t[kk] > 1.0 and enc_ok[kk]:
                    enc_ok[kk] = False; est.enc_ok = enc_ok.copy()
                    log("isolate", f"엔코더 {['FL','RL','FR','RR'][kk]} 정지(짝 바퀴 {wp} tick/0.1s) -> 짝 바퀴로 대체")
            enc_prev_ticks = ticks.copy()
            enc_h = 1.0 if enc_ok.all() else (0.3 if (enc_ok[:2].any() and enc_ok[2:].any()) else 0.0)
            # 슬립 · 기울기 · 전방 위험
            slip = est.slip_est if est.kind == "proposed" else 0.0
            if slip_hold > 0:                                   # 후진 직후 5 s 불응기: 같은 슬립으로 다시 후진하지 않는다
                slip_hold -= 0.1; slip = min(slip, 0.40)
            _, gz_roll, gz_pitch = imu.read(rv, faults, 0.0, t) if False else (0, rv.roll, rv.pitch)
            tilt = max(abs(gz_roll), abs(gz_pitch)) / math.radians(spec.MECH["slope_limit_deg"])
            if k_step % 10 == 0 or trav is None:
                trav = mp.traversability()[0]
            risk = collision_risk(trav, est, mp, path, rv, t - last_lidar_t, avoid_left > 0 or escape > 0)
            if last_scan is None or lidar_h < 0.5:
                risk = max(risk, 0.0)
            # 저장·통신
            bw, lat = w.comm(rv.x, rv.y)
            if faults.on("comm_delay", t):
                bw, lat = faults.arg("comm_delay", (2e4, 8.0))
            if faults.on("comm_loss", t):
                bw = 0.0
            health = (lidar_h, imu_h, enc_h, cam_h, gnss_h)
            # 결정 (C 커널, 10 Hz)
            dec = pol.step(j_explore=(cand.get("explore", {}).get("J", 0), cand.get("explore", {}).get("x", 0), cand.get("explore", {}).get("y", 0)),
                           j_revisit=(cand.get("revisit", {}).get("J", 0), cand.get("revisit", {}).get("x", 0), cand.get("revisit", {}).get("y", 0)),
                           j_observe=(cand.get("observe", {}).get("J", 0), rv.x, rv.y),
                           coverage=(1.0 if mission_done else kp_cov), bat_need=bat_need,
                           storage=stored / storage_cap, slip=slip, link=link_age / 30.0, tilt=tilt,
                           health=health, battery=rv.bat.usable(), collision=risk, pos_sigma=est.sigma,
                           gps_valid=gnss_h > 0.5, imu_valid=imu_h > 0.5, actuator_ok=not faults.on("estop", t))
            # 실행층 기동 잠금: 시작한 후진(AVOID)·정지관측(OBSERVE)은 끝까지 한다. 안전 행동(STOP·비상·귀환)만 끊는다.
            # 첫 판은 0.1 s 마다 다시 고르는 바람에 AVOID 가 한 틱 만에 풀려 후진을 한 번도 못 했다(T04: AVOID↔EXPLORE 189회).
            if avoid_left > 0 and act == "AVOID" and dec["act"] in ("EXPLORE", "REVISIT", "OBSERVE", "HOLD", "RELOCALIZE"):
                dec = dict(dec, act="AVOID", lock=True)
            elif dwell > 0 and act == "OBSERVE" and dec["act"] in ("EXPLORE", "REVISIT", "HOLD"):
                dec = dict(dec, act="OBSERVE", lock=True)
            if dec["act"] != act:
                timeline.append((round(t, 1), dec["act"], dec["safety"]))
                if dec["act"] in ("AVOID", "SAFE_STOP", "EMERGENCY", "RETURN", "RELOCALIZE") and not quiet:
                    print(f"[{t:6.1f}] act {act} -> {dec['act']} ({dec['safety']}, bt={dec['bt']}, arb={dec['arb']})")
                if dec["act"] == "AVOID":
                    avoid_left = 0.4; dwell = 0.0
                    last_avoid_why = "slip" if slip > 0.45 else ("tilt" if tilt > 0.8 else "risk")
                if dec["act"] == "OBSERVE":
                    dwell = 4.0
                goal = None
            for e in dec["events"]:
                if e in ("SENSOR_FAIL", "SENSOR_RECOVER", "ACTUATOR_FAIL", "SENSOR_STALE"):
                    log("detect", f"fw 이벤트 {e} {dec['failed']}")
            act = dec["act"]
            if health_prev is not None:
                for nm, a0, a1 in zip(("LIDAR", "IMU", "ENC", "CAM", "GNSS"), health_prev, health):
                    if a0 >= 0.5 > a1:
                        log("detect", f"{nm} 건강 {a0:.2f} -> {a1:.2f}")
                    if a0 < 0.5 <= a1:
                        log("recover", f"{nm} 건강 회복 {a1:.2f}")
            health_prev = health
        # ------------------------------------------------ 1 Hz: 계획·목적함수·지도 노화·통신
        if k_step % 50 == 1:
            mp.age(1.0)
            mp.footprint(est.s[0], est.s[1], est.s[2], rv.z, t=t)
            pl.penalty *= 0.985                                  # 벌점은 약 1 분 반감(환경이 바뀔 수 있다)
            pl.update(est.s[0], est.s[1])
            ib, jb = pl.ci(bx, by)
            d_base = pl.dist[ib, jb]
            if not np.isfinite(d_base):
                d_base = 3.0 * math.hypot(est.s[0] - bx, est.s[1] - by)
            bat_need = float(d_base / V_NOM * (P_BASE + 14.0) / 3600 * 1.5 / E_USABLE)
            keep = None
            if isinstance(goal, tuple) and act in ("EXPLORE", "REVISIT") and math.hypot(goal[0] - est.s[0], goal[1] - est.s[1]) > 0.8:
                keep = ({"EXPLORE": "explore", "REVISIT": "revisit"}[act], goal[0], goal[1])
            o = pl.objective(est.s[0], est.s[1], rv.bat.usable() * E_USABLE, keep=keep)
            cand = baseline_candidates(method, o, pl, est, w, fixed_wp, fixed_i, rand_goal, rng)
            if method == "fixed":
                fixed_i = cand.pop("_fixed_i"); mission_done = fixed_i >= len(fixed_wp)
            if method == "random":
                rand_goal = cand.pop("_rand_goal")
            kp = kpis(mp, tr, est_err, t, rv, coder, info0, aoi)
            kp_cov = kp["coverage"]
            if act not in ("EXPLORE", "REVISIT", "RETURN"):          # 서 있을 때도 '가려는 길' 을 갱신 (위험 판단 방향)
                best = max(("explore", "revisit"), key=lambda q: cand.get(q, {}).get("J", 0))
                if cand.get(best, {}).get("J", 0) > 0:
                    path = pl.path_to(cand[best]["x"], cand[best]["y"]) or path
            if act == "SAFE_STOP" and risk > 0.9:                  # 사람이면 3 s 사이 비키고, 아니면 돌아간다
                stop_static += 1.0
                if stop_static >= 3:                                # 정적 장애물 앞 교착: 전방에 벌점, 재계획
                    mark_penalty(pl, est, 1.0); stop_static = 0; goal = None; n_break += 1
                    if n_break >= 2:                                 # 두 번 풀어도 그대로면 끼인 것: 뒤로 빠져나오는 기동
                        escape = 0.5; n_break = 0
                        log("recover", "정지 교착 6 s -> 뒤가 비었는지 보고 0.5 m 후진 탈출")
                    else:
                        log("recover", "정지 3 s 지속(정적 장애물) -> 전방 벌점·재계획")
            else:
                stop_static = 0
                if act not in ("SAFE_STOP",):
                    n_break = 0
            if method in ("proposed", "frontier"):                # 후보 소진이 5 s 이어지면 완료 — 다시 생기면 풀린다(첫 판은 한 번 켜지면 영영 귀환)
                empty = cand.get("explore", {}).get("J", 0) < 0.05 and cand.get("revisit", {}).get("J", 0) < 0.05 and t > 20
                done_cnt = done_cnt + 1 if empty else 0
                mission_done = done_cnt >= 5
            est_err.append(math.hypot(est.s[0] - rv.x, est.s[1] - rv.y))
            # 통신: 이번 초 예산 안에서 정보밀도 높은 타일부터
            budget = max(0, bw / 8 - 1000 - (30000 if cam_h > 0.5 and bw > 1e6 else 0))
            nb, bits = coder.send(mp, budget) if bw > 0 else (0, 0)
            comm_q.append((t + lat, nb))
            rate_down = nb + 1000
            arrived = [q for q in comm_q if q[0] <= t]
            comm_q = [q for q in comm_q if q[0] > t]
            if bw > 0 and (arrived or lat < 1.0):
                link_age = max(0.0, lat)
            else:
                link_age += 1.0
        else:
            kp_cov = locals().get("kp_cov", 0.0)
        # ------------------------------------------------ 유도 (행동 → v, ω)
        v_max = V_NOM * (0.5 if dec.get("safety") == "DEGRADED" else 1.0)
        v_c = om_c = 0.0
        if act in ("EXPLORE", "REVISIT", "RETURN"):
            if act == "RETURN" and lidar_h < 0.5:
                if goal != "crumbs":
                    goal = "crumbs"; path = list(reversed(breadcrumbs)); log("degrade", "LiDAR 없음 -> 지나온 길(빵부스러기)로 저속 귀환")
                v_max = 0.2
            else:
                key = {"EXPLORE": "explore", "REVISIT": "revisit"}.get(act)
                gxy = (bx, by) if act == "RETURN" else (cand.get(key, {}).get("x"), cand.get(key, {}).get("y"))
                if gxy[0] is not None and (goal is None or goal == "crumbs" or math.hypot(goal[0] - gxy[0], goal[1] - gxy[1]) > 1.0 or k_step % 50 == 2):
                    goal = gxy; path = pl.path_to(*gxy) or []
            v_c, om_c, remain = pure_pursuit(path, est.s[0], est.s[1], est.s[2], v_max)
            if act == "RETURN" and math.hypot(est.s[0] - bx, est.s[1] - by) < 0.6 and goal != "crumbs":
                v_c = om_c = 0.0
                if done_reason is None and t > 10.0:
                    done_reason = "기지 귀환 완료"; log("stop", "기지 도착 — 임무 종료")
        elif act == "OBSERVE":
            dwell -= DT
        elif act == "AVOID":
            if avoid_left > 0:
                v_c = -0.15; avoid_left -= max(abs(rv.v), 0.0) * DT; avoid_t += DT
                if avoid_t > 6.0:                                 # 뒤도 막혀 못 물러난다: 기동을 끝내고 벌점으로 넘어간다
                    avoid_left = 0.0; log("recover", "후진 막힘 6 s -> 후진 중단")
                if avoid_left <= 0:
                    avoid_t = 0.0
                    if last_avoid_why == "slip":
                        mark_disk(pl, est.s[0], est.s[1], 1.6, 0.7); slip_hold = 5.0
                        log("recover", "슬립 후진 완료 -> 반경 1.6 m 를 무른 지반으로 표시(비용↑), 재계획")
                    else:
                        mark_penalty(pl, est, 1.2)
                        log("recover", f"후진 0.4 m 완료({last_avoid_why}) -> 전방 구역에 벌점, 재계획")
                    goal = None
        elif act == "RELOCALIZE":
            pass
        if escape > 0 and act in ("SAFE_STOP", "EXPLORE", "REVISIT", "HOLD", "OBSERVE", "RETURN"):
            v_c, om_c = -0.15, 0.0                                   # 실행층 탈출 기동: 뒤쪽 위험으로 판정 중(그래서 커널이 정지를 풀어 준다)
            escape -= max(abs(rv.v), 0.02) * DT
            if escape <= 0:
                goal = None
        # 빵부스러기
        if math.hypot(est.s[0] - breadcrumbs[-1][0], est.s[1] - breadcrumbs[-1][1]) > 0.5 and act not in ("RETURN",):
            breadcrumbs.append((est.s[0], est.s[1]))
        # ------------------------------------------------ 50 Hz: 바퀴 속도 PID → 모터
        rv.relay_on = not faults.on("estop", t)
        chi = 0.8
        wl = (v_c - om_c * B / chi / 2) / R_W; wr = (v_c + om_c * B / chi / 2) / R_W
        tgt = np.array([wl, wl, wr, wr])
        ticks = enc.read(rv, faults, t)
        dticks = ticks - last_ticks; last_ticks = ticks
        meas = dticks / 3200 * 2 * math.pi / DT
        for kk, pp in ((0, 1), (1, 0), (2, 3), (3, 2)):
            if not enc_ok[kk]:
                meas[kk] = meas[pp]                                    # 격리: 짝 바퀴 속도로 되먹임
        err = tgt - meas
        wheel_i = np.clip(wheel_i + err * DT, -5, 5)
        Vb = rv.bat.ocv()
        duty = (K_E * tgt + np.sign(tgt) * I0 * R_M * 3) / Vb + 0.08 * err + 0.3 * wheel_i / Vb
        duty = np.where(np.abs(tgt) < 1e-3, 0.0, duty)
        wheel_i = np.where(np.abs(tgt) < 1e-3, 0.0, wheel_i)
        evs = rv.step(np.clip(duty, -1, 1), DT, t)
        for e in evs:
            log("physics", {"collision": "참 충돌/걸림 발생", "crash": f"임무 실패: {rv.crashed}"}[e])
        gz, _, _ = imu.read(rv, faults, DT, t)
        for k, e in ests.items():
            e.predict(dticks.astype(float), gz, DT, imu_ok=imu_h > 0.5 or k != "proposed")
        t += DT
        # ------------------------------------------------ 기록
        if record and t >= next_frame:
            next_frame += t_frame
            frames.append(frame(t, rv, est, dec, act, cand, goal, path, last_scan, rng, health, slip, tilt, risk,
                                rate_raw, rate_down, bw, lat, link_age, stored, storage_cap, kp if 'kp' in locals() else {},
                                w, events, bat_need, dwell, avoid_left))
            if t >= next_snap:
                next_snap += t_max / 120
                snaps.append((len(frames) - 1, snap(mp)))
        if done_reason or rv.crashed:
            if rv.crashed and done_reason is None:
                done_reason = "임무 실패: " + rv.crashed
            if t > 1.0 and (done_reason and (rv.crashed or not record)):
                break
            if record and done_reason and t_max - t > 1:
                # 영상 길이를 맞추려고 정지 상태로 기록을 이어 간다
                pass
    wall = time.time() - wall0
    kp = kpis(mp, tr, est_err, t, rv, coder, info0, aoi)
    kp.update(method=method, seed=seed, wall_s=round(wall, 1), done=done_reason or "시간 종료",
              info_per_kB=round(kp["info_kbit"] / max(kp["down_kB"], 1e-3), 2),
              info_per_Wh=round(kp["info_kbit"] / max(kp["energy_Wh"], 1e-3), 2),
              revisit_share=round(sum(1 for f in frames if f["act"] in ("REVISIT", "OBSERVE")) / max(len(frames), 1), 3),
              voxels=len(voxels), raw_B=stored, crashed=rv.crashed)
    res = dict(id=sc["id"], title=sc["title"], kpi=kp, events=events, timeline=timeline)
    if compare_filters:
        comp = {}
        for k, e in ests.items():
            m = maps[k]
            good = (m.var < 0.01) & ~tr.edge & tr.inreg
            comp[k] = dict(final_err_m=round(math.hypot(e.s[0] - rv.x, e.s[1] - rv.y), 3),
                           yaw_err_deg=round(math.degrees(abs(wrap(e.s[2] - rv.yaw))), 2),
                           map_rmse_m=round(float(np.sqrt(np.mean((m.h[good] - tr.h[good]) ** 2))), 4),
                           ghost_cells=int(((m.var < 0.01) & (np.abs(m.h - tr.h) > 0.15) & tr.inreg & ~tr.edge).sum()),
                           mapped_cells=int(good.sum()))
        res["filters"] = comp
        res["filter_maps"] = {k: m for k, m in maps.items()}
    res["compression"] = compression_table(mp, stored, tr.h)
    if record:
        res["frames"] = frames; res["snaps"] = snaps; res["world"] = w; res["truth"] = tr; res["map"] = mp
    return res


def Rz_T(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])


enc_prev_ticks = np.zeros(4)


def lawnmower(region, sp=4.0):
    x0, y0, x1, y1 = region
    pts = []
    ys = np.arange(y0 + 1.5, y1 - 1.0, sp)
    for k, y in enumerate(ys):
        xs = (x0 + 1.5, x1 - 1.5) if k % 2 == 0 else (x1 - 1.5, x0 + 1.5)
        pts += [(xs[0], y), (xs[1], y)]
    return pts


def baseline_candidates(method, o, pl, est, w, wp, wi, rgoal, rng):
    if method == "proposed":
        return {k: o[k] for k in ("explore", "revisit", "observe")}
    z = dict(J=0.0, x=0.0, y=0.0)
    if method == "fixed":
        while wi < len(wp) and math.hypot(est.s[0] - wp[wi][0], est.s[1] - wp[wi][1]) < 0.8:
            wi += 1
        # 도달 불가 웨이포인트는 건너뛴다 (고정 경로의 한계를 그대로 둔다)
        while wi < len(wp) and not np.isfinite(pl.dist[pl.ci(*wp[wi])]):
            wi += 1
        e = dict(J=0.5, x=wp[wi][0], y=wp[wi][1]) if wi < len(wp) else dict(z)
        return {"explore": e, "revisit": dict(z), "observe": dict(z), "_fixed_i": wi}
    if method == "frontier":
        # 가장 가까운 프런티어(아는 자유 셀 중 미지 이웃이 있는 것) — Yamauchi 1997
        kn = pl.pool((pl.m.var < 0.09).astype(np.uint8), "min").astype(bool)
        unk = pl.pool((pl.m.var >= 0.09).astype(np.uint8), "max").astype(bool)
        from scipy.ndimage import binary_dilation as bd
        far = np.hypot(pl.CX - est.s[0], pl.CY - est.s[1]) > 1.5
        fr = kn & bd(unk & pl.inreg, iterations=1) & (pl.risk < 0.6) & np.isfinite(pl.dist) & (pl.dist > 1.0) & far & ~pl.lethal
        if not fr.any():
            return {"explore": dict(z), "revisit": dict(z), "observe": dict(z)}
        d = np.where(fr, pl.dist, np.inf)
        k = np.unravel_index(np.argmin(d), d.shape)
        return {"explore": dict(J=0.5, x=float(pl.CX[k]), y=float(pl.CY[k])), "revisit": dict(z), "observe": dict(z)}
    if method == "random":
        if rgoal is None or math.hypot(est.s[0] - rgoal[0], est.s[1] - rgoal[1]) < 0.8 or not np.isfinite(pl.dist[pl.ci(*rgoal)]):
            ok = np.isfinite(pl.dist) & pl.inreg & (pl.risk < 0.6) & (pl.dist > 1.0) & ~pl.lethal
            ii = np.argwhere(ok)
            if len(ii) == 0:
                rgoal = None
            else:
                k = ii[rng.integers(len(ii))]
                rgoal = (float(pl.CX[tuple(k)]), float(pl.CY[tuple(k)]))
        e = dict(J=0.5, x=rgoal[0], y=rgoal[1]) if rgoal else dict(z)
        return {"explore": e, "revisit": dict(z), "observe": dict(z), "_rand_goal": rgoal}
    raise ValueError(method)


def mark_disk(pl, x, y, rad, val):
    i0, j0 = pl.ci(x, y); k = int(rad / pl.cres) + 1
    for di in range(-k, k + 1):
        for dj in range(-k, k + 1):
            if di * di + dj * dj <= k * k and 0 <= i0 + di < pl.nc and 0 <= j0 + dj < pl.nc:
                pl.penalty[i0 + di, j0 + dj] = max(pl.penalty[i0 + di, j0 + dj], val)


def mark_penalty(pl, est, dist):
    c, s = math.cos(est.s[2]), math.sin(est.s[2])
    for d in np.arange(0.2, dist + 0.61, 0.2):
        for lat in np.arange(-0.4, 0.41, 0.2):
            i, j = pl.ci(est.s[0] + c * d - s * lat, est.s[1] + s * d + c * lat)
            pl.penalty[i, j] = 0.95


def collision_risk(trav, est, mp, path, rv, age, backing):
    """가려는 길 앞 0.3..1.0 m 의 지도 주행위험(기울기·계단·불확실도)과 음장애(도랑).
    지도는 10 Hz 로 새 점을 받으므로 새로 나타난 물체(사람)도 여기 들어온다.
    첫 판은 점 높이를 로버 바닥과 비교해 오르막을 장애물로 읽었다(T02 정지 교착)."""
    if age > 0.5:
        return 0.0
    x, y, th = est.s[0], est.s[1], est.s[2]
    if backing:
        th += math.pi
    samp = []
    if path and not backing:
        P = np.asarray(path, float); d = np.hypot(P[:, 0] - x, P[:, 1] - y); k = int(np.argmin(d))
        pts = np.vstack([[x, y], P[k:]])
        seg = np.hypot(*np.diff(pts, axis=0).T); cs = np.concatenate([[0], np.cumsum(seg)])
        for s_ in np.arange(0.3, 1.01, 0.1):
            if s_ > cs[-1]:
                break
            q = np.searchsorted(cs, s_) - 1; q = max(0, min(q, len(seg) - 1))
            f = (s_ - cs[q]) / max(seg[q], 1e-9)
            samp.append((pts[q, 0] + f * (pts[q + 1, 0] - pts[q, 0]), pts[q, 1] + f * (pts[q + 1, 1] - pts[q, 1]), s_))
    if not samp:
        c, s = math.cos(th), math.sin(th)
        samp = [(x + c * s_, y + s * s_, s_) for s_ in np.arange(0.3, 1.01, 0.1)]
    r = 0.0
    z0 = rv.z
    for px, py, s_ in samp:
        w = 1.0 if s_ <= 0.6 else 0.75
        for dl in (-0.15, 0.0, 0.15):                            # 차체 폭 방향 세 줄
            c, s = math.cos(th), math.sin(th)
            i = int((px - s * dl) / mp.res); j = int((py + c * dl) / mp.res)
            if not (0 <= i < mp.n and 0 <= j < mp.n):
                continue
            if mp.var[i, j] < 0.05:
                r = max(r, float(trav[i, j]) * w)
                if mp.h[i, j] < z0 - 0.12:
                    r = max(r, 0.95 * w)
    return min(r, 1.0)


def frame(t, rv, est, dec, act, cand, goal, path, scan, rng, health, slip, tilt, risk, rraw, rdown, bw, lat,
          link_age, stored, cap, kp, w, events, bat_need, dwell, avoid_left):
    sp = []
    if scan is not None and len(scan):
        k = rng.choice(len(scan), min(700, len(scan)), replace=False)
        sp = np.round(scan[k, :3], 2).tolist()
    pth = []
    if path and goal is not None:
        P = np.asarray(path); pth = np.round(P[:: max(1, len(P) // 40)], 2).tolist()
    return dict(t=round(t, 2), tp=[round(rv.x, 3), round(rv.y, 3), round(rv.z, 3), round(rv.yaw, 3), round(rv.roll, 3), round(rv.pitch, 3)],
                ep=[round(est.s[0], 3), round(est.s[1], 3), round(est.s[2], 3)], sig=round(est.sigma, 3),
                act=act, bt=dec.get("bt"), arb=dec.get("arb"), safety=dec.get("safety"), mode=dec.get("mode"),
                J={k: round(v.get("J", 0), 3) for k, v in cand.items()},
                Jxy={k: [round(v.get("x", 0), 2), round(v.get("y", 0), 2)] for k, v in cand.items()},
                goal=list(goal) if isinstance(goal, tuple) else None, path=pth, pts=sp,
                bat=round(rv.bat.usable(), 4), V=round(rv.bat.ocv(), 2), P=round(P_BASE + rv.P_motor, 1),
                Wh=round(rv.bat.Wh_used, 2), need=round(bat_need, 3),
                health=[round(h, 2) for h in health], slip=round(slip, 3), tilt=round(tilt, 3), risk=round(risk, 3),
                raw=round(rraw), down=round(rdown), bw=round(bw), lat=round(lat, 2), link=round(link_age, 1),
                store=round(stored / cap, 4), kpi=kp, dyn=[[round(a, 2) for a in d] for d in w.dyn_h(t)],
                relay=rv.relay_on, v=round(rv.v, 3), om=round(rv.om, 3), true_slip=round(rv.slip, 3),
                ev=[e for e in events if e["t"] <= t][-4:], dwell=round(dwell, 1))


def snap(mp):
    f = 2
    n = mp.n // f
    h = mp.h.reshape(n, f, n, f).max((1, 3))
    v = mp.var.reshape(n, f, n, f).min((1, 3))
    qh = np.clip(np.round(h * 100), -32000, 32000).astype(np.int16)
    qs = np.clip(np.round(np.log2(np.sqrt(v) / 0.005) * 32), 0, 255).astype(np.uint8)
    return qh.tobytes() + qs.tobytes()


def save(res, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    w, tr = res["world"], res["truth"]
    f = 2; n = tr.h.shape[0] // f
    th = tr.h.reshape(n, f, n, f).max((1, 3))
    tk = tr.kind.reshape(n, f, n, f).max((1, 3))
    with open(outdir / "world.bin", "wb") as fh:
        fh.write(struct.pack("<ii", n, 0))
        fh.write(np.clip(np.round(th * 100), -32000, 32000).astype(np.int16).tobytes())
        fh.write(tk.astype(np.uint8).tobytes())
    with open(outdir / "snaps.bin", "wb") as fh:
        fh.write(struct.pack("<ii", n, len(res["snaps"])))
        for fi, b in res["snaps"]:
            fh.write(struct.pack("<i", fi)); fh.write(b)
    meta = {k: res[k] for k in ("id", "title", "kpi", "events", "timeline")}
    meta["compression"] = [list(r) for r in res["compression"]]
    if "filters" in res:
        meta["filters"] = res["filters"]
    meta["base"] = list(w.base); meta["size"] = w.size; meta["region"] = list(w.region)
    meta["notes"] = w.notes
    (outdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=float))
    (outdir / "frames.json").write_text(json.dumps(res["frames"], ensure_ascii=False, separators=(",", ":"), default=float))


if __name__ == "__main__":
    from scenarios import SCENARIOS
    ap = argparse.ArgumentParser()
    ap.add_argument("sid"); ap.add_argument("--method", default=None); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-record", action="store_true"); ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    sc = SCENARIOS[a.sid]
    m = a.method or sc.get("method", "proposed")
    r = run(sc, m, a.seed, record=not a.no_record, compare_filters=sc.get("compare_filters", False), quiet=a.quiet)
    print(json.dumps(r["kpi"], ensure_ascii=False))
    if "filters" in r:
        print(json.dumps(r["filters"], ensure_ascii=False))
    if not a.no_record:
        save(r, OUT / a.sid)
