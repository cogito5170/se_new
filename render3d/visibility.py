# -*- coding: utf-8 -*-
"""3D visibility for the reference world (referee) -- numpy only, no browser, fast enough for Monte Carlo.

Contract: render3d/핸드오프_센서스펙_관측계약.md
- The SUT never sees this module or its results. The reference world uses it to compute the observations (detection packets).
- Returned values: terrain_los, canopy_vis, pixel_count, slant_m, aspect_deg (handoff section 3).
- Sensor physics (thermal_dn, lidar_return, ...) stays in sar/sensors_ref.py. No reimplementation here -- only geometry.

## Where the geometry comes from (one source)

TREE below is the single definition of a tree's shape. html.py injects it into the three.js tree, so the two methods
(numpy rays <-> three.js mask render, vv G) measure **the same tree**. If they differed, the check would compare different trees.

    crown (cone)  radius TREE.cone_r*size, height TREE.cone_h*size, centre height TREE.cone_c*size  (base 0.1s ~ apex 1.2s)
    trunk (cylinder) radius TREE.trunk_r*size, height TREE.trunk_h*size, centre TREE.trunk_c*size

## Foliage transmittance -- the path length replaces the constant

The current reference world multiplies canopy targets by constants (RGB x0.05, thermal x0.25, LiDAR x0.1). Here the
foliage path length L that a ray actually crosses gives Beer's law (Monsi-Saeki):

    T_foliage = exp(-G * LAD * L)        G=0.5 (random leaf angle), LAD = leaf area density (m2/m3)

LAD is a **representative-value assumption** (default 1.5, conifer class). At L~4 m it gives exp(-3)=0.05, the same scale
as the current RGB constant. That is not a finding -- the value was chosen that way. So sweep LAD for sensitivity (vv).

## Camera (pixels on target) -- assumption

The repository has no camera resolution/FOV spec (sar/camera.py's 220x140 is for drawing). CAMERAS is a
**representative-class assumption** and is written as such in the output. Johnson: detection 50% at N50=1.0 cycle (~2 px).
"""
from __future__ import annotations

import math

TREE = {"cone_r": 0.35, "cone_h": 1.1, "cone_c": 0.65, "trunk_r": 0.07, "trunk_h": 0.3, "trunk_c": 0.12, "segments": 64}
CAMERAS = {  # Representative-class assumption (not a spec). w_px = horizontal pixels, hfov_deg = horizontal field of view
    "rgb": {"w_px": 4000, "hfov_deg": 84.0, "note": "가정: 소형 드론 광각 RGB 급"},
    "thermal": {"w_px": 640, "hfov_deg": 32.0, "note": "가정: 640 급 LWIR"},
}
PERSON = {"w": 0.5, "l": 1.7, "h": 0.15}      # Lying person, modelled as a flat rectangle (so the two methods measure the same shape)
LAD_DEFAULT, G_LEAF = 1.5, 0.5


def johnson_p(cycles: float, n50: float = 1.0) -> float:
    """TTPF: P = (N/N50)^E / (1 + (N/N50)^E), E = 2.7 + 0.7 (N/N50). Referent: P(N50) = 0.5."""
    if cycles <= 0:
        return 0.0
    x = cycles / n50
    e = 2.7 + 0.7 * x
    return float(x ** e / (1.0 + x ** e))


def pixels_across(crit_m: float, range_m: float, cam: dict) -> float:
    """Pixels spanned by a target of critical dimension crit_m at range_m. IFOV = hfov / w_px (small-angle approximation)."""
    ifov = math.radians(cam["hfov_deg"]) / cam["w_px"]
    return crit_m / max(1e-9, range_m * ifov)


