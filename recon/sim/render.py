"""시나리오 → 1분 MP4. frame.html(three.js r128, swiftshader) 을 프레임마다 renderAt(k) 하고 ffmpeg 로 묶는다.
python3 render.py T01 [--workers 2] [--fps 8] [--stills]"""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
from recon import paths  # noqa: E402
import argparse, base64, json, subprocess, sys, tempfile, shutil
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS, VID = paths.RUNS, paths.VIDEO
THREE = paths.THREE
CHROME = sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome"))


def page(sid):
    from scenarios import SCENARIOS
    d = RUNS / sid
    meta = json.loads((d / "meta.json").read_text())
    sc = SCENARIOS.get(sid, {})
    meta["how"] = sc.get("how", ""); meta["what"] = sc.get("what", "")
    frames = (d / "frames.json").read_text()
    js = ("window.RUN={meta:" + json.dumps(meta, ensure_ascii=False, default=float) + ",frames:" + frames +
          ",world:'" + base64.b64encode((d / "world.bin").read_bytes()).decode() +
          "',snaps:'" + base64.b64encode((d / "snaps.bin").read_bytes()).decode() + "'};")
    (d / "data.js").write_text(js, encoding="utf-8")
    html = (ROOT / "web/frame.html").read_text(encoding="utf-8").replace("__THREE__", THREE.as_uri()).replace("__DATA__", (d / "data.js").as_uri())
    p = d / "frame.html"; p.write_text(html, encoding="utf-8")
    return p, len(json.loads(frames))


def launch(pw):
    return paths.launch(pw)


def worker(sid, k0, k1, out, fps, crf):
    import imageio_ffmpeg
    from playwright.sync_api import sync_playwright
    p, n = page(sid) if not (RUNS / sid / "frame.html").exists() else (RUNS / sid / "frame.html", None)
    with sync_playwright() as pw:
        b = launch(pw); pg = b.new_page(viewport={"width": 960, "height": 540})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(p.as_uri(), wait_until="commit", timeout=180000)
        pg.wait_for_function("window.__ready===true", timeout=600000)
        if errs:
            raise RuntimeError("; ".join(errs[:3]))
        proc = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
                                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf), "-preset", "medium", str(out)], stdin=subprocess.PIPE)
        for k in range(k0, k1):
            pg.evaluate(f"renderAt({k})")
            proc.stdin.write(pg.screenshot(type="jpeg", quality=88))
        proc.stdin.close(); proc.wait(); b.close()


def stills(sid, ks, tag=""):
    from playwright.sync_api import sync_playwright
    p, n = page(sid)
    out = []
    with sync_playwright() as pw:
        b = launch(pw); pg = b.new_page(viewport={"width": 960, "height": 540})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        pg.goto(p.as_uri(), wait_until="commit", timeout=180000)
        pg.wait_for_function("window.__ready===true", timeout=600000)
        import time
        for k in ks:
            k = min(k, n - 1); t = time.time()
            pg.evaluate(f"renderAt({k})")
            f = VID / "stills" / f"{sid}{tag}_{k:03d}.png"; f.parent.mkdir(parents=True, exist_ok=True)
            pg.screenshot(path=str(f)); out.append(str(f))
            print(f, round(time.time() - t, 2), "s")
        if errs:
            print("ERR", errs[:5])
        b.close()
    return out


def video(sid, workers=2, fps=8, crf=27):
    p, n = page(sid)
    VID.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=VID))
    procs = []
    for i in range(workers):
        a, b = n * i // workers, n * (i + 1) // workers
        procs.append(subprocess.Popen([sys.executable, __file__, sid, "--part", f"{a},{b}", "--out", str(tmp / f"p{i}.mp4"), "--fps", str(fps), "--crf", str(crf)]))
    bad = [q.wait() for q in procs]
    if any(bad):
        raise RuntimeError(f"part fail {bad}")
    import imageio_ffmpeg
    (tmp / "l.txt").write_text("".join(f"file 'p{i}.mp4'\n" for i in range(workers)))
    out = VID / f"{sid}.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "l.txt"), "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("sid"); ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--fps", type=int, default=8); ap.add_argument("--crf", type=int, default=27)
    ap.add_argument("--part"); ap.add_argument("--out"); ap.add_argument("--stills", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(HERE))
    if a.stills:
        stills(a.sid, [0, 120, 240, 360, 479])
    elif a.part:
        k0, k1 = map(int, a.part.split(",")); worker(a.sid, k0, k1, a.out, a.fps, a.crf)
    else:
        print(video(a.sid, a.workers, a.fps, a.crf))
