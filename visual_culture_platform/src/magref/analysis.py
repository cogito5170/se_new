"""Automatic measurements from stored image files (kind='measured').

Only values computed from the actual bytes on disk are written, each with the
tool and the file's SHA-256. Without Pillow only header-derived values are
measured (size, dimensions, aspect ratio, orientation); colour/brightness
features are then simply absent -- not estimated.

Level labels (brightness_level, contrast_level, colorfulness_level, dominant_hue)
are fixed-threshold bucketings of the measured numbers; the thresholds are part
of `method` so a reader can recompute them.
"""
from __future__ import annotations

import colorsys
import math
import sqlite3
from pathlib import Path

from . import images as imglib
from .research import FeatureRepo
from .storage import Layout, sha256_file
from .timeutil import utcnow

TOOL_HEADER = "magref.images header parser"
BRIGHTNESS_RULE = "brightness_mean: <0.35 dark, <0.65 medium, else light"
CONTRAST_RULE = "contrast_rms: <0.15 low, <0.28 medium, else high"
COLORFULNESS_RULE = "Hasler-Suesstrunk M: <15 muted, <45 moderate, else vivid"
HUES = [(15, "red"), (45, "orange"), (70, "yellow"), (160, "green"), (200, "cyan"),
        (260, "blue"), (300, "purple"), (340, "magenta"), (360, "red")]


def _hue_name(r: int, g: int, b: int) -> str:
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if s < 0.15 or l < 0.08 or l > 0.92:
        return "neutral"
    deg = h * 360
    return next(name for limit, name in HUES if deg < limit)


def _level(value: float, cuts: tuple[float, float], names: tuple[str, str, str]) -> str:
    return names[0] if value < cuts[0] else names[1] if value < cuts[1] else names[2]


def measure_file(path: Path) -> tuple[dict, str]:
    """Return ({feature_type: value}, tool)."""
    data = path.read_bytes()
    out: dict = {"file_size": len(data)}
    dims = imglib.dimensions(data[:65536])
    tool = TOOL_HEADER
    if dims:
        ar = imglib.aspect_ratio(dims.width, dims.height)
        out.update(width=dims.width, height=dims.height, aspect_ratio=ar["ratio"],
                   orientation=ar["orientation"])
    if not imglib.pillow_available():
        return out, tool
    import PIL
    from PIL import Image, ImageStat
    tool = f"Pillow {PIL.__version__}"
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        rgb.thumbnail((128, 128))
        if "width" not in out:
            out.update(width=im.width, height=im.height)
            ar = imglib.aspect_ratio(im.width, im.height)
            out.update(aspect_ratio=ar["ratio"], orientation=ar["orientation"])
        palette = imglib.dominant_colors(path, count=5) or []
        out["palette"] = palette
        if palette:
            top = palette[0]["hex"]
            out["dominant_color"] = top
            r, g, b = (int(top[i:i + 2], 16) for i in (1, 3, 5))
            out["dominant_hue"] = _hue_name(r, g, b)
        gray = rgb.convert("L")
        stat = ImageStat.Stat(gray)
        mean = stat.mean[0] / 255
        std = stat.stddev[0] / 255
        out["brightness_mean"] = round(mean, 4)
        out["brightness_level"] = _level(mean, (0.35, 0.65), ("dark", "medium", "light"))
        out["contrast_rms"] = round(std, 4)
        out["contrast_level"] = _level(std, (0.15, 0.28), ("low", "medium", "high"))
        hsv = rgb.convert("HSV")
        out["saturation_mean"] = round(ImageStat.Stat(hsv).mean[1] / 255, 4)
        pixels = list(rgb.getdata())
        rg = [p[0] - p[1] for p in pixels]
        yb = [(p[0] + p[1]) / 2 - p[2] for p in pixels]
        n = len(pixels) or 1
        mrg, myb = sum(rg) / n, sum(yb) / n
        srg = math.sqrt(sum((x - mrg) ** 2 for x in rg) / n)
        syb = math.sqrt(sum((x - myb) ** 2 for x in yb) / n)
        m = math.sqrt(srg ** 2 + syb ** 2) + 0.3 * math.sqrt(mrg ** 2 + myb ** 2)
        out["colorfulness"] = round(m, 2)
        out["colorfulness_level"] = _level(m, (15, 45), ("muted", "moderate", "vivid"))
    return out, tool


