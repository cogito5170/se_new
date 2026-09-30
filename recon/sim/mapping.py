"""2.5D 고도 지도(셀마다 칼만 평균·분산·관측수·시각·신뢰) + 자세 불확실도 팽창 + 압축 파이프라인."""
import math
import zlib

import numpy as np

VAR0 = 1.0          # 미지 셀 분산 (m^2)
SIG_TARGET = 0.05   # '안다' 기준 σ (m)


class ElevationMap:
    def __init__(self, size=30.0, res=0.10):
        self.res, self.n = res, int(round(size / res))
        n = self.n
        self.h = np.zeros((n, n), np.float32)
        self.var = np.full((n, n), VAR0, np.float32)
        self.cnt = np.zeros((n, n), np.uint16)
        self.t = np.full((n, n), -1.0, np.float32)
        self.hmax = np.full((n, n), -9.0, np.float32)
        self.changed = np.zeros((n, n), bool)
        self.points_in = 0

    def known(self, sig=0.3):
        return self.var < sig ** 2

    def conf(self):
        return np.clip(1 - np.sqrt(self.var) / 0.2, 0, 1)

    def entropy_bits(self, region=None):
        v = self.var if region is None else self.var[region]
        return float(0.5 * np.log2(v / 1e-4).sum())

    def integrate(self, P, sig_att, pose_P, sig_r, t):
        """P: 추정 자세로 세계 좌표로 옮긴 점[N,3] (센서 원점 기준 거리 포함 → 4번째 열).
        측정 분산 = LiDAR 잡음 + (거리·자세각 σ)^2 + 자세 z σ^2 + (지형 기울기·자세 xy σ)^2  (Fankhauser 식의 단순형)."""
        if P is None or len(P) == 0:
            return
        x, y, z, r = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
        i = (x / self.res).astype(int); j = (y / self.res).astype(int)
        ok = (i >= 0) & (i < self.n) & (j >= 0) & (j < self.n)
        i, j, z, r = i[ok], j[ok], z[ok], r[ok]
        self.points_in += len(z)
        s_xy2 = pose_P[0, 0] + pose_P[1, 1]
        s_th2 = pose_P[2, 2]
        gi = np.clip(i, 1, self.n - 2); gj = np.clip(j, 1, self.n - 2)
        kn = self.var[gi, gj] < 0.05
        slope = np.where(kn, np.hypot(self.h[gi + 1, gj] - self.h[gi - 1, gj], self.h[gi, gj + 1] - self.h[gi, gj - 1]) / (2 * self.res), 0.3)
        # 독립 성분(점마다 다른 거리 잡음)은 점 수로 줄고, 상관 성분(이 프레임의 자세·자세각 오차)은 안 준다.
        v_ind = np.full_like(z, sig_r ** 2)
        v_cor = (r * sig_att) ** 2 + 0.01 ** 2 + slope ** 2 * (s_xy2 + (r ** 2) * s_th2) + (slope * self.res / 2) ** 2
        lin = i * self.n + j
        w = 1 / v_ind
        W = np.bincount(lin, w, self.n * self.n)
        Z = np.bincount(lin, w * z, self.n * self.n)
        C = np.bincount(lin, None, self.n * self.n)
        VC = np.bincount(lin, v_cor, self.n * self.n)
        zmax = np.full(self.n * self.n, -9.0); np.maximum.at(zmax, lin, z)
        zmin = np.full(self.n * self.n, 9.0); np.minimum.at(zmin, lin, z)
        u = np.nonzero(C)[0]
        zm = Z[u] / W[u]
        vm = (1 / W[u]) * C[u] / np.minimum(C[u], 4) + VC[u] / C[u]   # 독립: 유효 표본 ≤ 4 · 상관: 평균, 안 줄어듦
        vert = (zmax[u] - zmin[u]) > 0.10                            # 수직 구조(벽 면) → 최고값을 쓴다
        zm = np.where(vert, zmax[u], zm)
        hf, vf = self.h.reshape(-1), self.var.reshape(-1)
        h0, v0 = hf[u], vf[u]
        new = v0 >= VAR0 * 0.999
        d = np.abs(zm - h0)
        chg = (~new) & (v0 < 0.05) & (d > 3 * np.sqrt(v0 + vm) + 0.05)          # 변화(동적 물체·오정합)
        v0 = np.where(chg, v0 + d ** 2, v0)
        hn = np.where(new, zm, (h0 * vm + zm * v0) / (v0 + vm))
        vn = np.where(new, vm, v0 * vm / (v0 + vm))
        hf[u] = hn; vf[u] = np.maximum(vn, 1e-4)
        self.cnt.reshape(-1)[u] = np.minimum(self.cnt.reshape(-1)[u] + C[u].astype(np.uint16), 60000)
        self.t.reshape(-1)[u] = t
        self.hmax.reshape(-1)[u] = np.maximum(self.hmax.reshape(-1)[u], zmax[u])
        self.changed.reshape(-1)[u] = True
        self.n_changed_last = int(chg.sum())

    def footprint(self, x, y, yaw, z, sig=0.02, t=0.0):
        """바퀴가 닿은 몸체 아래 셀: 바로 아래는 LiDAR 사각(반경 0.47 m)이지만 바퀴 접지로 높이를 안다.
        이것이 없으면 로버 발밑이 영원히 '미지' 라 프런티어가 제자리를 가리킨다(B03 실측)."""
        c, s_ = np.cos(yaw), np.sin(yaw)
        for dx in np.arange(-0.25, 0.26, 0.05):
            for dy in np.arange(-0.22, 0.23, 0.05):
                i = int((x + c * dx - s_ * dy) / self.res); j = int((y + s_ * dx + c * dy) / self.res)
                if 0 <= i < self.n and 0 <= j < self.n and self.var[i, j] > sig ** 2:
                    v0 = self.var[i, j]
                    if v0 >= VAR0 * 0.999:
                        self.h[i, j] = z; self.var[i, j] = sig ** 2
                    else:
                        self.h[i, j] = (self.h[i, j] * sig ** 2 + z * v0) / (v0 + sig ** 2); self.var[i, j] = v0 * sig ** 2 / (v0 + sig ** 2)
                    self.cnt[i, j] += 1; self.t[i, j] = t

    def age(self, dt, q=2e-6):
        """시간에 따른 분산 성장(동적 환경 가정). 이미 아는 셀만."""
        k = self.var < VAR0 * 0.999
        self.var[k] = np.minimum(self.var[k] + q * dt, VAR0 * 0.99)

    def traversability(self):
        """위험 0..1: 기울기(25° 에서 1) · 계단(5 cm 에서 0.9) · 불확실도. 미지 = 0.35.
        계단·기울기는 **불확실도를 뺀 나머지**만 센다: |Δh| - 2·√(σa²+σb²). 첫 판은 먼 셀의 잡음이
        가짜 계단이 되어 지도의 42 % 를 치명으로 만들었다(측정: T01 60 s)."""
        h, v = self.h, self.var
        sd = np.sqrt(v)
        step = np.zeros_like(h); slope = np.zeros_like(h)
        for ax in (0, 1):
            for sh in (1, -1):
                hn = np.roll(h, sh, ax); sn = np.roll(sd, sh, ax)
                d = (h - hn) - 2 * np.sqrt(sd ** 2 + sn ** 2)       # 높은 쪽 셀에만 계단을 매긴다(벽 셀 · 도랑 가장자리)
                both = (sd < 0.3) & (sn < 0.3)
                d = np.where(both, np.maximum(d, 0), 0)
                step = np.maximum(step, d)
        gx = np.zeros_like(h); gy = np.zeros_like(h)
        gx[1:-1] = (h[2:] - h[:-2]) / (2 * self.res); gy[:, 1:-1] = (h[:, 2:] - h[:, :-2]) / (2 * self.res)
        wallish = (np.abs(gx) > 1.0) | (np.abs(gy) > 1.0)          # 45° 넘는 기울기는 경사가 아니라 계단(위에서 따로 잰다)
        gx = np.where(wallish, 0, gx); gy = np.where(wallish, 0, gy)
        from scipy.ndimage import uniform_filter
        slope_s = np.degrees(np.arctan(np.hypot(uniform_filter(gx, 3), uniform_filter(gy, 3))))   # 0.3 m 창 경사
        # 첫 판: 0.5 m 창이 벽 계단을 경사로 번지게 하고 계단을 양쪽 셀에 매겨 벽마다 ~0.4 m 가 치명이 됐다
        # -> 1.2 m 틈도 계획상 막혔다(P06).
        risk = np.maximum(slope_s / 25.0, np.minimum(step / 0.05, 1.0) * 0.9)
        risk = np.where(sd < 0.05, risk, np.maximum(risk * np.clip(0.05 / sd, 0, 1), 0.3))
        known = v < 0.09
        risk = np.where(known, risk, 0.35)
        return np.clip(risk, 0, 1).astype(np.float32), known


