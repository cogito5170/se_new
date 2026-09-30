"""시험장 세계: 참값 고도(0.05 m), 지반 종류(슬립·요 효율), GNSS 가림, 통신 품질, 동적 장애물.
전부 절차적으로 만든다. 이것은 **실제 지형 데이터가 아니다** -- 실험 전 논리 검증용 가상 시험장이다."""
import numpy as np
from scipy.ndimage import gaussian_filter

KIND = {0: "지면", 1: "바위", 2: "벽", 3: "모래", 4: "진흙", 5: "도랑", 6: "경사", 7: "덤불"}
KIND_COLOR = {0: (0.55, 0.50, 0.40), 1: (0.45, 0.45, 0.47), 2: (0.62, 0.60, 0.58), 3: (0.85, 0.76, 0.52),
              4: (0.38, 0.30, 0.22), 5: (0.30, 0.26, 0.22), 6: (0.50, 0.55, 0.38), 7: (0.30, 0.45, 0.25)}


class World:
    def __init__(self, size=30.0, res=0.05, seed=0):
        self.size, self.res = size, res
        self.n = int(round(size / res))
        self.rng = np.random.default_rng(seed)
        n = self.n
        self.h = np.zeros((n, n), np.float32)          # h[ix, iy]
        self.kind = np.zeros((n, n), np.uint8)
        self.slip = np.full((n, n), 0.03, np.float32)  # 종방향 기본 슬립
        self.chi = np.full((n, n), 0.80, np.float32)   # 스키드 조향 요 효율(유효 윤거 = B/chi)
        self.gnss_block = np.zeros((n, n), bool)
        self.comm_shadow = []                          # (x0,y0,x1,y1, bw_bps, latency_s)
        self.dyn = []                                  # 동적 장애물
        self.base = (3.0, 15.0)
        self.start_yaw = 0.0
        self.region = (1.0, 1.0, size - 1.0, size - 1.0)
        self.notes = []

    # ---- 좌표 ----
    def idx(self, x, y):
        return (np.clip((np.asarray(x) / self.res).astype(int), 0, self.n - 1),
                np.clip((np.asarray(y) / self.res).astype(int), 0, self.n - 1))

    def height(self, x, y):
        i, j = self.idx(x, y)
        return self.h[i, j]

    def mask_rect(self, x0, y0, x1, y1):
        i0, j0 = self.idx(x0, y0); i1, j1 = self.idx(x1, y1)
        m = np.zeros((self.n, self.n), bool); m[i0:i1 + 1, j0:j1 + 1] = True
        return m

    def grid_xy(self):
        c = (np.arange(self.n) + 0.5) * self.res
        return np.meshgrid(c, c, indexing="ij")

    # ---- 지형 조각 ----
    def rough(self, amp, scale):
        r = gaussian_filter(self.rng.standard_normal((self.n, self.n)), scale / self.res)
        r /= (np.abs(r).max() + 1e-9)
        self.h += (amp * r).astype(np.float32)

    def rock(self, x, y, r, hgt):
        X, Y = self.grid_xy()
        d2 = (X - x) ** 2 + (Y - y) ** 2
        bump = hgt * np.clip(1 - d2 / r ** 2, 0, None) ** 0.5
        m = bump > 0.02
        self.h = np.maximum(self.h, (self.h + bump).astype(np.float32) * m + self.h * ~m)
        self.kind[m] = 1

    def box(self, x0, y0, x1, y1, hgt, kind=2):
        m = self.mask_rect(x0, y0, x1, y1)
        self.h[m] = np.maximum(self.h[m], hgt); self.kind[m] = kind

    def ditch(self, x0, y0, x1, y1, depth):
        m = self.mask_rect(x0, y0, x1, y1)
        self.h[m] -= depth; self.kind[m] = 5

    def hill(self, x, y, r, hgt):
        X, Y = self.grid_xy()
        d = np.sqrt((X - x) ** 2 + (Y - y) ** 2)
        bump = hgt * np.clip(1 - d / r, 0, None)             # 원뿔: 경사 = atan(hgt/r)
        bump = gaussian_filter(bump, 0.3 / self.res)
        self.h += bump.astype(np.float32); self.kind[bump > 0.05] = 6

    def soil(self, x0, y0, x1, y1, slip, chi, kind):
        m = self.mask_rect(x0, y0, x1, y1)
        self.slip[m] = slip; self.chi[m] = chi; self.kind[m] = kind

    def fence(self, hgt=1.0):
        """임무 구역 바깥 경계를 벽으로 둘러 참값 세계를 닫는다."""
        t = 0.3
        s = self.size
        for r in ((0, 0, s, t), (0, s - t, s, s), (0, 0, t, s), (s - t, 0, s, s)):
            self.box(*r, hgt)

    def dyn_h(self, t):
        """시각 t 의 동적 장애물 (x, y, r, hgt) 목록."""
        out = []
        for d in self.dyn:
            if not (d["t0"] <= t <= d["t1"]):
                continue
            P = np.asarray(d["path"], float)
            seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
            L = seg.sum(); s = (d["v"] * (t - d["t0"])) % (2 * L)
            s = s if s <= L else 2 * L - s                           # 왕복
            k = np.searchsorted(np.cumsum(seg), s)
            k = min(k, len(seg) - 1)
            s0 = np.cumsum(seg)[k] - seg[k]
            p = P[k] + (P[k + 1] - P[k]) * ((s - s0) / max(seg[k], 1e-9))
            out.append((p[0], p[1], d["r"], d["h"]))
        return out

    def comm(self, x, y):
        """(대역폭 bps, 지연 s). 기지에서 멀수록 줄고 음영 구역에서 급감."""
        d = np.hypot(x - self.base[0], y - self.base[1])
        bw, lat = 4e6 * np.clip(1 - d / 60, 0.1, 1), 0.05
        for x0, y0, x1, y1, b, l in self.comm_shadow:
            if x0 <= x <= x1 and y0 <= y <= y1:
                bw, lat = b, l
        return bw, lat
