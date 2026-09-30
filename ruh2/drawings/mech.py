"""mm-unit drawing helpers on a full-sheet axes (A3 = 420 x 297 mm, so 1 unit = 1 mm printed)."""
from common import *
from matplotlib.patches import Polygon, Circle, FancyArrowPatch, Rectangle as Rct
MM = 25.4

def mm_axes(fig):
    ax = fig.add_axes([0, 0, 1, 1], zorder=2)
    ax.set_xlim(0, W * MM); ax.set_ylim(0, H * MM); ax.set_aspect("equal"); ax.axis("off")
    ax.patch.set_alpha(0)
    return ax

HATCH = dict(steel=("////", "#dfe6ee"), ptfe=("xxxx", "#fbf3dc"), stack=("", "#8fa7c4"), epdm=("", "#222"),
             brass=("\\\\\\\\", "#f2e2b8"), none=("", "white"))

def rect(ax, x0, y0, x1, y1, mat="steel", lw=0.9, z=3, ec="k", **kw):
    h, fc = HATCH[mat]
    ax.add_patch(Rct((x0, y0), x1 - x0, y1 - y0, fc=fc, ec=ec, lw=lw, hatch=h, zorder=z, **kw))

def poly(ax, pts, mat="steel", lw=0.9, z=3, ec="k"):
    h, fc = HATCH[mat]
    ax.add_patch(Polygon(pts, closed=True, fc=fc, ec=ec, lw=lw, hatch=h, zorder=z))

def arr(ax, p, q, lw=0.6, color="k", both=True, ms=6):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="<|-|>" if both else "-|>", mutation_scale=ms, lw=lw,
                                 color=color, shrinkA=0, shrinkB=0, zorder=8))

def dim_h(ax, x1, x2, yf1, yf2, yd, text, fs=7.5, above=True, tx=None):
    for x, yf in ((x1, yf1), (x2, yf2)):
        s = 1 if yd > yf else -1
        ax.plot([x, x], [yf + s * 1.0, yd + s * 1.5], color="k", lw=0.45, zorder=8)
    arr(ax, (x1, yd), (x2, yd))
    ax.text((x1 + x2) / 2 if tx is None else tx, yd + (0.8 if above else -0.8), text, ha="center",
            va="bottom" if above else "top", fontsize=fs, zorder=9, bbox=dict(fc="white", ec="none", pad=0.3))

def dim_v(ax, y1, y2, xf1, xf2, xd, text, fs=7.5, left=True, ty=None):
    for y, xf in ((y1, xf1), (y2, xf2)):
        s = 1 if xd > xf else -1
        ax.plot([xf + s * 1.0, xd + s * 1.5], [y, y], color="k", lw=0.45, zorder=8)
    arr(ax, (xd, y1), (xd, y2))
    ax.text(xd + (-0.8 if left else 0.8), (y1 + y2) / 2 if ty is None else ty, text, ha="right" if left else "left",
            va="center", rotation=0, fontsize=fs, zorder=9, bbox=dict(fc="white", ec="none", pad=0.3))

def leader(ax, p, tpos, text, fs=7.3, ha="left", color="k"):
    ax.plot([p[0], tpos[0]], [p[1], tpos[1]], color=color, lw=0.5, zorder=9)
    ax.plot(p[0], p[1], "o", ms=1.8, color=color, zorder=9)
    ax.text(tpos[0] + (0.8 if ha == "left" else -0.8), tpos[1], text, ha=ha, va="center", fontsize=fs, zorder=9,
            color=color, bbox=dict(fc="white", ec="none", pad=0.4))

def center_line(ax, p, q):
    ax.plot([p[0], q[0]], [p[1], q[1]], color="#555", lw=0.5, ls=(0, (12, 3, 2, 3)), zorder=7)

def table(ax, x0, y0, colw, rows, rh=5.2, fs=7.2, head_fc="#eef4fb", title=None, red_rows=()):
    n = len(rows); xs = [x0]
    for c in colw: xs.append(xs[-1] + c)
    ytop = y0 + n * rh
    ax.add_patch(Rct((x0, ytop - rh), xs[-1] - x0, rh, fc=head_fc, ec="none", zorder=4))
    for i, r in enumerate(rows):
        y = ytop - (i + 0.5) * rh
        for j, c in enumerate(r):
            ax.text(xs[j] + 1.2, y, c, fontsize=fs, va="center", zorder=6, fontweight="bold" if i == 0 else "normal",
                    color="#b00000" if (i in red_rows and j == len(r) - 1) else "k")
    for i in range(n + 1):
        ax.plot([x0, xs[-1]], [ytop - i * rh] * 2, color="k", lw=0.9 if i in (0, 1, n) else 0.4, zorder=5)
    for x in xs:
        ax.plot([x, x], [y0, ytop], color="k", lw=0.5, zorder=5)
    if title:
        ax.text(x0, ytop + 1.5, title, fontsize=8.5, fontweight="bold", va="bottom", zorder=6)
    return xs[-1], ytop