class World:
    """DEM (+ trees, buildings) -> geometric visibility. Coordinates are the sar/camera.py world coordinates (x = col*mpp, y = row*mpp, z = elevation)."""

    def __init__(self, dem, mpp: float, features=(), lad: float = LAD_DEFAULT, cell: float = 60.0):
        import numpy as np
        self.dem = np.asarray(dem, dtype=float); self.mpp = float(mpp)
        self.DH, self.DW = self.dem.shape
        self.lad = float(lad); self.cell = float(cell)
        self.trees, self.buildings = [], []
        self._grid = {}
        for f in features:
            k = f.get("kind")
            if k == "tree":
                self.add_tree(float(f["wx"]), float(f["wy"]), float(f.get("size", 8.0)), z=float(f["z"]))
            elif k == "building":
                self.buildings.append((float(f["wx"]), float(f["wy"]), float(f["z"]), float(f.get("size", 10.0))))

    # ---- terrain (the same bilinear sampler as sar/camera.py _terrain_sampler)
    def ground(self, x, y):
        import numpy as np
        px = np.clip(np.asarray(x, dtype=float) / self.mpp, 0, self.DW - 1.001)
        py = np.clip(np.asarray(y, dtype=float) / self.mpp, 0, self.DH - 1.001)
        x0 = px.astype(int); y0 = py.astype(int); fx = px - x0; fy = py - y0
        d = self.dem
        h00 = d[y0, x0]; h10 = d[y0, x0 + 1]; h01 = d[y0 + 1, x0]; h11 = d[y0 + 1, x0 + 1]
        return (h00 * (1 - fx) + h10 * fx) * (1 - fy) + (h01 * (1 - fx) + h11 * fx) * fy

    def add_tree(self, x: float, y: float, size: float, z: "float | None" = None):
        z = float(self.ground(x, y)) if z is None else z
        self.trees.append((x, y, z, size))
        self.max_size = max(getattr(self, "max_size", 0.0), size)
        k = (int(x // self.cell), int(y // self.cell))
        self._grid.setdefault(k, []).append(len(self.trees) - 1)

    def _trees_near_segment(self, a, b, pad: float):
        """Indices of trees within pad (m) of segment ab, in the horizontal plane. Grid buckets -> only the few candidates."""
        x0, x1 = sorted((a[0], b[0])); y0, y1 = sorted((a[1], b[1]))
        out = set()
        for i in range(int((x0 - pad) // self.cell), int((x1 + pad) // self.cell) + 1):
            for j in range(int((y0 - pad) // self.cell), int((y1 + pad) // self.cell) + 1):
                out.update(self._grid.get((i, j), ()))
        return sorted(out)

    # ---- terrain line of sight
    def terrain_los(self, cam, tgt, step: "float | None" = None) -> bool:
        """Is the camera->target segment above the terrain? The first 1 m near the target (the target's own ground) is not checked."""
        import numpy as np
        L = math.dist(cam, tgt)
        n = max(8, int(L / (step or self.mpp * 0.5)))
        t = np.linspace(0.0, 1.0, n + 1)[1:-1]
        t = t[t * L > 1.0]
        if t.size == 0:
            return True
        xs = tgt[0] + (cam[0] - tgt[0]) * t; ys = tgt[1] + (cam[1] - tgt[1]) * t; zs = tgt[2] + (cam[2] - tgt[2]) * t
        return bool(np.all(zs > self.ground(xs, ys)))

    def terrain_los_many(self, cam, P, step: "float | None" = None):
        """terrain_los for many target points at once (vectorised). P: (n,3) -> bool (n,). Same rule as terrain_los (skip the first 1 m)."""
        import numpy as np
        cam = np.asarray(cam, dtype=float)
        L = np.linalg.norm(cam[None, :] - P, axis=1).max()
        m = max(8, int(L / (step or self.mpp * 0.5)))
        t = np.linspace(0.0, 1.0, m + 1)[1:-1]
        D = cam[None, :] - P
        lens = np.linalg.norm(D, axis=1)
        pts = P[:, None, :] + t[None, :, None] * D[:, None, :]
        gz = self.ground(pts[..., 0], pts[..., 1])
        above = pts[..., 2] > gz
        skip = (t[None, :] * lens[:, None]) <= 1.0
        return np.all(above | skip, axis=1)

    # ---- crown/trunk intersection (vectorised: many rays x one tree)
    @staticmethod
    def _cone_chord(P, D, tree):
        """Length of each ray segment P + t*D (t in [0,1]) inside the solid cone (between apex and base plane). P, D: (n,3).

        With w = distance down from the apex, inside <=> x^2 + y^2 <= k w^2 (k = (r/h)^2) and 0 <= w <= h.
        f(t) = A t^2 + B t + C <= 0 is the double-cone interior. **When A<0 the interior is the two outer intervals**
        (-inf, r1] and [r2, inf) -- the common case for steep rays looking down from a UAV. The first version assumed [r1, r2]
        only and treated this case as 0 (under-counting occlusion). Now every case is split out."""
        import numpy as np
        x, y, z, s = tree
        r, h = TREE["cone_r"] * s, TREE["cone_h"] * s
        zb = z + (TREE["cone_c"] - TREE["cone_h"] / 2) * s; za = zb + h
        k = (r / h) ** 2
        ox, oy, oz = P[:, 0] - x, P[:, 1] - y, za - P[:, 2]
        dx, dy, dz = D[:, 0], D[:, 1], -D[:, 2]
        A = dx * dx + dy * dy - k * dz * dz
        B = 2 * (ox * dx + oy * dy - k * oz * dz)
        C = ox * ox + oy * oy - k * oz * oz
        n = len(P); INF = np.inf
        # Slab 0<=w<=h intersected with t in [0,1]
        with np.errstate(divide="ignore", invalid="ignore"):
            ta = np.where(np.abs(dz) > 1e-12, (0 - oz) / dz, np.where((oz >= 0) & (oz <= h), -INF, INF))
            tb = np.where(np.abs(dz) > 1e-12, (h - oz) / dz, np.where((oz >= 0) & (oz <= h), INF, -INF))
        a = np.maximum(np.minimum(ta, tb), 0.0); b = np.minimum(np.maximum(ta, tb), 1.0)
        # Interior intervals of f<=0: (p1,q1) U (p2,q2)
        p1 = np.full(n, INF); q1 = np.full(n, -INF); p2 = np.full(n, INF); q2 = np.full(n, -INF)
        disc = B * B - 4 * A * C
        lin = np.abs(A) <= 1e-12
        with np.errstate(divide="ignore", invalid="ignore"):
            sq = np.sqrt(np.maximum(disc, 0.0))
            r1 = np.where(lin, 0.0, (-B - sq) / (2 * A)); r2 = np.where(lin, 0.0, (-B + sq) / (2 * A))
            lo, hi = np.minimum(r1, r2), np.maximum(r1, r2)
            t0 = np.where(np.abs(B) > 1e-12, -C / B, 0.0)
        # A>0, disc>=0: [lo,hi]
        m = (~lin) & (A > 0) & (disc >= 0); p1[m], q1[m] = lo[m], hi[m]
        # A<0, disc>=0: (-inf,lo] U [hi,inf)
        m = (~lin) & (A < 0) & (disc >= 0); p1[m], q1[m] = -INF, lo[m]; p2[m], q2[m] = hi[m], INF
        # A<0, disc<0: everywhere
        m = (~lin) & (A < 0) & (disc < 0); p1[m], q1[m] = -INF, INF
        # Linear: B t + C <= 0
        m = lin & (np.abs(B) > 1e-12) & (B > 0); p1[m], q1[m] = -INF, t0[m]
        m = lin & (np.abs(B) > 1e-12) & (B < 0); p1[m], q1[m] = t0[m], INF
        m = lin & (np.abs(B) <= 1e-12) & (C <= 0); p1[m], q1[m] = -INF, INF
        seg = np.maximum(0.0, np.minimum(q1, b) - np.maximum(p1, a)) + np.maximum(0.0, np.minimum(q2, b) - np.maximum(p2, a))
        return np.where(b > a, seg, 0.0) * np.linalg.norm(D, axis=1)

    @staticmethod
    def _cyl_hit(P, D, tree):
        """Does the ray hit the trunk cylinder (bool). Mostly hidden under the crown seen from above, but it matters for oblique views."""
        import numpy as np
        x, y, z, s = tree
        r = TREE["trunk_r"] * s
        zb = z + (TREE["trunk_c"] - TREE["trunk_h"] / 2) * s; zt = zb + TREE["trunk_h"] * s
        ox, oy = P[:, 0] - x, P[:, 1] - y
        A = D[:, 0] ** 2 + D[:, 1] ** 2; B = 2 * (ox * D[:, 0] + oy * D[:, 1]); C = ox * ox + oy * oy - r * r
        disc = B * B - 4 * A * C
        ok = (disc >= 0) & (A > 1e-12)
        sq = np.sqrt(np.where(ok, disc, 0.0))
        with np.errstate(divide="ignore", invalid="ignore"):
            t1 = (-B - sq) / (2 * A); t2 = (-B + sq) / (2 * A)
        hit = np.zeros(len(P), dtype=bool)
        for t in (t1, t2):
            zz = P[:, 2] + t * D[:, 2]
            hit |= ok & (t > 0) & (t < 1) & (zz >= zb) & (zz <= zt)
        return hit

    def _building_hit(self, P, D, b):
        import numpy as np
        x, y, z, s = b                             # html.py building: x=size, height 0.7size, depth 0.8size, centre z+0.35size
        lo = np.array([x - 0.5 * s, y - 0.4 * s, z]); hi = np.array([x + 0.5 * s, y + 0.4 * s, z + 0.7 * s])
        with np.errstate(divide="ignore", invalid="ignore"):
            t0 = (lo - P) / D; t1 = (hi - P) / D
        tmin = np.nanmax(np.minimum(t0, t1), axis=1); tmax = np.nanmin(np.maximum(t0, t1), axis=1)
        return (tmax >= np.maximum(tmin, 0)) & (tmin < 1)

    # ---- target visible fraction
    def target_samples(self, tgt_xy, yaw_deg: float = 0.0, n=(5, 15), dims=None):
        """Sample points on the target rectangle (flat, at ground + PERSON.h)."""
        import numpy as np
        w, l = (dims or (PERSON["w"], PERSON["l"]))
        u = (np.arange(n[0]) + 0.5) / n[0] - 0.5; v = (np.arange(n[1]) + 0.5) / n[1] - 0.5
        U, Vv = np.meshgrid(u * w, v * l)
        c, s_ = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
        X = tgt_xy[0] + c * U.ravel() - s_ * Vv.ravel(); Y = tgt_xy[1] + s_ * U.ravel() + c * Vv.ravel()
        Z = self.ground(X, Y) + PERSON["h"]
        return np.stack([X, Y, Z], axis=1)

    def visible_fraction(self, cam, tgt_xy, yaw_deg: float = 0.0, opaque: bool = False, n=(5, 15), lad=None) -> dict:
        """Of the target samples, the fraction whose ray to the camera is clear.
        opaque=True: trees are opaque (for comparison with the three.js mask render). False: Beer's-law foliage transmittance."""
        import numpy as np
        P = self.target_samples(tgt_xy, yaw_deg, n)
        cam = np.asarray(cam, dtype=float)
        D = cam[None, :] - P
        los = self.terrain_los_many(cam, P)
        T = np.ones(len(P))                        # foliage/building transmittance only (terrain is separate)
        centre = P.mean(axis=0)
        for i in self._trees_near_segment(centre, cam, pad=TREE["cone_r"] * getattr(self, "max_size", 0.0) + 2.0):
            tr = self.trees[i]
            chord = self._cone_chord(P, D, tr)
            trunk = self._cyl_hit(P, D, tr)
            if opaque:
                T = T * ((chord <= 1e-6) & ~trunk)
            else:
                T = T * np.exp(-G_LEAF * (self.lad if lad is None else lad) * chord) * (~trunk)
        for b in self.buildings:
            T = T * (~self._building_hit(P, D, b))
        return {"vis": float((T * los).mean()), "foliage_vis": float(T.mean()), "terrain_los": bool(los.mean() > 0.5),
                "los_frac": float(los.mean())}

    def observe_geometry(self, cam, tgt_xy, yaw_deg: float = 0.0, cams=None) -> dict:
        """Handoff section 3 values: terrain_los, canopy_vis, pixel_count(by sensor), slant_m, aspect_deg, p_johnson(by sensor)."""
        tz = float(self.ground(tgt_xy[0], tgt_xy[1])) + PERSON["h"]
        slant = math.dist(cam, (tgt_xy[0], tgt_xy[1], tz))
        horiz = math.hypot(cam[0] - tgt_xy[0], cam[1] - tgt_xy[1])
        aspect = math.degrees(math.atan2(horiz, max(1e-6, cam[2] - tz)))          # 0 = nadir
        vf = self.visible_fraction(cam, tgt_xy, yaw_deg)
        crit = math.sqrt(PERSON["w"] * PERSON["l"] * max(0.05, math.cos(math.radians(aspect))))  # projected critical dimension (lying)
        # canopy_vis = terrain x foliage combined (handoff section 3). foliage_vis and los_frac are exposed separately for ablation.
        out = {"terrain_los": vf["terrain_los"], "canopy_vis": vf["vis"], "foliage_vis": vf["foliage_vis"], "los_frac": vf["los_frac"],
               "slant_m": slant, "aspect_deg": aspect}
        for k, c in (cams or CAMERAS).items():
            px = pixels_across(crit, slant, c)
            out["pixel_count_" + k] = px
            out["p_johnson_" + k] = johnson_p(px / 2.0)            # cycles = pixels / 2
        return out
