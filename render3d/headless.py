# -*- coding: utf-8 -*-
"""html.py output -> PNG (headless Chromium, playwright). **Without a browser, say so. Do not pretend.**

    render(html_path, png_path, view="aerial", w=1600, h=1000) -> {"ok": bool, "backend": str, "reason": str}

- The browser comes from SE_CHROMIUM (executable path) or the one playwright installed (deploy runs
  `python3 -m playwright install chromium`). The sandbox's /opt/pw-browsers is also searched.
- three.js is loaded from the CDN by default. If SE_THREE_DIR (a local copy of the three package: a directory
  with build/ and examples/) is set, it is served as /three/ and the page uses that instead -- for environments
  where the CDN is blocked.
- The page raises window.__done or window.__err. The only waits are for those two and a timeout.
"""
from __future__ import annotations

import functools
import glob
import http.server
import os
import re
import shutil
import socketserver
import tempfile
import threading
import time
from pathlib import Path


def _chromium() -> "str | None":
    p = os.environ.get("SE_CHROMIUM")
    if p and os.path.exists(p):
        return p
    for c in sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"), reverse=True):
        return c
    return None                                   # Leave it to playwright's default install location


def available() -> "tuple[bool, str]":
    """(available?, why). Checks import only; whether it can launch is only known by running render()."""
    try:
        import playwright.sync_api  # noqa: F401
    except Exception as e:                         # noqa: BLE001
        return False, "playwright 가 없다 (%s)" % type(e).__name__
    return True, "playwright 있음" + (" · chromium=%s" % _chromium() if _chromium() else "")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):                     # noqa: D401 -- keep the server log out of stderr
        pass


def render(html_path, png_path, view: str = "aerial", w: int = 1600, h: int = 1000, timeout_s: float = 240.0) -> dict:
    ok, why = available()
    if not ok:
        return {"ok": False, "backend": "없음", "reason": why}
    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp(prefix="render3d_"))
    try:
        page_html = Path(html_path).read_text(encoding="utf-8")
        three_dir = os.environ.get("SE_THREE_DIR")
        if three_dir and os.path.isdir(three_dir):
            os.symlink(os.path.abspath(three_dir), tmp / "three")
            page_html = re.sub(r'"three":"[^"]*build/three\.module\.js","three/addons/":"[^"]*examples/jsm/"',
                               '"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"', page_html)
        (tmp / "index.html").write_text(page_html, encoding="utf-8")
        handler = functools.partial(_Quiet, directory=str(tmp))
        with socketserver.TCPServer(("127.0.0.1", 0), handler) as srv:
            port = srv.server_address[1]
            th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
            try:
                with sync_playwright() as pw:
                    kw = {"args": ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]}
                    exe = _chromium()
                    if exe:
                        kw["executable_path"] = exe
                    try:
                        b = pw.chromium.launch(**kw)
                    except Exception as e:          # noqa: BLE001
                        return {"ok": False, "backend": "없음", "reason": "chromium 을 못 띄웠다: %s" % str(e).splitlines()[0][:160]}
                    try:
                        pg = b.new_page(viewport={"width": w, "height": h})
                        errs = []
                        pg.on("pageerror", lambda e: errs.append(str(e)))
                        pg.goto("http://127.0.0.1:%d/index.html?view=%s&w=%d&h=%d&headless=1" % (port, view, w, h))
                        pg.wait_for_function("window.__done === true || window.__err !== null", timeout=timeout_s * 1000)
                        err = pg.evaluate("window.__err") or (errs[0] if errs else None)
                        if err and not pg.evaluate("window.__done === true"):
                            if "load error" in err or "import" in err.lower() or "fetch" in err.lower():
                                err = "three.js 를 못 불렀다(CDN 차단?) -- SE_THREE_DIR 에 로컬 사본을 주거나 네트워크를 확인: " + err
                            return {"ok": False, "backend": "없음", "reason": "페이지 오류: %s" % err[:200]}
                        Path(png_path).parent.mkdir(parents=True, exist_ok=True)
                        pg.locator("canvas").screenshot(path=str(png_path))
                        return {"ok": True, "backend": "three.js r170 · headless chromium", "reason": ""}
                    finally:
                        b.close()
            except Exception as e:                  # noqa: BLE001 -- timeouts (three.js failed to load, etc.) are 'not rendered' too
                return {"ok": False, "backend": "없음", "reason": "%s: %s" % (type(e).__name__, str(e).splitlines()[0][:160])}
            finally:
                srv.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def record(html_path, webm_path, w: int = 1600, h: int = 900, cam: str = "tour", speed: float = 20.0,
           timeout_s: float = 600.0) -> dict:
    """Record a mission-animation page (with an anim block) to webm. Waits for window.__animDone. Frame rate depends on swiftshader speed (time-based playback, frames may skip)."""
    ok, why = available()
    if not ok:
        return {"ok": False, "reason": why}
    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp(prefix="render3d_rec_"))
    try:
        page_html = Path(html_path).read_text(encoding="utf-8")
        three_dir = os.environ.get("SE_THREE_DIR")
        if three_dir and os.path.isdir(three_dir):
            os.symlink(os.path.abspath(three_dir), tmp / "three")
            page_html = re.sub(r'"three":"[^"]*build/three\.module\.js","three/addons/":"[^"]*examples/jsm/"',
                               '"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"', page_html)
        (tmp / "index.html").write_text(page_html, encoding="utf-8")
        vid = tmp / "vid"; vid.mkdir()
        handler = functools.partial(_Quiet, directory=str(tmp))
        with socketserver.TCPServer(("127.0.0.1", 0), handler) as srv:
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    kw = {"args": ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]}
                    if _chromium():
                        kw["executable_path"] = _chromium()
                    b = pw.chromium.launch(**kw)
                    ctx = b.new_context(viewport={"width": w, "height": h}, record_video_dir=str(vid), record_video_size={"width": w, "height": h})
                    pg = ctx.new_page(); errs = []
                    pg.on("pageerror", lambda e: errs.append(str(e)))
                    t0 = time.time()
                    pg.goto("http://127.0.0.1:%d/index.html?w=%d&h=%d&cam=%s&speed=%g" % (port, w, h, cam, speed))
                    pg.wait_for_function("window.__animDone === true || window.__err !== null", timeout=timeout_s * 1000, polling=500)
                    err = pg.evaluate("window.__err") or (errs[0] if errs else None)
                    wall = time.time() - t0
                    v = pg.video; pg.close(); ctx.close(); b.close()
                    if err:
                        return {"ok": False, "reason": "페이지 오류: %s" % str(err)[:200]}
                    Path(webm_path).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(v.path(), webm_path)
                    return {"ok": True, "wall_s": round(wall, 1), "reason": ""}
            except Exception as e:                  # noqa: BLE001
                return {"ok": False, "reason": "%s: %s" % (type(e).__name__, str(e).splitlines()[0][:160])}
            finally:
                srv.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
