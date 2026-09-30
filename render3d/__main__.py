# -*- coding: utf-8 -*-
"""python3 -m render3d <command>

    vv [--no-browser]                    V&V report (SAR camera, fog, heightfield, area) -> public_agent_memory/render3d/vv_*.md|png
    example <name> [--views aerial,eye]  bundled layouts (list: example --list). e.g. hongdae/F1, store_module/tobe
    layout <file.json> [--key K]         your own layout file (for multiple floors, --key picks the floor)
    sar [--case] [--V 400]               SAR world: default is synthetic DEM + SceneDB (no network), --case is the IV&V Taebaek case (real DEM)

Output: public_agent_memory/render3d/<stem>_*.png|html|md. Prints "산출물: <path>" lines (relay.산출물꼴) and a "=== 보고 ===" summary.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))                  # So a `python3 render3d/__main__.py` launch can still find sar/ (entrypoints risk)

OUT = REPO / "public_agent_memory" / "render3d"


def _rel(p) -> str:
    try:
        return str(Path(p).resolve().relative_to(REPO))
    except ValueError:
        return str(p)


def _summary_md(title: str, r: dict, extra: "list[str] | None" = None) -> str:
    L = ["# " + title, ""]
    L += ["- **충실도: %s** (이 저장소에 L3+ 실영상·실센서 장면은 없다)" % r.get("fidelity", "미표기"),
          "- 평면: `%s`" % _rel(r["plan"]), "- 인터랙티브 3D: `%s` (브라우저로 열면 궤도 회전)" % _rel(r["html"])]
    for k, v in r["views"].items():
        L.append("- 시점 `%s`: **%s**%s" % (k, v["backend"], (" — " + v["reason"]) if v["reason"] else ""))
    if r.get("area"):
        L += ["", "| 용도 | 면적(m²) |", "|---|---|"] + ["| %s | %.1f |" % (k, v) for k, v in r["area"].items() if v > 0]
    L += extra or []
    L += ["", "![plan](%s)" % Path(r["plan"]).name] + ["![%s](%s)" % (k, Path(v["png"]).name) for k, v in r["views"].items()]
    return "\n".join(L) + "\n"


def _emit(title: str, stem: str, r: dict, extra=None) -> None:
    md = OUT / (stem + ".md")
    md.write_text(_summary_md(title, r, extra), encoding="utf-8")
    for p in [md, r["plan"]] + [v["png"] for v in r["views"].values()]:
        print("산출물:", _rel(p))
    fb = [k for k, v in r["views"].items() if v["backend"].startswith("matplotlib")]
    print("=== 보고 ===")
    print("%s — 평면 1 · 3D %d장 · HTML 1 · 충실도 %s" % (title, len(r["views"]), r.get("fidelity", "미표기")))
    print("백엔드: " + ", ".join(sorted(set(v["backend"] for v in r["views"].values()))))
    if fb:
        print("**실사 아님**: %s 시점은 브라우저가 없어 matplotlib 대체로 그렸다 (%s)" % (", ".join(fb), r["views"][fb[0]]["reason"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="render3d")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("vv"); a.add_argument("--no-browser", action="store_true")
    a = sub.add_parser("example"); a.add_argument("name", nargs="?"); a.add_argument("--list", action="store_true"); a.add_argument("--views", default="aerial,eye")
    a = sub.add_parser("layout"); a.add_argument("file"); a.add_argument("--key"); a.add_argument("--views", default="aerial,eye")
    a = sub.add_parser("sar"); a.add_argument("--case", action="store_true"); a.add_argument("--V", type=float, default=400.0)
    a = sub.add_parser("ab"); a.add_argument("--n", type=int, default=200)
    a.add_argument("--set", dest="세트", default="main", choices=["main", "units", "canyon", "trees", "all"],
                   help="main=요인별 A/B · units=사거리 단위 수정 영향 · canyon=저고도 협곡 지형가림·레이더그림자 · trees=나무 배치 쓸기")
    a = sub.add_parser("anim"); a.add_argument("--canyon", action="store_true"); a.add_argument("--V", type=float, default=6000.0)
    a.add_argument("--speed", type=float, default=20.0); a.add_argument("--video", action="store_true", help="webm 녹화(브라우저 필요)")
    a.add_argument("--fw", action="store_true", help="fw C 결정 executive를 선수로(SUT 대신)")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    from render3d import pipeline

    if a.cmd == "vv":
        from render3d import vv
        rows = vv.run_all(browser=not a.no_browser)
        md, png = OUT / ("vv_%s.md" % ts), OUT / ("vv_%s.png" % ts)
        vv.report(rows, md, png)
        print("산출물:", _rel(md)); print("산출물:", _rel(png))
        print("=== 보고 ===")
        for r in rows:
            print("[%s] %s — %s: %s" % (r["id"], r["판정"], r["항목"], r["측정"]))
        return 1 if any(r["판정"] == "FAIL" for r in rows) else 0

    if a.cmd == "ab":
        from render3d import scene3d_ab as AB
        if a.세트 != "main":
            import json
            sets = ["units", "canyon", "trees"] if a.세트 == "all" else [a.세트]
            got = {k: {"units": AB.run_units, "canyon": AB.run_canyon, "trees": AB.run_trees}[k](a.n) for k in sets}
            md = OUT / ("scene3d_ab_%s_%s.md" % (a.세트, ts))
            md.write_text(AB.report_extra_md(n=a.n, **got), encoding="utf-8")
            (OUT / ("scene3d_ab_%s_%s.json" % (a.세트, ts))).write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
            print("산출물:", _rel(md))
            print("=== 보고 ===")
            print(md.read_text(encoding="utf-8"))
            return 0
        r = AB.run(n=a.n)
        md = OUT / ("scene3d_ab_%s.md" % ts)
        md.write_text(AB.report_md(r, a.n), encoding="utf-8")
        import json
        (OUT / ("scene3d_ab_%s.json" % ts)).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print("산출물:", _rel(md))
        print("=== 보고 ===")
        for k, v in r.items():
            if not k.startswith("_"):
                print("%-16s 탐지율 %.3f [%.3f, %.3f]  오경보 %d" % (k, v["detect_rate"], v["ci95"][0], v["ci95"][1], v["false_alarms"]))
        print("충실도 L1(합성 DEM) · 카메라·LAD·나무배치 = 대표값 가정. 사거리 단위는 참조세계에서 고쳤다 -- 옛 단위와의 차이는 --set units.")
        return 0

    if a.cmd == "anim":
        from render3d import mission_anim as MA, sar_bridge as B, html as H, headless
        dem = B.canyon_dem(96, seed=0) if a.canyon else B.synthetic_dem(96, seed=2)
        player = None; who = "SUT"
        if getattr(a, "fw", False):                         # fw C 결정 executive를 선수로(같은 텔레메트리/3D)
            import sys as _sys, os as _os
            _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "sar", "ivv"))
            import fw_vv as _F
            player = _F.FwBridgePolicy(_F.load_lib(), confirm_n=2, nis_gate=24.0, cmpc_min=2,
                                       require_live=True, nav_by_action=True); who = "fw C executive"
        sc, summ = MA.build(MA.default_spec(V=a.V, canyon=a.canyon), dem, speed=a.speed,
                            name="임무 재생 (%s, V=%.0f m · %s)" % ("협곡 AGL 60" if a.canyon else "언덕 AGL 90", a.V, who), sut=player)
        stem = "mission_%s%s_%s" % ("canyon" if a.canyon else "hill", "_fw" if getattr(a, "fw", False) else "", ts)
        hp = OUT / (stem + ".html"); H.write(sc, hp)
        print("산출물:", _rel(hp))
        if a.video:
            r = headless.record(hp, OUT / (stem + ".webm"), speed=a.speed)
            print("산출물:", _rel(OUT / (stem + ".webm")) if r["ok"] else "영상 못 만듦: " + r["reason"])
        print("=== 보고 ===")
        m, rt = summ["metrics"], summ["rates_measured"]
        print("탐지 %d/%d · 오경보 %d · SUT 결정 %d회(%.0f s 마다) · 기계상태 %d개(실측 %.1f Hz) · 운용보고 %d개(실측 %.1f Hz) · 이벤트 %d"
              % (m["detected"], m["n_targets"], m["false_alarms"], summ["n_decisions"], summ["decision_s"], summ["n_states"], rt["state_hz"], summ["n_reports"], rt["report_hz"], summ["n_events"]))
        print("스펙: 10 Hz(기계상태 갱신) · 1 Hz(운용보고) · 이벤트 즉시 · SUT 결정 20 s — 대역폭이 아니라 갱신 주기. 10 Hz 는 NASA 표준이 아니라 연구 설계점.")
        print("충실도 %s · 관측 뷰(추적·조감)의 빨간 기둥은 truth 다 -- 탑재 RGB 뷰에는 안 그린다." % summ["fidelity"])
        return 0

    if a.cmd in ("example", "layout"):
        from render3d import layout as LY
        if a.cmd == "example":
            ex = LY.examples()
            if a.list or not a.name:
                print("\n".join(sorted(ex))); return 0
            if a.name not in ex:
                print("모르는 예제: %s (있는 것: %s)" % (a.name, ", ".join(sorted(ex)))); return 2
            L, stem = ex[a.name], a.name.replace("/", "_")
        else:
            import json
            d = json.loads(Path(a.file).read_text(encoding="utf-8"))
            L = d[a.key] if a.key else (d if "items" in d else d[sorted(d)[0]])
            stem = Path(a.file).stem + ("_" + a.key if a.key else "")
        sc = LY.to_scene(L)
        r = pipeline.run(sc, OUT, "%s_%s" % (stem, ts), views=[v for v in a.views.split(",") if v])
        _emit(sc["name"], "%s_%s" % (stem, ts), r)
        return 0

    if a.cmd == "sar":
        from render3d import sar_bridge as B
        if a.case:
            from sar.ivv import harness as Hn
            _m, frames = Hn.run_case(Hn.CASE_TAEBAEK, record_frames=True)
            from sar.ivv import reference as Rf
            ref = Rf.Reference(Hn.CASE_TAEBAEK)
            sc = B.mission_scene(ref.dem, float(ref.mpp), frames, agl=ref.AGL, V_m=ref.V, name="IV&V 태백 케이스")
            stem = "sar_case_%s" % ts
        else:
            dem, mpp, frames, feats, sdb = B.synthetic_mission(V_m=a.V)
            sc = B.mission_scene(dem, mpp, frames, V_m=a.V, features=feats, scenedb=sdb, name="SAR 합성 임무(무네트워크)")
            stem = "sar_syn_%s" % ts
        r = pipeline.run(sc, OUT, stem, views=["aerial", "onboard"])
        extra = ["", "- 안개: Beer-Lambert β=%.4f/m (V=%.0f m, Koschmieder) — **탑재 카메라 시점에만** 적용(관찰자 조감은 맑게)"
                 % (sc["fog"]["beta"], sc["fog"]["V_m"])] if sc.get("fog") else []
        _emit(sc["name"], stem, r, extra)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