# ---------------------------------------------------------------- 압축
def encode_full_float(m):
    return m.h.tobytes() + m.var.tobytes() + m.cnt.tobytes() + m.t.tobytes()


def q_height(h):
    return np.clip(np.round(h / 0.01), -32768, 32767).astype(np.int16)          # 1 cm


def q_sigma(var):
    s = np.sqrt(var)
    return np.clip(np.round((np.log2(s / 0.005)) * 32), 0, 255).astype(np.uint8)   # 로그 σ, 5 mm..1 m, 약 2 % 단계


def dq_sigma(q):
    return (0.005 * 2 ** (q.astype(np.float32) / 32)) ** 2


class TileCoder:
    """결정에 쓰이는 정보만 보낸다: 16x16 셀 타일 · 1 cm 고도 · 로그 σ · 직전 전송본 대비 델타 · zlib.
    우선순위 = 타일의 정보 이득(bits) / 바이트, 대역 예산 안에서 높은 것부터."""

    def __init__(self, n, tile=16):
        self.n, self.T = n, tile
        self.sent_h = np.zeros((n, n), np.int16)
        self.sent_s = np.full((n, n), 255, np.uint8)
        self.sent_var = np.full((n, n), VAR0, np.float32)
        self.bytes_total = 0
        self.bits_total = 0.0

    def candidates(self, m):
        qh, qs = q_height(m.h), q_sigma(m.var)
        out = []
        T = self.T
        for a in range(0, self.n, T):
            for b in range(0, self.n, T):
                sh, ss = qh[a:a + T, b:b + T], qs[a:a + T, b:b + T]
                dh = sh.astype(np.int32) - self.sent_h[a:a + T, b:b + T]
                ds = ss.astype(np.int32) - self.sent_s[a:a + T, b:b + T]
                mask = (np.abs(dh) >= 2) | (np.abs(ds) >= 8)            # 2 cm 또는 σ 19 % 이상 바뀐 셀만
                if not mask.any():
                    continue
                v_new = m.var[a:a + T, b:b + T]; v_old = self.sent_var[a:a + T, b:b + T]
                gain = float(0.5 * np.log2(np.maximum(v_old, 1e-4) / np.maximum(v_new, 1e-4))[mask].clip(0).sum())
                payload = np.packbits(mask).tobytes() + dh[mask].astype(np.int16).tobytes() + ds[mask].astype(np.int16).tobytes()
                blob = zlib.compress(payload, 6)
                out.append((gain / (len(blob) + 6), gain, a, b, mask, sh, ss, len(blob) + 6))
        out.sort(key=lambda c: -c[0])
        return out

    def send(self, m, budget_bytes):
        sent, bits = 0, 0.0
        for dens, gain, a, b, mask, sh, ss, nb in self.candidates(m):
            if sent + nb > budget_bytes:
                continue
            T = self.T
            self.sent_h[a:a + T, b:b + T][mask] = sh[mask]
            self.sent_s[a:a + T, b:b + T][mask] = ss[mask]
            self.sent_var[a:a + T, b:b + T][mask] = m.var[a:a + T, b:b + T][mask]
            sent += nb; bits += gain
        self.bytes_total += sent; self.bits_total += bits
        return sent, bits

    def reconstruct(self):
        return self.sent_h.astype(np.float32) * 0.01, dq_sigma(self.sent_s)


