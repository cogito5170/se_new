"""보고서 그림. python3 figs.py spec|results"""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
from recon import paths  # noqa: E402
import json, math, sys, struct
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import spec
paths.ensure()
FIG = paths.FIG
RUNS = paths.RUNS; OUT = paths.ANALYSIS
for f in font_manager.findSystemFonts():
    if "NanumGothic.ttf" in f or "NanumGothic-Regular" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams.update({"font.family": "NanumGothic", "axes.unicode_minus": False, "font.size": 9.5, "axes.grid": True, "grid.alpha": .3,
                     "savefig.dpi": 170, "savefig.bbox": "tight"})
C = {"fixed": "#8b949e", "random": "#d29922", "frontier": "#58a6ff", "proposed": "#2ea043"}
NM = {"fixed": "고정 웨이포인트", "random": "무작위", "frontier": "프런티어", "proposed": "제안(J+fw)"}


def save(name):
    plt.savefig(FIG / name); plt.close()


def spec_figs():
    # 전력
    ks = list(spec.POWER); a = [spec.POWER[k][0] for k in ks]; p = [spec.POWER[k][1] for k in ks]
    fig, ax = plt.subplots(figsize=(8, 3.2)); y = np.arange(len(ks))
    ax.barh(y + .2, a, .4, label="평균 [A]", color="#2a78d6"); ax.barh(y - .2, p, .4, label="최대", color="#e8a33d")
    ax.set_yticks(y); ax.set_yticklabels([k.split("(")[0] for k in ks]); ax.set_xlabel("W"); ax.invert_yaxis(); ax.legend()
    ax.set_title(f"전력 예산: 평균 {spec.P_AVG:.1f} W · 최대 {spec.P_PEAK:.0f} W · 가용 {spec.E_WH:.0f} Wh → {spec.RUNTIME_H:.2f} h (가정 부하)")
    save("power_budget.png")
    # 데이터율
    d = {"LiDAR 20만 점/s × 26 B": spec.DATA["lidar_Bps"], "카메라 H.264 720p30": spec.DATA["cam_Bps"], "IMU 1 kHz": spec.DATA["imu_Bps"],
         "엔코더 100 Hz": spec.DATA["enc_Bps"], "GNSS 10 Hz": spec.DATA["gnss_Bps"]}
    fig, ax = plt.subplots(figsize=(8, 2.6)); ax.barh(list(d), [v / 1e3 for v in d.values()], color="#6e40c9"); ax.set_xscale("log"); ax.invert_yaxis()
    for i, v in enumerate(d.values()):
        ax.text(v / 1e3 * 1.1, i, f"{v / 1e3:,.1f} kB/s", va="center", fontsize=8.5)
    ax.set_xlabel("kB/s (로그)"); ax.set_title(f"원시 데이터율 합 {spec.DATA['raw_Bps'] / 1e6:.2f} MB/s → 512 GB 에 {512e9 / spec.DATA['raw_Bps'] / 3600:.0f} h"); save("data_budget.png")
    # LiDAR 장착
    M = spec.MECH; h = M["lidar_h"]
    fig, axs = plt.subplots(1, 2, figsize=(9, 2.8), sharey=True)
    for ax, (nm, lo, hi) in zip(axs, (("바로 세움 -7..+52°", -7, 52), ("뒤집음 -52..+7°", -52, 7))):
        ax.fill_between([-0.5, 12], -0.2, 0, color="#b09a72")
        for e in np.linspace(lo, hi, 14):
            r = np.radians(e); L = 12
            if e < 0:
                L = min(12, h / math.tan(-r) / math.cos(r) if math.tan(-r) > 0 else 12)
            ax.plot([0, L * math.cos(r)], [h, h + L * math.sin(r)], color="#2a78d6", lw=.7)
        br = h / math.tan(math.radians(-lo if lo < 0 else 7)) if nm.startswith("뒤") else h / math.tan(math.radians(7))
        ax.axvspan(0, br, ymin=0, ymax=.15, color="#e8a33d", alpha=.6); ax.text(br, 0.1, f" 사각 {br:.2f} m", fontsize=9)
        ax.plot([0], [h], "ks"); ax.set_xlim(-0.5, 8); ax.set_ylim(-0.2, 3); ax.set_title(nm); ax.set_xlabel("m")
    axs[0].set_ylabel("m"); save("lidar_mount.png")
    # 잡음 모델
    fig, axs = plt.subplots(1, 3, figsize=(10, 2.8))
    r = np.linspace(0.3, 12, 100); sa = math.radians(0.2)
    axs[0].plot(r, np.sqrt(0.02 ** 2 + (r * sa) ** 2 + 0.01 ** 2) * 100, label="한 프레임 σ_h (평지)")
    axs[0].plot(r, np.sqrt(0.02 ** 2 / 4 + (r * sa) ** 2 + 0.01 ** 2 + (0.3 * r * math.radians(0.3)) ** 2) * 100, label="기울기 0.3·자세 σ 포함")
    axs[0].set_xlabel("거리 m"); axs[0].set_ylabel("cm"); axs[0].set_title("셀 고도 측정 σ (지도 식)"); axs[0].legend(fontsize=7.5)
    rng = np.random.default_rng(0); t = np.arange(0, 600, 0.02); b = np.cumsum(math.radians(0.002) * math.sqrt(0.02) * rng.standard_normal(len(t)))
    axs[1].plot(t, np.degrees(b) * 3600, lw=.8); axs[1].set_xlabel("s"); axs[1].set_ylabel("°/h"); axs[1].set_title("자이로 편향 랜덤워크 (모델)")
    d = np.linspace(0, 0.002, 400); q = np.floor(d / (2 * math.pi * 0.06 / 3200)) * (2 * math.pi * 0.06 / 3200)
    axs[2].plot(d * 1000, (d - q) * 1000); axs[2].set_xlabel("이동 mm"); axs[2].set_ylabel("양자화 오차 mm"); axs[2].set_title(f"엔코더 {spec.DRIVE['dist_per_tick_mm']:.3f} mm/tick")
    plt.tight_layout(); save("noise_models.png")
    # 결정 구조 (고정 크기 상자, 화살표는 선으로 — 나눔 글꼴에 → 글리프가 없다)
    from matplotlib.patches import FancyBboxPatch
    fig, ax = plt.subplots(figsize=(12, 4.6)); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 4.6)
    top = [("센서 원시 데이터", "LiDAR · IMU · 엔코더\n카메라 · GNSS", "#dbe9f7"), ("상태추정 (Jetson)", "EKF (x,y,θ,b_g)\n+ LIO + 슬립 추정", "#dbe9f7"),
           ("증거층 (Jetson)", "건강 5 · 슬립 · 기울기 · 위험\n후보 J: 탐사·재방문·관측", "#e8f3e0"),
           ("fw C 커널 (MCU 10 Hz)", "guard - BT 우선순위\n- precondition+효용 중재\n- 안전필터", "#fde7c8"),
           ("행동 9", "EXPLORE · OBSERVE · REVISIT\nRETURN · AVOID · RELOCALIZE\nSAFE_STOP · EMERGENCY · HOLD", "#f7d6d6")]
    bot = [("하드웨어 안전", "E-stop · 무선킬 · 워치독\n코일 차단 (SW 를 거치지 않음)", "#f7d6d6"), ("구동기", "MDD20A ×2 - 37D 모터 ×4\n접촉기 K1", "#e8e0f7"),
           ("제어기 (MCU 50 Hz)", "바퀴 속도 PID\n+ 역기전력 앞먹임", "#e8e0f7"), ("유도 (Jetson 1-10 Hz)", "Dijkstra 비용지도 + 순수추종\n기동 잠금(후진·정지관측)", "#e8e0f7")]
    def bx(x, y, t, sub, c):
        ax.add_patch(FancyBboxPatch((x, y), 1.8, 1.25, boxstyle="round,pad=0.04", fc=c, ec="#444"))
        ax.text(x + .9, y + 1.02, t, ha="center", va="center", fontsize=9, fontweight="bold")
        ax.text(x + .9, y + .48, sub, ha="center", va="center", fontsize=7.8, linespacing=1.35)
    for k, (t, sub, c) in enumerate(top):
        bx(0.05 + k * 2.0, 2.95, t, sub, c)
        if k:
            ax.annotate("", (0.05 + k * 2.0, 3.57), (0.05 + k * 2.0 - 0.2, 3.57), arrowprops=dict(arrowstyle="-|>", lw=1.3, color="#333"))
    for k, (t, sub, c) in enumerate(bot):
        bx(0.05 + k * 2.2 + 1.2, 0.55, t, sub, c)
        if k == 1:   # 안전이 구동기를 끊는다 (방향 반대, 빨강)
            ax.annotate("", (0.05 + k * 2.2 + 1.2, 1.17), (0.05 + (k - 1) * 2.2 + 1.2 + 1.8, 1.17), arrowprops=dict(arrowstyle="-|>", lw=1.6, color="#c73535"))
        elif k:
            ax.annotate("", (0.05 + (k - 1) * 2.2 + 1.2 + 1.8, 1.17), (0.05 + k * 2.2 + 1.2, 1.17), arrowprops=dict(arrowstyle="-|>", lw=1.3, color="#333"))
    ax.annotate("", (0.05 + 3 * 2.2 + 1.2 + 0.9, 1.84), (8.95, 2.95), arrowprops=dict(arrowstyle="-|>", lw=1.3, color="#333"))
    ax.text(5, 4.45, "결정 executive: 추정 - 증거 - guard - BT - 효용 중재 - 안전감독 - 유도 - 제어 - 구동  (유도·제어·구동을 나눈다)", ha="center", fontsize=10.5)
    ax.text(0.1, 0.12, "안전 경로는 소프트웨어를 거치지 않는다: E-stop·무선킬·MCU MOTOR_EN·워치독 중 하나라도 끊기면 K1 코일이 풀려 모터 버스만 끊긴다(계산·기록은 산다).", fontsize=8.2, color="#8a1f1f")
    save("decision_arch.png")


