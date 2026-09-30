"""자세 추정기 네 가지(필터 비교용)와 LIO 의사측정 모델.

  F1 odom     : 엔코더 추측항법(요 = 좌우 속도차 / 보정된 유효윤거)
  F2 odom+gyro: 엔코더 속도 + 자이로 요율 (편향 고정 보정)
  F3 EKF+LIO  : F2 예측 + LIO 자세 갱신, 고정 Q
  F4 제안     : F3 + 자이로 편향 상태 + 슬립 적응 Q(엔코더↔LIO 속도 불일치로 Q 팽창) + 카이제곱 게이트 + GNSS

LIO(예: FAST-LIO2)는 여기서 돌리지 않는다. **정직한 대용**: 참 자세 + 누적 표류(거리의 0.3 %) +
관측된 점들의 면 법선으로 만든 정보행렬에서 나온 백색 잡음. 평평한 들판처럼 수평 법선이 없으면
x·y 불확실도가 커진다(실제 LIO 의 퇴화와 같은 방향). 이 모델은 실 LIO 로 TEST-05 에서 교체·검증한다."""
import math

import numpy as np

from rover import R_W, B


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class LIOModel:
    def __init__(self, rng):
        self.rng = rng
        self.err = np.zeros(3)
        self.last_d = 0.0

    def measure(self, rover, world, pts_world_true, degraded):
        """반환 (z[3], Rcov[3x3]) 또는 None."""
        if pts_world_true is None or len(pts_world_true) < 50:
            return None
        ds = rover.dist - self.last_d; self.last_d = rover.dist
        self.err[:2] += 0.003 * ds * self.rng.standard_normal(2)
        self.err[2] += math.radians(0.02) * ds * self.rng.standard_normal()
        # 정보행렬: 수평 법선 성분 (지형 기울기에서)
        P = pts_world_true[:: max(1, len(pts_world_true) // 600)]
        hx = (world.height(P[:, 0] + 0.1, P[:, 1]) - world.height(P[:, 0] - 0.1, P[:, 1])) / 0.2
        hy = (world.height(P[:, 0], P[:, 1] + 0.1) - world.height(P[:, 0], P[:, 1] - 0.1)) / 0.2
        nz = 1 / np.sqrt(1 + hx ** 2 + hy ** 2)
        n = np.stack([-hx * nz, -hy * nz], 1)
        H = (n.T @ n) / 0.02 ** 2 / 40.0 + np.eye(2) * 1.0      # 상관 보정 /40, 사전 1 m^-2 [A]
        Cxy = np.linalg.inv(H)
        s_th = math.radians(0.3) if np.linalg.eigvalsh(H).min() > 50 else math.radians(2.0)
        k = 3.0 if degraded else 1.0
        C = np.zeros((3, 3)); C[:2, :2] = Cxy * k ** 2 + np.eye(2) * 0.02 ** 2; C[2, 2] = (s_th * k) ** 2
        w = self.rng.multivariate_normal(np.zeros(3), C)
        z = np.array([rover.x, rover.y, rover.yaw]) + self.err + w
        z[2] = wrap(z[2])
        return z, C


class Estimator:
    def __init__(self, kind, x, y, yaw, chi_nom=0.80, gyro_bias0=0.0):
        self.kind = kind
        self.s = np.array([x, y, yaw, gyro_bias0], float)
        self.P = np.diag([0.01 ** 2, 0.01 ** 2, math.radians(1) ** 2, math.radians(0.1) ** 2])
        self.chi = chi_nom
        self.slip_est = 0.0
        self.prev_lio = None
        self.v_enc = 0.0
        self.rej = 0
        self.use_gyro = kind != "odom"
        self.enc_ok = np.ones(4, bool)
        self.win = []
        self.odo_d = 0.0
        self.resets = 0
        self.slip_unobs = False

    def predict(self, dticks, gz, dt, imu_ok):
        m_per_tick = 2 * math.pi * R_W / 3200
        d = dticks * m_per_tick
        ok = self.enc_ok
        dl = d[:2][ok[:2]].mean() if ok[:2].any() else np.nan
        dr = d[2:][ok[2:]].mean() if ok[2:].any() else np.nan
        if np.isnan(dl) or np.isnan(dr):
            dl = dr = 0.0
        ds = (dl + dr) / 2
        self.v_enc = ds / dt
        self.odo_d += abs(ds)
        if self.use_gyro and imu_ok:
            dth = (gz - self.s[3]) * dt
            s_th = math.radians(0.02) * math.sqrt(dt) + 0.0
        else:
            dth = (dr - dl) / B * self.chi
            s_th = abs(dr - dl) / B * 0.25 + 1e-5
        th = self.s[2] + dth / 2
        self.s[0] += ds * math.cos(th); self.s[1] += ds * math.sin(th); self.s[2] = wrap(self.s[2] + dth)
        k_slip = 0.03 + (2.0 * self.slip_est if self.kind == "proposed" else 0.0)
        if self.kind == "proposed" and self.slip_unobs:
            k_slip = max(k_slip, 0.20)                           # 슬립을 못 재는 동안은 주행거리를 20 % 까지 의심한다
        s_ds = abs(ds) * k_slip + 1e-5
        F = np.eye(4); F[0, 2] = -ds * math.sin(th); F[1, 2] = ds * math.cos(th)
        if self.use_gyro and imu_ok:
            F[2, 3] = -dt
        Q = np.diag([(s_ds * math.cos(th)) ** 2 + 1e-8, (s_ds * math.sin(th)) ** 2 + 1e-8, s_th ** 2,
                     (math.radians(0.002) ** 2 * dt if self.kind == "proposed" else 0.0)])
        self.P = F @ self.P @ F.T + Q

    def update_lio(self, z, C, dt_since):
        if self.kind in ("odom", "odom_gyro"):
            return
        # 슬립 추정: 1 s 창의 LIO 변위 vs 엔코더 변위 (0.1 s 미분은 LIO 잡음을 슬립으로 읽었다: 참 0.04 에 0.21)
        if math.sqrt(C[0, 0] + C[1, 1]) > 0.05:              # LIO 가 퇴화(평평한 들판)면 슬립을 못 잰다 -> 창을 비우고 감쇠
            self.win = []; self.slip_est *= 0.9; self.slip_unobs = True
        else:
            self.slip_unobs = False
        self.win.append((z[0], z[1], self.odo_d))
        if len(self.win) > 10:
            x0, y0, d0 = self.win.pop(0)
            d_lio = math.hypot(z[0] - x0, z[1] - y0); d_enc = self.odo_d - d0
            if d_enc > 0.12:
                s = float(np.clip(1 - d_lio / d_enc, 0, 1))
                self.slip_est += 0.5 * (s - self.slip_est)
            else:
                self.slip_est *= 0.8
        self.prev_lio = z.copy()
        Hm = np.zeros((3, 4)); Hm[0, 0] = Hm[1, 1] = Hm[2, 2] = 1
        y = z - self.s[:3]; y[2] = wrap(y[2])
        Sm = Hm @ self.P @ Hm.T + C
        nis = float(y @ np.linalg.solve(Sm, y))
        if self.kind == "proposed" and nis > 16.3:            # 3자유도 99.9 %
            self.rej += 1
            if self.rej < 3:
                return
            # 세 번 연속 기각 = 이상치가 아니라 필터가 발산한 것이다(첫 판: σ 0.9 cm 인데 실제 오차 3.3 m 로
            # 좋은 LIO 를 계속 버렸다). 공분산을 혁신 크기만큼 부풀려 받아들인다.
            self.P[0, 0] += y[0] ** 2; self.P[1, 1] += y[1] ** 2; self.P[2, 2] += y[2] ** 2
            self.resets += 1
            Sm = Hm @ self.P @ Hm.T + C
        self.rej = 0
        K = self.P @ Hm.T @ np.linalg.inv(Sm)
        self.s += K @ y; self.s[2] = wrap(self.s[2])
        self.P = (np.eye(4) - K @ Hm) @ self.P
        if self.kind != "proposed":
            self.s[3] = 0.0

    def update_gnss(self, z, s):
        if self.kind != "proposed":
            return
        Hm = np.zeros((2, 4)); Hm[0, 0] = Hm[1, 1] = 1
        y = np.array(z) - self.s[:2]
        Sm = Hm @ self.P @ Hm.T + np.eye(2) * s ** 2
        if float(y @ np.linalg.solve(Sm, y)) > 13.8:
            return
        K = self.P @ Hm.T @ np.linalg.inv(Sm)
        self.s += K @ y
        self.P = (np.eye(4) - K @ Hm) @ self.P

    @property
    def sigma(self):
        return float(math.sqrt(max(self.P[0, 0] + self.P[1, 1], 0)))
