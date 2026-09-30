# -*- coding: utf-8 -*-
"""Scene -> 2D plan PNG (matplotlib).

- Interior (boxes): architectural plan. Wall thickness, glass facade and door openings, columns with grid
  bubbles, dimension lines, scale bar, north arrow, colour by zone, stair (UP/DN), lift, café seating, flow arrows.
- Heightfield (SAR): hillshade map + UAV track + truth/detection markers. The same world as the 3D view, from above.

Flows use scene["paths"] kind="flow" (list of 2D points).
"""
from __future__ import annotations

import os

_FONTS = ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
          "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
ZC = {"sale": "#F3D36B", "exp": "#F29E7B", "pay": "#7FB3D5", "boh": "#B9B3A9", "o2o": "#9BD19B", "circ": "#FFFFFF",
      "cafe": "#C9A27E", "evt": "#E8B4D8", "core": "#FFFFFF", "": "#DDDDDD"}
INK = "#222222"


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in _FONTS:
        if os.path.exists(f):
            try:
                fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
            except Exception:                        # noqa: BLE001
                continue
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def render(s: dict, png_path, title: "str | None" = None, note: "str | None" = None, heat=None, dpi: int = 170) -> str:
    plt = _mpl()
    if s.get("heightfield") and not s.get("boxes"):
        return _terrain(plt, s, png_path, title, dpi)
    return _interior(plt, s, png_path, title, note, heat, dpi)