METHODS = {
    "brightness_level": f"threshold ({BRIGHTNESS_RULE})",
    "contrast_level": f"threshold ({CONTRAST_RULE})",
    "colorfulness_level": f"threshold ({COLORFULNESS_RULE})",
    "colorfulness": "Hasler & Suesstrunk 2003 colourfulness metric on 128px thumbnail",
    "palette": "median-cut quantization of 64px thumbnail, top 5 by pixel share",
    "dominant_color": "largest share in palette",
    "dominant_hue": "HLS hue bucket of dominant_color (neutral if s<0.15)",
    "brightness_mean": "mean of 8-bit luminance / 255 on 128px thumbnail",
    "contrast_rms": "standard deviation of luminance / 255 (RMS contrast)",
    "saturation_mean": "mean HSV saturation / 255",
}


def make_thumbnail(layout: Layout, sha: str, path: Path, size: int = 320) -> Path | None:
    """JPEG thumbnail under thumbnails/<sha[:2]>/<sha>.jpg (Pillow only; derived, re-creatable)."""
    if not imglib.pillow_available():
        return None
    from PIL import Image
    target = layout.thumbnails / sha[:2] / f"{sha}.jpg"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((size, size))
        tmp = target.with_suffix(".tmp")
        im.save(tmp, "JPEG", quality=85)
        tmp.replace(target)
    return target


def analyze_asset(conn: sqlite3.Connection, layout: Layout, asset_id: str) -> dict:
    row = conn.execute(
        """SELECT r.id, r.file_sha256, f.rel_path FROM image_refs r
           JOIN image_files f ON f.sha256 = r.file_sha256
           WHERE r.id=? AND r.download_status='downloaded'""", (asset_id,)).fetchone()
    if row is None:
        return {"id": asset_id, "status": "not_applicable", "reason": "no downloaded file"}
    path = layout.resolve(row["rel_path"])
    if not path.is_file() or sha256_file(path) != row["file_sha256"]:
        conn.execute("UPDATE image_refs SET analysis_status='failed', updated_at=? WHERE id=?",
                     (utcnow(), asset_id))
        conn.commit()
        return {"id": asset_id, "status": "failed", "reason": "file missing or hash mismatch (run verify)"}
    try:
        values, tool = measure_file(path)
    except Exception as exc:  # noqa: BLE001 -- decoder errors are recorded, not raised
        conn.execute("UPDATE image_refs SET analysis_status='failed', updated_at=? WHERE id=?",
                     (utcnow(), asset_id))
        conn.commit()
        return {"id": asset_id, "status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
    try:
        make_thumbnail(layout, row["file_sha256"], path)
    except Exception:  # noqa: BLE001 -- a thumbnail is a convenience, never a failure
        pass
    repo = FeatureRepo(conn)
    repo.clear_measured(asset_id)
    for ftype, value in values.items():
        method = METHODS.get(ftype, "image header" if tool == TOOL_HEADER else "Pillow image statistics")
        repo.add_measured(asset_id, ftype, value, method=method, tool=tool, file_sha256=row["file_sha256"])
    conn.execute("UPDATE image_refs SET analysis_status='measured', updated_at=? WHERE id=?",
                 (utcnow(), asset_id))
    conn.commit()
    return {"id": asset_id, "status": "measured", "tool": tool, "features": sorted(values)}


def analyze_pending(conn: sqlite3.Connection, layout: Layout, limit: int = 100,
                    redo: bool = False) -> list[dict]:
    statuses = ("pending", "failed", "measured") if redo else ("pending",)
    rows = conn.execute(
        f"""SELECT id FROM image_refs WHERE download_status='downloaded' AND analysis_status IN
            ({', '.join('?' * len(statuses))}) ORDER BY id LIMIT ?""", (*statuses, limit)).fetchall()
    return [analyze_asset(conn, layout, r[0]) for r in rows]
