# -*- coding: utf-8 -*-
"""3D fallback for environments without a browser (matplotlib mplot3d). **Not photoreal** -- it only shows shapes.

pipeline.py always writes the backend it used ("matplotlib 대체(비실사)") in the output. Never report this as a photoreal render.
"""
from __future__ import annotations

import math


def render(s: dict, png_path, view: str = "aerial", dpi: int = 140) -> str:
    from render3d.plan import _mpl
    plt = _mpl()
    import numpy as np
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from render3d.plan import ZC
    fig = plt.figure(figsize=(11, 7), dpi=dpi)
    ax = fig.add_subplot(111, projection="3d")
    W, D, H = s["bounds"]
    light = np.array([-0.4, -0.5, 0.77]); light /= np.linalg.norm(light)
    polys, cols = [], []

    def cuboid(x0, y0, x1, y1, z0, z1, hexc):
        base = np.array([int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)])
        faces = {(0, 0, 1): [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
                 (0, -1, 0): [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
                 (0, 1, 0): [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
                 (-1, 0, 0): [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)],
                 (1, 0, 0): [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]}
        for n, f in faces.items():
            k = 0.45 + 0.55 * max(0.0, float(np.dot(n, light)))
            polys.append(f); cols.append(tuple(np.clip(base * k, 0, 1)))
    for b in s.get("boxes", []):
        if b["type"] in ("zone", "queue", "door", "dead"):
            continue
        h = {"stair": 1.2, "tables": 0.75, "room": b.get("h", 2.4)}.get(b["type"], b.get("h", 1.0)) or 0.3
        cuboid(b["x0"], b["y0"], b["x1"], b["y1"], 0, h, ZC.get(b.get("zone", ""), "#dddddd"))
    for (cx, cy) in s.get("columns", []):
        cuboid(cx - 0.3, cy - 0.3, cx + 0.3, cy + 0.3, 0, H, "#bbbbbb")
    if polys:
        ax.add_collection3d(Poly3DCollection(polys, facecolors=cols, edgecolors=(0, 0, 0, 0.25), linewidths=0.3))
    if s.get("heightfield"):
        hf = s["heightfield"]; Z = np.asarray(hf["z"], dtype=float)
        xs = np.asarray(hf.get("xs") or np.arange(Z.shape[1]) * hf["mpp"]); ys = np.asarray(hf.get("ys") or np.arange(Z.shape[0]) * hf["mpp"])
        X, Y = np.meshgrid(xs, ys)
        ax.plot_surface(X, Y, Z, cmap="terrain", linewidth=0, antialiased=True, alpha=0.95)
        for p in s.get("paths", []):
            a = np.asarray(p["pts"]); ax.plot(a[:, 0], a[:, 1], a[:, 2], color="#00a8e0", lw=2)
        for m in s.get("markers", []):
            ax.scatter([m["x"]], [m["y"]], [m["z"]], c={"truth": "#e53935", "detect": "#1e8449", "uav": "#e53935"}.get(m["kind"], "#f2b200"), s=40)
        zlo, zhi = float(Z.min()), float(Z.max())
    else:
        zlo, zhi = 0.0, H
    ax.set_xlim(0, W); ax.set_ylim(0, D); ax.set_zlim(zlo, zlo + max(zhi - zlo, 0.35 * max(W, D)))
    if s.get("y_axis") == "south":
        ax.invert_yaxis()
    v = (s.get("views") or {}).get(view)
    if v and view != "top":
        dx, dy, dz = (v["pos"][k] - v["target"][k] for k in range(3))
        az = math.degrees(math.atan2(dy, dx)); el = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        ax.view_init(elev=max(5, el), azim=az)
    elif view == "top":
        ax.view_init(elev=90, azim=-90)
    ax.set_axis_off()
    ax.set_title("%s  (matplotlib 대체 렌더 — 비실사)" % s["name"], fontsize=10)
    fig.savefig(png_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(png_path)