def _interior(plt, s, png_path, title, note, heat, dpi):
    from matplotlib import patches
    W, D, _ = s["bounds"]
    fig, ax = plt.subplots(figsize=(12, 7.6), dpi=dpi)
    ax.set_aspect("equal"); ax.set_xlim(-2.4, W + 1.2); ax.set_ylim(-2.4, D + 2.6); ax.axis("off")
    if heat is not None:
        from matplotlib.colors import LinearSegmentedColormap
        cm = LinearSegmentedColormap.from_list("h", ["#ffffff00", "#fde68a", "#f97316", "#b91c1c"])
        ax.imshow(heat.T, origin="lower", extent=(0, W, 0, D), cmap=cm, alpha=0.85, interpolation="bilinear", zorder=1)
    else:
        ax.add_patch(patches.Rectangle((0, 0), W, D, fc="#FAF8F3", ec="none", zorder=0))
    for x in range(0, int(W) + 1):
        ax.plot([x, x], [0, D], color="#000", lw=0.15, alpha=0.12, zorder=0.5)
    for y in range(0, int(D) + 1):
        ax.plot([0, W], [y, y], color="#000", lw=0.15, alpha=0.12, zorder=0.5)
    for i in s["boxes"]:
        x0, y0, x1, y1, t = i["x0"], i["y0"], i["x1"], i["y1"], i["type"]
        zc = ZC.get(i.get("zone", ""), "#ddd")
        if t == "door":
            continue
        if t == "zone":
            ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fc=zc, alpha=0.25, ec="#666", lw=0.8, ls=(0, (4, 3)), zorder=2))
        elif t == "queue":
            ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fc="#7FB3D5", alpha=0.18, ec="#2E86C1", lw=0.8, ls=(0, (2, 2)), hatch="///", zorder=2))
        elif t == "dead":
            ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fc="none", ec="#B03A2E", lw=1.0, hatch="xx", zorder=2))
        elif t == "stair":
            ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fc="white", ec=INK, lw=1.4, zorder=3))
            mid = (x0 + x1) / 2
            ax.plot([mid, mid], [y0, y1], color=INK, lw=0.8, zorder=3.1)
            yy = y0 + 0.28
            while yy < y1 - 0.1:
                ax.plot([x0, x1], [yy, yy], color=INK, lw=0.4, zorder=3.1); yy += 0.28
            ax.annotate("", xy=((x0 + mid) / 2, y1 - 0.4), xytext=((x0 + mid) / 2, y0 + 0.3), arrowprops=dict(arrowstyle="-|>", color="#1E8449", lw=1.4), zorder=6)
            ax.annotate("", xy=((mid + x1) / 2, y0 + 0.3), xytext=((mid + x1) / 2, y1 - 0.4), arrowprops=dict(arrowstyle="-|>", color="#B03A2E", lw=1.4), zorder=6)
            ax.text((x0 + mid) / 2 + 0.35, y0 + 0.25, "UP", ha="center", fontsize=6.5, color="#1E8449", zorder=6)
            ax.text((mid + x1) / 2 + 0.35, y1 - 0.35, "DN", ha="center", fontsize=6.5, color="#B03A2E", zorder=6)
        elif t == "elevator":
            ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fc="#EDEDED", ec=INK, lw=1.4, zorder=3))
            ax.plot([x0, x1], [y0, y1], color=INK, lw=0.6, zorder=3.1); ax.plot([x0, x1], [y1, y0], color=INK, lw=0.6, zorder=3.1)
        elif t == "tables":
            ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fc=ZC["cafe"], alpha=0.12, ec="#8a6a4a", lw=0.6, ls=(0, (3, 3)), zorder=2))
            yy = y0 + 0.9
            while yy < y1 - 0.5:
                xx = x0 + 0.9
                while xx < x1 - 0.5:
                    ax.add_patch(patches.Circle((xx, yy), 0.38, fc="white", ec=INK, lw=0.7, zorder=3))
                    for dx in (-0.62, 0.62):
                        ax.add_patch(patches.Circle((xx + dx, yy), 0.2, fc=ZC["cafe"], ec=INK, lw=0.4, zorder=3))
                    xx += 2.2
                yy += 1.7
        elif t == "room":
            ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fc=ZC["exp"], alpha=0.35, ec=INK, lw=2.2, zorder=3))
            mid = (x0 + x1) / 2
            ax.plot([mid - 1.1, mid + 1.1], [y0, y0], color="#FAF8F3", lw=3.2, zorder=3.1)
        else:
            ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fc=zc, ec=INK, lw=1.6 if i.get("h", 0) >= 1.8 else 1.0, zorder=3))
            if t == "figure":
                ax.add_patch(patches.Circle(((x0 + x1) / 2, (y0 + y1) / 2), 0.55, fc="#C8813B", ec=INK, lw=1, zorder=3.2))
            if t == "stock":
                ax.plot([x0, x1], [y0, y1], color=INK, lw=0.6, zorder=3.1); ax.plot([x0, x1], [y1, y0], color=INK, lw=0.6, zorder=3.1)
        lab = "" if t in ("stair", "window") else i.get("label", "")
        if lab:
            cx, cy, ha = (x0 + x1) / 2, (y0 + y1) / 2, "center"
            vert = (y1 - y0) > 2.2 * (x1 - x0) and (x1 - x0) < 1.3
            if t in ("zone", "room", "tables", "queue") and not vert:
                cx, cy, ha = x0 + 0.15, y1 - 0.35, "left"
            elif t == "figure":
                cy = y0 - 0.35
            ax.text(cx, cy, lab, ha=ha, va="center", fontsize=6.2, rotation=90 if vert else 0, zorder=6, color=INK,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
    for (cx, cy) in s.get("columns", []):
        ax.add_patch(patches.Rectangle((cx - 0.3, cy - 0.3), 0.6, 0.6, fc=INK, ec=INK, zorder=5))
    t = 0.25
    doors = [i for i in s["boxes"] if i["type"] == "door"]
    segs = [(0, W)]
    for d in doors:
        new = []
        for a, b in segs:
            if d["x1"] <= a or d["x0"] >= b:
                new.append((a, b))
            else:
                if d["x0"] > a: new.append((a, d["x0"]))
                if d["x1"] < b: new.append((d["x1"], b))
        segs = new
    for a, b in segs:
        ax.add_patch(patches.Rectangle((a, -t), b - a, t, fc="#9EC9E2", ec=INK, lw=0.8, zorder=4))
    ax.add_patch(patches.Rectangle((-t, -t), t, D + 2 * t, fc=INK, zorder=4))
    ax.add_patch(patches.Rectangle((W, -t), t, D + 2 * t, fc=INK, zorder=4))
    ax.add_patch(patches.Rectangle((-t, D), W + 2 * t, t, fc=INK, zorder=4))
    for d in doors:
        out = "OUT" in d.get("label", "")
        mx = (d["x0"] + d["x1"]) / 2
        ax.annotate("", xy=(mx, -1.3 if out else 1.1), xytext=(mx, 1.1 if out else -1.3), arrowprops=dict(arrowstyle="-|>", color="#1E8449", lw=2), zorder=7)
        ax.text(mx, -1.75, d.get("label", ""), ha="center", fontsize=7.5, color="#1E8449")
    for p in s.get("paths", []):
        if p.get("kind") != "flow" or len(p["pts"]) < 2:
            continue
        pts = [(q[0], q[1]) for q in p["pts"]]
        col = p.get("color", "#1E8449")
        ax.plot(*zip(*pts), color=col, lw=2.2, alpha=0.9, zorder=6.5, solid_capstyle="round")
        for (a, b), (c, e) in zip(pts, pts[1:]):
            ax.annotate("", xy=(a + (c - a) * 0.6, b + (e - b) * 0.6), xytext=(a + (c - a) * 0.4, b + (e - b) * 0.4),
                        arrowprops=dict(arrowstyle="-|>", color=col, lw=2), zorder=6.6)

    def dim(x0, y0, x1, y1, txt, off):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="<|-|>", lw=0.7, color=INK))
        ax.text((x0 + x1) / 2 + (off if x0 == x1 else 0), (y0 + y1) / 2 + (0 if x0 == x1 else off), txt, ha="center", va="center",
                fontsize=7.5, rotation=90 if x0 == x1 else 0)
    dim(0, D + 0.9, W, D + 0.9, f"{W * 1000:,.0f}", 0.3)
    dim(-1.0, 0, -1.0, D, f"{D * 1000:,.0f}", -0.3)
    gxs = [0.0] + sorted({c[0] for c in s.get("columns", [])}) + [W]
    gys = [0.0] + sorted({c[1] for c in s.get("columns", [])}) + [D]
    for k, gx in enumerate(gxs):
        ax.add_patch(patches.Circle((gx, D + 1.35), 0.28, fc="white", ec=INK, lw=0.7, zorder=8))
        ax.text(gx, D + 1.35, chr(65 + k), ha="center", va="center", fontsize=7, zorder=9)
    for k, gy in enumerate(gys):
        ax.add_patch(patches.Circle((-2.0, gy), 0.28, fc="white", ec=INK, lw=0.7, zorder=8))
        ax.text(-2.0, gy, str(k + 1), ha="center", va="center", fontsize=7, zorder=9)
    for k in range(5):
        ax.add_patch(patches.Rectangle((W - 5 + k, -2.2), 1, 0.2, fc=INK if k % 2 == 0 else "white", ec=INK, lw=0.6))
    ax.text(W - 5, -1.75, "0", fontsize=6.5, ha="center"); ax.text(W, -1.75, "5 m", fontsize=6.5, ha="center")
    ax.annotate("N", xy=(W + 0.7, -0.4), xytext=(W + 0.7, -1.9), ha="center", fontsize=8, arrowprops=dict(arrowstyle="-|>", color=INK))
    ax.text(-2.3, D + 2.3, (title or s["name"]) + "  |  " + (note or "%.1f × %.1f m = %.0f m²" % (W, D, W * D)) + "  |  1:100 상당",
            fontsize=9, ha="left", va="bottom", color="#333", weight="bold")
    fig.savefig(png_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(png_path)


def _terrain(plt, s, png_path, title, dpi):
    import numpy as np
    hf = s["heightfield"]
    Z = np.asarray(hf["z"], dtype=float)
    xs = np.asarray(hf.get("xs") or np.arange(Z.shape[1]) * hf["mpp"]); ys = np.asarray(hf.get("ys") or np.arange(Z.shape[0]) * hf["mpp"])
    gy, gx = np.gradient(Z, ys, xs)
    az, alt = np.radians(315), np.radians(45)          # Same light source as sar/camera.py (315 deg)
    shade = np.clip(np.sin(alt) - np.cos(alt) * (gx * np.cos(az) + gy * np.sin(az)) / np.sqrt(1 + gx ** 2 + gy ** 2), 0, 1)
    fig, ax = plt.subplots(figsize=(9, 8), dpi=dpi)
    ext = (xs[0], xs[-1], ys[-1], ys[0])               # y = south (row direction) -> north at the top
    ax.imshow(Z, cmap="terrain", extent=ext, alpha=0.85)
    ax.imshow(shade, cmap="gray", extent=ext, alpha=0.35)
    for p in s.get("paths", []):
        a = np.asarray(p["pts"]); ax.plot(a[:, 0], a[:, 1], "-", color="#00a8e0", lw=2, label="UAV 궤적")
    for m in s.get("markers", []):
        st = {"uav": ("^", "#e53935", "UAV"), "truth": ("o", "#e53935", "TRUTH(관찰자만)"), "detect": ("x", "#1e8449", "SUT 탐지"),
              "poi": ("*", "#f2b200", "POI")}[m["kind"]]
        ax.scatter([m["x"]], [m["y"]], marker=st[0], c=st[1], s=90, edgecolor="k" if st[0] != "x" else None, label=st[2], zorder=5)
    h, l = ax.get_legend_handles_labels()
    u = dict(zip(l, h))
    if u:
        ax.legend(u.values(), u.keys(), loc="lower right", fontsize=8)
    ax.set_xlabel("x 동(m)"); ax.set_ylabel("y 남(m) — DEM 행 방향"); ax.set_title(title or s["name"], fontsize=10)
    fig.savefig(png_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(png_path)