def load(id_):
    return json.loads((RUNS / id_ / "meta.json").read_text())


def frames(id_):
    return json.loads((RUNS / id_ / "frames.json").read_text())


def snaps_last(id_):
    b = (RUNS / id_ / "snaps.bin").read_bytes(); n, k = struct.unpack("<ii", b[:8]); o = 8; last = None
    for _ in range(k):
        o += 4; h = np.frombuffer(b[o:o + n * n * 2], np.int16).reshape(n, n) / 100; o += n * n * 2
        q = np.frombuffer(b[o:o + n * n], np.uint8).reshape(n, n); o += n * n; last = (h, 0.005 * 2 ** (q / 32))
    return last


def results_figs():
    # 불확실도 지도 최종
    sel = [i for i in ("T01", "T06", "T08", "P09") if (RUNS / i / "meta.json").exists()]
    fig, axs = plt.subplots(1, len(sel), figsize=(3.1 * len(sel), 3.2))
    for ax, i in zip(np.atleast_1d(axs), sel):
        h, s = snaps_last(i); s = np.where(s > 0.29, np.nan, s)
        im = ax.imshow(s.T * 100, origin="lower", extent=(0, 30, 0, 30), cmap="turbo", vmin=1, vmax=15)
        F = frames(i); tr = np.array([f["tp"][:2] for f in F]); ax.plot(tr[:, 0], tr[:, 1], "w-", lw=.8)
        k = load(i)["kpi"]; ax.set_title(f"{i}  커버리지 {k['coverage'] * 100:.0f}%", fontsize=9); ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=axs, shrink=.8, label="셀 σ (cm) · 흰 선 = 참 궤적 · 빈칸 = 미지"); save("unc_maps.png")
    # 시간에 따른 커버리지 (기준선 기록판)
    fig, ax = plt.subplots(figsize=(7, 3))
    for i, m in (("B01", "fixed"), ("B02", "random"), ("B03", "frontier"), ("B04", "proposed")):
        if not (RUNS / i / "frames.json").exists():
            continue
        F = frames(i); t = [f["t"] for f in F if f["kpi"]]; c = [f["kpi"]["coverage"] * 100 for f in F if f["kpi"]]
        ax.plot(t, c, color=C[m], label=NM[m])
    ax.set_xlabel("s"); ax.set_ylabel("커버리지 % (σ<5 cm)"); ax.legend(); ax.set_title("같은 세계·같은 시드 (시드 0) — 커버리지 곡선"); save("baseline_curves.png")


