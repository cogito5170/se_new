# -*- coding: utf-8 -*-
"""Two camera models, and the conversion between them.

1. **SAR camera** (`sar/camera.py`) -- the heightfield voxel ray-march. Written out, its equations are:

       yaw     = heading_deg (math angle from +x towards +y. The DEM's y is the row direction, i.e. south)
       ang     = wrap(atan2(dy, dx) - yaw)                       # azimuth relative to the heading
       u       = (ang / fov_h + 0.5) * (W - 1)                   # **linear in angle** (linspace)
       focal   = (H/2) / tan(fov_h * H/W / 2)                    # vertical focal length (pixels)
       horizon = H/2 + focal * tan(pitch)                        # **pitch is a vertical shift (shear)**
       v       = horizon - focal * (z - cz) / r                  # r = horizontal range

2. **three.js pinhole** (`PerspectiveCamera` + `lookAt`) -- rectilinear. u = W/2 + f*x_c/z_c.

The two are the same only at the image centre. Elsewhere they differ, and vv.py measures by how much.
Coordinate conversion (scene -> three): X = x, Y = z, Z = -y (y_axis=north) | +y (y_axis=south).
"""
from __future__ import annotations

import math


def to_three(p, y_axis: str):
    """Scene coordinates (x, y, z-up) -> three.js coordinates (X, Y-up, Z). Right-handed; a north-up plan is not mirrored."""
    x, y, z = p
    return (x, z, -y if y_axis == "north" else y)


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def pinhole_pixel(view: dict, pt, W: int, H: int, y_axis: str):
    """Pixel (u, v) of a scene point in the three.js PerspectiveCamera(fov=vertical) + lookAt(target) model.
    Returns None if the point is behind the camera. v is 0 at the top of the image."""
    P = to_three(view["pos"], y_axis); T = to_three(view["target"], y_axis); X = to_three(pt, y_axis)
    f = _norm(_sub(T, P))
    r = _norm(_cross(f, (0.0, 1.0, 0.0)))          # three.js lookAt: up = +Y
    u_ = _cross(r, f)
    d = _sub(X, P)
    xc, yc, zc = _dot(d, r), _dot(d, u_), _dot(d, f)
    if zc <= 1e-9:
        return None
    fpx = (H / 2) / math.tan(math.radians(view["fov"]) / 2)
    return (W / 2 + fpx * xc / zc, H / 2 - fpx * yc / zc)


def sar_pixel(cam: dict, pt, W: int, H: int):
    """Pixel (u, v) of a point (x, y, z), using exactly the equations of `sar/camera.py`. None if outside the FOV.

    cam: {"x","y","z"(camera altitude),"heading_deg","pitch_deg","fov_deg"}. u is continuous here;
    sar/camera.py truncates it with int() when drawing -- vv.py compares at +/-1 px."""
    yaw = math.radians(cam["heading_deg"])
    half = math.radians(cam["fov_deg"]) / 2
    dx, dy = pt[0] - cam["x"], pt[1] - cam["y"]
    rng = math.hypot(dx, dy)
    if rng <= 1e-9:
        return None
    ang = (math.atan2(dy, dx) - yaw + math.pi) % (2 * math.pi) - math.pi
    if abs(ang) > half:
        return None
    focal = (H / 2) / math.tan(math.radians(cam["fov_deg"] * H / W) / 2)
    horizon = H / 2 + focal * math.tan(math.radians(cam["pitch_deg"]))
    u = (ang / (2 * half) + 0.5) * (W - 1)
    v = horizon - focal * (pt[2] - cam["z"]) / rng
    return (u, v)


def sar_to_view(cam: dict, W: int, H: int, dist: float = 100.0) -> dict:
    """The three.js view closest to the SAR camera: same position and heading, pitch as a rotation, same vertical FOV.
    In the scene the heading is a math angle from +x towards +y (y is south on a DEM)."""
    yaw = math.radians(cam["heading_deg"]); p = math.radians(cam["pitch_deg"])
    fov_v = cam["fov_deg"] * H / W                 # vertical FOV, as sar/camera.py uses it for its focal length
    tgt = [cam["x"] + dist * math.cos(yaw) * math.cos(p), cam["y"] + dist * math.sin(yaw) * math.cos(p),
           cam["z"] + dist * math.sin(p)]
    return {"pos": [cam["x"], cam["y"], cam["z"]], "target": tgt, "fov": fov_v}
