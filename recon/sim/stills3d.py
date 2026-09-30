"""RECON-R1 3D 스틸 네 장(iso·explode·side·rear) -> inbox/recon/fig/rover3d_*.png"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recon import paths, spec  # noqa: E402
S = {k: getattr(spec, k) for k in ("MECH", "DRIVE", "P_AVG", "P_PEAK", "E_WH", "RUNTIME_H")}
WEB = paths.PKG / "web"
paths.ensure()
html = ((WEB / "rover_still.html").read_text().replace("__THREE__", paths.THREE.as_uri()).replace("__ROOMENV__", (paths.VENDOR / "RoomEnvironment.js").as_uri())
        .replace("__SPEC__", json.dumps(S, default=str)).replace('src="rover3d.js"', f'src="{(WEB / "rover3d.js").as_uri()}"'))
p = paths.FIG / "_rover_still.html"; p.write_text(html)
out = paths.FIG
from playwright.sync_api import sync_playwright  # noqa: E402
with sync_playwright() as pw:
    b = paths.launch(pw); pg = b.new_page(viewport={"width": 1600, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(p.as_uri(), wait_until="commit"); pg.wait_for_function("window.__ready===true", timeout=300000)
    for v in ("iso", "explode", "side", "rear"):
        pg.evaluate(f"view('{v}')"); pg.screenshot(path=str(out / f"rover3d_{v}.png")); print(out / f"rover3d_{v}.png")
    if errs:
        print("ERR", errs)
    b.close()
