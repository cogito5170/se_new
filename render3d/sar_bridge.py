# -*- coding: utf-8 -*-
"""SAR world -> scene. The SAR pipeline and render3d look at **the same world**.

Input (the SAR package's own formats, as-is):
    dem[y,x] (m), mpp (m/px)                   sar/terrain.py, sar/ivv/reference.py (Reference.dem, .mpp)
    SceneDB features {"kind","size","wx","wy","z"}  sar/scene.py (SceneDB.generate)
    IV&V frames [{"sut_pose":(gx,gy), "truth":{"targets":[(gx,gy)]}, "sut":{"detections":[(gx,gy,..)]}}]
                                               sar/ivv/harness.run_one(record_frames=True). Grid GW=GH=24
    Fog: visibility V (m) -> beta = 3.912/V    sar/sensors.py (Koschmieder)

World coordinates are those of sar/camera.py: x = column * mpp (east), y = row * mpp (row direction = south), z = elevation.
So the scene is y_axis="south". The **viewer may see truth** (sar/ivv/viewer.py rule) -- this is a visualisation, not an evaluator.
"""
from __future__ import annotations

import math

from render3d import scene as S
from render3d import fog as FOG

GRID = 24          # sar/ivv/reference.py GW=GH


def _subsample(dem, max_n: int = 129):
    """Heightfield subsampling (vertex count). Keeps the endpoints so the extent does not change."""
    import numpy as np
    DH, DW = dem.shape
    ix = np.unique(np.round(np.linspace(0, DW - 1, min(DW, max_n))).astype(int))
    iy = np.unique(np.round(np.linspace(0, DH - 1, min(DH, max_n))).astype(int))
    return dem[np.ix_(iy, ix)], ix, iy


def terrain_scene(dem, mpp: float, name: str = "SAR 지형", features=None, V_m: "float | None" = None,
                  max_n: int = 129, scenedb=None, fidelity: str = "L1 합성/주어진 DEM(출처 미상)") -> dict:
    """DEM (+ SceneDB features, + fog) -> scene. The heightfield vertices are at exact DEM grid points (vv checks this)."""
    import numpy as np
    dem = np.asarray(dem, dtype=float)
    DH, DW = dem.shape
    sub, ix, iy = _subsample(dem, max_n)
    # Vertex spacing is not uniform (unique rounding), so give the actual x/y coordinates explicitly.
    W, D = (DW - 1) * mpp, (DH - 1) * mpp
    relief = float(dem.max() - dem.min()) or 1.0
    s = S.new(name, "south", (W, D, relief), shell=False)
    s["fidelity"] = fidelity
    s["heightfield"] = {"z": [[round(float(v), 2) for v in row] for row in sub], "mpp": mpp,
                        "xs": [float(i * mpp) for i in ix], "ys": [float(j * mpp) for j in iy],
                        "zmin": float(dem.min()), "zmax": float(dem.max())}
    if scenedb is not None:                 # Ground colour = SceneDB land-cover RGB view (the same ground_rgb sar/camera.py uses)
        try:
            X, Y = np.meshgrid(ix * mpp, iy * mpp)
            g = np.asarray(scenedb.ground_rgb(X.ravel(), Y.ravel()), dtype=float).reshape(len(iy), len(ix), 3)
            s["heightfield"]["colors"] = [[[round(float(c), 3) for c in px] for px in row] for row in g]
        except Exception:                   # noqa: BLE001 -- fall back to the elevation palette
            pass
    try:
        from sar.scene import MATERIAL as _MAT       # Same material RGB as the SAR RGB view
    except Exception:                                # noqa: BLE001
        _MAT = {}
    for f in (features or [])[:4000]:
        k = f.get("kind")
        if k in S.PROP_KINDS:
            p = {"kind": k, "x": float(f["wx"]), "y": float(f["wy"]), "z": float(f["z"]), "size": float(f.get("size", 6.0))}
            if k in _MAT:
                p["color"] = list(_MAT[k]["rgb"])
            s["props"].append(p)
    if V_m:
        s["fog"] = {"beta": FOG.beta_from_visibility(V_m), "color": [0.75, 0.78, 0.82], "model": "beer_lambert", "V_m": V_m,
                    "views": ["onboard"]}          # Fog is on the sensor (onboard camera) only, not the observer's aerial view
    big = max(W, D)
    s["views"]["aerial"] = {"pos": [W * 0.5 + 0.55 * big, D + 0.55 * big, float(dem.max()) + 0.55 * big],
                            "target": [W / 2, D / 2, float(dem.mean())], "fov": 40.0}
    return s


def _grid_to_world(g, DW, DH, mpp):
    """IV&V grid (GW=GH=24) -> world (m). Same as sar/ivv/viewer.py zc(): pixel index = g/GRID*DW. Clipped to the DEM extent."""
    return (min(g[0] / GRID * DW, DW - 1) * mpp, min(g[1] / GRID * DH, DH - 1) * mpp)


