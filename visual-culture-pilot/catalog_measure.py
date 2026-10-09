"""Measure colour from the actual image: dominant palette, tonal key, contrast, saturation, scheme.

Everything here is computed from pixels (Pillow only). The scheme and key labels are rule-based
classifications of those measurements; the thresholds are stated in the code and in the output.
"""
from __future__ import annotations

import colorsys
import math
from pathlib import Path

from PIL import Image

SAMPLE = 160          # longest side used for measurement
PALETTE_SIZE = 6
MIN_SHARE = 0.03      # palette entries below 3 % of pixels are dropped


def _lum(r, g, b):  # relative luminance of sRGB 0..1 (approximate, no gamma decode)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def measure(path: Path) -> dict:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((SAMPLE, SAMPLE))
        pixels = list(im.getdata())
        q = im.quantize(colors=PALETTE_SIZE, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[: PALETTE_SIZE * 3]
        counts = sorted(q.getcolors(), reverse=True)
    n = len(pixels)
    palette = []
    for count, idx in counts:
        share = count / n
        if share < MIN_SHARE:
            continue
        r, g, b = pal[idx * 3: idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        palette.append({"hex": f"#{r:02X}{g:02X}{b:02X}", "share": round(share, 3),
                        "hue": round(h * 360), "sat": round(s, 2), "val": round(v, 2)})

    lums = [_lum(r / 255, g / 255, b / 255) for r, g, b in pixels]
    mean = sum(lums) / n
    std = math.sqrt(sum((x - mean) ** 2 for x in lums) / n)
    sats = [colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[1] for r, g, b in pixels]
    sat = sum(sats) / n

    key = "하이키" if mean > 0.65 else "로우키" if mean < 0.35 else "미드키"
    contrast = "고대비" if std > 0.25 else "저대비" if std < 0.12 else "중간 대비"
    chroma = "무채색" if sat < 0.08 else "저채도" if sat < 0.25 else "중채도" if sat < 0.5 else "고채도"
    return {"palette": palette, "luminance_mean": round(mean, 3), "luminance_std": round(std, 3),
            "saturation_mean": round(sat, 3), "key": key, "contrast": contrast, "chroma": chroma,
            "scheme": scheme(palette),
            "method": f"Pillow median-cut {PALETTE_SIZE} colours on a {SAMPLE}px sample; "
                      "key: mean luminance >0.65 high / <0.35 low; contrast: std >0.25 high / <0.12 low; "
                      "chroma: mean saturation <0.08 / <0.25 / <0.5"}


def _hue_gap(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def scheme(palette) -> str:
    """Colour-scheme label from the chromatic palette entries (sat >= 0.2, val >= 0.2).

    Hues are on the HSV circle derived from RGB, not the painter's RYB wheel, so red-yellow-blue
    is "다색" here, while red-green-blue is "트라이어딕"."""
    hues = [p["hue"] for p in palette if p["sat"] >= 0.2 and p["val"] >= 0.2]
    if not hues:
        return "무채색 배색"
    groups = []  # hues within 30° form one group
    for h in sorted(hues):
        for g in groups:
            if _hue_gap(h, g[0]) <= 30:
                g.append(h)
                break
        else:
            groups.append([h])
    centres = [g[0] for g in groups]
    if len(centres) == 1:
        return "모노크로매틱 배색"
    widest = max(_hue_gap(a, b) for i, a in enumerate(centres) for b in centres[i + 1:])
    if widest <= 60:
        return "유사색 배색"
    if len(centres) == 2 and widest >= 150:
        return "보색 배색"
    if len(centres) == 3 and all(90 <= _hue_gap(a, b) <= 150 for i, a in enumerate(centres) for b in centres[i + 1:]):
        return "트라이어딕 배색"
    return "다색 배색"
