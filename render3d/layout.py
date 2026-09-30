# -*- coding: utf-8 -*-
"""Store/interior layout -> scene. The layout format is the one used in the 2026-09-28 store analysis:

    {"name","W","D","H","columns":[[x,y]],"items":[{"id","type","x0","y0","x1","y1","h","label","zone","n"?}],
     "people":[[x,y]], "signs":[[text,x,y,z,w,h,rotY]], "views":{name:[[x,h,y],[x,h,y],fov]},
     "entry":[x,y], "exit":[x,y], "tag"?}

Views are stored as [x, height, y] (camera position, look-at target), vertical FOV. Converted here to the scene's {pos,target,fov}.
"""
from __future__ import annotations

import json
from pathlib import Path

from render3d import scene as S

EXAMPLES = Path(__file__).resolve().parent / "examples"


def to_scene(L: dict, name: "str | None" = None) -> dict:
    s = S.new(name or L.get("name", "layout"), "north", (L["W"], L["D"], L.get("H", 3.6)), shell=True)
    s["fidelity"] = "L0 원시도형(배치 설계 · 실측 아님)"
    for it in L["items"]:
        b = {k: it[k] for k in ("id", "type", "x0", "y0", "x1", "y1", "h", "label", "zone") if k in it}
        if "n" in it:
            b["n"] = it["n"]
        s["boxes"].append(b)
    s["columns"] = [list(c) for c in L.get("columns", [])]
    s["people"] = [list(p[:2]) for p in L.get("people", [])]
    s["signs"] = [list(x) for x in L.get("signs", [])]
    for k, v in (L.get("views") or {}).items():
        (px, ph, py), (tx, th, ty), fov = v
        s["views"][k] = {"pos": [px, py, ph], "target": [tx, ty, th], "fov": float(fov)}
    if "aerial" not in s["views"]:
        s["views"].update(S.auto_views(s))
    for f in L.get("flows", []):          # flow arrows: [[x,y],...] or {"pts":[[x,y]...],"color":..}
        pts, col = (f["pts"], f.get("color")) if isinstance(f, dict) else (f, None)
        p = {"kind": "flow", "pts": [[float(x), float(y), 0.02] for x, y in pts]}
        if col:
            p["color"] = col
        s["paths"].append(p)
    s["meta"] = {k: L[k] for k in ("entry", "exit", "tag") if k in L}
    return s


def examples() -> "dict[str, dict]":
    """Bundled examples: {'hongdae/F1': layout, ...}. Estimated footprints, not surveyed (see examples/README)."""
    out = {}
    for p in sorted(EXAMPLES.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for k, L in d.items():
            out["%s/%s" % (p.stem, k)] = L
    return out


def area_program(s: dict, cs: float = 0.1) -> dict:
    """Area per use on a 0.1 m grid, counting each cell for one use only (higher priority first). The total must equal W*D (vv checks this)."""
    import numpy as np
    W, D, _ = s["bounds"]
    nx, ny = int(round(W / cs)), int(round(D / cs))
    lab = np.zeros((nx, ny), dtype=np.int8)
    names = ["통로(잔여)", "코어(계단·EV)", "BOH", "카페", "결제·서비스", "판매 집기", "O2O", "체험·포토"]

    def cat(b):
        t, zn = b.get("type"), b.get("zone", "")
        if t in ("stair", "elevator"): return 1
        if zn == "boh" and t == "stock": return 2
        if zn == "cafe": return 3
        if zn == "pay" and t in ("checkout", "queue", "island", "bin"): return 4
        if zn == "o2o": return 6
        if t in ("wall_shelf", "island", "gondola", "window") and zn in ("sale", ""): return 5
        if zn in ("exp", "evt") and t in ("zone", "room", "media", "figure"): return 7
        return 0
    order = sorted((b for b in s["boxes"] if cat(b)), key=lambda b: [1, 2, 3, 4, 6, 5, 7].index(cat(b)))
    for b in order:
        x0, x1 = max(0, int(round(b["x0"] / cs))), min(nx, int(round(b["x1"] / cs)))
        y0, y1 = max(0, int(round(b["y0"] / cs))), min(ny, int(round(b["y1"] / cs)))
        sub = lab[x0:x1, y0:y1]; sub[sub == 0] = cat(b)
    return {names[k]: round(float((lab == k).sum()) * cs * cs, 2) for k in range(len(names))}