def _h(dem, mpp, x, y):
    """Terrain height (m) -- the same bilinear sampler sar/camera.py uses."""
    import numpy as np
    from sar.camera import _terrain_sampler
    return float(_terrain_sampler(dem, mpp)(np.array([x]), np.array([y]))[0])


def mission_scene(dem, mpp: float, frames, agl: float = 90.0, V_m: "float | None" = None,
                  features=None, name: str = "IV&V 임무", scenedb=None, fidelity: str = "L1 합성/주어진 DEM(출처 미상)") -> dict:
    """IV&V frames -> terrain + UAV track + truth targets (visible to the viewer only) + SUT detections + onboard camera view."""
    import numpy as np
    dem = np.asarray(dem, dtype=float)
    DH, DW = dem.shape
    s = terrain_scene(dem, mpp, name=name, features=features, V_m=V_m, scenedb=scenedb, fidelity=fidelity)
    track = []
    for fr in frames:
        x, y = _grid_to_world(fr["sut_pose"], DW, DH, mpp)
        track.append([x, y, _h(dem, mpp, x, y) + agl])
    if track:
        s["paths"].append({"kind": "uav_track", "pts": track})
        s["markers"].append({"kind": "uav", "x": track[-1][0], "y": track[-1][1], "z": track[-1][2], "label": "UAV"})
    seen = set()
    for fr in frames[-1:]:
        for t in fr.get("truth", {}).get("targets", []):
            x, y = _grid_to_world(t, DW, DH, mpp)
            s["markers"].append({"kind": "truth", "x": x, "y": y, "z": _h(dem, mpp, x, y) + 2.0, "label": "TRUTH"})
    for fr in frames:
        for d in fr.get("sut", {}).get("detections", []):
            key = (round(d[0], 1), round(d[1], 1))
            if key in seen:
                continue
            seen.add(key)
            x, y = _grid_to_world(d, DW, DH, mpp)
            s["markers"].append({"kind": "detect", "x": x, "y": y, "z": _h(dem, mpp, x, y) + 2.0, "label": "SUT"})
    if len(track) >= 2:                     # Onboard camera: at the last pose, looking along the direction of travel (SAR camera convention)
        (x0, y0, _), (x1, y1, z1) = track[-2], track[-1]
        hd = math.degrees(math.atan2(y1 - y0, x1 - x0)) if (x1, y1) != (x0, y0) else 0.0
        from render3d.camera import sar_to_view
        s["views"]["onboard"] = sar_to_view({"x": x1, "y": y1, "z": z1, "heading_deg": hd, "pitch_deg": -30.0,
                                             "fov_deg": 72.0}, 220, 140, dist=200.0)
        s["meta"] = {"onboard_sar_cam": {"x": x1, "y": y1, "z": z1, "heading_deg": hd, "pitch_deg": -30.0, "fov_deg": 72.0}}
    return s


def synthetic_dem(n: int = 96, seed: int = 0):
    """DEM for testing and demos without network (same form as the synthetic terrain the tests use)."""
    import numpy as np
    y, x = np.mgrid[0:n, 0:n] / float(n)
    rng = np.random.default_rng(seed)
    return 700 + 300 * (np.sin(3 * x) * np.cos(2 * y) + x) + rng.normal(0, 2.0, (n, n))


def canyon_dem(n: int = 96, seed: int = 0, relief: float = 450.0, spacing_px: float = 18.0):
    """Canyon terrain -- deep V-shaped valleys at intervals of spacing_px (in pixels; 96 px over 6 km is ~1.1 km).

    Why it exists: on synthetic_dem (gentle hills), with AGL 60-150 m, terrain occlusion never happened in 200 scenarios
    (scene3d A/B 'terrain only' == off). To measure the terrain effect you need valleys deep enough that targets inside them can be hidden."""
    import numpy as np
    y, x = np.mgrid[0:n, 0:n].astype(float)
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * np.pi, 2)
    # Meandering valley axes: a folded triangle wave (sharp ridges, V-shaped valleys)
    u = (x + 6.0 * np.sin(y / 11.0 + ph[0])) / spacing_px
    tri = 2 * np.abs(u - np.floor(u) - 0.5)                # 0 = valley floor, 1 = ridge crest
    return 600.0 + relief * tri ** 1.3 + 40.0 * np.sin(y / 23.0 + ph[1]) + rng.normal(0, 1.5, (n, n))


