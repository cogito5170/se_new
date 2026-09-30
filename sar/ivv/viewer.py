#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3D 임무 뷰어 — 참조세계·SUT 상태를 실시간으로 보여준다. **뷰어는 truth 를 봐도 된다.**

핵심(NASA 실시간 sim + telemetry viz): 뷰어는 검증자가 아니라 시각화 계층이다. SUT 와 분리돼
있으니 **관찰자는 정답(표적 실위치)을 보면서** SUT 가 그것을 모른 채 탐색하는 행동을 지켜본다.
photorealism ≠ validation — 여기 3D 는 matplotlib(실배포는 Unreal/Cesium). 그림은 예뻐도
검증 강도는 참조 물리·독립 평가에서 온다.

frames: harness.run_one(record_frames=True) 가 준다 — sut_pose·telemetry·sensors·truth 포함.
"""
import math
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",):
    if os.path.exists(_c):
        fm.fontManager.addfont(_c); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

GW = GH = 24


def render(dem, frames, path, fps=2):
    DH, DW = dem.shape
    Zc = dem[::max(1, DH//60), ::max(1, DW//60)]
    Xc, Yc = np.meshgrid(np.arange(Zc.shape[1]), np.arange(Zc.shape[0]))
    def g2s(gx, gy):                                     # 격자 → 서브샘플 표면 좌표
        return gx/GW*Zc.shape[1], gy/GH*Zc.shape[0]
    def zc(gx, gy):
        return dem[min(DH-1, int(gy/GH*DH)), min(DW-1, int(gx/GW*DW))]
    fig = plt.figure(figsize=(13, 7.2))
    ax = fig.add_subplot(1, 2, 1, projection="3d")
    axh = fig.add_subplot(1, 2, 2); axh.axis("off")
    NF = len(frames)

    def draw(i):
        ax.clear(); axh.clear(); axh.axis("off")
        fr = frames[i]
        ax.plot_surface(Xc, Yc, Zc, cmap="terrain", alpha=0.6, linewidth=0)
        # UAV 궤적 + 현재
        xs = [g2s(*f["sut_pose"])[0] for f in frames[:i+1]]
        ys = [g2s(*f["sut_pose"])[1] for f in frames[:i+1]]
        zs = [zc(*f["sut_pose"])+90 for f in frames[:i+1]]
        ax.plot(xs, ys, zs, "-", color="cyan", lw=2)
        ax.scatter([xs[-1]], [ys[-1]], [zs[-1]], c="red", s=45, label="UAV")
        # TRUTH 표적(관찰자만 본다 — SUT 는 모름)
        for (tx, ty) in fr["truth"]["targets"]:
            sx, sy = g2s(tx, ty)
            ax.scatter([sx], [sy], [zc(tx, ty)+10], c="red", marker="o", s=80, edgecolor="k", label="TRUTH 표적(SUT 모름)")
        # SUT 주장(추정)
        for f in frames[:i+1]:
            for (cx, cy, *_r) in f["sut"].get("detections", []):
                sx, sy = g2s(cx, cy)
                ax.scatter([sx], [sy], [zc(cx, cy)+10], c="lime", marker="x", s=70, label="SUT 주장")
        h, l = ax.get_legend_handles_labels()
        seen = dict(zip(l, h)); ax.legend(seen.values(), seen.keys(), fontsize=7, loc="upper left")
        ax.set_title("3D 임무 뷰 (관찰자는 TRUTH 를 본다 · SUT 는 못 본다)", fontsize=9)
        ax.view_init(elev=52, azim=-60 + i*1.5); ax.set_axis_off()
        # ── HUD: 실시간 텔레메트리 (기계 상태를 사람이 읽게) ──
        tm = fr["sut"]["telemetry"]; se = fr["sensors"]
        vis = se["rgb"]["vis"]; vist = "GOOD" if vis >= .6 else ("DEGRADED" if vis >= .25 else "POOR")
        axh.text(0, 1.0, "TELEMETRY  t=%02d/%02d" % (i, NF), fontsize=12, weight="bold", va="top")
        rows = [("정책 상태", fr["sut"]["state"]),
                ("커버리지", "%.0f%%" % tm["coverage"]),
                ("RGB 가시도", "%s (t=%.2f)" % (vist, vis)),
                ("IMU σ", "%.0f m %s" % (tm["sigma"], "OK" if se["imu"]["ok"] else "고장")),
                ("GPS", "불확실↑" if tm["gps_uncertain"] else "정상"),
                ("SAR(전천후)", "ACTIVE · 반사 %d" % tm["sar_hits"]),
                ("방위", "%03d°" % (int(tm["heading"]) % 360)),
                ("표적(SUT 인지)", "%d 주장" % sum(len(f["sut"].get("detections", [])) for f in frames[:i+1])),
                ("표적(TRUTH)", "%d (SUT 모름)" % len(fr["truth"]["targets"]))]
        for k, (a, b) in enumerate(rows):
            axh.text(0.0, 0.86-k*0.088, a, fontsize=10, va="top", color="0.35")
            axh.text(0.52, 0.86-k*0.088, b, fontsize=10, va="top", weight="bold")
        axh.text(0.0, 0.02, "photorealism ≠ validation. 검증 강도는 참조 물리·독립 평가에서 온다(실배포 3D=Unreal/Cesium).",
                 fontsize=7, color="0.4", va="bottom")
        return []

    fig.suptitle("IV&V 실시간 3D — 독립 참조세계 · SUT(센서만) · 관찰자(TRUTH)", fontsize=11)
    anim = FuncAnimation(fig, draw, frames=NF, interval=500, blit=False)
    anim.save(path, writer=PillowWriter(fps=fps), dpi=80); plt.close(fig)
