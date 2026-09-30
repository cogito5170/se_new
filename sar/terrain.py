#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실제 지형(DEM) 받아오기 -- AWS Terrain Tiles(Terrarium). 무키·전지구.

왜 이 소스: 이 컨테이너에서 OSM 타일·wikimedia·opentopodata·open-elevation·VWorld 는
막혀 있고(403/000), AWS elevation-tiles-prod 만 실측으로 200 을 준다(무키). Terrarium 은
고도를 RGB 로 인코딩한다:  elevation[m] = R*256 + G + B/256 - 32768.

계층화(ITU 채널 모델과 같은 사고): 물리 지형(DEM) -> 몇 개 '센싱 상태'(고도·경사·가시성)로
압축 -> 탐지/비행에 쓴다. 여기선 그 '물리 입력층'(진짜 고도장)을 받는 것까지.
"""
import math, io, os, urllib.request
import numpy as np
from PIL import Image

TILE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

def _tilexy_frac(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y

def _fetch_tile(z, x, y, timeout=25):
    req = urllib.request.Request(TILE.format(z=z, x=x, y=y), headers={"User-Agent": "sar-terrain"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return np.array(Image.open(io.BytesIO(r.read())).convert("RGB")).astype(np.float64)

def _decode(rgb):
    return rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0

def fetch_dem(lat, lon, radius_m=3000.0, zoom=13):
    """중심(lat,lon) 반경 radius_m 를 덮는 Terrarium 타일들을 이어붙여 실제 DEM 반환.
    반환: dem[H,W] (m), extent(lon0,lon1,lat0,lat1), meta. 힙 밖 다운로드는 여러 타일."""
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat))
    dlat = radius_m / m_per_deg_lat
    dlon = radius_m / m_per_deg_lon
    lat0, lat1 = lat - dlat, lat + dlat
    lon0, lon1 = lon - dlon, lon + dlon
    # 덮는 정수 타일 범위 (y 는 위도 증가에 감소)
    x_lo, _ = _tilexy_frac(lat, lon0, zoom); x_hi, _ = _tilexy_frac(lat, lon1, zoom)
    _, y_lo = _tilexy_frac(lat1, lon, zoom); _, y_hi = _tilexy_frac(lat0, lon, zoom)
    xa, xb = int(math.floor(min(x_lo, x_hi))), int(math.floor(max(x_lo, x_hi)))
    ya, yb = int(math.floor(min(y_lo, y_hi))), int(math.floor(max(y_lo, y_hi)))
    ntiles = (xb - xa + 1) * (yb - ya + 1)
    rows = []
    for ty in range(ya, yb + 1):
        row = [_decode(_fetch_tile(zoom, tx, ty)) for tx in range(xa, xb + 1)]
        rows.append(np.hstack(row))
    mosaic = np.vstack(rows)                      # [ (yb-ya+1)*256 , (xb-xa+1)*256 ]
    # 모자이크의 지리 범위 -> 요청 박스로 크롭
    n = 2 ** zoom
    def lon_of_px(px): return (xa + px / 256.0) / n * 360.0 - 180.0
    def lat_of_px(py):
        t = math.pi * (1 - 2 * (ya + py / 256.0) / n)
        return math.degrees(math.atan(math.sinh(t)))
    H, W = mosaic.shape
    # 요청 박스에 해당하는 픽셀 인덱스
    def px_of_lon(lo): return (( (lo + 180.0) / 360.0 * n) - xa) * 256.0
    def py_of_lat(la):
        yy = (1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * n
        return (yy - ya) * 256.0
    c0, c1 = int(max(0, px_of_lon(lon0))), int(min(W, px_of_lon(lon1)))
    r0, r1 = int(max(0, py_of_lat(lat1))), int(min(H, py_of_lat(lat0)))  # lat1(위)=작은 py
    dem = mosaic[r0:r1, c0:c1]
    meta = dict(zoom=zoom, tiles=ntiles, center=(lat, lon), radius_m=radius_m,
                m_per_px=(2 * radius_m) / max(1, dem.shape[1]))
    return dem, (lon0, lon1, lat0, lat1), meta

if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.font_manager as fm
    for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
               "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
        if os.path.exists(_c):
            fm.fontManager.addfont(_c)
            matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name(); break
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    LAT, LON, R = 37.6586, 126.9880, 4000.0        # 북한산(서울 북부) 반경 4km
    dem, ext, meta = fetch_dem(LAT, LON, R, zoom=13)
    print("DEM shape %s  tiles=%d  m/px=%.1f" % (dem.shape, meta["tiles"], meta["m_per_px"]))
    print("elevation min/mean/max = %.0f / %.0f / %.0f m" % (dem.min(), dem.mean(), dem.max()))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"); os.makedirs(out, exist_ok=True)
    ls = LightSource(azdeg=315, altdeg=45)
    fig = plt.figure(figsize=(14, 5.2))
    ax1 = fig.add_subplot(1, 2, 1)
    hs = ls.shade(dem, cmap=plt.cm.terrain, blend_mode="soft", vert_exag=2.0)
    ax1.imshow(hs, extent=ext, aspect="auto"); ax1.set_title("실제 지형 hillshade (북한산, AWS Terrarium DEM)")
    ax1.set_xlabel("lon"); ax1.set_ylabel("lat")
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")
    step = max(1, dem.shape[0] // 120)
    Z = dem[::step, ::step]; X, Y = np.meshgrid(np.arange(Z.shape[1]), np.arange(Z.shape[0]))
    ax2.plot_surface(X, Y, Z, cmap="terrain", linewidth=0, antialiased=True)
    ax2.set_title("3D 실지형 (고도 %.0f~%.0f m)" % (dem.min(), dem.max())); ax2.view_init(elev=55, azim=-60)
    fig.tight_layout(); fig.savefig(os.path.join(out, "terrain_bukhansan.png"), dpi=110)
    print("saved:", os.path.join(out, "terrain_bukhansan.png"))
