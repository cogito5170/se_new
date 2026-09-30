#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로버 SITL 검증 하네스 — fw/(C99 결정 executive)를 로버 기준으로 잰다.

구조(sar/ivv 심판↔SUT 분리와 동형): **시뮬레이터가 로버 물리·가상 센서·고장을 생성**하고,
**fw_agent_step(실 libfw.so, ctypes)이 그 입력으로 행동을 결정**한다. 정책 C 코드는 손대지 않는다.

경계(정직):
 · 이 컨테이너엔 ROS2/Gazebo 가 없다. 여기 물리는 **L2 운동학-경량**(skid-steer 단순 슬립)이지
   Gazebo/ROAMS 의 토양-바퀴 동역학(침하·마찰)이 아니다. 고충실도는 fw/ROVER_VALIDATION.md 의 L3+.
 · fw 는 SAR 탐색 executive 다. 이 하네스는 fw 의 **상태추정·고장대응·안전전이 척추**를 로버 문맥에서
   잰다 — 목표주행(waypoint tracking)·토양분류는 fw 밖(항법/RTA)이며 그대로 표시한다.
 · fw_bridge_step 은 actuator_ok 를 안 받는다 → 구동계·stale 센서 고장(R-03류)은 네이티브
   fault_test.c 가 이미 다룬다. 여기선 물리 루프로 닿는 것(슬립·IMU·GPS·장애물·가짜표적)을 잰다.
