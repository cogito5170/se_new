"""로버 물리(스키드 조향 + 슬립 + 모터 + 배터리)와 센서 모델(엔코더·IMU·LiDAR·GNSS·카메라).
수치의 출처: recon/spec.py (데이터시트 [조각] 또는 가정 [A]). 모델 자체는 가정이며 TEST-01~05 로 맞춰야 한다."""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spec  # noqa: E402

G = 9.81
M = spec.MECH
MOT = spec.PARTS["motor"]
R_W, B, L = M["wheel_r"], M["track"], M["wheelbase"]
MASS = M["mass_kg"]
K_E = MOT["rated_V"] / (MOT["noload_rpm_24V"] / 60 * 2 * math.pi)       # V/(rad/s) at wheel
R_M = MOT["rated_V"] / MOT["stall_A_24V"]                                # ohm
K_T = MOT["stall_Nm_24V"] / MOT["stall_A_24V"]                           # N·m/A at wheel (incl. gear)
I0 = 0.2                                                                 # no-load current [A]
P_BASE = 12.0 + 6.5 + 1.5 + 2.0                                          # Jetson+LiDAR+MCU/cam+drivers [W]
TICKS = spec.DRIVE["ticks_per_rev"]
C_RR, MU_LAT = 0.05, 0.45                                               # 구름저항, 조향 마찰 [A]
WHEELS = [(+L / 2, +B / 2), (-L / 2, +B / 2), (+L / 2, -B / 2), (-L / 2, -B / 2)]  # FL RL FR RR (좌=+y)


class Battery:
    def __init__(self, soc=1.0):
        p = spec.PARTS["battery"]
        self.cap_Ah, self.soc, self.R = p["Ah"], soc, 0.05
        self.Wh_used = 0.0

    def ocv(self):
        s = self.soc
        return 4 * (3.0 + 1.2 * s - 0.35 * (1 - s) ** 6 + 0.1 * math.sin(math.pi * s))   # 4S, 12.0-16.8 V 근사

    def draw(self, P, dt):
        V = self.ocv()
        I = P / max(V, 1)
        Vt = V - I * self.R
        self.soc = max(0.0, self.soc - I * dt / 3600 / self.cap_Ah)
        self.Wh_used += P * dt / 3600
        return Vt, I

    def usable(self):
        """정책이 보는 배터리 비율: 가용 85 % 창(SOC 1.0 .. 0.15)을 1..0 으로. spec.E_WH 와 같은 창.
        첫 판은 (soc-0.05)/0.90 이라 만충이 1.055 -> 1 로 잘려 처음 7 Wh 동안 100 % 로 보였다."""
        return float(np.clip((self.soc - 0.15) / 0.85, 0, 1))


