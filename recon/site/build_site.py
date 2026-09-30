"""artifact 페이지: site/index.html + 게시 파일 목록(files.json)."""
import json, sys
from pathlib import Path
R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R.parent)); sys.path.insert(0, str(R)); sys.path.insert(0, str(R / "sim"))
from recon import paths
import spec
from scenarios import SCENARIOS
rows = []
for i, sc in SCENARIOS.items():
    p = paths.RUNS / i / "meta.json"
    if not p.exists():
        continue
    m = json.loads(p.read_text()); k = m["kpi"]
    ev = [e for e in m["events"] if e["kind"] in ("detect", "isolate", "degrade", "recover", "stop")][:6]
    rows.append(dict(id=i, title=sc["title"], what=sc["what"], how=sc["how"], cov=k["coverage"], aoi=k.get("aoi_cov"), rmse=k["rmse_m"], ate=k.get("ate_m"),
                     dist=k["dist_m"], wh=k["energy_Wh"], coll=k["collisions"], t=k["t"], done=k["done"], ev=ev,
                     acts=sorted(set(a for _, a, _ in m["timeline"]) - {"HOLD"}), video=(paths.VIDEO / f"{i}.mp4").exists()))
S = {k: getattr(spec, k) for k in ("MECH", "DRIVE", "P_AVG", "P_PEAK", "E_WH", "RUNTIME_H")}
mc = json.loads((paths.ANALYSIS / "mc.json").read_text()) if (paths.ANALYSIS / "mc.json").exists() else []
mcs = {}
for r in mc:
    mcs.setdefault(r["method"], []).append(dict(cov=r["coverage"], aoi=r.get("aoi_cov") or 0, dist=r["dist_m"], wh=r["energy_Wh"], ipw=r["info_per_Wh"]))
fil = json.loads((paths.ANALYSIS / "filters.json").read_text()) if (paths.ANALYSIS / "filters.json").exists() else []
tpl = (R / "site/template.html").read_text()
html = (tpl.replace("__ROWS__", json.dumps(rows, ensure_ascii=False)).replace("__SPEC__", json.dumps(S, default=str))
        .replace("__MC__", json.dumps(mcs)).replace("__FIL__", json.dumps(fil)).replace("__ROVER3D__", (R / "web/rover3d.js").read_text()))
paths.ensure(); (paths.SITE / "index.html").write_text(html)
files = {f"v/{r['id']}.mp4": str(paths.VIDEO / f"{r['id']}.mp4") for r in rows if r["video"]}
for d in ("RCN-E-001_power", "RCN-E-002_signal", "RCN-S-001_system", "RCN-M-001_mech", "RCN-H-001_harness", "RCN-A-001_assembly"):
    files[f"d/{d}.png"] = str(paths.DRAW / f"{d}.png")
for f in ("filters_maps", "mc_bars", "unc_maps", "rover3d_iso"):
    if (paths.FIG / f"{f}.png").exists():
        files[f"f/{f}.png"] = str(paths.FIG / f"{f}.png")
(paths.SITE / "files.json").write_text(json.dumps(files, indent=0))
print(len(rows), "rows", len(files), "files", sum(Path(v).stat().st_size for v in files.values()) / 1e6, "MB")