"""
from __future__ import annotations
import ctypes
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sar", "ivv"))
import fw_vv as _fw

ACT = ["NONE", "SEARCH", "APPROACH", "INSPECT", "RETURN", "AVOID", "RELOCALIZE", "EMERGENCY", "ABSTAIN"]
SAFE = {"RETURN", "AVOID", "RELOCALIZE", "EMERGENCY"}   # 안전 전이로 치는 행동
DT = 0.5                                                # 제어 주기(s)
CRUISE = 0.6                                            # 순항 속도(m/s)


class Rover:
    """평면 skid-steer 운동학 + 바퀴 슬립. 상태=참(truth). 추정(odom/IMU/GPS)은 별도."""
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.x = self.y = 0.0; self.th = 0.0           # 참 자세
        self.ex = self.ey = 0.0; self.eth = 0.0        # 추정 자세(로버가 아는 것)
        self.unc = 0.3                                 # 자기추정 불확실도(m) — fw.position_error 입력

    def step(self, v_cmd, w_cmd, slip, imu_bias, gps_ok, enc_stuck):
        # ── 참 물리: 명령 속도에 슬립을 곱해 실제 이동 ──
        v_true = v_cmd * (1.0 - slip)
        self.th += (w_cmd + (0.0 if slip == 0 else self.rng.normal(0, 0.15 * slip))) * DT
        self.x += v_true * math.cos(self.th) * DT
        self.y += v_true * math.sin(self.th) * DT
        # ── 추정(로버가 아는 자세) ──
        if enc_stuck:                                  # 엔코더 고착: 추정이 안 갱신(움직여도 멈춘 줄 안다)
            d_est = 0.0
        else:                                          # 엔코더는 '명령'을 적분 → 슬립만큼 과대(dead-reckoning 표류)
            d_est = v_cmd * DT
        self.eth += w_cmd * DT + imu_bias * DT + self.rng.normal(0, 0.02)
        self.ex += d_est * math.cos(self.eth)
        self.ey += d_est * math.sin(self.eth)
        if gps_ok:                                     # GPS 유효 → 추정을 참에 보정(잡음 포함), 불확실도 리셋
            self.ex = self.x + self.rng.normal(0, 0.4)
            self.ey = self.y + self.rng.normal(0, 0.4)
            self.unc = 0.4
        else:                                          # GPS 없음 → 추측항법, 불확실도 성장(+슬립 가중)
            self.unc += (0.15 + 0.5 * slip) * DT
        return math.hypot(self.ex - self.x, self.ey - self.y)   # 참 위치오차(관찰자 채점용)


def action_to_cmd(act, rov, goal, home, obst, nav_avoid=False):
    """fw Action(이산 모드) → (v_cmd, w_cmd)(연속 명령). **여기가 행동 제어(모션 층)다** — fw 는
    모터를 안 돌리고 '무엇을 할지'만 고른다. 조향·국소 회피·복구는 이 어댑터(실 HW 는 PX4/항법)의 일.
    nav_avoid=True 면 모션 층이 퍼텐셜 필드로 장애물을 **부드럽게 우회**한다(fw Action 과 무관)."""
    ex, ey, eth = rov.ex, rov.ey, rov.eth
    if act in ("RELOCALIZE", "NONE", "INSPECT"):
        return 0.0, 0.0                                # 정지(불확실·재정렬·정밀관측)
    tgt = home if act in ("RETURN", "EMERGENCY") else goal
    if act == "AVOID":                                 # fw 의 근접 충돌 반사: 장애물 반대로 선회
        ang = math.atan2(ey - obst[1], ex - obst[0])
        return CRUISE, _wrap(ang - eth) / DT
    ang = math.atan2(tgt[1] - ey, tgt[0] - ex)         # 목표 방위(APPROACH/SEARCH/RETURN)
    if nav_avoid:                                      # 모션 층 국소 회피: 목표방위 + 장애물 반발 벡터합성
        d = math.hypot(ex - obst[0], ey - obst[1])
        if d < 3.0:
            rep = math.atan2(ey - obst[1], ex - obst[0])
            w = min(1.0, (3.0 - d) / 3.0)
            gx = math.cos(ang) * (1 - w) + math.cos(rep) * w
            gy = math.sin(ang) * (1 - w) + math.sin(rep) * w
            ang = math.atan2(gy, gx)
    return CRUISE, _wrap(ang - eth) / DT


def _wrap(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return max(-1.2, min(1.2, a))                      # 각속도 상한


class Motion:
    """행동 제어(모션 층). fw Action → (v,w) 로 옮기고, **immobilization 을 검출·복구**한다.
    fw 는 안 건드린다(결정론·인증 표면 유지) — 실 HW 의 PX4 failsafe 와 같은 자리.

    검출: 시각오도메트리(VO, 바퀴 인코더와 독립)로 잰 실제 지면 이동 vs 명령 이동. 명령은 전진인데
    VO 이동이 거의 없으면(창 8스텝에 '명령했지만 안 움직인' 스텝 ≥3) 헛돎으로 본다.
    복구: 후진(도랑에서 빠져나옴) → **도랑 옆 우회 waypoint 로 주행**(도랑을 돌아 나감) → 재개.
    단순 후진·선회만으론 도랑이 목표 직선상에 있을 때 되빨려 든다(퍼텐셜필드 국소최소) — 그래서
    도랑 옆을 지나는 waypoint 를 명시적으로 잡아 우회한다. 복구 후엔 도랑을 장애물로 보고 우회(nav_avoid)."""
    def __init__(self, nav_avoid=False, recover=False):
        self.nav_avoid = nav_avoid; self.recover_on = recover
        self.hist = []; self.plan = []; self.attempts = 0; self.escaped = False
        self.waypoint = None; self.wp_steps = 0

    def command(self, act, rov, goal, home, obst, vo_speed):
        base = action_to_cmd(act, rov, goal, home, obst, nav_avoid=(self.nav_avoid or self.escaped))
        self.hist.append((abs(base[0]) * DT, vo_speed * DT)); self.hist = self.hist[-8:]
        if self.plan:                                  # 복구 후진 기동 진행 중
            return self.plan.pop(0)
        if self.waypoint is not None:                  # 우회 waypoint 로 주행 중
            wx, wy = self.waypoint
            if math.hypot(rov.ex - wx, rov.ey - wy) < 0.8 or self.wp_steps <= 0:
                self.waypoint = None                   # 우회점 도달/타임아웃 → fw 행동 재개(도랑 옆 통과 완료)
            else:
                self.wp_steps -= 1
                ang = math.atan2(wy - rov.ey, wx - rov.ex)
                return CRUISE, _wrap(ang - rov.eth) / DT
        # 검출: '전진을 명령했는데 실제로 안 움직인' 스텝을 센다(fw 의 INSPECT-잦은 패턴에 강건).
        stuck = sum(1 for c, m in self.hist if c > 0.15 and m < 0.05) >= 3
        if stuck and self.recover_on and act not in ("RELOCALIZE", "NONE", "RETURN", "EMERGENCY"):
            self.attempts += 1; self.hist = []; self.escaped = True   # 이후 전진은 도랑 우회(nav_avoid)
            self.plan = [(-CRUISE, 0.0)] * 4                          # 후진 4: 도랑에서 빠져나온다
            ga = math.atan2(goal[1] - rov.ey, goal[0] - rov.ex)      # 목표 방위
            perp = ga + math.pi / 2                                  # 목표방위에 수직(한쪽으로 우회 — 결정론적)
            rad = obst[2] if len(obst) > 2 else 1.6
            R = rad + 1.2                                            # 도랑 반지름 + 여유만큼 옆으로
            self.waypoint = (obst[0] + R * math.cos(perp), obst[1] + R * math.sin(perp))
            self.wp_steps = 40
            return self.plan.pop(0)
        return base


def run_scenario(sc, seed=7, steps=120):
    """한 시나리오 실행 → 지표. sc: fault 스케줄·기대 dict."""
    steps = sc.get("steps", steps)
    lib = _fw.load_lib(); h = lib.fw_bridge_new()
    lib.fw_bridge_set_confirm(h, 2, ctypes.c_float(0.6))
    lib.fw_bridge_set_nisgate(h, ctypes.c_float(24.0))
    lib.fw_bridge_set_cmpc(h, 2, 0)                    # CMPC≥2(교차모달), require_live=0(생체는 UAV 전용 — 정직)
    rov = Rover(seed)
    goal = sc.get("goal", (8.0, 6.0)); home = (0.0, 0.0)
    ditch = sc.get("ditch")                            # (cx,cy,r) 공간 위험지역(들어가면 헛돎)
    obst = ditch if ditch else sc.get("obst", (99.0, 99.0))   # 도랑은 우회 대상이기도(반지름 포함 3-tuple)
    motion = Motion(nav_avoid=sc.get("nav_avoid", False), recover=sc.get("recover", False))
    cf = (ctypes.c_float * 5); ci = (ctypes.c_int * 5)
    px = ctypes.c_float(); py = ctypes.c_float(); conf = ctypes.c_int(); tc = ctypes.c_float(); nis = ctypes.c_float()
    errs = []; acts = []; false_confirm = False; reached_at = None; min_obst = 9e9
    n_avoid = n_reloc = 0; progress = 0.0; vo_speed = 0.0
    fault_on = sc.get("fault_step", 10 ** 9)
    for t in range(steps):
        f = sc["fault"] if t >= fault_on else {}
        slip = f.get("slip", sc.get("slip", 0.0))
        imu_bias = f.get("imu_bias", 0.0)
        gps_ok = 0 if f.get("gps_drop") else (1 if t % 5 == 0 else 0)   # 주기 GPS(5스텝)+사이 추측항법 → 표류가 드러난다
        enc_stuck = bool(f.get("enc_stuck"))
        # 모션 층: fw 행동을 명령으로 옮기고(+immobilization 복구), 그 명령으로 물리 전진
        v_cmd, w_cmd = motion.command(acts[-1] if acts else "NONE", rov, goal, home, obst, vo_speed)
        # 도랑 물리: 안에서 **전진**하면 헛돎(먼 벽에 처박힘). **후진**은 들어온 쪽 접지가 남아 빠져나올
        # 수 있다(로킹 탈출). 그래서 fw(전진만)는 영영 갇히고, 모션 층 후진 복구만 탈출한다 — 이 방향
        # 의존이 곧 두 시나리오를 가른다(전진뿐인 정책 vs 후진 복구를 아는 모션 층).
        if ditch and math.hypot(rov.x - ditch[0], rov.y - ditch[1]) < ditch[2] and v_cmd > 0:
            slip = 0.98
        _x0, _y0 = rov.x, rov.y
        true_err = rov.step(v_cmd, w_cmd, slip, imu_bias, gps_ok, enc_stuck)
        disp = math.hypot(rov.x - _x0, rov.y - _y0)
        vo_speed = disp / DT                           # 시각오도메트리(실제 지면 속도, 바퀴와 독립) — 다음 스텝 검출용
        progress += disp
        errs.append(true_err)
        gps_trust = 1 if rov.unc < 2.0 else 0          # fw.gps_valid = 측위 신뢰(불확실도 낮음) — 매 GPS틱 아님(추측항법 사이엔 유효)
        # ── 가상 센서 → fw 입력 ──
        d_goal = math.hypot(goal[0] - rov.ex, goal[1] - rov.ey)
        ev = [0.0] * 5; xs = [0.0] * 5; ys = [0.0] * 5; pres = [0] * 5; health = [1.0] * 5
        # 목표 탐지: 사거리 안이면 두 채널(교차모달)로 관측. no_goal(R-08)이면 목표 신호 없음.
        if d_goal < 12.0 and not f.get("sensor_drop") and not sc.get("no_goal"):
            for i in (0, 1):
                ev[i] = 0.8; xs[i] = goal[0]; ys[i] = goal[1]; pres[i] = 1
        # 가짜 표적(R-08). 지속=두 모달이 **같은 고정 자리**에 co-locate(CMPC·시간 통과 → gap).
        # 순간=두 모달이 **각기 독립으로 튄다**(co-locate 안 됨 → CMPC 실패·시간 실패 → 거부).
        if "fake" in sc:
            if sc["fake"] == "persistent":
                for i in (2, 3):
                    ev[i] = 0.8; xs[i] = 5.0; ys[i] = -4.0; pres[i] = 1
            else:                                       # transient: 센서독립 위치(현실 clutter)
                for i in (2, 3):
                    ev[i] = 0.8; xs[i] = rov.rng.uniform(-8, 8); ys[i] = rov.rng.uniform(-8, 8); pres[i] = 1
        collision = max(0.0, 1.0 - math.hypot(rov.x - obst[0], rov.y - obst[1]) / 2.5)
        battery = max(0.0, 1.0 - t / float(sc.get("batt_steps", 400)))
        imu_ok = 0 if f.get("imu_lost") else 1
        act_i = lib.fw_bridge_step(h, cf(*ev), cf(*xs), cf(*ys), ci(*pres), cf(*health),
                                   ctypes.c_float(battery), ctypes.c_float(collision),
                                   ctypes.c_int(imu_ok), ctypes.c_int(gps_trust), ctypes.c_float(rov.unc),
                                   ctypes.c_int(0), ctypes.c_float(0), ctypes.c_float(0),
                                   ctypes.byref(px), ctypes.byref(py), ctypes.byref(conf),
                                   ctypes.byref(tc), ctypes.byref(nis))
        act = ACT[act_i] if 0 <= act_i < len(ACT) else "NONE"; acts.append(act)
        n_avoid += (act == "AVOID"); n_reloc += (act == "RELOCALIZE")
        min_obst = min(min_obst, math.hypot(rov.x - obst[0], rov.y - obst[1]))
        if conf.value and sc.get("no_goal"):            # 목표 없이 확정 = 가짜를 확정(오확정)
            false_confirm = True
        if not sc.get("no_goal") and d_goal < 1.5 and reached_at is None:
            reached_at = t
    lib.fw_bridge_free(h)
    from collections import Counter
    top = Counter(acts).most_common(1)[0][0] if acts else "NONE"
    return {"rmse": float(np.sqrt(np.mean(np.square(errs)))), "reached": reached_at,
            "n_avoid": n_avoid, "n_reloc": n_reloc, "min_obst": (min_obst if obst[0] < 90 else None),
            "false_confirm": false_confirm, "progress": progress, "top": top,
            "n_recover": motion.attempts, "acts": dict(Counter(acts)), "final_err": errs[-1]}


# ── R-01 .. R-08 (사용자 제안 시나리오) ──
SCENARIOS = {
    "R-01 평탄·정상": dict(goal=(8, 6)),
    "R-02 바퀴 미끄러짐↑": dict(goal=(8, 6), fault_step=6, fault={"slip": 0.45}),
    "R-03 엔코더 고착": dict(goal=(8, 6), fault_step=20, fault={"enc_stuck": True}),
    "R-04 IMU 편향": dict(goal=(8, 6), fault_step=6, fault={"imu_bias": 0.25}),
    "R-05 GPS 지연·누락": dict(goal=(8, 6), fault_step=15, fault={"gps_drop": True}),
    "R-06 경로 암석(장애물)": dict(goal=(8, 6), obst=(5.0, 3.75)),   # 직선 경로(y=0.75x) 위
    "R-06b 암석+모션층 회피": dict(goal=(8, 6), obst=(5.0, 3.75), nav_avoid=True),
    "R-07 통신 단절(RTA 영역)": dict(goal=(8, 6), fault_step=20, fault={"comms_lost": True}),
    "R-08a 순간 가짜표적": dict(goal=(8, 6), fake="transient", no_goal=True),
    "R-08b 지속 가짜표적": dict(goal=(8, 6), fake="persistent", no_goal=True),
    "R-09 도랑 빠짐(복구 없음)": dict(goal=(8, 6), ditch=(4.0, 3.0, 1.6)),
    "R-09b 도랑+모션층 복구": dict(goal=(8, 6), ditch=(4.0, 3.0, 1.6), recover=True),
}

EXPECT = {   # 정직한 기대: fw 척추 안 / 밖 / 알려진 gap
    "R-01 평탄·정상": "목표 접근·도달",
    "R-02 바퀴 미끄러짐↑": "추측항법 표류 → 불확실도↑ → RELOCALIZE/감속",
    "R-03 엔코더 고착": "GAP: fw 는 고착 센서 판별 없음(fault_test 의 stale gap 과 동뿌리)",
    "R-04 IMU 편향": "자세오차↑ → 위치오차↑ → 재정렬 경향",
    "R-05 GPS 지연·누락": "추측항법·불확실도↑ → 오래된 관측으로 확정 안 함",
    "R-06 경로 암석(장애물)": "fw AVOID 는 collision≥0.8(~0.5m) 근접 반사 — 경로 회피는 항법 몫(fw 밖)",
    "R-06b 암석+모션층 회피": "행동제어(모션층) 퍼텐셜필드가 부드럽게 우회 — fw Action 무관(조향은 어댑터)",
    "R-07 통신 단절(RTA 영역)": "fw 밖 — 링크 실패안전은 RTA/RTL(HW_DESIGN §3.3), fw 입력 아님",
    "R-08a 순간 가짜표적": "시간적 확인이 거른다 → 확정 안 함",
    "R-08b 지속 가짜표적": "GAP: 지속 가짜는 시간·운동 통과 → 생체(UAV 전용) 없이 확정될 수 있음",
    "R-09 도랑 빠짐(복구 없음)": "복구 없으면 헛돎·미도달(fw 는 immobilization 을 모른다)",
    "R-09b 도랑+모션층 복구": "모션 층이 VO 로 헛돎 검출 → 후진·선회·우회 복구 → 도달(fw 불변)",
}


def main():
    print("로버 SITL — fw(실 libfw.so) 결정을 로버 물리·고장에서 잰다. L2 운동학-경량(Gazebo/ROAMS 아님).\n")
    print("%-22s | %6s %5s %6s %5s %5s | 기대(정직)" % ("시나리오", "이동m", "도달", "우세행동", "복구", "가짜"))
    print("-" * 126)
    for name, sc in SCENARIOS.items():
        r = run_scenario(sc)
        rc = "t=%d" % r["reached"] if r["reached"] is not None else "—"
        fc = "예" if r["false_confirm"] else "—"
        mo = (" [암석최근접 %.1fm]" % r["min_obst"]) if r["min_obst"] is not None else ""
        print("%-22s | %6.1f %5s %6s %5d %5s | %s%s" % (name, r["progress"], rc, r["top"], r["n_recover"], fc, EXPECT[name], mo))
    print("\n지표: 이동m=실제 참 이동거리 · 도달=목표 1.5m 내 · 우세행동=최다 fw Action · 복구=모션층 immobilization 복구 발동수 · 가짜=목표없이 확정")
    print("정직: 물리는 L2 운동학-경량. 고충실도(토양-바퀴 동역학·slip/sinkage)는 Gazebo Harmonic+ROS2 / ROAMS 참조(fw/ROVER_VALIDATION.md).")


if __name__ == "__main__":
    main()
