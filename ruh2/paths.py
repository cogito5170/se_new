"""RuH2 파이프라인의 자리. 산출물은 **저장소 밖으로 무시되는 자리**(inbox/ruh2)에 쓴다 --
검사가 원장을 더럽혔던 사고(CLAUDE.md '검사는 재는 것이지 남기는 것이 아니다')와 같은 병을 피한다.
RUH2_OUT 으로 바꿀 수 있다."""
from __future__ import annotations

import glob
import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = PKG.parent
WEB = PKG / "web"
VENDOR = PKG / "vendor"
DATA = PKG / "data"
DRAW_SRC = PKG / "drawings"
OUT = Path(os.environ.get("RUH2_OUT") or (REPO / "inbox" / "ruh2"))
FIG = OUT / "fig"
DRAW = OUT / "drawings"
VIDEO = OUT / "video"
REPORT = OUT / "report"
SITE = OUT / "site"


def ensure() -> None:
    for d in (OUT, FIG, DRAW, VIDEO, REPORT, SITE):
        d.mkdir(parents=True, exist_ok=True)


def chromium() -> "str | None":
    """render3d.headless 와 같은 규칙으로 브라우저를 찾는다. 없으면 None(= playwright 기본 자리)."""
    p = os.environ.get("SE_CHROMIUM")
    if p and os.path.exists(p):
        return p
    for c in sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"), reverse=True):
        return c
    return None


def launch(pw, gl: bool = True):
    args = ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"] if gl else []
    exe = chromium()
    return pw.chromium.launch(executable_path=exe, args=args) if exe else pw.chromium.launch(args=args)
