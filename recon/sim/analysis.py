"""통계 실험: 기준선 몬테카를로(같은 세계·같은 시드·같은 안전층), 필터 비교(슬립), 지도 표현 비교.
python3 analysis.py mc|filters|gap   (결과: inbox/recon/analysis/*.json)"""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
from recon import paths  # noqa: E402
import json, sys, math
from multiprocessing import Pool
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
paths.ensure()
OUT = paths.ANALYSIS
FIG = paths.FIG


def one_mc(a):
    method, seed = a
    import run as R
    from scenarios import SCENARIOS
    sc = dict(SCENARIOS["B04"]); sc["id"] = f"MC-{method}-{seed}"
    r = R.run(sc, method, seed, record=True, quiet=True)
    curve = [(f["t"], f["kpi"].get("coverage", 0), f["kpi"].get("aoi_cov") or 0, f["Wh"]) for f in r["frames"][::8] if f["kpi"]]
    k = r["kpi"]; k["curve"] = curve
    return k


def one_filter(seed):
    import run as R
    from scenarios import SCENARIOS
    r = R.run(SCENARIOS["T05"], "proposed", seed, record=True, quiet=True, compare_filters=True)
    maps = r["filter_maps"]; tr = r["truth"]
    err = {k: np.where(m.var < 0.01, m.h - tr.h, np.nan).astype(np.float32) for k, m in maps.items()}
    if seed == 0:
        np.savez_compressed(OUT / "filters_err_seed0.npz", **err, truth=tr.h, kind=tr.kind)
        traj = [(f["tp"][0], f["tp"][1]) for f in r["frames"]]
        np.save(OUT / "filters_traj_seed0.npy", np.array(traj))
    return r["filters"]


def one_gap(a):
    gap, seed = a
    import run as R
    from scenarios import SCENARIOS, base_world
    def wf(sd, g=gap):
        w = base_world(sd, rough=0.02, rocks=0, ruins=False)
        w.box(12, 1, 12.4, 15 - g / 2, 1.0); w.box(12, 15 + g / 2, 12.4, 29, 1.0); return w
    sc = dict(SCENARIOS["P06"]); sc["world"] = wf; sc["id"] = f"GAP{gap}"
    r = R.run(sc, "proposed", seed, record=True, quiet=True, t_max=180)
    tp = [f["t"] for f in r["frames"] if f["tp"][0] > 12.6]
    return dict(gap=gap, seed=seed, passed=bool(tp), t_pass=(tp[0] if tp else None), coverage=r["kpi"]["coverage"], collisions=r["kpi"]["collisions"])


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "mc":
        jobs = [(m, s) for s in range(5) for m in ("fixed", "random", "frontier", "proposed")]
        with Pool(4) as p:
            res = p.map(one_mc, jobs)
        (OUT / "mc.json").write_text(json.dumps(res, ensure_ascii=False, default=float))
        print("mc done", len(res))
    elif what == "gap":
        with Pool(4) as p:
            res = p.map(one_gap, [(g, s) for g in (0.8, 0.9, 1.0, 1.1, 1.2) for s in (0, 1)])
        (OUT / "gap.json").write_text(json.dumps(res))
        print(json.dumps(res))
    elif what == "filters":
        with Pool(3) as p:
            res = p.map(one_filter, [0, 1, 2])
        (OUT / "filters.json").write_text(json.dumps(res, ensure_ascii=False, default=float))
        print(json.dumps(res, ensure_ascii=False))