def synthetic_mission(n: int = 96, mpp: float = 20.0, seed: int = 0, V_m: float = 400.0):
    """No network: synthetic DEM + SceneDB + lawnmower-pattern frames -> (dem, mpp, frames, features, scenedb)."""
    dem = synthetic_dem(n, seed)
    feats, sdb = [], None
    try:
        from sar.scene import SceneDB
        sdb = SceneDB(dem, mpp, seed=seed)
        feats = sdb.generate(max_features=600)
    except Exception:                                   # noqa: BLE001 -- terrain only, without SceneDB
        feats, sdb = [], None
    frames, truth = [], {"targets": [(17.0, 7.0), (6.0, 18.0)]}
    path = [(x, y) for y in (4, 10, 16, 20) for x in (range(3, 22, 3) if y % 12 == 4 else range(21, 2, -3))]
    for k, (gx, gy) in enumerate(path):
        det = [(17.3, 7.2, 0.9)] if k > len(path) // 2 else []
        frames.append({"t": float(k), "sut_pose": [float(gx), float(gy)], "sut": {"detections": det}, "truth": truth})
    return dem, mpp, frames, feats, sdb


def reference_scene(ref, pose, target_index: int = 0, W: int = 1600, H: int = 1200, name: str = "참조세계 3D") -> dict:
    """The scene3d reference world (Reference.world3d) as-is -> scene. **The same trees, buildings and targets the visibility calculation uses.**

    pose: UAV grid position (gx, gy). Views:
      rgb      onboard RGB camera: UAV at AGL, looking at the target, horizontal FOV = visibility.CAMERAS['rgb'] (assumption)
      closeup  observer oblique view 60 m around the target (no fog)
      aerial   whole patch (no fog)
    Fog (Beer-Lambert, beta=3.912/V) is applied only to the rgb view -- fog is sensor physics (the observer view is clear)."""
    import numpy as np
    from render3d.visibility import CAMERAS, PERSON
    w3 = ref.world3d
    feats = [{"kind": "tree", "wx": x, "wy": y, "z": z, "size": s} for (x, y, z, s) in w3.trees]
    feats += [{"kind": "building", "wx": x, "wy": y, "z": z, "size": s} for (x, y, z, s) in w3.buildings]
    s = terrain_scene(ref.dem, float(ref.mpp), name=name, features=feats, V_m=float(ref.V), fidelity=ref.fidelity)
    for k, tg in enumerate(ref._targets):
        x, y = ref._g2w(tg["gx"], tg["gy"])
        s["props"].append({"kind": "person", "x": x, "y": y, "z": float(w3.ground(x, y)), "size": 1.0, "yaw_deg": tg.get("yaw3d", 0.0)})
    tg = ref._targets[target_index]
    tx, ty = ref._g2w(tg["gx"], tg["gy"]); tz = float(w3.ground(tx, ty)) + PERSON["h"]
    cx, cy = ref._g2w(*pose); cz = float(w3.ground(cx, cy)) + float(ref.AGL)
    hf = CAMERAS["rgb"]["hfov_deg"]
    fov_v = 2 * math.degrees(math.atan(math.tan(math.radians(hf / 2)) * H / W))
    slant = math.dist((cx, cy, cz), (tx, ty, tz))
    s["views"]["rgb"] = {"pos": [cx, cy, cz], "target": [tx, ty, tz], "fov": fov_v, "near": max(0.5, slant / 400)}
    d = np.array([tx - cx, ty - cy]); d = d / (np.linalg.norm(d) or 1.0)
    s["views"]["closeup"] = {"pos": [tx - 45 * d[0] + 20, ty - 45 * d[1] + 20, tz + 38], "target": [tx, ty, tz], "fov": 40.0, "near": 0.3}
    s["fog"]["views"] = ["rgb"]
    s["meta"] = {"rgb_cam": {"pos": [cx, cy, cz], "hfov_deg": hf, "w_px": W, "h_px": H, "slant_m": slant,
                             "person_px_across": PERSON["w"] / (slant * math.radians(hf) / W)}}
    return s


def render_mission(ref, frames, out_dir, stem: str, repo=None, views=("aerial", "onboard")) -> "list[str]":
    """IV&V hook: Reference (.dem, .mpp, .AGL, .V) + frames -> plan, photoreal 3D and HTML. Returns output paths (relative to the repo if possible).

    sar/ivv/harness.py calls this after the IV&V GIF. **It is a visualisation layer** -- if it fails, the IV&V result does not change."""
    from pathlib import Path
    from render3d import pipeline
    sc = mission_scene(ref.dem, float(ref.mpp), frames, agl=float(getattr(ref, "AGL", 90.0)), V_m=float(getattr(ref, "V", 0) or 0) or None,
                       fidelity=getattr(ref, "fidelity", "L2 실측 DEM + SceneDB"))
    r = pipeline.run(sc, out_dir, stem, views=list(views))
    root = Path(repo) if repo else None
    rel = lambda p: str(Path(p).resolve().relative_to(root.resolve())) if root and str(Path(p).resolve()).startswith(str(root.resolve())) else str(p)
    out = [rel(r["plan"])] + [rel(v["png"]) for v in r["views"].values()]
    print("render3d 백엔드: " + ", ".join("%s=%s" % (k, v["backend"]) for k, v in r["views"].items()))
    return out
