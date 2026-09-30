"""RECON 파이프라인의 자리. 산출물은 저장소가 무시하는 inbox/recon 에 쓴다(RECON_OUT 으로 바꿀 수 있다).
ruh2/paths.py 와 같은 규칙 -- 검사·실행이 저장소를 더럽히지 않게 한다."""
from __future__ import annotations

import glob
import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = PKG.parent
FW_KERNEL = REPO / "fw"                       # SE 결정 커널 (읽기만)
VENDOR = REPO / "ruh2" / "vendor"             # three.js r128 · RoomEnvironment (RuH2 가 동봉한 것을 같이 쓴다)
THREE = VENDOR / "three.min.js"
RESULTS = PKG / "results"                     # 커밋된 결과 요약(작은 JSON)
OUT = Path(os.environ.get("RECON_OUT") or (REPO / "inbox" / "recon"))
RUNS = OUT / "runs"
VIDEO = OUT / "video"
FIG = OUT / "fig"
DRAW = OUT / "drawings"
ANALYSIS = OUT / "analysis"
REPORT = OUT / "report"
SITE = OUT / "site"
BUILD = OUT / "build"
LIB = BUILD / "libfw_recon.so"
LOGS = OUT / "logs"


def ensure() -> None:
    for d in (OUT, RUNS, VIDEO, FIG, DRAW, ANALYSIS, REPORT, SITE, BUILD, LOGS):
        d.mkdir(parents=True, exist_ok=True)


def chromium() -> "str | None":
    p = os.environ.get("SE_CHROMIUM")
    if p and os.path.exists(p):
        return p
    for c in sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"), reverse=True):
        return c
    return None


def launch(pw):
    args = ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--allow-file-access-from-files"]
    exe = chromium()
    return pw.chromium.launch(executable_path=exe, args=args) if exe else pw.chromium.launch(args=args)