def compression_table(m, raw_points_bytes, truth_h=None):
    """같은 지도를 여러 표현으로 부호화해 크기와 오차를 잰다(지도 최종 상태 기준)."""
    known = m.var < 0.09
    rows = []
    full = encode_full_float(m)
    rows.append(("원시 점 로그 (Mid-360 26 B/점, 실 점률 환산)", raw_points_bytes, 0.0, 0.0))
    rows.append(("격자 float32 전부 (h,var,cnt,t)", len(full), 0.0, 0.0))
    qh, qs = q_height(m.h), q_sigma(m.var)
    blob = zlib.compress(qh.tobytes() + qs.tobytes(), 9)
    eh = np.sqrt(np.mean((qh[known] * 0.01 - m.h[known]) ** 2))
    es = np.sqrt(np.mean((np.sqrt(dq_sigma(qs[known])) - np.sqrt(m.var[known])) ** 2))
    rows.append(("양자화(1 cm·로그σ 8bit)+zlib", len(blob), eh, es))
    kb = np.packbits(known).tobytes()
    blob2 = zlib.compress(kb + qh[known].tobytes() + qs[known].tobytes(), 9)
    rows.append(("+ 아는 셀만(마스크)", len(blob2), eh, es))
    # 8 cm 양자화 (거친 판)
    qh8 = np.round(m.h / 0.08).astype(np.int16)
    blob3 = zlib.compress(kb + qh8[known].tobytes() + (qs[known] // 16).astype(np.uint8).tobytes(), 9)
    eh8 = np.sqrt(np.mean((qh8[known] * 0.08 - m.h[known]) ** 2))
    es8 = np.sqrt(np.mean((np.sqrt(dq_sigma((qs[known] // 16) * 16 + 8)) - np.sqrt(m.var[known])) ** 2))
    rows.append(("거친 양자화(8 cm·σ 4bit) — 비교용", len(blob3), eh8, es8))
    # 복셀(0.1 m) 점유 — 옥트리 잎 수로 근사
    vox = int(known.sum() * 2)
    rows.append(("복셀 0.1 m 점유(잎당 4 B 근사)", vox * 4, 0.05 / math.sqrt(3), float("nan")))
    return rows
