"""유도(guidance): 비용지도 + Dijkstra/A* 경로 + 후보 목적함수 J + 순수추종(pure pursuit).
목적함수 (kbit):
    U(g) = IG(g) - λ_E·E(g) - λ_T·T(g) - λ_R·R(g)
    IG(g)  = Σ_c K(|c-g|) · g_c,   g_c = ½ log2( max(σ_c², σ_t²) / max(σ_c,post², σ_t²) )   -- 목표 σ_t 아래로는 가치 0
    E(g)   = 경로 에너지 [Wh] (기저 22 W + 구동, 경사 반영) ,  T(g) = 경로 시간 [s],  R(g) = 경로 최대 위험
    C 커널에 넘길 때 J = U / (U + U0)  (0..1)
모든 항은 지도(= 시뮬 LiDAR 원시점에서 만든 것)와 경로 탐색 결과에서 계산된다."""
import math

import numpy as np
from scipy.ndimage import binary_dilation, maximum_filter
from scipy.signal import fftconvolve
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

from mapping import SIG_TARGET

LAM_E, LAM_T, LAM_R, U0 = 2.0, 0.10, 5.0, 5.0      # [A] 튜닝 가중: kbit/Wh, kbit/s, kbit/위험, 정규화 kbit
V_NOM = 0.40
P_BASE = 22.0
SIG_MEAS2 = 0.03 ** 2


