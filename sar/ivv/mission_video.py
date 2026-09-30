#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mission_sim.py 산출 JSON → 두 mp4: (1) 온보드 RGB+센서 뷰, (2) 상공 샷.

정직: 대표 렌더(L2)다 — 실사 영상 아님. 관찰자(상공) 뷰는 truth(표적·decoy)를 그리지만 SUT 는 truth 를
못 본다(센서만). false positive(decoy·순간 식생)와 false negative(수관 은폐 미탐)는 물리·평가기가 낸
것을 그대로 표시한다(색·주석은 truth 로 분류 — 관찰자 몫). 시스템 ffmpeg 없이 imageio-ffmpeg 로 mp4.
"""
from __future__ import annotations
import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import Circle, Rectangle, Polygon

for _p in ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"):
    if os.path.exists(_p):
        fm.fontManager.addfont(_p)
plt.rcParams["font.family"] = ["NanumGothic", "NanumBarunGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

C = dict(bg="#0b0f16", panel="#141b26", ink="#e6edf6", muted="#93a1b3", line="#25303f",
         accent="#22d3ee", uav="#60a5fa", live="#34d399", decoy="#f59e0b", crit="#f87171",
         relo="#a78bfa", clutter="#6b7280", rgb="#38bdf8", thermal="#fb923c")
ACTC = dict(SEARCH="accent", APPROACH="uav", INSPECT="live", RETURN="decoy",
            EMERGENCY="crit", AVOID="crit", RELOCALIZE="relo", NONE="muted")
FR_S = 20.0
DET_R = 3.2                                          # 탐지 반경(칸)


def _phase(fr, near_decoy):
    a = fr["act"]
    if a == "EMERGENCY":
        return "전력 임계 — 비상 귀환(안전필터)"
    if a == "RETURN":
        return "저전력(<25%) — 자동 귀환(FDIR)"
    if a == "RELOCALIZE" or not fr["imu_ok"]:
        return "IMU/GNSS 상실 — 재정렬, 전진 금지"
    if fr["belief"][2]:
        return "생존자 확인 — liveness 있음(호흡·심박), georef 기록"
    if fr["health"][1] < 0.3:
        return "열화상 고장 감지·격리 — 남은 센서로 융합(FDIR)"
    if a == "AVOID":
        return "충돌 위험 — 회피(안전필터)"
    if near_decoy:
        return "후보 조사 — 생체징후 없음, 사람 아님(오인 거부·FP)"
    if a == "APPROACH":
        return "센서 후보로 접근·정밀관측(확인 시도)"
    return "탐색 — 미탐색 구역 커버(격자 스윕)"


def _near(ax, ay, pts, r):
    return any((ax - px) ** 2 + (ay - py) ** 2 <= r * r for px, py in pts)


def _load(json_path):
    d = json.load(open(json_path))
    d["_dem"] = np.array(d["dem"]) if d.get("dem") else None
    return d


def _interp_frames(F, interp):
    """결정 프레임 사이 veh 위치를 interp 개 보간(움직임 매끄럽게). 다른 상태는 그대로."""
    out = []
    for i, fr in enumerate(F):
        nxt = F[min(i + 1, len(F) - 1)]
        for s in range(interp):
            a = s / interp
            g = dict(fr)
            g["veh"] = [fr["veh"][0] + (nxt["veh"][0] - fr["veh"][0]) * a,
                        fr["veh"][1] + (nxt["veh"][1] - fr["veh"][1]) * a]
            g["_i"] = i
            out.append(g)
    return out


def _target_style(d, fr, i):
    found = fr["found"][i]
    if found:
        return C["live"], "✓ 생존자 확인", "o"
    if d["canopy"][i]:
        return C["muted"], "수관 은폐(미탐 FN 후보)", "s"
    return C["muted"], "미탐", "o"


# ─────────────────────────── 상공 샷 ───────────────────────────
def render_aerial(d, out_mp4, fps=10, interp=2):
    GW, GH = d["GW"], d["GH"]
    dem = d["_dem"]
    F = _interp_frames(d["frames"], interp)
    tt = d["targets"]; dc = d["decoys"]
    trail_x, trail_y = [], []
    cover = np.zeros((GH, GW))
    frames_rgb = []
    fig = plt.figure(figsize=(11, 6.2), dpi=110)
    for fr in F:
        v = fr["veh"]
        yy, xx = np.ogrid[0:GH, 0:GW]
        cover[((xx - v[0]) ** 2 + (yy - v[1]) ** 2) <= 9] = 1.0
        trail_x.append(v[0]); trail_y.append(v[1])
        fig.clf(); fig.patch.set_facecolor(C["bg"])
        axm = fig.add_axes([0.02, 0.06, 0.62, 0.9]); axt = fig.add_axes([0.66, 0.06, 0.32, 0.9])
        if dem is not None:
            axm.imshow(dem, extent=[0, GW, 0, GH], origin="lower", cmap="cividis", alpha=0.9, aspect="auto")
        axm.imshow(np.where(cover > 0, 1.0, np.nan), extent=[0, GW, 0, GH], origin="lower",
                   cmap="Greys_r", alpha=0.12, vmin=0, vmax=1, aspect="auto")
        axm.add_patch(Circle((v[0], v[1]), DET_R, fc=C["accent"], ec=C["accent"], alpha=0.08, lw=1))
        axm.plot(trail_x, trail_y, color=C["uav"], lw=1.4, alpha=0.7)
        # clutter(순간 식생 오인): 이 프레임 센서 블립 중 표적·decoy 근처 아닌 것
        for k in ("rgb", "thermal"):
            for bx, by in fr["sensors"].get(k, []):
                if not _near(bx, by, tt, 2.5) and not _near(bx, by, dc, 2.5):
                    axm.scatter([bx], [by], s=14, c=C["clutter"], marker="x", alpha=0.5, zorder=3)
        # decoys
        for dx, dy in dc:
            axm.scatter([dx], [dy], s=70, c=C["decoy"], marker="X", edgecolors="white", lw=0.6, zorder=5)
            if math.hypot(v[0] - dx, v[1] - dy) < 1.8 and not fr["belief"][2]:
                axm.add_patch(Circle((dx, dy), 1.3, fc="none", ec=C["decoy"], lw=1.8, ls=":"))
                axm.text(dx, dy - 1.7, "생체 없음→거부", color=C["decoy"], fontsize=7.5, ha="center")
        # targets
        for i, (tx, ty) in enumerate(tt):
            col, lab, mk = _target_style(d, fr, i)
            axm.scatter([tx], [ty], s=95, c=col, marker=mk, edgecolors="white", lw=0.8, zorder=6)
            if d["canopy"][i]:
                axm.scatter([tx], [ty], s=240, facecolors="none", edgecolors=C["live"], lw=0.8, alpha=0.35, zorder=5)
            axm.text(tx + 0.5, ty + 0.5, lab, color=col, fontsize=7.5, fontweight="bold")
        # UAV
        axm.scatter([v[0]], [v[1]], s=150, marker="^", c=C["uav"], edgecolors="white", lw=1, zorder=8)
        axm.set_xlim(0, GW); axm.set_ylim(0, GH); axm.set_xticks([]); axm.set_yticks([])
        for s in axm.spines.values():
            s.set_color(C["line"])
        axm.set_title("상공 샷 · 관찰자 뷰(truth 표시 — SUT 는 센서만 봄) · %s" % d["scenario"].get("fidelity", ""),
                      color=C["muted"], fontsize=9.5, loc="left")
        _sidebar(axt, d, fr, aerial=True)
        frames_rgb.append(_grab(fig))
    plt.close(fig)
    _save(frames_rgb, out_mp4, fps)


# ─────────────────────────── 온보드 RGB+센서 ───────────────────────────
def render_onboard(d, out_mp4, fps=10, interp=2):
    GW, GH = d["GW"], d["GH"]
    dem = d["_dem"]
    F = _interp_frames(d["frames"], interp)
    tt = d["targets"]; dc = d["decoys"]
    R = 6.0                                          # 온보드 시야 반경(칸)
    frames_rgb = []
    fig = plt.figure(figsize=(11, 6.2), dpi=110)
    for fr in F:
        v = fr["veh"]
        fig.clf(); fig.patch.set_facecolor(C["bg"])
        axv = fig.add_axes([0.02, 0.06, 0.62, 0.9]); axt = fig.add_axes([0.66, 0.06, 0.32, 0.9])
        axv.set_facecolor("#05080d")
        if dem is not None:
            axv.imshow(dem, extent=[0, GW, 0, GH], origin="lower", cmap="bone", alpha=0.5, aspect="auto")
        # 시야 원
        axv.add_patch(Circle((v[0], v[1]), R, fc="none", ec=C["line"], lw=1))
        axv.add_patch(Circle((v[0], v[1]), DET_R, fc=C["accent"], ec="none", alpha=0.06))
        # 센서 블립(모달 색): RGB=cyan, Thermal=orange. 시야 안만.
        for k, col in (("rgb", C["rgb"]), ("thermal", C["thermal"])):
            for bx, by in fr["sensors"].get(k, []):
                if math.hypot(bx - v[0], by - v[1]) <= R:
                    axv.scatter([bx], [by], s=42, facecolors="none", edgecolors=col, lw=1.6, zorder=5)
        # liveness(호흡·심박): 초록 점
        for bx, by in fr.get("live", []):
            if math.hypot(bx - v[0], by - v[1]) <= R:
                axv.scatter([bx], [by], s=70, c=C["live"], marker="*", zorder=6)
        # truth 표적/decoy 는 온보드엔 안 그린다(SUT 는 못 봄) — 대신 확인된 belief 만 링
        if fr["belief"][2]:
            axv.add_patch(Circle((fr["belief"][0], fr["belief"][1]), 0.9, fc="none", ec=C["live"], lw=2.2, zorder=7))
        # 조사 중 후보(미확인)로 접근 표시
        axv.scatter([v[0]], [v[1]], s=170, marker="^", c=C["uav"], edgecolors="white", lw=1, zorder=8)
        axv.set_xlim(v[0] - R, v[0] + R); axv.set_ylim(v[1] - R, v[1] + R)
        axv.set_xticks([]); axv.set_yticks([])
        for s in axv.spines.values():
            s.set_color(C["line"])
        near_decoy = _near(v[0], v[1], dc, 1.8) and not fr["belief"][2]
        axv.set_title("온보드 뷰 · RGB(청)·열화상(주)·liveness(★) · L2 대표 렌더(실사 아님)",
                      color=C["muted"], fontsize=9.5, loc="left")
        # 하단 범례
        axv.text(0.02, 0.02, "○청 RGB탐지   ○주 열화상탐지   ★ liveness(호흡·심박)   ○초록 확인",
                 transform=axv.transAxes, color=C["muted"], fontsize=8)
        _sidebar(axt, d, fr, aerial=False, near_decoy=near_decoy)
        frames_rgb.append(_grab(fig))
    plt.close(fig)
    _save(frames_rgb, out_mp4, fps)


def _sidebar(axt, d, fr, aerial, near_decoy=False):
    axt.set_facecolor(C["panel"]); axt.set_xlim(0, 1); axt.set_ylim(0, 1)
    axt.add_patch(Rectangle((0, 0), 1, 1, transform=axt.transAxes, fc=C["panel"], ec=C["line"], lw=1))
    axt.set_xticks([]); axt.set_yticks([])
    a = fr["act"]
    axt.text(0.05, 0.95, a, color=C[ACTC.get(a, "ink")], fontsize=22, fontweight="bold", va="top")
    axt.text(0.95, 0.97, "t %04.0f s" % (fr["t"] * FR_S), color=C["muted"], fontsize=9.5, ha="right", va="top")
    ndec = near_decoy or (_near(fr["veh"][0], fr["veh"][1], d["decoys"], 1.8) and not fr["belief"][2])
    axt.text(0.05, 0.86, _phase(fr, ndec), color=C["ink"], fontsize=10, va="top", wrap=True)
    # 배터리
    b = fr["battery"]; bc = C["crit"] if b < 0.1 else C["decoy"] if b < 0.25 else C["live"]
    axt.text(0.05, 0.72, "배터리", color=C["muted"], fontsize=9.5)
    axt.add_patch(Rectangle((0.34, 0.705), 0.56, 0.028, fc=C["line"], ec="none"))
    axt.add_patch(Rectangle((0.34, 0.705), 0.56 * max(0, b), 0.028, fc=bc, ec="none"))
    axt.text(0.92, 0.715, "%d%%" % round(b * 100), color=C["ink"], fontsize=9, ha="right")
    found = sum(fr["found"]); nt = len(fr["found"])
    rows = [("생존자 확인", "%d / %d" % (found, nt)),
            ("target_conf", "%.2f" % fr["belief"][3]),
            ("NIS(운동일관성)", "%.1f" % fr["belief"][4]),
            ("확인(liveness)", "✓" if fr["belief"][2] else "—"),
            ("커버리지", "%.0f%%" % fr["coverage"]),
            ("IMU/GNSS", "OK" if fr["imu_ok"] else "상실")]
    y = 0.64
    for k, val in rows:
        axt.text(0.05, y, k, color=C["muted"], fontsize=9.5)
        axt.text(0.92, y, val, color=C["ink"], fontsize=9.5, ha="right"); y -= 0.052
    # 센서 칩(RGB·Thermal·IMU 만 이 시나리오)
    axt.text(0.05, 0.30, "센서 (present·건강)", color=C["muted"], fontsize=9.5)
    names = ["RGB", "Thermal", "IMU"]; idx = [0, 1, None]
    x = 0.05; w = 0.28; step = 0.30
    for j, nm in enumerate(names):
        if nm == "IMU":
            on = fr["imu_ok"]; bad = not fr["imu_ok"]
        else:
            hi = idx[j]; bad = fr["health"][hi] < 0.3
            on = any(fr["sensors"].get(nm.lower(), []))
        fc = (C["crit"] if bad else C["accent"]) if (on or nm == "IMU") else C["panel"]
        axt.add_patch(Rectangle((x, 0.23), w, 0.05, fc=fc if (on and not bad) else C["panel"], ec=C["crit"] if bad else C["line"], lw=1))
        axt.text(x + w / 2, 0.255, nm + ("✕" if bad else ""), color=("#04121a" if (on and not bad) else C["muted"]),
                 fontsize=8, ha="center", va="center")
        x += step
    axt.text(0.05, 0.16, "종료: %s" % d["end_reason"], color=C["muted"], fontsize=8.5, va="top")
    axt.text(0.05, 0.10, "FP(오인)후보 센서레벨 %d · 확인까지 샌 FP %d" % (
        d["metrics"]["fp_candidates_sensor"], d["metrics"]["false_alarms_confirmed"]), color=C["muted"], fontsize=8, va="top")
    axt.text(0.05, 0.04, "fw C 결정 executive(ctypes) · IV&V 참조세계 · 현장 아님", color=C["muted"], fontsize=7.5, va="top")


def _grab(fig):
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    h, w = buf.shape[:2]
    if h % 2 or w % 2:
        buf = buf[:h - (h % 2), :w - (w % 2)]
    return buf.copy()


def _save(frames, out_mp4, fps):
    import imageio.v2 as imageio
    imageio.mimsave(out_mp4, frames, fps=fps, codec="libx264", quality=7,
                    macro_block_size=None, output_params=["-pix_fmt", "yuv420p"])
    print("wrote", out_mp4, os.path.getsize(out_mp4), "bytes,", len(frames), "frames @", fps, "fps")


def render_both(json_path, out_prefix, fps=10, interp=2):
    d = _load(json_path)
    render_onboard(d, out_prefix + "_onboard.mp4", fps=fps, interp=interp)
    render_aerial(d, out_prefix + "_aerial.mp4", fps=fps, interp=interp)


if __name__ == "__main__":
    import argparse
    HERE = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(HERE, "mission_run.json"))
    ap.add_argument("--prefix", default=os.path.join(HERE, "mission"))
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--interp", type=int, default=2)
    a, _ = ap.parse_known_args()
    render_both(a.json, a.prefix, fps=a.fps, interp=a.interp)