class Rover:
    """참 상태. pose=(x,y,yaw), 4 바퀴 각속도, 자세(z, roll, pitch)."""

    def __init__(self, world, x, y, yaw, soc=1.0):
        self.w = world
        self.x, self.y, self.yaw = x, y, yaw
        self.wh = np.zeros(4)                 # 바퀴 각속도 rad/s
        self.ang = np.zeros(4)                # 누적 바퀴 각
        self.v = self.om = 0.0
        self.slip = 0.0
        self.bat = Battery(soc)
        self.relay_on = True
        self.stuck = False
        self.crashed = None
        self.collisions = 0
        self._blocked = False
        self.dist = 0.0
        self.P_motor = 0.0
        self.pose3()

    def contact(self, x, y, yaw):
        c, s = math.cos(yaw), math.sin(yaw)
        pts = [(x + c * dx - s * dy, y + s * dx + c * dy) for dx, dy in WHEELS]
        hs = np.array([self.w.height(px, py) for px, py in pts], float)
        return pts, hs

    def pose3(self):
        _, hs = self.contact(self.x, self.y, self.yaw)
        self.z = float(hs.mean())
        self.pitch = math.atan2(((hs[0] + hs[2]) - (hs[1] + hs[3])) / 2, L)      # 앞이 높으면 +
        self.roll = math.atan2(((hs[0] + hs[1]) - (hs[2] + hs[3])) / 2, B)
        return hs

    def step(self, duty, dt, t):
        """duty[4] in -1..1 (FL RL FR RR). 반환: 이번 스텝 사건 목록."""
        ev = []
        Vb = self.bat.ocv()
        i, j = self.w.idx(self.x, self.y)
        s_terr, chi = float(self.w.slip[i, j]), float(self.w.chi[i, j])
        # 바퀴 부하 토크: 구름 + 경사 + 조향 마찰
        tau_roll = R_W * MASS * G / 4 * (C_RR * math.cos(self.pitch) + math.sin(self.pitch) * np.sign(self.v or 1))
        turn = min(1.0, abs(self.om) / 0.2) if abs(self.om) > 0.02 else 0.0
        tau_turn = R_W * MU_LAT * MASS * G * L / (4 * B) * turn
        P_m = 0.0
        for k in range(4):
            V = float(np.clip(duty[k], -1, 1)) * Vb * (1 if self.relay_on else 0)
            tl = abs(tau_roll) + tau_turn                          # 부하 크기(방향은 전압 부호를 따른다)
            if not self.relay_on:
                w_ss = 0.0
            else:
                I = tl / K_T + I0
                w_ss = (V - np.sign(V) * I * R_M) / K_E if abs(V) > I * R_M else 0.0
                P_m += abs(V * I) if abs(V) > 0.05 else 0.0
            lag = 0.08 if self.relay_on else 0.3
            self.wh[k] += (w_ss - self.wh[k]) * min(1.0, dt / lag)
        self.P_motor = P_m
        Vt, _ = self.bat.draw(P_BASE + P_m, dt)
        # 몸체 운동: 종방향 슬립, 요 효율
        vL = self.wh[:2].mean() * R_W; vR = self.wh[2:].mean() * R_W
        v_w = (vL + vR) / 2
        s = s_terr + 0.9 * max(0.0, math.sin(self.pitch) * np.sign(v_w)) + 0.02 * abs(np.random.standard_normal())
        s = float(np.clip(s, 0, 1))
        v = v_w * (1 - s)
        om = (vR - vL) / B * chi
        if self.stuck:
            v = 0.0; s = 1.0 if abs(v_w) > 0.02 else 0.0
        # 진행 가능성 검사(계단 · 배바닥 · 도랑)
        nx = self.x + v * math.cos(self.yaw) * dt; ny = self.y + v * math.sin(self.yaw) * dt; nyaw = self.yaw + om * dt
        _, h_old = self.contact(self.x, self.y, self.yaw)
        _, h_new = self.contact(nx, ny, nyaw)
        step_up = (h_new - h_old).max()
        belly = self._belly(nx, ny, nyaw)
        dyn_hit = any(math.hypot(nx - dx, ny - dy) < dr + 0.25 for dx, dy, dr, _ in self.w.dyn_h(t))
        if step_up > 0.05 or belly or dyn_hit:                     # 120 mm 바퀴가 못 넘는 5 cm 이상 턱 [A]
            if not self._blocked:
                self.collisions += 1; ev.append("collision")
            self._blocked = True
            v, s = 0.0, (1.0 if abs(v_w) > 0.02 else 0.0)
            if belly or dyn_hit:
                om = 0.0
            nx, ny = self.x, self.y
            if om == 0.0:
                nyaw = self.yaw
        else:
            self._blocked = False
        self.x, self.y, self.yaw = nx, ny, nyaw
        self.v, self.om, self.slip = v, om, s
        self.dist += abs(v) * dt
        self.ang += self.wh * dt
        hs = self.pose3()
        if hs.min() < self.z - 0.18 and self.crashed is None:
            self.crashed = "도랑에 빠짐"; self.stuck = True; ev.append("crash")
        if (abs(self.roll) > math.radians(M["roll_over_deg"]) or abs(self.pitch) > math.radians(M["pitch_over_deg"])) and self.crashed is None:
            self.crashed = "전복"; self.stuck = True; ev.append("crash")
        return ev

    def _belly(self, x, y, yaw):
        """차체 바닥(지상고 6 cm)에 닿는 참 지형이 있는가 -- 바퀴 사이 바위."""
        c, s = math.cos(yaw), math.sin(yaw)
        _, hs = self.contact(x, y, yaw)
        z0 = hs.mean()
        for dx in (-0.1, 0.0, 0.1, 0.2):
            for dy in (-0.1, 0.0, 0.1):
                h = self.w.height(x + c * dx - s * dy, y + s * dx + c * dy)
                if h - z0 > M["ground_clear"] + 0.02:
                    return True
        return False


# ---------------------------------------------------------------- 센서
class Faults:
    """시나리오가 켜는 고장. 각 항목 = (t_start, t_end, 인자)."""

    def __init__(self, **kw):
        self.f = kw

    def on(self, name, t):
        v = self.f.get(name)
        return v is not None and v[0] <= t < v[1]

    def arg(self, name, default=None):
        v = self.f.get(name)
        return v[2] if v is not None and len(v) > 2 else default


class Encoders:
    def __init__(self):
        self.stuck_val = None

    def read(self, rover, faults, t):
        ticks = np.floor(rover.ang / (2 * math.pi) * TICKS).astype(np.int64)
        if faults.on("enc_fail", t):
            k = faults.arg("enc_fail", 0)
            if self.stuck_val is None:
                self.stuck_val = ticks[k]
            ticks[k] = self.stuck_val
        return ticks


