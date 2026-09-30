"""RECON-R1 산출물 만들기.  python3 -m recon.make <무엇> [인자]

  커널            SE fw 커널 + profile_recon.c 빌드, 결정 검사 21개, freestanding 크기
  시뮬 <ID|전부>   폐루프 시뮬 (30 시나리오: T01-08 · F01-09 · B01-04 · P01-09) -> inbox/recon/runs/<ID>
  분석            필터 비교(3 시드) · 통로 폭 쓸기 · 기준선 몬테카를로(4 방법 × 5 시드)
  영상 <ID|전부>   60 s MP4 (시뮬이 먼저 있어야 한다)
  도면 | 3D | 그림 | 보고서 | 웹 | 오프라인(PDF·영상 전부·html 을 30 MiB 아래 zip 여러 개로)
  전부            시뮬 전부 -> 분석 -> 그림 -> 3D -> 도면 -> 영상 전부 -> 보고서 -> 웹   (수십 분~1 시간)
산출물은 inbox/recon/ (커밋하지 않음). 모든 성능 수치는 가상 시험장 시뮬레이션 출력이다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from recon import fwbuild, paths

SIM = paths.PKG / "sim"
PY = sys.executable


def _ids():
    sys.path.insert(0, str(SIM))
    from scenarios import SCENARIOS
    return list(SCENARIOS)


def _py(args, log=None, env=None, cwd=SIM):
    e = dict(os.environ, **(env or {}))
    if log:
        with open(log, "w") as f:
            return subprocess.run([PY, *args], cwd=cwd, stdout=f, stderr=subprocess.STDOUT, env=e).returncode
    return subprocess.run([PY, *args], cwd=cwd, env=e).returncode


def 커널() -> str:
    fwbuild.build(force=True)
    r = subprocess.run([PY, str(paths.PKG / "fw" / "host_test.py")], capture_output=True, text=True)
    return r.stdout[-1500:] + "\n" + fwbuild.footprint().splitlines()[-1] + "  (freestanding .text/.data/.bss 합, 호스트 x86)"


def 시뮬(sid: str = "전부", seed: int = 0, workers: int = 4) -> dict:
    paths.ensure(); fwbuild.build()
    ids = _ids() if sid in ("전부", "all") else [s.strip().upper() for s in sid.split(",")]
    def one(i):
        return i, _py(["run.py", i, "--quiet", "--seed", str(seed)], log=paths.LOGS / f"run_{i}.log")
    with ThreadPoolExecutor(workers) as ex:
        codes = dict(ex.map(one, ids))
    out = {}
    for i in ids:
        m = paths.RUNS / i / "meta.json"
        out[i] = json.loads(m.read_text())["kpi"] if m.exists() and codes[i] == 0 else {"error": codes[i]}
    return out


def 분석() -> list:
    fwbuild.build()
    return [_py(["analysis.py", w], log=paths.LOGS / f"an_{w}.log") for w in ("filters", "gap", "mc")]


def 영상(sid: str = "전부", workers: int = 4) -> list:
    ids = _ids() if sid in ("전부", "all") else [s.strip().upper() for s in sid.split(",")]
    ids = [i for i in ids if (paths.RUNS / i / "frames.json").exists()]
    def one(i):
        (paths.RUNS / i / "frame.html").unlink(missing_ok=True)
        _py(["render.py", i, "--workers", "1" if len(ids) > 1 else "3", "--fps", "8"], log=paths.LOGS / f"v_{i}.log")
        return str(paths.VIDEO / f"{i}.mp4")
    with ThreadPoolExecutor(workers if len(ids) > 1 else 1) as ex:
        return [p for p in ex.map(one, ids) if Path(p).exists()]


def 도면() -> list:
    paths.ensure()
    _py([str(paths.PKG / "drawings" / "make_drawings.py")], env={"RECON_DRAW_OUT": str(paths.DRAW)}, log=paths.LOGS / "drawings.log")
    return sorted(str(p) for p in paths.DRAW.glob("RCN-*.png"))


def 삼디() -> list:
    _py(["stills3d.py"], log=paths.LOGS / "3d.log")
    return sorted(str(p) for p in paths.FIG.glob("rover3d_*.png"))


def 그림() -> list:
    for w in ("spec", "results", "mc", "filters"):
        _py(["figs.py", w], log=paths.LOGS / f"fig_{w}.log")
    return sorted(str(p) for p in paths.FIG.glob("*.png") if not p.name.startswith("_"))


def 보고서() -> dict:
    """reportkit 정책 검사를 통과해야 PDF 가 나온다. 도면·그림이 없으면 먼저 만든다."""
    if not list(paths.DRAW.glob("RCN-*.png")):
        도면()
    if not (paths.FIG / "decision_arch.png").exists():
        그림()
    if not (paths.FIG / "rover3d_iso.png").exists():
        삼디()
    r = subprocess.run([PY, str(paths.PKG / "report.py")], cwd=paths.REPO, capture_output=True, text=True)
    try:
        return json.loads(r.stdout[r.stdout.index("{"):])
    except ValueError:
        return {"pdf": None, "error": (r.stdout + r.stderr)[-1500:]}


def 웹() -> str:
    """인터랙티브 페이지(3D·영상 30·KPI·도면) 폴더와 zip. 영상·도면이 있는 만큼 담긴다."""
    import shutil
    _py([str(paths.PKG / "site" / "build_site.py")], log=paths.LOGS / "site.log")
    files = json.loads((paths.SITE / "files.json").read_text())
    for k, v in files.items():
        d = paths.SITE / k; d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v, d)
    z = shutil.make_archive(str(paths.OUT / "RECON-R1_site"), "zip", paths.SITE)
    return z


def 오프라인(한도_MiB: float = 29.0) -> list:
    """html 은 사라진다(사용자 2026-09-29) -> 인터넷 없이 열리는 묶음: index.html(three.js 동봉) + PDF + 영상 전부 +
    도면 PNG/SVG + 3D + README. 파일 전송 한도(30 MiB) 아래로 여러 zip 으로 나눈다 -- 같은 폴더에 풀면 하나로 합쳐진다."""
    import shutil
    import zipfile
    웹()
    root = paths.OUT / "offline" / "RECON-R1"
    shutil.rmtree(root.parent, ignore_errors=True)
    shutil.copytree(paths.SITE, root, ignore=shutil.ignore_patterns("files.json"))
    h = (root / "index.html").read_text(encoding="utf-8")
    for cdn, loc in (("https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js", "lib/three.min.js"),
                     ("https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js", "lib/OrbitControls.js"),
                     ("https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/environments/RoomEnvironment.js", "lib/RoomEnvironment.js")):
        h = h.replace(cdn, loc)
    h = ('<!doctype html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
         + h.replace('<div class="wrap">', '</head><body>\n<div class="wrap">', 1).replace('<div class="warn">', '<p><a href="RECON-R1_blueprint.pdf">청사진 PDF</a></p>\n  <div class="warn">', 1) + "\n</body></html>\n")
    (root / "index.html").write_text(h, encoding="utf-8")
    (root / "lib").mkdir(exist_ok=True)
    for f in ("three.min.js", "OrbitControls.js", "RoomEnvironment.js", "LICENSE.three"):
        shutil.copy2(paths.VENDOR / f, root / "lib" / f)
    (root / "v").mkdir(exist_ok=True)
    for v in paths.VIDEO.glob("*.mp4"):
        shutil.copy2(v, root / "v" / v.name)
    for d in paths.DRAW.glob("RCN-*.svg"):
        shutil.copy2(d, root / "d" / d.name) if (root / "d").exists() else None
    for pdf in paths.REPORT.glob("*.pdf"):
        shutil.copy2(pdf, root / pdf.name)
    (root / "README.txt").write_text("RECON-R1 오프라인 묶음: 모든 zip 을 같은 폴더에 풀고 RECON-R1/index.html 을 크롬·엣지로 연다.\n"
                                    "수치는 가상 시험장 시뮬레이션 출력(실측 아님).\n", encoding="utf-8")
    files = sorted(p for p in root.rglob("*") if p.is_file())
    head = [p for p in files if not p.match("*/v/*.mp4")]
    vids = [p for p in files if p.match("*/v/*.mp4")]
    groups, cur, size = [head], [], 0
    for v in vids:
        if cur and size + v.stat().st_size > 한도_MiB * 2 ** 20:
            groups.append(cur); cur, size = [], 0
        cur.append(v); size += v.stat().st_size
    if cur:
        groups.append(cur)
    out = []
    for k, g in enumerate(groups, 1):
        z = paths.OUT / "offline" / f"RECON-R1_part{k}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED if k == 1 else zipfile.ZIP_STORED) as zf:
            for f in g:
                zf.write(f, f.relative_to(root.parent))
        out.append(str(z))
    return out


def 전부() -> None:
    시뮬("전부"); 분석(); 그림(); 삼디(); 도면(); 영상("전부"); print(보고서()); print(웹())


if __name__ == "__main__":
    a = sys.argv[1:] or ["도움"]
    w, arg = a[0], (a[1] if len(a) > 1 else "전부")
    fn = {"커널": lambda: 커널(), "시뮬": lambda: 시뮬(arg), "분석": 분석, "영상": lambda: 영상(arg), "도면": 도면, "3D": 삼디,
          "그림": 그림, "보고서": 보고서, "웹": 웹, "오프라인": 오프라인, "전부": 전부}.get(w)
    if not fn:
        print(__doc__); sys.exit(2)
    r = fn()
    if r is not None:
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str) if not isinstance(r, str) else r)