def mc_figs():
    R = json.loads((OUT / "mc.json").read_text())
    by = {}
    for r in R:
        by.setdefault(r["method"], []).append(r)
    ms = [m for m in ("fixed", "random", "frontier", "proposed") if m in by]
    fig, axs = plt.subplots(1, 5, figsize=(12, 2.8))
    for ax, (key, lab, sc) in zip(axs, (("coverage", "커버리지 %", 100), ("aoi_cov", "관심구역 σ≤2cm %", 100), ("dist_m", "주행 m", 1),
                                         ("info_per_Wh", "정보 kbit/Wh", 1), ("collisions", "충돌 수", 1))):
        vals = [[(r[key] or 0) * sc for r in by[m]] for m in ms]
        ax.bar(range(len(ms)), [np.mean(v) for v in vals], yerr=[np.std(v) for v in vals], color=[C[m] for m in ms], capsize=3)
        for k, v in enumerate(vals):
            ax.plot([k] * len(v), v, "k.", ms=3)
        ax.set_xticks(range(len(ms))); ax.set_xticklabels([NM[m] for m in ms], rotation=30, fontsize=8); ax.set_title(lab, fontsize=9)
    plt.suptitle(f"기준선 비교 몬테카를로: 시드 {len(by[ms[0]])}개 × 방법 {len(ms)} · 240 s · 같은 안전층 (막대 = 평균 ± 표준편차, 점 = 시드)", fontsize=9.5)
    plt.tight_layout(); save("mc_bars.png")
    fig, ax = plt.subplots(figsize=(7, 3))
    for m in ms:
        T = np.arange(0, 241, 8); Y = []
        for r in by[m]:
            c = np.array(r["curve"]); Y.append(np.interp(T, c[:, 0], c[:, 1] * 100))
        Y = np.array(Y); ax.plot(T, Y.mean(0), color=C[m], label=NM[m]); ax.fill_between(T, Y.min(0), Y.max(0), color=C[m], alpha=.15)
    ax.set_xlabel("s"); ax.set_ylabel("커버리지 %"); ax.legend(fontsize=8); ax.set_title("커버리지 곡선 (선 = 평균, 띠 = 최소~최대)"); save("mc_curves.png")
    return by


