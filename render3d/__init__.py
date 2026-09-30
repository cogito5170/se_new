# -*- coding: utf-8 -*-
"""render3d -- one scene (JSON) rendered as a 2D plan, a photoreal three.js 3D render and an interactive HTML.

## Why it exists

- A store layout analysis (2026-09-28) produced 2D plans, three.js renders and a flow simulation, but as scratch
  code outside the repository. The user asked for it as a tool, wired into the other tools.
- It shares a world with the SAR V&V pipeline (`sar/`). SAR describes the world with `dem[y,x]`, SceneDB
  features and IV&V frames, and renders it with a heightfield ray-march (`sar/camera.py`) and matplotlib
  (`sar/ivv/viewer.py`, which notes "photorealism != validation"). This package renders the same world with
  PBR, and **checks that it is drawn with the same equations** (see vv.py).

## One scene, two inputs

    layout.py      store/interior layout (items: shelves, islands, checkouts, stair/lift, ...)  -> scene
    sar_bridge.py  DEM + SceneDB features + IV&V frames (UAV track, truth, SUT detections)     -> scene

## Outputs

    plan.py        2D plan PNG (matplotlib; for a heightfield: hillshade map + track/targets)
    html.py        self-contained three.js HTML (PBR, soft shadows, Beer-Lambert fog)
    headless.py    that HTML -> PNG in headless Chromium (playwright). Without a browser, returns None
    mpl3d.py       fallback 3D when there is no browser (not photoreal; the output says so)
    pipeline.py    runs all of the above once and records **which backend was used**

## Verification (vv.py) -- the same form as `sar/ivv/refval.py`: measurement, reference, error, validity domain, GAP

- Does our reimplementation of the SAR camera model match the real `sar/camera.py` output, pixel by pixel?
- How far apart are the SAR camera (column azimuth linear in angle, pitch as a vertical shift) and the
  three.js pinhole? This is a measurement of the difference between two models, not an error of either.
- Fog: three.js FogExp2 is `1-exp(-(rho d)^2)` over view depth. SAR is Beer-Lambert `exp(-beta r)` over ray
  range. This package overrides the shader to use Beer-Lambert, then checks it against Koschmieder
  (V = 3.912/beta), the referent `sar/sensors.py` also uses.
- Heightfield: do the scene vertices agree with the bilinear sampler of `sar/camera.py`?

## Closed loop: the reference world computes observations from the 3D scene (scene3d, contract: 핸드오프_센서스펙_관측계약.md)

    visibility.py  numpy only (no browser; Monte Carlo): terrain line of sight, foliage visibility from real tree geometry (Beer's law), Johnson pixels on target, 3D slant range
    sar/ivv/reference.py  scene3d=True -> detections/vis computed from the values above. **Off by default = bit-identical** (fixture test)
    vv_scene3d.py  G numpy <-> three.js mask render · H line of sight <-> sar/camera.py occlusion · I Johnson referent
    scene3d_ab.py  on/off x per factor (terrain, canopy, pixels, range) A/B + Wilson CI. Fidelity L1 (synthetic DEM)
The SUT never sees any of this -- it gets the same detection-packet schema.

Coordinates: metres. x = east; y = scene["y_axis"] ("north": floor-plan convention, "south": DEM row
direction); z = up. Converted once, in camera.py and html.py.
"""
