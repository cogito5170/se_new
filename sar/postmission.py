#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사후 임무보고 — 실시간 화면과 반대로 **시간축**이 핵심.

실시간(playback.py) = "지금 무슨 일?"  ↔  사후보고(여기) = "무슨 일이 있었고,
정책이 왜 그렇게 반응했고, 어떻게 복구했나". 그래서 모든 패널이 t(프레임)축을 공유한다.

패널(사용자 설계):
  ① 3D 궤적(전 구간, 단계색)         ② 최종 커버리지 top-down
  ③ 정책 타임라인 SEARCH→VERIFY→REPORT→HOLD→REPLAN (상태전이의 띠)
  ④ 센서 타임라인 RGB/IMU/GPS/링크 (프레임별 상태 막대)  ← 실패/회복 구간이 여기서 보인다
  ⑤ 이벤트·SAR 무전 로그(타임스탬프)
③+④의 빨강(실패)→초록/파랑(회복) 구간이 곧 robustness/resilience 의 증거 그림이다.

수치는 새로 만들지 않는다. playback.simulate() 이 이미 기록한 frames 를 시간축으로 다시 그릴 뿐.
"""
import os, math, argparse
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.font_manager as fm
for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",):
    if os.path.exists(_c): fm.fontManager.addfont(_c); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from matplotlib.patches import Rectangle
import playback  # simulate() · GW · GH · cpx
import radar

# 정책 단계 어휘(사용자 지정) 와 색.
PHASE_ORDER = ["SEARCH", "VERIFY", "REPORT", "REPLAN", "HOLD"]
PHASE_COL = {"SEARCH": "#2e7d32", "VERIFY": "#f9a825", "REPORT": "#1565c0", "REPLAN": "#6a1b9a", "HOLD": "#c62828"}
PHASE_KR = {"SEARCH": "탐색", "VERIFY": "재확인", "REPORT": "보고", "REPLAN": "재계획", "HOLD": "체공/최소위험"}


def phase_of(fr):
    """기록된 state·det 을 정책 단계 어휘로 사상. (실시간 state → 사후 단계)"""
    st = fr["state"]
    if st == "MRC": return "HOLD"
    if st in ("RTL", "RECOVER↑"): return "REPLAN"      # 결함·안개 후 항로/고도 재계획
    if fr["det"] is not None: return "REPORT"           # 탐지 확정 + 무전 송신
    if st in ("DEGRADED", "LOW-INFO"): return "VERIFY"  # 신뢰도 저하 → 감속·재접근으로 재확인
    return "SEARCH"


def _stat3(val, ok, low):
    """값 → (색, 라벨). ok 이상 초록, low 이상 주황, 아니면 빨강."""
    if val >= ok:  return ("#2e7d32", "GOOD")
    if val >= low: return ("#f9a825", "DEGR")
    return ("#c62828", "POOR")


def render(V, path):
    dem, DH, DW, sc = V["dem"], V["DH"], V["DW"], V["sc"]; frames = V["frames"]; NF = len(frames)
    GW, GH = playback.GW, playback.GH
    ls = LightSource(315, 45); hs = ls.hillshade(dem, vert_exag=2.0)
    phases = [phase_of(f) for f in frames]

    fig = plt.figure(figsize=(15, 10))
    gs = fig.add_gridspec(4, 3, height_ratios=[1.35, 0.34, 0.66, 0.9], hspace=0.55, wspace=0.28)
    ax3 = fig.add_subplot(gs[0, 0], projection="3d")   # ① 3D 궤적
    axm = fig.add_subplot(gs[0, 1])                     # ② 최종 커버리지
    axg = fig.add_subplot(gs[0, 2]); axg.axis("off")    # 요약 카드
    axp = fig.add_subplot(gs[1, :])                     # ③ 정책 타임라인
    axse = fig.add_subplot(gs[2, :])                    # ④ 센서 타임라인
    axl = fig.add_subplot(gs[3, :]); axl.axis("off")    # ⑤ 이벤트·무전

    # ① 3D 궤적 — 점을 단계색으로
    Zc = dem[::max(1, DH//70), ::max(1, DW//70)]; Xc, Yc = np.meshgrid(np.arange(Zc.shape[1]), np.arange(Zc.shape[0]))
    ax3.plot_surface(Xc, Yc, Zc, cmap="terrain", alpha=0.55, linewidth=0)
    xs = [f["veh"][0]/GW*Zc.shape[1] for f in frames]; ys = [f["veh"][1]/GH*Zc.shape[0] for f in frames]
    zs = [dem[min(DH-1, int(f["veh"][1]/GH*DH)), min(DW-1, int(f["veh"][0]/GW*DW))]+80 for f in frames]
    ax3.plot(xs, ys, zs, "-", color="0.3", lw=1.0, alpha=0.6)
    ax3.scatter(xs, ys, zs, c=[PHASE_COL[p] for p in phases], s=22, depthshade=False)
    ax3.set_title("① 3D 궤적 (색=정책단계)", fontsize=10); ax3.view_init(elev=55, azim=-60); ax3.set_axis_off()

    # ② 최종 커버리지 top-down
    axm.imshow(hs, cmap="gray", alpha=0.9)
    cov = np.zeros((*hs.shape, 4)); c = frames[-1]["cov"]
    covbig = np.kron(c, np.ones((DH//GH+1, DW//GW+1)))[:hs.shape[0], :hs.shape[1]]
    cov[covbig > 0] = (0.1, 0.8, 0.3, 0.30); axm.imshow(cov)
    def cpx(cc): return (cc[0]/GW*DW, cc[1]/GH*DH)
    tp = [cpx(f["veh"]) for f in frames]
    axm.plot([p[0] for p in tp], [p[1] for p in tp], "-", color="cyan", lw=1.4, alpha=0.9)
    if sc["fire"]:
        fp = cpx(frames[-1]["fire"]); axm.plot(*fp, "^", color="red", ms=12)
    for (sx, sy) in V["survs"]:
        p = cpx((sx, sy)); ok = any((sx-c2[0])**2+(sy-c2[1])**2 <= 4 for c2 in V["confirmed"])
        axm.plot(*p, "*", ms=15, color="lime" if ok else "white", mec="k")
    covpct = 100.0*c.sum()/(GW*GH)
    axm.set_title("② 최종 커버리지 %.0f%% · ★=조난자(초록=확보)" % covpct, fontsize=10)
    axm.set_xlim(0, DW); axm.set_ylim(DH, 0); axm.axis("off")

    # 요약 카드
    dur = NF * 20  # 프레임당 20 s 명목
    verdict = "임무 성공" if len(V["confirmed"]) >= len(V["survs"]) else \
              ("부분 성공" if V["confirmed"] else "미탐 — 안전강등")
    n_repl = sum(1 for p in phases if p == "REPLAN"); n_hold = sum(1 for p in phases if p == "HOLD")
    cfg = radar.RadarCfg()
    lines = [("임무 판정", verdict), ("조난자 확보", "%d / %d 명" % (len(V["confirmed"]), len(V["survs"]))),
             ("장소·조건", "%s · %s" % (sc["place"], sc["condition"])),
             ("소요(명목)", "%d 프레임 ≈ %d s" % (NF, dur)), ("커버리지", "%.0f%%" % covpct),
             ("재계획(REPLAN)", "%d 회" % n_repl), ("체공/최소위험(HOLD)", "%d 회" % n_hold),
             ("센서", "RGB+IMU + SAR 레이더(전천후)"),
             ("SAR 제원", "X-FMCW %.0fGHz δr=%.1fm" % (cfg.fc / 1e9, cfg.range_res))]
    axg.text(0, 1.0, "임무 요약", fontsize=13, weight="bold", va="top")
    for k, (a, b) in enumerate(lines):
        axg.text(0, 0.88-k*0.104, "%s:" % a, fontsize=9, va="top", color="0.35")
        axg.text(0.60, 0.88-k*0.104, b, fontsize=9, va="top", weight="bold")

    # ③ 정책 타임라인 — 단계 띠 (전이가 곧 이야기)
    for i, p in enumerate(phases):
        axp.add_patch(Rectangle((i, 0), 1, 1, color=PHASE_COL[p]))
        if i == 0 or phases[i-1] != p:                    # 전이 지점만 라벨
            axp.text(i+0.05, 1.15, PHASE_KR[p], fontsize=7.5, color=PHASE_COL[p], weight="bold", va="bottom", rotation=0)
    for i, f in enumerate(frames):
        if f["event"]: axp.plot(i+0.5, 0.5, "v", color="white", mec="k", ms=9, zorder=5)
    axp.set_xlim(0, NF); axp.set_ylim(0, 1.7); axp.set_yticks([])
    axp.set_xlabel("프레임 t (▽=사건: 탐지·결함·전이)", fontsize=8.5)
    axp.set_title("③ 정책 타임라인  SEARCH→VERIFY→REPORT→REPLAN→HOLD", fontsize=10, loc="left")
    # 범례
    for k, p in enumerate(PHASE_ORDER):
        axp.add_patch(Rectangle((NF*0.0+k*NF*0.13, 1.32), NF*0.02, 0.3, color=PHASE_COL[p], transform=axp.transData, clip_on=False))
        axp.text(NF*0.0+k*NF*0.13+NF*0.025, 1.47, PHASE_KR[p], fontsize=7, va="center")

    # ④ 센서 타임라인 — 실패/회복 구간이 보이는 곳
    rows = ["RGB", "IMU", "GPS", "SAR", "링크"]
    nrow = len(rows)
    for i, f in enumerate(frames):
        rgb_c = "#111" if (f["rho"] == 0 and f["state"] in ("RTL", "MRC")) else _stat3(f["rho"], 0.6, 0.25)[0]
        # IMU/GPS 는 드리프트 σ(작을수록 좋음) → 반전
        sig = f["sig"]; imu_c = "#111" if sig >= 99 else ("#2e7d32" if sig < 15 else ("#f9a825" if sig < 30 else "#c62828"))
        gps_c = imu_c  # GPS 불확실도는 관성드리프트와 함께 커진다(항법해 공유)
        sar_c = "#2e7d32"  # SAR 레이더 = 전천후(안개·연기·야간 무관) → 항상 양호
        link_c = "#2e7d32"  # 링크는 모델 안 함 → 가정 정상(아래 라벨에 명시)
        for r, col in enumerate((rgb_c, imu_c, gps_c, sar_c, link_c)):
            axse.add_patch(Rectangle((i, nrow - 1 - r), 1, 0.86, color=col))
    axse.set_xlim(0, NF); axse.set_ylim(0, nrow); axse.set_yticks([r + 0.43 for r in range(nrow)][::-1]); axse.set_yticklabels(rows, fontsize=9)
    axse.set_xlabel("프레임 t   (초록=양호 · 주황=저하 · 빨강=불량 · 검정=소실)   SAR=전천후 항상 양호", fontsize=8.5)
    axse.set_title("④ 센서 타임라인 — 빨강→초록 구간이 robustness·resilience 의 증거 (통신'링크'는 미모델→가정 정상)", fontsize=10, loc="left")

    # ⑤ 이벤트·SAR 무전 로그 (타임스탬프)
    axl.text(0, 1.0, "⑤ 사건·SAR 무전 로그 (t = 프레임 · 20s)", fontsize=10, weight="bold", va="top")
    y = 0.9
    shown = 0
    for i, f in enumerate(frames):
        if f["event"]:
            axl.text(0, y, "t=%02d  [!] %s" % (i, f["event"]), fontsize=8.5, va="top", color="crimson"); y -= 0.11; shown += 1
        if shown >= 5: break
    y2 = 0.9
    for m in V["radio"][:6]:
        axl.text(0.42, y2, "> " + m[:78], fontsize=7.3, va="top"); y2 -= 0.145
    axl.set_xlim(0, 1); axl.set_ylim(0, 1)

    fig.suptitle("UAV-01  사후 임무보고 (V&V: Reliability·Robustness·Resilience 근거)  |  %s · %s"
                 % (sc["place"], sc["condition"]), fontsize=12, y=0.98)
    fig.savefig(path, dpi=110, bbox_inches="tight"); plt.close(fig)
    return dict(verdict=verdict, covpct=covpct, phases=phases, n_replan=n_repl, n_hold=n_hold)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--nl", default="설악산 일대 산불, 안개, 조난자 2명 탐색")
    ap.add_argument("--seed", type=int, default=None)
    a, _ = ap.parse_known_args()
    V = playback.simulate(a.nl, a.seed)
    out = os.path.join(playback.HERE, "out"); os.makedirs(out, exist_ok=True)
    r = render(V, os.path.join(out, "postmission.png"))
    print("판정=%s 커버리지=%.0f%% REPLAN=%d HOLD=%d, %d프레임" % (r["verdict"], r["covpct"], r["n_replan"], r["n_hold"], len(V["frames"])))
    print("saved:", os.path.join(out, "postmission.png"))
