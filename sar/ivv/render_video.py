#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""demo_run.json → mp4/gif 영상. 폐루프 UAV 정책 제어를 프레임마다 그린다(센서 FOV 포함).

시스템 ffmpeg 없이 imageio-ffmpeg 번들 바이너리로 mp4 를 낸다. 한글은 Nanum 등록.
"""
from __future__ import annotations
import json, math, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import Circle, Rectangle, FancyArrow

HERE = os.path.dirname(os.path.abspath(__file__))
for p in ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
          "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"):
    if os.path.exists(p):
        fm.fontManager.addfont(p)
plt.rcParams["font.family"] = ["NanumGothic", "NanumBarunGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

C = dict(bg="#0b0f16", panel="#141b26", ink="#e6edf6", muted="#93a1b3", line="#25303f",
         accent="#22d3ee", uav="#60a5fa", live="#34d399", decoy="#f59e0b", crit="#f87171", relo="#a78bfa")
ACTC = dict(SEARCH="accent", APPROACH="uav", INSPECT="live", RETURN="decoy",
            EMERGENCY="crit", AVOID="crit", RELOCALIZE="relo", NONE="muted")
SENS = ["RGB", "THERMAL", "LIDAR", "SAR", "AUDIO"]
FOV = 5.0   # 센싱 반경(칸) — 시각용 footprint


def phase(fr, dc):
    if fr["act"] == "EMERGENCY": return "전력 임계 — 비상 귀환 (safety filter override)"
    if fr["act"] == "RETURN": return "저전력(<25%) — 자동 귀환 (FDIR)"
    if fr["imu"] == 0 or fr["act"] == "RELOCALIZE": return "IMU/GNSS 상실 — 재정렬, 전진 금지"
    if fr["health"][2] < 0.3: return "LiDAR 고장 감지·격리 — 남은 센서로 융합 (FDIR)"
    if fr["act"] == "AVOID": return "충돌 위험 — 회피 (safety filter)"
    if fr.get("los", 1) == 0: return "표적 능선 뒤 — 가시선 없음 (3D 지형 가림)"
    if fr["belief"][2]: return "생존자 확인 — liveness 있음, 접근·관측"
    near = math.hypot(fr["veh"][0]-dc[0], fr["veh"][1]-dc[1]) < 4
    if fr["act"] == "APPROACH" and near: return "후보 조사 — decoy는 생체징후 없음 → 확인 거부"
    if fr["act"] == "APPROACH": return "후보로 접근"
    return "탐색 — 미탐색 구역 커버"


def render(json_path=None, fps=6, out_mp4=None, out_gif=True):
    d = json.load(open(json_path or os.path.join(HERE, "demo_run.json")))
    s3 = bool(d.get("scene3d", False))
    GW, GH, F = d["GW"], d["GH"], d["frames"]
    dem = np.array(d["dem"]); tg = d["targets"][0]; dc = d["decoys"][0]; ob = d["obstacle"]; hm = d["home"]
    cover = np.zeros((GH, GW))
    frames_rgb = []
    fig = plt.figure(figsize=(11, 5.6), dpi=110)
    fig.patch.set_facecolor(C["bg"])
    for i, fr in enumerate(F):
        v = fr["veh"]
        yy, xx = np.ogrid[0:GH, 0:GW]
        cover[((xx-v[0])**2 + (yy-v[1])**2) <= 9] = 1.0
        fig.clf(); fig.patch.set_facecolor(C["bg"])
        axm = fig.add_axes([0.02, 0.06, 0.56, 0.88]); axt = fig.add_axes([0.60, 0.04, 0.38, 0.92])
        # ── map ──
        axm.imshow(dem, extent=[0, GW, 0, GH], origin="lower", cmap="cividis", alpha=0.9, aspect="auto")
        axm.imshow(np.where(cover > 0, 1.0, np.nan), extent=[0, GW, 0, GH], origin="lower",
                   cmap="Greys_r", alpha=0.12, vmin=0, vmax=1, aspect="auto")
        # FOV
        axm.add_patch(Circle((v[0], v[1]), FOV, fc=C["accent"], ec=C["accent"], alpha=0.10, lw=1))
        # trail
        tr = np.array([f["veh"] for f in F[:i+1]])
        axm.plot(tr[:, 0], tr[:, 1], color=C["uav"], lw=1.6, alpha=0.75)
        # obstacle / home
        axm.plot(ob[0], ob[1], "x", color=C["crit"], ms=11, mew=3)
        axm.text(hm[0], hm[1], "⌂", color=C["muted"], fontsize=12, ha="center", va="center")
        # target + decoy, rays if within FOV (3D: 가시선 없으면 광학 ray 없음)
        flos = fr.get("los", 1)
        dt = math.hypot(v[0]-tg[0], v[1]-tg[1]); dd = math.hypot(v[0]-dc[0], v[1]-dc[1])
        if dt <= FOV and flos: axm.plot([v[0], tg[0]], [v[1], tg[1]], color=C["live"], lw=1, alpha=0.5)
        if dd <= FOV: axm.plot([v[0], dc[0]], [v[1], dc[1]], color=C["decoy"], lw=1, alpha=0.5, ls="--")
        if s3 and not flos:      # 능선 뒤: 표적 흐리게 + 가림 표시
            axm.scatter([tg[0]], [tg[1]], s=90, facecolors="none", edgecolors=C["muted"], lw=1.5, zorder=5)
            axm.text(tg[0]+0.5, tg[1]+0.5, "가림", color=C["muted"], fontsize=9)
        else:
            axm.scatter([tg[0]], [tg[1]], s=90, c=C["live"], edgecolors="white", zorder=5)
            axm.text(tg[0]+0.5, tg[1]+0.5, "LIVE", color=C["live"], fontsize=9, fontweight="bold")
        axm.scatter([dc[0]], [dc[1]], s=80, c=C["decoy"], edgecolors="white", zorder=5)
        axm.text(dc[0]+0.5, dc[1]+0.5, "decoy", color=C["decoy"], fontsize=8)
        # decoy 조사·거부 강조
        if fr["act"] == "APPROACH" and dd < 4 and not fr["belief"][2]:
            axm.add_patch(Circle((dc[0], dc[1]), 1.4, fc="none", ec=C["decoy"], lw=2, ls=":"))
            axm.text(dc[0], dc[1]-1.8, "생체징후 없음 → 거부", color=C["decoy"], fontsize=8, ha="center")
        # belief ring
        if fr["belief"][2]:
            axm.add_patch(Circle((fr["belief"][0], fr["belief"][1]), 0.9, fc="none", ec=C["live"], lw=2.2))
        # UAV marker
        axm.scatter([v[0]], [v[1]], s=120, marker="^", c=C["uav"], edgecolors="white", zorder=6)
        axm.set_xlim(0, GW); axm.set_ylim(0, GH); axm.set_xticks([]); axm.set_yticks([])
        for s in axm.spines.values(): s.set_color(C["line"])
        axm.set_title("실측 지리산 · 폐루프 정책 제어" + (" · 3D 지형 가시선" if s3 else ""),
                      color=C["muted"], fontsize=10, loc="left")

        # ── telemetry ──
        axt.set_facecolor(C["panel"]); axt.set_xlim(0, 1); axt.set_ylim(0, 1)
        axt.add_patch(Rectangle((0, 0), 1, 1, transform=axt.transAxes, fc=C["panel"], ec=C["line"], lw=1))
        axt.set_xticks([]); axt.set_yticks([])
        axt.text(0.05, 0.93, fr["act"], color=C[ACTC.get(fr["act"], "ink")], fontsize=26, fontweight="bold")
        axt.text(0.95, 0.95, "t %03d/%03d" % (fr["t"], len(F)-1), color=C["muted"], fontsize=11, ha="right")
        axt.text(0.05, 0.84, phase(fr, dc), color=C["ink"], fontsize=11.5, va="top", wrap=True)
        # battery bar
        b = fr["battery"]; bc = C["crit"] if b < 0.1 else C["decoy"] if b < 0.25 else C["live"]
        axt.text(0.05, 0.70, "배터리", color=C["muted"], fontsize=11)
        axt.add_patch(Rectangle((0.30, 0.685), 0.6, 0.03, fc=C["line"], ec="none"))
        axt.add_patch(Rectangle((0.30, 0.685), 0.6*max(0, b), 0.03, fc=bc, ec="none"))
        axt.text(0.95, 0.695, "%d%%" % round(b*100), color=C["ink"], fontsize=10, ha="right")
        rows = ([("가시선(3D)", "가림" if fr.get("los", 1) == 0 else "✓ 보임")] if s3 else []) + \
               [("커버리지", "%.1f%%" % fr["coverage"]),
                ("target_conf", "%.2f" % fr["belief"][3]),
                ("NIS(운동일관성)", "%.1f" % fr["belief"][4]),
                ("확인", "✓ 생존자" if fr["belief"][2] else "—"),
                ("IMU/GNSS", "OK" if fr["imu"] else "상실")]
        y = 0.62
        for k, val in rows:
            axt.text(0.05, y, k, color=C["muted"], fontsize=11)
            axt.text(0.95, y, val, color=C["ink"], fontsize=11, ha="right")
            y -= 0.058
        # sensors
        axt.text(0.05, 0.26, "센서 (present·건강)", color=C["muted"], fontsize=10.5)
        x = 0.05; w = 0.168; step = 0.188
        for k, s in enumerate(SENS):
            on = fr["present"][k]; bad = fr["health"][k] < 0.3
            fc = (C["crit"] if bad else C["accent"]) if on else C["panel"]
            ec = C["crit"] if bad else C["line"]
            axt.add_patch(Rectangle((x, 0.17), w, 0.055, fc=fc, ec=ec, lw=1))
            axt.text(x+w/2, 0.197, s[:4]+("✕" if bad else ""), color=("#04121a" if on and not bad else C["ink"] if on else C["muted"]),
                     fontsize=7.2, ha="center", va="center")
            x += step
        axt.text(0.05, 0.06, "L2 verification · 현장 아님 · fw C executive(ctypes)", color=C["muted"], fontsize=8.5)

        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
        h, w = buf.shape[:2]
        if h % 2 or w % 2:
            buf = buf[:h - (h % 2), :w - (w % 2)]
        frames_rgb.append(buf.copy())
    plt.close(fig)

    import imageio.v2 as imageio
    base = "demo_video_3d" if s3 else "demo_video"
    out_mp4 = out_mp4 or os.path.join(HERE, base + ".mp4")
    imageio.mimsave(out_mp4, frames_rgb, fps=fps, codec="libx264", quality=8,
                    macro_block_size=None, output_params=["-pix_fmt", "yuv420p"])
    print("wrote", out_mp4, os.path.getsize(out_mp4), "bytes,", len(frames_rgb), "frames @", fps, "fps")
    if out_gif:
        g = os.path.join(HERE, base + ".gif")
        imageio.mimsave(g, frames_rgb[::2], duration=1.0/(fps/2))
        print("wrote", g, os.path.getsize(g), "bytes")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--fps", type=int, default=6); ap.add_argument("--nogif", action="store_true")
    ap.add_argument("--json", default=None, help="입력 상태 JSON(기본 demo_run.json)")
    a, _ = ap.parse_known_args()
    render(json_path=a.json, fps=a.fps, out_gif=not a.nogif)
