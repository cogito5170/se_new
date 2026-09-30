"""RuH2 3D 장면 -> MP4 (headless Chromium 프레임 렌더 + ffmpeg).

    python3 -m ruh2.render battery                  # 배터리 시뮬레이션 70 s
    python3 -m ruh2.render atom                     # 원자 반응 66 s
    python3 -m ruh2.render battery --stills         # 보고서용 스틸만 (빠름)
    옵션: --fps 24 --width 960 --crf 26 --workers 4

장면은 결정적이다(window.renderAt(t)). 그래서 시간 구간을 나눠 여러 브라우저에서 그리고
ffmpeg concat 으로 잇는다. 실측(이 컨테이너, swiftshader, 4코어): 1280×720 30fps 70 s 에 약 40분.
디스코드 한도(~10 MB) 때문에 기본은 960px · crf 26.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ruh2 import paths

SCENES = {"battery": ("battery_video.html", 70.0, [3, 12, 32, 52, 66]),
          "atom": ("atom_video.html", 66.0, [8.5, 19, 31.5, 44, 52])}


def _page(scene: str) -> Path:
    name = SCENES[scene][0]
    src = (paths.WEB / name).read_text(encoding="utf-8")
    V = paths.VENDOR
    sub = {"__THREE__": (V / "three.min.js").as_uri(), "__ROOMENV__": (V / "RoomEnvironment.js").as_uri(),
           "__GEOM__": (paths.DATA / "dft_geom.json").read_text(encoding="utf-8"),
           "__BATT__": (paths.OUT / "battery.json").read_text(encoding="utf-8") if (paths.OUT / "battery.json").exists() else "null"}
    for k, v in sub.items():
        src = src.replace(k, v)
    for js in ("atom3d.js", "battery3d.js", "nih2.js"):
        src = src.replace(f'src="{js}"', f'src="{(paths.WEB / js).as_uri()}"')
    out = paths.VIDEO / f"_{scene}_page.html"
    out.write_text(src, encoding="utf-8")
    return out


def _worker(scene, out_mp4, fps, t0, t1, width, crf):
    import imageio_ffmpeg
    from playwright.sync_api import sync_playwright
    page = _page(scene)
    with sync_playwright() as p:
        b = paths.launch(p)
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(page.as_uri(), wait_until="commit", timeout=180000)
        pg.wait_for_function("window.__ready===true", timeout=600000)
        if errs:
            raise RuntimeError("장면 오류: " + "; ".join(errs[:3]))
        k0, k1 = int(round(t0 * fps)), int(round(t1 * fps))
        vf = ["-vf", f"scale={width}:-2"] if width and width != 1280 else []
        proc = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
                                 *vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf), "-preset", "medium", str(out_mp4)], stdin=subprocess.PIPE)
        for k in range(k0, k1):
            pg.evaluate(f"window.renderAt({k / fps})")
            proc.stdin.write(pg.screenshot(type="jpeg", quality=90))
            if k % 60 == 0:
                print(f"[{scene}] frame {k}/{k1}", flush=True)
        proc.stdin.close(); proc.wait()
        b.close()


def stills(scene: str, times=None) -> "list[str]":
    from playwright.sync_api import sync_playwright
    page = _page(scene)
    out = []
    with sync_playwright() as p:
        b = paths.launch(p)
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        pg.goto(page.as_uri(), wait_until="commit", timeout=180000)
        pg.wait_for_function("window.__ready===true", timeout=600000)
        for i, t in enumerate(times or SCENES[scene][2]):
            pg.evaluate(f"window.renderAt({t})")
            f = paths.VIDEO / (f"frames_batt_{i}.png" if scene == "battery" else f"atom_t{t:05.1f}.png")
            pg.screenshot(path=str(f)); out.append(str(f))
        b.close()
    return out


def video(scene: str, fps=24, width=960, crf=26, workers=4, seconds=None) -> str:
    import imageio_ffmpeg
    paths.ensure()
    dur = float(seconds) if seconds else SCENES[scene][1]      # seconds: 시험용으로 앞부분만
    out = paths.VIDEO / f"{'ruh2_battery_simulation' if scene == 'battery' else 'ru_atomic_reactions'}.mp4"
    tmp = Path(tempfile.mkdtemp(dir=paths.VIDEO))
    procs = []
    for i in range(workers):
        a, b = dur * i / workers, dur * (i + 1) / workers
        cmd = [sys.executable, "-m", "ruh2.render", scene, "--part", f"{a},{b}", "--out", str(tmp / f"p{i}.mp4"),
               "--fps", str(fps), "--width", str(width), "--crf", str(crf)]
        procs.append(subprocess.Popen(cmd, cwd=str(paths.REPO)))
    bad = [p.wait() for p in procs]
    if any(bad):
        raise RuntimeError(f"구간 렌더 실패: {bad}")
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file 'p{i}.mp4'\n" for i in range(workers)))
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return str(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", choices=list(SCENES))
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--crf", type=int, default=26)
    ap.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    ap.add_argument("--part"); ap.add_argument("--out")
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--seconds", type=float, help="앞 N 초만 (시험용)")
    a = ap.parse_args()
    paths.ensure()
    if a.stills:
        print(json.dumps(stills(a.scene), ensure_ascii=False))
    elif a.part:
        t0, t1 = (float(x) for x in a.part.split(","))
        _worker(a.scene, a.out, a.fps, t0, t1, a.width, a.crf)
    else:
        print(video(a.scene, a.fps, a.width, a.crf, a.workers, a.seconds))