class IMU:
    def __init__(self, rng):
        self.rng = rng
        self.bias = math.radians(0.05) * rng.standard_normal()
        self.sig = math.radians(0.0028) * math.sqrt(25)       # rad/s, 25 Hz 대역
        self.sig_tilt = math.radians(0.2)

    def read(self, rover, faults, dt, t):
        self.bias += math.radians(0.002) * math.sqrt(dt) * self.rng.standard_normal()
        drift = 0.0
        if faults.on("imu_drift", t):
            drift = math.radians(faults.arg("imu_drift", 0.03)) * (t - faults.f["imu_drift"][0])   # °/s² 램프
        gz = rover.om + self.bias + drift + self.sig * self.rng.standard_normal()
        return gz, rover.roll + self.sig_tilt * self.rng.standard_normal(), rover.pitch + self.sig_tilt * self.rng.standard_normal()


class Lidar:
    """Mid-360 을 뒤집어 단 것: 고각 -52..+7°. 시뮬은 24고리 x 150방위 = 3600선/프레임
    (실제 20,000점/프레임의 약 1/5.6). 지형 위를 0.05 m 로 행진해 첫 교차를 잡는다."""

    def __init__(self, rng, rings=24, az=150, rmax=12.0, step=0.05):
        self.rng = rng
        el = np.radians(np.linspace(spec.MECH["lidar_fov_deg"][0], spec.MECH["lidar_fov_deg"][1], rings))
        a = np.radians(np.arange(az) * 360.0 / az)
        E, A = np.meshgrid(el, a, indexing="ij")
        self.dirs = np.stack([np.cos(E) * np.cos(A), np.cos(E) * np.sin(A), np.sin(E)], -1).reshape(-1, 3)
        self.r = np.arange(0.2, rmax, step)
        self.n_rays = len(self.dirs)
        self.sig = spec.PARTS["lidar"]["noise_cm"] / 100

    def scan(self, world, rover, faults, t):
        """반환: (센서 좌표 점[N,3], 거리[N]) 또는 None(드롭아웃)."""
        if faults.on("lidar_drop", t):
            return None
        # 센서 자세: 몸체 yaw/pitch/roll + 마스트 높이
        cy, sy = math.cos(rover.yaw), math.sin(rover.yaw)
        cp, sp = math.cos(rover.pitch), math.sin(rover.pitch)
        cr, sr = math.cos(rover.roll), math.sin(rover.roll)
        Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
        Ry = np.array([[cp, 0, -sp], [0, 1, 0], [sp, 0, cp]])       # 앞이 높으면 +pitch
        Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
        R = Rz @ Ry @ Rx
        o = np.array([rover.x + spec.MECH["lidar_x"] * cy, rover.y + spec.MECH["lidar_x"] * sy, rover.z + spec.MECH["lidar_h"]])
        D = self.dirs @ R.T
        P = o[None, None, :] + D[:, None, :] * self.r[None, :, None]        # rays x steps x 3
        i = np.clip((P[..., 0] / world.res).astype(int), 0, world.n - 1)
        j = np.clip((P[..., 1] / world.res).astype(int), 0, world.n - 1)
        H = world.h[i, j]
        for dx, dy, dr, dh in world.dyn_h(t):
            m = ((P[..., 0] - dx) ** 2 + (P[..., 1] - dy) ** 2 < dr ** 2)
            H = np.where(m, np.maximum(H, world.height(dx, dy) + dh), H)
        below = P[..., 2] <= H
        hit = below.any(1)
        k = below.argmax(1)
        rng_ = self.r[k][hit]
        noise = self.sig
        drop = 0.0
        if faults.on("lidar_degrade", t):
            noise *= faults.arg("lidar_degrade", 4.0); drop = 0.35
        rng_ = rng_ + noise * self.rng.standard_normal(rng_.shape)
        dirs_s = self.dirs[hit]
        keep = self.rng.random(len(rng_)) >= drop
        pts = dirs_s[keep] * rng_[keep, None]
        tag = np.zeros(len(pts), bool)
        if faults.on("lidar_degrade", t):         # 먼지: 0.6-2 m 허공 되돌림. Mid-360 은 점마다 신뢰 태그를 준다 -> 80 % 가 '잡음' 태그 [가정]
            nd = int(0.08 * len(pts))
            dd = self.dirs[self.rng.integers(0, self.n_rays, nd)]
            pts = np.vstack([pts, dd * self.rng.uniform(0.6, 2.0, (nd, 1))])
            tag = np.concatenate([tag, self.rng.random(nd) < 0.8])
        return pts.astype(np.float32), R, o, tag

    def expected_ground_rays(self):
        return int((self.dirs[:, 2] < -0.05).sum())


class GNSS:
    def __init__(self, rng):
        self.rng = rng

    def read(self, world, rover, faults, t):
        i, j = world.idx(rover.x, rover.y)
        if faults.on("gnss_loss", t) or world.gnss_block[i, j]:
            return None
        s = 0.02
        return rover.x + s * self.rng.standard_normal(), rover.y + s * self.rng.standard_normal(), s