def filter_figs():
    R = json.loads((OUT / "filters.json").read_text()); E = np.load(OUT / "filters_err_seed0.npz"); tr = np.load(OUT / "filters_traj_seed0.npy")
    ks = [("odom", "F1 엔코더만"), ("odom_gyro", "F2 +자이로"), ("ekf_lio", "F3 EKF+LIO"), ("proposed", "F4 제안")]
    fig, axs = plt.subplots(1, 4, figsize=(12, 3.3))
    for ax, (k, nm) in zip(axs, ks):
        im = ax.imshow(np.abs(E[k]).T * 100, origin="lower", extent=(0, 30, 0, 30), cmap="magma", vmin=0, vmax=30)
        ax.contour(np.arange(300) * .1, np.arange(300) * .1, (E["kind"] == 4).T, levels=[.5], colors="c", linewidths=.8)
        ax.plot(tr[:, 0], tr[:, 1], "w-", lw=.6); ax.set_title(f"{nm}\n지도 RMSE {np.mean([r[k]['map_rmse_m'] for r in R]) * 100:.1f} cm (3시드)", fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=axs, shrink=.8, label="|고도 오차| cm · 청록 = 진흙(슬립 0.35)"); save("filters_maps.png")
    fig, axs = plt.subplots(1, 3, figsize=(10, 2.6))
    for ax, (key, lab, sc) in zip(axs, (("final_err_m", "최종 위치 오차 m", 1), ("yaw_err_deg", "최종 요 오차 °", 1), ("ghost_cells", "유령 셀 (|오차|>15 cm)", 1))):
        v = [[r[k][key] * sc for r in R] for k, _ in ks]
        ax.bar(range(4), [np.mean(x) for x in v], yerr=[np.std(x) for x in v], color=["#8b949e", "#d29922", "#58a6ff", "#2ea043"], capsize=3)
        ax.set_xticks(range(4)); ax.set_xticklabels([n for _, n in ks], rotation=20, fontsize=8); ax.set_title(lab, fontsize=9)
        if key == "final_err_m":
            ax.set_yscale("log")
    plt.tight_layout(); save("filters_bars.png")
    return R


if __name__ == "__main__":
    w = sys.argv[1]
    if w == "spec":
        spec_figs()
    elif w == "results":
        results_figs()
    elif w == "mc":
        mc_figs()
    elif w == "filters":
        filter_figs()
    print("ok", w)
