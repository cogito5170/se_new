# -*- coding: utf-8 -*-
"""Scene -> {scene.json, plan.png, interactive.html, view PNGs}. **The backend used is recorded per view.**

    r = run(scene, out_dir, "hongdae_F1", views=["aerial", "eye"])
    r["views"]["aerial"] == {"png": ".../hongdae_F1_aerial.png", "backend": "three.js r170 · headless chromium", "reason": ""}
                        or {"png": ..., "backend": "matplotlib 대체(비실사)", "reason": "playwright 가 없다 ..."}

Why the backend is recorded: a matplotlib picture reported as a photoreal render is a false green (CLAUDE.md
'검사하지 않은 초록불'). The reader must be able to see which one it is.
"""
from __future__ import annotations

from pathlib import Path

from render3d import html as HTML
from render3d import scene as S

FALLBACK = "matplotlib 대체(비실사)"


def run(sc: dict, out_dir, stem: str, views=None, w: int = 1600, h: int = 1000, try_browser: "bool | None" = None) -> dict:
    """try_browser=None: follow the environment. SE_RENDER3D_NO_BROWSER=1 skips the browser (tests, fast path) -- the output then says '대체'."""
    if try_browser is None:
        import os
        try_browser = os.environ.get("SE_RENDER3D_NO_BROWSER") != "1"
    bad = S.check(sc)
    if bad:
        raise ValueError("invalid scene: " + "; ".join(bad[:5]))
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    r = {"scene": S.save(sc, out / (stem + ".scene.json")), "views": {}, "fidelity": sc.get("fidelity", "미표기")}
    from render3d import plan
    r["plan"] = plan.render(sc, out / (stem + "_plan.png"))
    r["html"] = HTML.write(sc, out / (stem + ".html"))
    names = list(views or [v for v in ("aerial", "eye", "onboard") if v in sc.get("views", {})] or ["aerial"])
    for v in names:
        png = out / ("%s_%s.png" % (stem, v))
        rr = {"ok": False, "reason": "브라우저 시도 안 함"}
        if try_browser:
            from render3d import headless
            rr = headless.render(r["html"], png, view=v, w=w, h=h)
        if rr.get("ok"):
            r["views"][v] = {"png": str(png), "backend": rr["backend"], "reason": ""}
        else:
            from render3d import mpl3d
            mpl3d.render(sc, png, view=v)
            r["views"][v] = {"png": str(png), "backend": FALLBACK, "reason": rr.get("reason", "")}
    r["backend"] = sorted({x["backend"] for x in r["views"].values()})
    if sc.get("boxes") and sc.get("shell"):
        from render3d import layout
        r["area"] = layout.area_program(sc)
    return r
