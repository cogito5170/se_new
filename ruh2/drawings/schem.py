"""Thin helpers: schemdraw elements + matplotlib text on a shared data coordinate system."""
from common import *
import schemdraw, schemdraw.elements as elm
from matplotlib.patches import Rectangle
schemdraw.config(font="NanumGothic", fontsize=8.5, lw=1.1)

class Sch:
    def __init__(self, fig, rect_in, xlim, ylim):
        x0, y0, w, h = rect_in
        self.ax = fig.add_axes([x0 / W, y0 / H, w / W, h / H])
        self.d = schemdraw.Drawing(canvas=self.ax, show=False)
        self.xlim, self.ylim = xlim, ylim
        self.texts = []
    def add(self, e):
        return self.d.add(e)
    # ---- wires / nodes
    def w(self, *pts, color="k", lw=1.1):
        for a, b in zip(pts[:-1], pts[1:]):
            self.d.add(elm.Line(color=color, lw=lw).at(a).to(b))
    def dot(self, p):
        self.d.add(elm.Dot(radius=0.12).at(p))
    def gnd(self, p, kind="gnd"):
        e = {"gnd": elm.Ground, "sig": elm.GroundSignal, "chassis": elm.GroundChassis}[kind]
        self.d.add(e().at(p))
    def vdd(self, p, name):
        self.d.add(elm.Vdd().at(p).label(name, fontsize=8))
    # ---- 2-terminal
    def two(self, cls, p, dirn, L, lab=None, loc="top", ofst=None, fs=8, **kw):
        e = cls(**kw).at(p).length(L)
        e = getattr(e, dirn)()
        if lab:
            e = e.label(lab, loc=loc, fontsize=fs, **({"ofst": ofst} if ofst is not None else {}))
        return self.d.add(e)
    def R(self, p, dirn, lab, L=2.0, **k): return self.two(elm.Resistor, p, dirn, L, lab, **k)
    def C(self, p, dirn, lab, L=1.6, **k): return self.two(elm.Capacitor, p, dirn, L, lab, **k)
    # ---- text
    def t(self, x, y, s, fs=8, ha="left", va="center", color="k", bold=False, box=False, **kw):
        bb = dict(fc="white", ec="none", pad=0.4) if box is True else box if box else None
        self.texts.append((x, y, s, dict(fontsize=fs, ha=ha, va=va, color=color,
                                        fontweight="bold" if bold else "normal", bbox=bb, zorder=10, **kw)))
    def net(self, p, name, side="right", color="#1f5fa8", fs=7.8):
        """net flag: pentagon-ish box text next to point p"""
        x, y = p
        ha = "left" if side == "right" else "right"
        dx = 0.15 if side == "right" else -0.15
        self.t(x + dx, y, name, fs=fs, ha=ha, color=color,
               box=dict(fc="#eef4fb", ec=color, lw=0.7, boxstyle="round,pad=0.25"))
    def ic(self, x0, y0, w, h, name, part, left=(), right=(), bottom=(), top=(), stub=0.8, fs=7.4, fill="#fafafa"):
        """pins: list of (name, offset from bottom/left). returns dict name->pin tip point"""
        self.boxes = getattr(self, "boxes", [])
        self.boxes.append((x0, y0, w, h, fill))
        pins = {}
        for n, yy in left:
            self.w((x0 - stub, y0 + yy), (x0, y0 + yy)); pins[n] = (x0 - stub, y0 + yy)
            self.t(x0 + 0.15, y0 + yy, n, fs=fs)
        for n, yy in right:
            self.w((x0 + w, y0 + yy), (x0 + w + stub, y0 + yy)); pins[n] = (x0 + w + stub, y0 + yy)
            self.t(x0 + w - 0.15, y0 + yy, n, fs=fs, ha="right")
        for n, xx in bottom:
            self.w((x0 + xx, y0 - stub), (x0 + xx, y0)); pins[n] = (x0 + xx, y0 - stub)
            self.t(x0 + xx, y0 + 0.2, n, fs=fs, ha="center", va="bottom")
        for n, xx in top:
            self.w((x0 + xx, y0 + h), (x0 + xx, y0 + h + stub)); pins[n] = (x0 + xx, y0 + h + stub)
            self.t(x0 + xx, y0 + h - 0.2, n, fs=fs, ha="center", va="top")
        self.t(x0 + w / 2, y0 + h + 0.25, name, fs=8.6, ha="center", va="bottom", bold=True)
        self.t(x0 + w / 2, y0 - (stub + 1.35 if bottom else 0.25), part, fs=7.4, ha="center", va="top", color="#333")
        return pins
    def frame(self, x0, y0, x1, y1, title, color="#777"):
        self.frames = getattr(self, "frames", [])
        self.frames.append((x0, y0, x1, y1, color))
        self.t(x0 + 0.3, y1 - 0.3, title, fs=9.5, va="top", bold=True, color=color)
    def finish(self):
        self.d.draw(show=False)
        ax = self.ax
        for (x0, y0, w, h, fill) in getattr(self, "boxes", []):
            ax.add_patch(Rectangle((x0, y0), w, h, fc=fill, ec="k", lw=1.2, zorder=3))
        for (x0, y0, x1, y1, c) in getattr(self, "frames", []):
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=c, lw=1.0, ls=(0, (5, 3)), zorder=0))
        for x, y, s, kw in self.texts:
            ax.text(x, y, s, **kw)
        ax.set_xlim(*self.xlim); ax.set_ylim(*self.ylim); ax.set_aspect("equal", adjustable="box")
        ax.axis("off")