class Planner:
    def __init__(self, mp, region, cres=0.2):
        self.m, self.cres = mp, cres
        self.f = int(round(cres / mp.res))
        self.nc = mp.n // self.f
        self.region = region
        c = (np.arange(self.nc) + 0.5) * cres
        self.CX, self.CY = np.meshgrid(c, c, indexing="ij")
        x0, y0, x1, y1 = region
        self.inreg = (self.CX > x0) & (self.CX < x1) & (self.CY > y0) & (self.CY < y1)
        self.penalty = np.zeros((self.nc, self.nc), np.float32)       # AVOID 가 칠하는 벌점
        r = np.arange(-40, 41) * cres
        RX, RY = np.meshgrid(r, r, indexing="ij"); RR = np.hypot(RX, RY)
        self.K = np.where((RR >= 0.5) & (RR <= 8.0), np.exp(-(RR / 4.0) ** 2), 0.0)
        self.Kd = np.where((RR >= 0.5) & (RR <= 10.0), np.exp(-(RR / 6.0) ** 2), 0.0)   # 정지 스캔(비반복 패턴 누적)
        self.dist = self.pred = None
        self.st2 = np.full((mp.n, mp.n), SIG_TARGET ** 2, np.float32)   # 셀별 목표 σ² (임무가 정한다: 관심구역은 더 엄격)

    def set_aoi(self, x0, y0, x1, y1, sig):
        r = self.m.res
        self.st2[int(x0 / r):int(x1 / r), int(y0 / r):int(y1 / r)] = sig ** 2

    def pool(self, a, how):
        f = self.f
        a = a[: self.nc * f, : self.nc * f].reshape(self.nc, f, self.nc, f)
        return a.max((1, 3)) if how == "max" else (a.sum((1, 3)) if how == "sum" else a.min((1, 3)))

    def ci(self, x, y):
        return (int(np.clip(x / self.cres, 0, self.nc - 1)), int(np.clip(y / self.cres, 0, self.nc - 1)))

    def update(self, rx, ry, unknown_ok=True):
        """비용지도 → Dijkstra(로버에서). 반환 없음; self.dist, self.pred, self.risk 갱신."""
        risk, known = self.m.traversability()
        R = self.pool(risk, "max")
        R = np.maximum(R, self.penalty)
        R[~self.inreg] = 1.0
        lethal = R >= 0.8
        lethal = binary_dilation(lethal, iterations=1)                     # 몸체 반폭 여유(0.2 m)
        near = maximum_filter(R, size=3); near2 = maximum_filter(np.where(R >= 0.8, 1.0, 0.0), size=5)
        cost_cell = 1.0 + 3.0 * near + 2.0 * near2                         # 벽 옆 두 칸은 비싸게(스치지 않게)
        if not unknown_ok:
            kn = self.pool(known.astype(np.uint8), "min").astype(bool)
            lethal |= ~kn
        i0, j0 = self.ci(rx, ry)
        lethal[max(0, i0 - 1):i0 + 2, max(0, j0 - 1):j0 + 2] = False          # 자기 자리는 비운다
        n = self.nc
        idx = np.arange(n * n).reshape(n, n)
        rows, cols, w = [], [], []
        for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
            if dj < 0:
                a = idx[0:n - di, -dj:n]; b = idx[di:n, 0:n + dj]
            elif dj > 0:
                a = idx[0:n - di, 0:n - dj]; b = idx[di:n, dj:n]
            else:
                a = idx[0:n - di, :]; b = idx[di:n, :]
            L = math.hypot(di, dj) * self.cres
            ok = ~(lethal.reshape(-1)[a.reshape(-1)] | lethal.reshape(-1)[b.reshape(-1)])
            ww = L * 0.5 * (cost_cell.reshape(-1)[a.reshape(-1)] + cost_cell.reshape(-1)[b.reshape(-1)])
            rows.append(a.reshape(-1)[ok]); cols.append(b.reshape(-1)[ok]); w.append(ww[ok])
        rows, cols, w = np.concatenate(rows), np.concatenate(cols), np.concatenate(w)
        G = coo_matrix((w, (rows, cols)), shape=(n * n, n * n)).tocsr()
        src = idx[i0, j0]
        d, p = dijkstra(G, directed=False, indices=src, return_predecessors=True)
        self.dist = d.reshape(n, n); self.pred = p; self.risk = R; self.lethal = lethal
        self.src = src
        # 경로 기하 거리 근사: 가중 거리 / 평균 비용 대신 별도 무가중 탐색은 비싸서 가중거리로 시간·에너지를 추정
        self.known = known

    def path_to(self, gx, gy):
        n = self.nc
        i, j = self.ci(gx, gy)
        k = i * n + j
        if not np.isfinite(self.dist.reshape(-1)[k]):
            return None
        out = []
        while k != self.src and k >= 0:
            out.append(((k // n + 0.5) * self.cres, (k % n + 0.5) * self.cres)); k = self.pred[k]
        out.reverse()
        return out

    def gain_fields(self):
        v = self.m.var
        vpost = v * SIG_MEAS2 / (v + SIG_MEAS2)
        st2 = self.st2
        vpost = v * (SIG_MEAS2 / 3) / (v + SIG_MEAS2 / 3)             # 한 번 더 지나가며 여러 프레임을 누적
        g = 0.5 * np.log2(np.maximum(v, st2) / np.maximum(vpost, st2))
        unk = v >= 0.09
        gu = self.pool(np.where(unk, g, 0), "sum"); gk = self.pool(np.where(~unk, g, 0), "sum")
        gu[~self.inreg] = 0; gk[~self.inreg] = 0
        IGu = fftconvolve(gu, self.K, mode="same"); IGk = fftconvolve(gk, self.K, mode="same")
        IGd = fftconvolve(gk, self.Kd, mode="same")                       # 정지 스캔: 부분적으로 아는 셀을 40 프레임 누적
        return np.maximum(IGu, 0) / 1000, np.maximum(IGk, 0) / 1000, np.maximum(IGd, 0) / 1000   # kbit

    def objective(self, rx, ry, bat_wh_left, mode="proposed", avoid_xy=None, keep=None):
        """반환 dict: explore/revisit/observe 후보 (J, x, y, U, 항목들) 과 귀환 필요 에너지."""
        IGu, IGk, IGd = self.gain_fields()
        d = self.dist
        T = d / V_NOM                                   # 가중 거리 → 시간(위험 가중 포함; 보수적)
        E = T * (P_BASE + 12.0) / 3600                  # Wh (구동 평균 12 W [A], 시뮬 실측으로 갱신)
        Rk = self.risk
        ok = np.isfinite(d) & self.inreg & (Rk < 0.6) & (d > 0.6) & ~self.lethal     # 목표는 벽 여유대 밖 (첫 판: 벽에 붙은 목표로 가서 끼었다, P06)
        out = {"IGu": IGu, "IGk": IGk}
        for name, IG in (("explore", IGu), ("revisit", IGk)):
            U = IG - LAM_E * E - LAM_T * T - LAM_R * Rk
            U = np.where(ok, U, -np.inf)
            k = np.unravel_index(np.argmax(U), U.shape)
            if keep is not None and keep[0] == name:                     # 이력(hysteresis): 지금 목표가 최고의 80 % 이상이면 유지
                kk = self.ci(keep[1], keep[2])
                if np.isfinite(U[kk]) and U[kk] >= 0.8 * U[k] and U[kk] > 0:
                    k = kk
            u = float(U[k])
            out[name] = dict(U=u, J=(u / (u + U0) if u > 0 else 0.0), x=float(self.CX[k]), y=float(self.CY[k]),
                             IG=float(IG[k]), E=float(E[k]), T=float(T[k]), R=float(Rk[k]))
        i, j = self.ci(rx, ry)
        extra = float(IGd[i, j])
        u = extra - LAM_T * 4.0 - LAM_E * 4.0 * P_BASE / 3600
        out["observe"] = dict(U=u, J=(u / (u + U0) if u > 0 else 0.0), x=rx, y=ry, IG=extra, E=4 * P_BASE / 3600, T=4.0, R=0.0)
        return out


def pure_pursuit(path, x, y, yaw, v_max, look=1.0):
    """경로 → (v, ω, 남은거리). 방향 오차 60° 넘으면 제자리 회전."""
    if not path:
        return 0.0, 0.0, 0.0
    P = np.asarray(path)
    d = np.hypot(P[:, 0] - x, P[:, 1] - y)
    k0 = int(np.argmin(d))
    rest = P[k0:]
    tgt = rest[-1]
    acc = 0.0
    for a, b in zip(rest[:-1], rest[1:]):
        acc += math.hypot(*(b - a))
        if acc >= look:
            tgt = b
            break
    remain = float(np.hypot(*(P[-1] - [x, y])))
    ang = math.atan2(tgt[1] - y, tgt[0] - x) - yaw
    ang = (ang + math.pi) % (2 * math.pi) - math.pi
    if abs(ang) > math.radians(60):
        return 0.0, float(np.clip(1.5 * ang, -0.8, 0.8)), remain
    Ld = max(math.hypot(tgt[0] - x, tgt[1] - y), 0.2)
    kappa = 2 * math.sin(ang) / Ld
    v = v_max / (1 + 0.8 * abs(kappa))
    v = min(v, 0.3 + remain)
    return v, float(np.clip(v * kappa, -1.0, 1.0)), remain
