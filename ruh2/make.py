"""RuH2-P1 산출물을 순서대로 짓는다.   python3 -m ruh2.make <무엇> [--force]

    데이터   ruh2.experiments + ruh2.rupt      -> OUT/battery.json, rupt.json      (~3 s)
    그림     데이터 + ruh2.figures              -> OUT/fig/*.png                    (~5 s)
    도면     ruh2/drawings/*.py                 -> OUT/drawings/*.png|svg|jpg       (~1 min)
    스틸     영상 장면에서 보고서용 장면만       -> OUT/video/*.png                  (~1-3 min)
    보고서   데이터 → 그림 → 도면 → 스틸 → PDF  -> OUT/RuH2-P1_prototype_report.pdf (~3-5 min)
    웹       데이터 + 도면 → 한 파일 HTML        -> OUT/site/ruh2_lab.html
    영상     battery|atom (느리다, 수십 분)      -> OUT/video/*.mp4

규율: 사양은 ruh2/spec.py 한 곳. 산출물은 무시되는 자리(OUT). 보고서는 reportkit 정책 검사를 통과해야 나온다.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

from ruh2 import paths

DRAW = ["e001_block", "e002_power", "e003_sense", "e004_mcu_safety", "m001_vessel", "m002_stack", "m003_pcb"]


def _py(mod, *args, env=None):
    r = subprocess.run([sys.executable, "-m", mod, *args], cwd=str(paths.REPO), capture_output=True, text=True, env=env)
    if r.returncode:
        raise RuntimeError(f"{mod} 실패: {(r.stderr or r.stdout)[-600:]}")
    return r.stdout


def 데이터():
    _py("ruh2.experiments"); _py("ruh2.rupt")
    return [str(paths.OUT / "battery.json"), str(paths.OUT / "rupt.json")]


def 그림():
    데이터(); _py("ruh2.figures")
    return sorted(glob.glob(str(paths.FIG / "*.png")))


def 도면():
    from PIL import Image
    env = dict(os.environ, RUH2_DRAW_OUT=str(paths.DRAW), MPLBACKEND="Agg")
    for d in DRAW:
        r = subprocess.run([sys.executable, str(paths.DRAW_SRC / f"{d}.py")], cwd=str(paths.DRAW_SRC), capture_output=True, text=True, env=env)
        if r.returncode:
            raise RuntimeError(f"도면 {d} 실패: {(r.stderr or r.stdout)[-600:]}")
    out = []
    for png in sorted(glob.glob(str(paths.DRAW / "*.png"))):
        im = Image.open(png).convert("RGB")
        im.resize((2400, int(im.height * 2400 / im.width)), Image.LANCZOS).save(png[:-4] + ".jpg", quality=85)
        out.append(png)
    return out


def 스틸():
    from ruh2 import render
    데이터()
    return render.stills("battery") + render.stills("atom")


def 보고서(strict=True, 스틸도=True):
    그림(); 도면()
    if 스틸도:
        try:
            스틸()
        except Exception as e:                                 # noqa: BLE001
            print(f"[보고서] 스틸 실패 -- 그림 없이 진행: {type(e).__name__}: {e}")
    import importlib
    import ruh2.report as R
    importlib.reload(R)
    return R.main(strict=strict)


def 웹():
    데이터()
    if not glob.glob(str(paths.DRAW / "*.png")):
        도면()
    from ruh2 import site
    return site.build()


def 영상(scene="battery", **kw):
    from ruh2 import render
    데이터()
    return render.video(scene, **kw)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "보고서"
    paths.ensure()
    if what == "보고서":
        r = 보고서(strict="--force" not in sys.argv)
    elif what == "영상":
        r = 영상(sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "battery")
    else:
        r = {"데이터": 데이터, "그림": 그림, "도면": 도면, "스틸": 스틸, "웹": 웹}[what]()
    print(json.dumps(r, ensure_ascii=False, default=str, indent=1))
