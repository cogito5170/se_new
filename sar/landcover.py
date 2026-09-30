#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실 land-cover (ESA WorldCover 10 m, 2021 v200) — 고도규칙 근사를 **실측 지표피복**으로 바꾼다.

왜 이 소스/방식:
  · terrascope WMTS 는 이 컨테이너에서 막혀 있다(403). AWS S3 의 WorldCover COG 는 **무키로
    200/206(Range)** 을 준다(실측). 그래서 그 COG 를 **부분(window)만 range-read** 한다.
  · rasterio·GDAL·tifffile 이 다 없다 — 그래서 **순수 파이썬**으로 COG 를 읽는다(struct+zlib+numpy).
    COG 규격: classic TIFF, little-endian, 8-bit 1밴드, **DEFLATE(zlib 내장)**, predictor 없음,
    1024×1024 타일. 창을 덮는 타일만 range 로 받아 해제·조립·크롭한다(전 36000² 안 받는다).

정직: 못 받으면(망·파싱 실패) **고도규칙으로 폴백하고 source='elevation_fallback' 로 명시**한다.
'실 land-cover' 라고 말하는 건 source='esa_worldcover' 일 때뿐이다. 좌표계는 WorldCover 가
EPSG:4326(지리) 이라 픽셀↔경위도가 선형이다.
"""
from __future__ import annotations
import io
import math
import struct
import urllib.request
import zlib
import numpy as np

# ESA WorldCover 클래스 코드 → 이 저장소 scene.LANDCOVER 키
WORLDCOVER_TO_CLASS = {
    10: "forest",   # Tree cover
    20: "grass",    # Shrubland
    30: "grass",    # Grassland
    40: "grass",    # Cropland
    50: "urban",    # Built-up
    60: "alpine",   # Bare / sparse vegetation (암반·나지)
    70: "alpine",   # Snow and ice
    80: "water",    # Permanent water bodies
    90: "coast",    # Herbaceous wetland
    95: "coast",    # Mangroves
    100: "grass",   # Moss and lichen
}

_S3 = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/"
       "v200/2021/map/ESA_WorldCover_10m_2021_v200_{ns}{lat:02d}{ew}{lon:03d}_Map.tif")


def _tile_name(lat, lon):
    """WorldCover 3°×3° 타일의 SW 코너(3의 배수)로 파일명을 정한다."""
    la = int(math.floor(lat / 3.0) * 3); lo = int(math.floor(lon / 3.0) * 3)
    ns = "N" if la >= 0 else "S"; ew = "E" if lo >= 0 else "W"
    return _S3.format(ns=ns, lat=abs(la), ew=ew, lon=abs(lo))


def _rng(url, a, b, timeout=25):
    req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (a, b), "User-Agent": "sar-lc"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _read_ifd(url):
    """첫 IFD 를 읽어 필요한 태그를 dict 로. (COG 규격 가정: classic LE TIFF.)"""
    hdr = _rng(url, 0, 15)
    if hdr[:2] != b"II" or struct.unpack("<H", hdr[2:4])[0] != 42:
        raise ValueError("COG 가 classic little-endian TIFF 아님")
    ifd_off = struct.unpack("<I", hdr[4:8])[0]
    n = struct.unpack("<H", _rng(url, ifd_off, ifd_off + 1))[0]
    body = _rng(url, ifd_off + 2, ifd_off + 2 + n * 12 - 1)
    tags = {}
    for i in range(n):
        tag, typ, cnt = struct.unpack("<HHI", body[i * 12:i * 12 + 8])
        off = struct.unpack("<I", body[i * 12 + 8:i * 12 + 12])[0]
        tags[tag] = (typ, cnt, off)
    def u32_array(tag):
        typ, cnt, off = tags[tag]
        raw = _rng(url, off, off + cnt * 4 - 1)
        return struct.unpack("<%dI" % cnt, raw)
    def dbl_array(tag):
        typ, cnt, off = tags[tag]
        raw = _rng(url, off, off + cnt * 8 - 1)
        return struct.unpack("<%dd" % cnt, raw)
    W = tags[256][2]; H = tags[257][2]; comp = tags[259][2]
    tw = tags[322][2]; th = tags[323][2]
    if comp != 8:
        raise ValueError("압축이 DEFLATE(8) 아님: %d" % comp)
    scale = dbl_array(33550)         # (sx, sy, sz)
    tie = dbl_array(33922)           # (I,J,K, X,Y,Z)
    return dict(W=W, H=H, tw=tw, th=th,
                offs=u32_array(324), cnts=u32_array(325),
                sx=scale[0], sy=scale[1], X=tie[3], Y=tie[4], I=tie[0], J=tie[1], url=url)


def _read_window(ifd, col0, row0, col1, row1):
    """[row0:row1, col0:col1] 픽셀 창을 덮는 타일만 range-read·해제·조립·크롭 → uint8 코드 격자."""
    tw, th, W = ifd["tw"], ifd["th"], ifd["W"]
    ntx = (ifd["W"] + tw - 1) // tw
    tx0, tx1 = col0 // tw, (col1 - 1) // tw
    ty0, ty1 = row0 // th, (row1 - 1) // th
    mosaic = np.zeros(((ty1 - ty0 + 1) * th, (tx1 - tx0 + 1) * tw), dtype=np.uint8)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            t = ty * ntx + tx
            raw = _rng(ifd["url"], ifd["offs"][t], ifd["offs"][t] + ifd["cnts"][t] - 1)
            flat = np.frombuffer(zlib.decompress(raw), dtype=np.uint8)
            if flat.size < tw * th:
                flat = np.pad(flat, (0, tw * th - flat.size))
            tile = flat[:tw * th].reshape(th, tw)
            mosaic[(ty - ty0) * th:(ty - ty0 + 1) * th, (tx - tx0) * tw:(tx - tx0 + 1) * tw] = tile
    return mosaic[row0 - ty0 * th:row1 - ty0 * th, col0 - tx0 * tw:col1 - tx0 * tw]


def fetch_worldcover(lat, lon, radius_m=3000.0, timeout=25):
    """중심 반경 radius_m 창의 ESA WorldCover 클래스코드 격자(uint8) 를 반환. 실패시 예외."""
    url = _tile_name(lat, lon)
    ifd = _read_ifd(url)
    m_per_deg_lat = 111320.0; m_per_deg_lon = 111320.0 * math.cos(math.radians(lat))
    dlat = radius_m / m_per_deg_lat; dlon = radius_m / m_per_deg_lon
    def col_of(lo): return ifd["I"] + (lo - ifd["X"]) / ifd["sx"]
    def row_of(la): return ifd["J"] + (ifd["Y"] - la) / ifd["sy"]
    col0 = int(max(0, math.floor(col_of(lon - dlon)))); col1 = int(min(ifd["W"], math.ceil(col_of(lon + dlon))))
    row0 = int(max(0, math.floor(row_of(lat + dlat)))); row1 = int(min(ifd["H"], math.ceil(row_of(lat - dlat))))
    if col1 <= col0 or row1 <= row0:
        raise ValueError("창이 이 타일 밖(경계 걸침) — 폴백")
    return _read_window(ifd, col0, row0, col1, row1)


def codes_to_classes(codes):
    """WorldCover 코드 격자 → scene.LANDCOVER 키 격자(object)."""
    out = np.empty(codes.shape, dtype=object)
    for code in np.unique(codes):
        out[codes == code] = WORLDCOVER_TO_CLASS.get(int(code), "grass")
    return out


def _resample_nn(grid, shape):
    """최근접 리샘플 → 목표 shape(보통 DEM/scene 격자)."""
    H, W = grid.shape; th, tw = shape
    ri = np.clip((np.arange(th) * H / th).astype(int), 0, H - 1)
    ci = np.clip((np.arange(tw) * W / tw).astype(int), 0, W - 1)
    return grid[np.ix_(ri, ci)]


def landcover_grid(lat, lon, radius_m, shape, dem=None, mpp=None):
    """목표 shape 의 land-cover 클래스 격자 + source 를 반환.

    실 WorldCover 를 받으면 (classes, 'esa_worldcover'). 실패하면 고도규칙 폴백
    (classes, 'elevation_fallback') — **폴백을 실 데이터라 부르지 않는다.**
    """
    try:
        codes = fetch_worldcover(lat, lon, radius_m)
        classes = codes_to_classes(codes)
        return _resample_nn(classes, shape), "esa_worldcover"
    except Exception as e:                                   # noqa: BLE001
        # 고도규칙 폴백 — scene.classify 와 동일 규칙
        import scene as _scene
        if dem is None:
            return np.full(shape, "grass", dtype=object), "elevation_fallback(%s)" % type(e).__name__
        dmin = float(dem.min()); drng = float(np.ptp(dem)) or 1.0
        gy, gx = np.gradient(dem); slope = np.hypot(gx, gy) / (mpp or 1.0)
        cls = np.empty(dem.shape, dtype=object)
        for j in range(dem.shape[0]):
            for i in range(dem.shape[1]):
                cls[j, i] = _scene.classify(dem[j, i], slope[j, i], dmin, drng)
        return _resample_nn(cls, shape), "elevation_fallback(%s)" % type(e).__name__


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=37.0966); ap.add_argument("--lon", type=float, default=128.9456)
    ap.add_argument("--radius", type=float, default=3000.0)
    a, _ = ap.parse_known_args()
    try:
        codes = fetch_worldcover(a.lat, a.lon, a.radius)
        uniq, cnt = np.unique(codes, return_counts=True)
        print("ESA WorldCover 창 %s @ (%.4f,%.4f) r=%.0fm" % (codes.shape, a.lat, a.lon, a.radius))
        NAMES = {10: "Tree", 20: "Shrub", 30: "Grass", 40: "Crop", 50: "Built", 60: "Bare",
                 70: "Snow", 80: "Water", 90: "Wetland", 95: "Mangrove", 100: "Moss"}
        for c, n in sorted(zip(uniq, cnt), key=lambda z: -z[1]):
            print("  %3d %-8s %5.1f%% -> %s" % (c, NAMES.get(int(c), "?"), 100.0 * n / codes.size,
                                                WORLDCOVER_TO_CLASS.get(int(c), "grass")))
    except Exception as e:                                   # noqa: BLE001
        print("실 WorldCover 못 받음:", type(e).__name__, e)
        print("→ 실 임무에선 고도규칙 폴백(source=elevation_fallback)")
