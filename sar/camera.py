#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""온보드 카메라가 실제로 보는 장면 — 실 DEM 하이트필드 1인칭 투영(복셀 레이마치).

'RGB 카메라가 보는 다양한 각도의 사진'을 지어내지 않는다: 실제 지형고도(fetch_dem)를
UAV 자세(위치·고도 AGL·기수방위·짐벌 하향틸트)에서 원근투영한다. 기수가 돌면 장면 각도가
바뀐다. 대기(안개/연기)는 sensors.py 물리(β)로 거리에 따라 흐려지고, 조난자는 시야 안에
들어올 때만 밝은 반점으로 보인다(가시도 ρ 가 낮으면 흐릿).

같은 프레임에서 레이더(radar.py)가 측방 SAR 영상을 낸다 — 카메라가 못 보는 안개 속을 뚫는다.
"""
import math
import numpy as np


def _terrain_sampler(dem, mpp):
    """dem[y,x] (미터고도), mpp=미터/픽셀 → 월드(x,y[m])에서 고도 보간 샘플러."""
    DH, DW = dem.shape

    def h(wx, wy):
        px = np.clip(wx / mpp, 0, DW - 1.001)
        py = np.clip(wy / mpp, 0, DH - 1.001)
        x0 = px.astype(int); y0 = py.astype(int)
        fx = px - x0; fy = py - y0
        h00 = dem[y0, x0]; h10 = dem[y0, np.minimum(x0 + 1, DW - 1)]
        h01 = dem[np.minimum(y0 + 1, DH - 1), x0]; h11 = dem[np.minimum(y0 + 1, DH - 1), np.minimum(x0 + 1, DW - 1)]
        return (h00 * (1 - fx) + h10 * fx) * (1 - fy) + (h01 * (1 - fx) + h11 * fx) * fy
    return h


def render(dem, mpp, cam_xy, agl, heading_deg, beta, survivor_xy=None, rho=1.0,
           haze=(0.75, 0.78, 0.82), W=220, H=140, fov_deg=72.0, pitch_deg=-30.0,
           zfar=1600.0, zstep=6.0, scene=None):
    """1인칭 RGB 뷰(H,W,3) float[0,1]. 복셀-공간 하이트필드 레이마치(열 단위 벡터화).

    cam_xy: 카메라 지상위치 [m].  agl: 지형 위 고도 [m].  heading_deg: 기수 방위.
    beta: 소광계수(안개/연기).  survivor_xy: 조난자 지상위치들 [(x,y)m] 또는 None.
    scene: SceneDB(선택). 주면 나무·바위·건물 피처를 그 **RGB view(분광반사색)**로 그린다
           (radar.py 는 같은 피처를 radar view 로 본다 — 하나의 세계, 센서마다 다른 관측).
           None 이면 예전처럼 고도대 forest_mask 로 나무를 절차생성한다(하위호환).
    """
    hfun = _terrain_sampler(dem, mpp)
    cx, cy = cam_xy
    cz = float(hfun(np.array([cx]), np.array([cy]))[0]) + agl
    yaw = math.radians(heading_deg)
    halffov = math.radians(fov_deg) / 2
    col_ang = yaw + np.linspace(-halffov, halffov, W)             # 열별 방위각(수평 FOV)
    dirx = np.cos(col_ang); diry = np.sin(col_ang)
    focal = (H / 2) / math.tan(math.radians(fov_deg * H / W) / 2)   # 세로 초점거리(픽셀)
    horizon = H / 2 + focal * math.tan(math.radians(pitch_deg))     # 지평선 화면행(하향틸트→위로)
    dmin = float(dem.min()); drng = float(np.ptp(dem)) + 1e-6
    snow = dmin + 0.86 * drng; forest_hi = dmin + 0.58 * drng      # 설선·수목한계 고도
    # ── 하늘: 위(천정 파랑)→지평선(haze) 세로 그라디언트, 안개면 전체 희뿌옇게 ──
    img = np.zeros((H, W, 3), dtype=np.float32)
    fog = min(1.0, beta * 22)
    zenith = np.array([0.40, 0.55, 0.78]); horiz_sky = np.array([0.72, 0.78, 0.85])
    for yy in range(max(1, int(horizon))):
        t = yy / max(1, horizon)
        img[yy, :] = (zenith * (1 - t) + horiz_sky * t) * (1 - 0.7 * fog) + np.array(haze) * (0.7 * fog)
    img[int(max(0, horizon)):, :] = np.array(haze)
    ybuf = np.full(W, H, dtype=float)
    cols = np.arange(W)
    ls = np.array([math.cos(math.radians(315)), math.sin(math.radians(315))])  # 힐셰이드 광원

    def terr_color(th, sx, sy, shade):
        """지면 색: scene 있으면 **land-cover 기반 지면 material**, 없으면 고도대 팔레트(하위호환).
        어느 경우든 설선(고도) 위는 눈으로 덮고 + 절차적 텍스처 + 힐셰이드 명암을 씌운다."""
        tn = np.clip((th - dmin) / drng, 0, 1)
        snowc = np.array([0.86, 0.88, 0.92])
        if scene is not None:                                     # RGB view: land-cover 지면색
            c = np.array(scene.ground_rgb(sx, sy), dtype=float)
        else:                                                     # 고도대 팔레트(예전)
            grass = np.array([0.34, 0.45, 0.24]); forest = np.array([0.20, 0.33, 0.17])
            rock = np.array([0.46, 0.43, 0.39])
            f1 = np.clip((tn - 0.12) / 0.30, 0, 1)[:, None]       # 풀→숲
            c = grass * (1 - f1) + forest * f1
            f2 = np.clip((tn - 0.55) / 0.20, 0, 1)[:, None]       # 숲→바위
            c = c * (1 - f2) + rock * f2
        f3 = np.clip((tn - 0.82) / 0.12, 0, 1)[:, None]           # 설선 위→눈(고도)
        c = c * (1 - f3) + snowc * f3
        # 절차적 텍스처(지표 얼룩) — 월드좌표 해시
        n = np.sin(sx * 0.13 + sy * 0.07) * np.cos(sx * 0.05 - sy * 0.11)
        c = c * (0.86 + 0.14 * ((n + 1) * 0.5))[:, None]
        return np.clip(c * shade[:, None], 0, 1)

    # Per-column terrain silhouette history per march step (distance -> ybuf after drawing up to that distance).
    # Features/survivors are compared only with the silhouette of terrain **nearer than themselves** -- see _silhouette below.
    sil_z, sil_rows = [], []
    z = 8.0
    while z < zfar:
        sx = cx + z * dirx; sy = cy + z * diry
        th = hfun(sx, sy)
        yscreen = np.clip(horizon - focal * (th - cz) / z, 0, H).astype(int)
        gx1 = hfun(sx + mpp, sy) - th; gy1 = hfun(sx, sy + mpp) - th
        shade = np.clip(0.55 - 0.55 * (gx1 * ls[0] + gy1 * ls[1]) / mpp, 0.30, 1.05)
        base = terr_color(th, sx, sy, shade)
        trans = math.exp(-beta * z)
        col = base * trans + np.array(haze) * (1 - trans)
        draw = yscreen < ybuf.astype(int)
        for c in cols[draw]:
            y1 = yscreen[c]; y0 = int(ybuf[c])
            img[y1:y0, c] = col[c]
            ybuf[c] = y1
        sil_z.append(z); sil_rows.append(ybuf.copy())
        z += zstep * (1 + z / 400.0)

    import bisect

    def _silhouette(u, rng):
        """Top row of terrain nearer than rng in column u (H if none). Rows below it are hidden by nearer terrain.

        **Why this exists (measured 2026-09-28, render3d/vv_scene3d H).** Occlusion used to be `vb < ybuf[u] - 1` --
        a comparison with the final silhouette, which includes terrain **farther** than the feature. A ground feature
        almost never satisfies it, so trees, buildings and survivors behind a ridge were painted over the ridge face.
        On the ridge DEM, 38 of 40 cases numpy called hidden were drawn by this camera."""
        k = bisect.bisect_left(sil_z, rng) - 1
        return float(sil_rows[k][u]) if k >= 0 else float(H)

    # ── 피처(나무·바위·건물): scene DB 가 있으면 그 RGB view 로, 없으면 고도대 절차생성(하위호환) ──
    feats = []                                                    # (rng, ang, th_base, kind, size)
    if scene is not None:
        for f in scene.query(cam_xy, zfar):                       # LOD 컬링된 가시 피처
            dx = f["wx"] - cx; dy = f["wy"] - cy; rng = math.hypot(dx, dy)
            ang = (math.atan2(dy, dx) - yaw + math.pi) % (2 * math.pi) - math.pi
            if abs(ang) > halffov:
                continue
            feats.append((rng, ang, float(f["z"]), f["kind"], float(f["size"]), f))
    else:
        trng = np.random.default_rng(int(cx) * 131 + int(cy))
        NT = 900
        trng_d = np.sqrt(trng.uniform(0, 1, NT)) * min(zfar, 850) + 15    # 근거리 밀집(sqrt 분포)
        ta = yaw + trng.uniform(-halffov, halffov, NT)
        tx = cx + trng_d * np.cos(ta); ty = cy + trng_d * np.sin(ta)
        tth = hfun(tx, ty)
        tsl = np.abs(hfun(tx + mpp, ty) - tth) + np.abs(hfun(tx, ty + mpp) - tth)
        forest_mask = (tth < forest_hi) & (tth > dmin + 0.05 * drng) & (tsl < 0.9 * mpp)
        for k in np.where(forest_mask)[0]:
            dx = tx[k] - cx; dy = ty[k] - cy; rng = math.hypot(dx, dy)
            ang = (math.atan2(dy, dx) - yaw + math.pi) % (2 * math.pi) - math.pi
            if abs(ang) > halffov:
                continue
            feats.append((rng, ang, float(tth[k]), "tree", 8.0, None))
    for rng, ang, th, kind, size, f in sorted(feats, key=lambda e: -e[0]):   # 원→근(painter)
        u = int((ang / (2 * halffov) + 0.5) * (W - 1))
        vb = horizon - focal * (th - cz) / rng                    # base row on screen
        sil = _silhouette(u, rng)                                 # silhouette of terrain nearer than this feature
        # 화면높이: scene 이면 실제 피처 크기[m]를 투영, 아니면 예전 나무높이 곡선
        htree = float(np.clip(focal * size / rng, 4, 46)) if scene is not None else (5 + 26 * math.exp(-rng / 420.0))
        wtree = max(1, int(htree * (0.42 if kind == "building" else 0.32)))
        trans = math.exp(-beta * rng)
        shade_t = 0.75 + 0.25 * math.sin(rng)                     # 미세 명암
        if scene is not None:                                     # RGB view: 분광반사색
            base = np.array(scene.rgb_of(f)["color"])
        else:
            base = np.array([0.12, 0.30, 0.13])
        body = base * shade_t * trans + np.array(haze) * (1 - trans)
        crown = np.clip(base * 1.15, 0, 1) * shade_t * trans + np.array(haze) * (1 - trans)
        top = int(np.clip(vb - htree, 0, H - 1)); bot = int(np.clip(min(vb, sil), 0, H - 1))   # rows >= sil are hidden by nearer terrain
        if top >= bot:
            continue                                              # fully hidden (behind the ridge)
        img[top:bot, max(0, u - wtree):min(W, u + wtree + 1)] = body        # 줄기/몸통
        if kind != "building":                                    # 수관(건물은 각지게 몸통만)
            img[top:int(np.clip(min(vb - htree * 0.55, sil), 0, H - 1)), max(0, u - wtree - 1):min(W, u + wtree + 2)] = crown
    # 조난자: 시야·거리 안이면 밝은 반점(가시도 ρ 로 밝기·번짐)
    if survivor_xy is not None:
        for (sxw, syw) in survivor_xy:
            dx = sxw - cx; dy = syw - cy
            rng = math.hypot(dx, dy)
            ang = (math.atan2(dy, dx) - yaw + math.pi) % (2 * math.pi) - math.pi
            if abs(ang) > halffov or rng > zfar:
                continue
            trans = math.exp(-beta * rng)
            if trans * rho < 0.12:                                # 안개로 사실상 안 보임
                continue
            u = int((ang / (2 * halffov) + 0.5) * (W - 1))
            th = float(hfun(np.array([sxw]), np.array([syw]))[0])
            v = int(np.clip(horizon - focal * ((th + 1.7) - cz) / rng, 0, H - 1))  # 사람 키 ~1.7m
            r = max(3, int(1.7 / max(rng, 1) * focal * 2.2))       # 사람 크기(약간 강조) — 원거리일수록 작다
            yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
            mask = xx * xx + yy * yy <= r * r
            warm = np.array([0.95, 0.75, 0.35]) * (0.5 + 0.5 * trans * rho)  # 사람=따뜻한 반점
            for (yy2, xx2) in np.argwhere(mask):
                py = v + yy2 - r; px = u + xx2 - r
                if 0 <= py < H and 0 <= px < W and py < _silhouette(px, rng):   # hidden by nearer terrain -> not drawn
                    img[py, px] = warm
    return np.clip(img, 0, 1)


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import terrain
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    dem, ext, meta = terrain.fetch_dem(38.12, 128.47, 3000.0, zoom=13)
    mpp = 6000.0 / dem.shape[1]
    cx = cy = 3000.0
    for i, (hd, beta, agl) in enumerate([(45, 0.002, 90.0), (135, 0.002, 90.0), (45, 0.03, 90.0)]):
        img = render(dem, mpp, (cx, cy), agl, hd, beta, survivor_xy=[(cx + 90, cy + 70)], rho=1.0)
        plt.imsave(os.path.join(os.path.dirname(__file__), "out", "cam_%d.png" % i), img)
        print("saved cam_%d.png (heading=%d beta=%.3f agl=%.0f)" % (i, hd, beta, agl))
