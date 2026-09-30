# -*- coding: utf-8 -*-
"""Scene format -- the one JSON that the plan, 3D render, HTML and V&V all read.

    {
      "name": str,
      "y_axis": "north" | "south",      # direction of +y (plan: north, DEM rows: south)
      "bounds": [W, D, H],               # extent (m). For a heightfield, [nx*mpp, ny*mpp, relief]
      "shell": bool,                     # draw walls, facade and ceiling (interior)
      "boxes": [{"id","type","x0","y0","x1","y1","h","label","zone", "n"?}],
      "columns": [[x, y], ...],
      "heightfield": {"z": [[...]], "mpp": m} | None,     # z[j][i] = elevation at (i*mpp, j*mpp)
      "props": [{"kind": "tree|rock|building", "x","y","z","size"}],   # SceneDB features
      "markers": [{"kind": "uav|truth|detect|poi", "x","y","z","label"}],
      "paths": [{"kind": "uav_track|flow", "pts": [[x,y,z],...]}],
      "people": [[x, y], ...],
      "signs": [[text, x, y, z, w, h, rotY], ...],
      "fog": {"beta": 1/m, "color": [r,g,b], "model": "beer_lambert" | "three_default", "views": [...]?} | None,
                                         # views: only these views get fog (none = every view)
      "views": {name: {"pos": [x,y,z], "target": [x,y,z], "fov": vertical fov (deg), "near"?: m}},
      "linear_output": bool,             # V&V only: no tone mapping, linear output (pixel = radiance)
      "unlit_planes": [{"x","y","z","size","color"}],   # V&V only: unlit planes (for measuring fog/projection)
      "mask": {"x","y","z","w","l","yaw_deg","occluders"},  # V&V G only: target = white, the rest = black (occluders=False hides the rest)
    }

Heavy dependencies (numpy/matplotlib) are not needed here -- the dispatch path imports this module too (G012).
"""
from __future__ import annotations

import json
from pathlib import Path

BOX_TYPES = {
    "wall_shelf", "island", "gondola", "checkout", "figure", "media", "stock", "kiosk", "room", "stair",
    "elevator", "tables", "window", "bin", "zone", "queue", "door", "dead", "block",
}
MARKER_KINDS = {"uav", "truth", "detect", "poi"}
PROP_KINDS = {"tree", "rock", "building", "person"}   # person = lying person 0.5x1.7 m (same shape as visibility.PERSON), yaw_deg


def new(name: str, y_axis: str = "north", bounds=(10.0, 10.0, 3.0), shell: bool = False) -> dict:
    return {"name": name, "y_axis": y_axis, "bounds": list(bounds), "shell": shell, "boxes": [], "columns": [],
            "heightfield": None, "props": [], "markers": [], "paths": [], "people": [], "signs": [],
            "fog": None, "views": {}}


def check(s: dict) -> "list[str]":
    """Return a list of problems (empty if none). Say what is wrong, do not silently fix it."""
    bad = []
    if s.get("y_axis") not in ("north", "south"):
        bad.append("y_axis must be north|south: %r" % s.get("y_axis"))
    b = s.get("bounds")
    if not (isinstance(b, (list, tuple)) and len(b) == 3 and all(isinstance(v, (int, float)) and v > 0 for v in b)):
        bad.append("bounds must be three positive numbers [W,D,H]: %r" % (b,))
    for i, x in enumerate(s.get("boxes", [])):
        if x.get("type") not in BOX_TYPES:
            bad.append("boxes[%d] unknown type %r" % (i, x.get("type")))
        if not (x.get("x1", 0) > x.get("x0", 0) and x.get("y1", 0) > x.get("y0", 0)):
            bad.append("boxes[%d](%s) has x1<=x0 or y1<=y0" % (i, x.get("id")))
    hf = s.get("heightfield")
    if hf:
        z = hf.get("z") or []
        if not z or len({len(r) for r in z}) != 1 or len(z) < 2 or len(z[0]) < 2:
            bad.append("heightfield.z must be a rectangular grid of at least 2x2")
        if not hf.get("mpp", 0) > 0:
            bad.append("heightfield.mpp must be > 0")
    for i, m in enumerate(s.get("markers", [])):
        if m.get("kind") not in MARKER_KINDS:
            bad.append("markers[%d] unknown kind %r" % (i, m.get("kind")))
    for i, p in enumerate(s.get("props", [])):
        if p.get("kind") not in PROP_KINDS:
            bad.append("props[%d] unknown kind %r" % (i, p.get("kind")))
    f = s.get("fog")
    if f and not (f.get("beta", -1) >= 0 and f.get("model", "beer_lambert") in ("beer_lambert", "three_default")):
        bad.append("fog must have beta>=0 and model beer_lambert|three_default")
    for k, v in (s.get("views") or {}).items():
        if not (len(v.get("pos", [])) == 3 and len(v.get("target", [])) == 3 and 0.01 < v.get("fov", 0) < 179):
            bad.append("views[%s] needs pos/target of length 3 and 0.01<fov<179" % k)
    return bad


def save(s: dict, path) -> str:
    bad = check(s)
    if bad:
        raise ValueError("invalid scene: " + "; ".join(bad[:5]))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return str(path)


def load(path) -> dict:
    s = json.loads(Path(path).read_text(encoding="utf-8"))
    bad = check(s)
    if bad:
        raise ValueError("invalid scene: " + "; ".join(bad[:5]))
    return s


def auto_views(s: dict) -> dict:
    """Aerial and top views computed from the bounds, for a scene that has no views."""
    W, D, H = s["bounds"]
    big = max(W, D)
    fr = -1.0 if s.get("y_axis") == "north" else D + 1.0          # 'front' = in front of the plan's bottom edge
    return {
        "aerial": {"pos": [W + 0.21 * big, fr - (0.7 * big if s.get("y_axis") == "north" else -0.7 * big) * 0.6,
                           max(H, 0.1 * big) + 0.66 * big],
                   "target": [W / 2, D / 2, 0.0], "fov": 40.0},
    }
