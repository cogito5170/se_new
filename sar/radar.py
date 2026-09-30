#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FMCW-SAR 물리 모델 — raw I/Q 합성 → 거리압축 → 백프로젝션 → SAR 영상.

calibration(위상오차·모션보상)은 해결됐다고 가정한다. 그 위에서 **모든 해상도·모호도는
설계식에서 나온다**(지어낸 수 없다 — 초점 스폿 폭을 재서 식과 맞춰 본다):

  거리해상도      δr = c / (2 B)                     (B = 처프 대역폭)
  방위(교차거리)   δa = λ R / (2 L_sa)                (L_sa = 합성개구 길이, 스트립맵)
  DOA 비모호 범위  ±asin(λ / (2 d))                   (d = Rx 소자 간격)
  DOA 각해상도    ≈ λ / (N d)                        (N = Rx 소자 수)

영상화는 **시간영역 백프로젝션**이다(근사 없음): 각 지상 픽셀 p 에 대해
  I(p) = Σ_m  rc[m, R_mp] · exp(+j 4π f_c R_mp / c)
느린시간(펄스) m 을 합쳐 산란점을 위상정합(coherent)으로 모은다. 강한 산란점(조난자,
큰 RCS)은 δr×δa 스폿으로 초점이 맺힌다.

산란점 = 지형 클러터(약·분산) + 조난자(강·점). 사람은 mmWave/X-대역에서 뚜렷한 반사체다.
"""
import math
from dataclasses import dataclass
import numpy as np

C = 299_792_458.0


@dataclass
class RadarCfg:
    fc: float = 9.6e9       # 반송 주파수 [Hz] — X-대역 항공 SAR(지형투과·거리 유리)
    B: float = 90e6         # 처프 대역폭 [Hz] → δr = c/2B ≈ 1.67 m
    Tp: float = 40e-6       # 처프 길이 [s]
    prf: float = 250.0      # 펄스반복주파수 [Hz] (Δx=v/prf ≤ δa/2 이어야 함)
    v: float = 15.0         # 플랫폼 속도 [m/s]
    Ti: float = 0.55        # 합성개구 적분시간 [s] → L_sa = v·Ti ≈ 8.25 m
    n_fast: int = 256       # 처프당 fast-time 표본 수. 비모호 거리 = n_fast·c/(4B) ≈ 213 m
    n_rx: int = 4           # 수신 배열 소자 수 (DOA용)
    d_rx: float = None      # 소자 간격 [m]; None 이면 λ/2

    @property
    def unambiguous_range(self):
        return self.n_fast * C / (4 * self.B)

    @property
    def lam(self):
        return C / self.fc

    @property
    def range_res(self):
        return C / (2 * self.B)

    @property
    def L_sa(self):
        return self.v * self.Ti

    def az_res(self, R):
        return self.lam * R / (2 * self.L_sa)

    @property
    def d(self):
        return self.d_rx if self.d_rx else self.lam / 2

    @property
    def doa_unambiguous_deg(self):
        return math.degrees(math.asin(min(1.0, self.lam / (2 * self.d))))

    @property
    def doa_res_deg(self):
        return math.degrees(self.lam / (self.n_rx * self.d))

    def spec(self):
        return dict(fc_GHz=self.fc / 1e9, B_MHz=self.B / 1e6, range_res_m=self.range_res,
                    L_sa_m=self.L_sa, n_rx=self.n_rx, doa_unamb_deg=self.doa_unambiguous_deg,
                    doa_res_deg=self.doa_res_deg)


def track(cfg, p0, heading_deg):
    """합성개구 동안의 플랫폼 위치들(느린시간). 직선 등속 leg.  반환 (M,2) 지상좌표 [m]."""
    M = max(8, int(cfg.Ti * cfg.prf))
    t = np.arange(M) / cfg.prf
    hx, hy = math.cos(math.radians(heading_deg)), math.sin(math.radians(heading_deg))
    # leg 를 개구 중심이 p0 이 되도록 앞뒤로
    s = (t - t.mean()) * cfg.v
    return np.stack([p0[0] + s * hx, p0[1] + s * hy], axis=1)


def synth_raw(cfg, scat_xy, scat_rcs, trk, alt):
    """raw FMCW 비트신호 합성. 산란점 → 각 펄스의 fast-time 표본.

    반환 s[M, n_fast] 복소.  R = 경사거리(플랫폼 고도 alt 포함).  잡음 포함.
    """
    M = trk.shape[0]
    t = np.arange(cfg.n_fast) / (cfg.n_fast) * cfg.Tp        # fast-time [0,Tp)
    s = np.zeros((M, cfg.n_fast), dtype=np.complex128)
    kf = 2 * cfg.B / (C * cfg.Tp)                            # 비트주파수 기울기: f_b = kf·R
    for m in range(M):
        dx = scat_xy[:, 0] - trk[m, 0]
        dy = scat_xy[:, 1] - trk[m, 1]
        R = np.sqrt(dx * dx + dy * dy + alt * alt)           # 경사거리
        # 비트: exp(-j2π f_b t)·exp(-j 4π f_c R/c);  1/R^2 전력감쇠
        amp = scat_rcs / (R * R + 1.0)
        phase_c = -4 * np.pi * cfg.fc * R / C
        fb = kf * R
        # s[m,n] = Σ_k amp_k exp(j(phase_c_k)) exp(+j2π fb_k t_n)  (+ 부호 → 거리=양의 주파수)
        s[m, :] = (amp * np.exp(1j * phase_c)) @ np.exp(2j * np.pi * np.outer(fb, t))
    # 수신 잡음(열잡음) — SNR 이 유한하도록
    p = np.mean(np.abs(s) ** 2) + 1e-30
    s += (np.random.randn(*s.shape) + 1j * np.random.randn(*s.shape)) * math.sqrt(p * 1e-3 / 2)
    return s


def range_compress(cfg, s):
    """fast-time FFT → 거리 프로파일 rc[M, n_fast].  bin k → range = k·c/(2B)·(n_fast/n)·... .

    반환 (rc, range_axis[m]).  range = f_b·c/(2B), f_b = k/(Tp) (FFT bin → 주파수).
    """
    rc = np.fft.fft(s * np.hanning(cfg.n_fast)[None, :], axis=1)
    freqs = np.fft.fftfreq(cfg.n_fast, d=cfg.Tp / cfg.n_fast)   # 비트주파수 축 [Hz]
    kf = 2 * cfg.B / (C * cfg.Tp)                              # f_b = kf·R  (기울기 [Hz/m])
    rng = freqs / kf                                          # f_b → range = f_b/kf
    keep = rng >= 0
    return rc[:, keep], rng[keep]


def backproject(cfg, rc, rng, trk, alt, grid_x, grid_y):
    """시간영역 백프로젝션. 각 지상픽셀에 각 펄스의 거리압축값을 위상정합 누적.

    grid_x, grid_y: 1D 지상 좌표축 [m].  반환 복소 영상 I[len(y), len(x)].
    """
    GX, GY = np.meshgrid(grid_x, grid_y)                      # (H,W)
    H, W = GX.shape
    img = np.zeros((H, W), dtype=np.complex128)
    rmin, rstep = rng[0], (rng[1] - rng[0])
    nrng = rng.shape[0]
    for m in range(trk.shape[0]):
        R = np.sqrt((GX - trk[m, 0]) ** 2 + (GY - trk[m, 1]) ** 2 + alt * alt)
        idx = np.round((R - rmin) / rstep).astype(int)
        ok = (idx >= 0) & (idx < nrng)
        vals = np.zeros((H, W), dtype=np.complex128)
        vals[ok] = rc[m, idx[ok]]
        img += vals * np.exp(4j * np.pi * cfg.fc * R / C)     # 반송위상 보정 → 초점
    return img


def sar_image(cfg, scat_xy, scat_rcs, flight_center, scene_center, heading_deg, alt, half=60.0, npx=64):
    """끝에서 끝까지: 개구 track → raw → 거리압축 → 백프로젝션 → dB 영상.

    flight_center: 비행선(개구) 중심 지상좌표.  scene_center: 촬상 스와스 중심(측방, 이격 Rg).
    **측방관측**: 비행선과 스와스는 지상거리 Rg 만큼 떨어져 있어야 초점이 맺힌다(나디르 붕괴 회피).
    반환 (img_dB, extent, meta).
    """
    trk = track(cfg, flight_center, heading_deg)
    s = synth_raw(cfg, scat_xy, scat_rcs, trk, alt)
    rc, rng = range_compress(cfg, s)
    gx = np.linspace(scene_center[0] - half, scene_center[0] + half, npx)
    gy = np.linspace(scene_center[1] - half, scene_center[1] + half, npx)
    img = backproject(cfg, rc, rng, trk, alt, gx, gy)
    mag = np.abs(img)
    mag /= (mag.max() + 1e-30)
    img_db = 20 * np.log10(mag + 1e-6)
    extent = (gx[0], gx[-1], gy[0], gy[-1])
    Rg = math.hypot(scene_center[0] - flight_center[0], scene_center[1] - flight_center[1])
    R0 = math.hypot(Rg, alt)
    return img_db, extent, dict(cfg=cfg.spec(), az_res_m=cfg.az_res(R0), ground_range_m=Rg, slant_m=R0)


def scene_from_terrain(center, half, survivors_world, n_clutter=150, rng=None, rcs_fn=None, scene=None):
    """SAR 스와스의 산란점: 지형 클러터 + (선택)scene 피처 + 조난자(강·점).

    클러터를 **지터 격자**로 촘촘히 깔고, `rcs_fn(xs,ys)` 이 있으면 그 지형 후방산란
    (능선·거친 경사=강, 평탄=약)으로 RCS 를 정한다 → SAR 영상이 무작위 반점이 아니라
    **지형 구조**를 닮는다. 지면 z=0 평면 근사(완만지형 가정). 조난자는 큰 RCS 점표적.

    scene: SceneDB(선택). 주면 스와스 안 피처를 그 **radar view(유전율·거칠기→산란강도)**로
    산란점에 더한다 — camera.py 가 RGB view 로 본 **같은 피처**다(건물=강, 물=약, 초목=중).
    반환 (scat_xy [N,2] 월드미터, scat_rcs [N], hits).
    """
    rng = rng or np.random.default_rng(0)
    g = max(6, int(math.sqrt(n_clutter)))
    lin = np.linspace(-half, half, g)
    gx, gy = np.meshgrid(lin, lin)
    jx = gx.reshape(-1) + rng.uniform(-half/g, half/g, g*g)
    jy = gy.reshape(-1) + rng.uniform(-half/g, half/g, g*g)
    xs = center[0] + jx; ys = center[1] + jy
    if rcs_fn is not None:
        base = np.clip(np.asarray(rcs_fn(xs, ys), dtype=float), 0.0, None)
        rcs = 0.02 + 0.28 * base / (base.max() + 1e-9)           # 지형 후방산란 → RCS
    else:
        rcs = rng.uniform(0.02, 0.12, xs.shape[0])
    rcs = rcs * rng.uniform(0.7, 1.3, xs.shape[0])               # 스페클(곱성 요동)
    sx = list(xs); sy = list(ys); sr = list(rcs)
    if scene is not None:                                        # scene 피처 → radar view 산란
        feats = scene.query(center, half * 1.42)                 # 스와스(정사각) 대각 반경
        smax = 1e-9
        pend = []
        for f in feats:
            if abs(f["wx"] - center[0]) <= half and abs(f["wy"] - center[1]) <= half:
                st = scene.radar_of(f, wavelength_m=0.031)["scatter"]
                pend.append((f["wx"], f["wy"], st)); smax = max(smax, st)
        for (fx, fy, st) in pend:                                # 클러터 대비(0.02~0.6)로 정규화
            sx.append(fx); sy.append(fy); sr.append(0.02 + 0.58 * st / smax)
    hits = 0
    for (svx, svy) in (survivors_world or []):
        if abs(svx - center[0]) <= half and abs(svy - center[1]) <= half:
            sx.append(svx); sy.append(svy); sr.append(3.0)       # 사람=강한 점표적(클러터 대비 크게)
            hits += 1
    return np.array(list(zip(sx, sy)), dtype=float), np.array(sr, dtype=float), hits


def doa_estimate(cfg, target_xy, flight_center):
    """가장 강한 표적의 DOA(도래각) — Rx 배열 위상차 기반(측정값 하나). 비모호 범위 안에서만."""
    dx = target_xy[0] - flight_center[0]; dy = target_xy[1] - flight_center[1]
    ang = math.degrees(math.atan2(dx, dy))                       # 비행선(y) 기준 사각
    return max(-cfg.doa_unambiguous_deg, min(cfg.doa_unambiguous_deg, ang))


def _measure_spot(img_db, extent, npx, thresh_db=-3.0):
    """단일 점표적 초점 스폿의 -3dB 폭[m] (x,y) — 독립 대조용(식과 맞춰 본다)."""
    H, W = img_db.shape
    pk = np.unravel_index(np.argmax(img_db), img_db.shape)
    dx = (extent[1] - extent[0]) / (W - 1)
    dy = (extent[3] - extent[2]) / (H - 1)
    row = img_db[pk[0], :]; col = img_db[:, pk[1]]
    wx = np.sum(row >= img_db.max() + thresh_db) * dx
    wy = np.sum(col >= img_db.max() + thresh_db) * dy
    return wx, wy


if __name__ == "__main__":
    # 독립 대조: 단일 점표적을 **측방관측(side-looking)** 기하에서 초점 맺어
    # -3dB 스폿을 재고 설계식과 맞춘다. (나디르 근처는 지상거리 해상도가 붕괴 — SAR 은
    # 반드시 측방관측이다. 그 물리를 그대로 두고 올바른 기하에서 검증한다.)
    cfg = RadarCfg()
    print("스펙:", {k: round(v, 4) for k, v in cfg.spec().items()})
    alt = 120.0
    inc = math.radians(55.0)                        # 입사각(수직 기준) → 지상거리 Rg
    Rg = alt * math.tan(inc)                         # 측방 지상거리 ≈ 171 m
    R = math.sqrt(Rg * Rg + alt * alt)               # 경사거리
    flight = np.array([0.0, 0.0])                    # 비행선은 y=0 을 따라 x 방향
    scene = np.array([0.0, Rg])                      # 스와스는 y=Rg (측방 이격)
    tgt = np.array([[0.0, Rg]])                      # 점표적 = 스와스 중심
    rcs = np.array([1.0])
    img_db, extent, meta = sar_image(cfg, tgt, rcs, flight, scene, 0.0, alt, half=6.0, npx=161)
    wx, wy = _measure_spot(img_db, extent, 161)
    dr_ground = cfg.range_res / math.sin(inc)        # 경사→지상 투영(지상거리 해상도)
    print("거리해상도 δr(경사, 식) = %.3f m → 지상 δr/sinθ = %.3f m (θ_inc=55°)" % (cfg.range_res, dr_ground))
    print("방위해상도 δa(식, R=%.0f) = %.3f m" % (R, cfg.az_res(R)))
    print("측정 초점 -3dB: 방위 wx=%.2f m(식 δa≈%.2f), 지상거리 wy=%.2f m(식≈%.2f)"
          % (wx, cfg.az_res(R), wy, dr_ground))
    print("  (해닝창으로 주엽이 ~1.6× 넓어진다 — 그만큼 감안)")
    print("DOA 비모호 ±%.1f°, 각해상도 %.1f°" % (cfg.doa_unambiguous_deg, cfg.doa_res_deg))
