"""보고서 그림 -> OUT/fig.   python3 -m ruh2.figures"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

for f in ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"):
    if os.path.exists(f):
        fm.fontManager.addfont(f)
plt.rcParams.update({"font.family": "NanumGothic", "axes.unicode_minus": False, "font.size": 10.5,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e3e6ea",
                     "grid.linewidth": 0.7, "axes.edgecolor": "#8a929c", "axes.titleweight": "bold", "axes.titlesize": 11.5,
                     "figure.dpi": 150, "savefig.bbox": "tight"})
C1, C2, C3, C4, INK, MUT = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#1d232b", "#6b7480"
from ruh2 import paths
paths.ensure()
B = json.load(open(paths.OUT / "battery.json"))


def save(fig, name):
    fig.savefig(paths.FIG / f"{name}.png", dpi=200); plt.close(fig)


# 1 cycle
s = B["cycle"]["series"]; t = np.array(s["t"]) / 3600
fig, ax = plt.subplots(4, 1, figsize=(7.2, 7.6), sharex=True)
ax[0].plot(t, s["V"], color=C1, lw=1.8); ax[0].set_ylabel("셀 전압 (V)")
ax[0].axhline(1.0, color=MUT, ls=":", lw=1); ax[0].text(t[-1], 1.005, "방전 종지 1.00 V", ha="right", va="bottom", color=MUT, fontsize=9)
ax[1].plot(t, s["I"], color=C2, lw=1.8); ax[1].set_ylabel("전류 (A)")
ax[2].plot(t, s["p"], color=C3, lw=1.8); ax[2].set_ylabel("H₂ 압력 (bar abs)")
ax2 = ax[2].twinx(); ax2.plot(t, np.array(s["s"]) * 100, color=INK, lw=1, ls="--"); ax2.set_ylabel("NiOOH 분율 (%)", color=INK); ax2.grid(False)
ax[3].plot(t, np.array(s["T"]) - 273.15, color=C4, lw=1.8); ax[3].set_ylabel("온도 (°C)"); ax[3].set_xlabel("시간 (h)")
for a, lab in zip(ax, "abcd"):
    a.text(-0.1, 1.02, f"({lab})", transform=a.transAxes, fontweight="bold")
ax[0].set_title("C/2 표준 사이클: 110 % 충전 → 1 h 휴지 → 1.0 V까지 방전 (모델)", loc="left")
save(fig, "f_cycle")

# 2 rate
fig, ax = plt.subplots(figsize=(6.4, 3.6))
for (cr, r), col in zip(B["rate"].items(), [C3, C1, C2, "#e87ba4"]):
    ax.plot(r["curve"]["q"], r["curve"]["V"], color=col, lw=1.8, label=f"{float(cr):g} C · {r['Qout']:.3f} Ah · 평균 {r['Vavg']:.3f} V")
ax.set_xlabel("방전 용량 (Ah)"); ax.set_ylabel("셀 전압 (V)"); ax.set_ylim(0.95, 1.4); ax.legend(frameon=False, fontsize=9)
ax.set_title("율 특성 (C/5 충전 110 % 후 방전, 25 °C)", loc="left"); save(fig, "f_rate")

# 3 self-discharge
fig, ax = plt.subplots(1, 2, figsize=(8.4, 3.4), sharey=True)
for a, (T, d) in zip(ax, B["selfdis"].items()):
    a.plot(d["t_h"], np.array(d["s_true"]) * 100, color=INK, lw=2.2, label="실제 NiOOH (모델 진값)")
    a.plot(d["t_h"], np.array(d["soc_p"]) * 100, color=C3, lw=1.4, ls="--", label="압력으로 읽은 SOC")
    a.plot(d["t_h"], np.array(d["soc_count"]) * 100, color=C2, lw=1.6, label="쿨롱 카운팅 SOC")
    a.set_title(f"{T} °C · 72 h 손실 {d['loss_72h']*100:.1f} %p", loc="left"); a.set_xlabel("휴지 시간 (h)")
ax[0].set_ylabel("SOC (%)"); ax[0].legend(frameon=False, fontsize=8.5, loc="lower left")
save(fig, "f_selfdis")

# 4 catalyst
fig, ax = plt.subplots(figsize=(6.4, 3.0))
names = list(B["catalyst"].keys()); ee = [B["catalyst"][n]["EE"] * 100 for n in names]; eta = [B["catalyst"][n]["eta_h2_mV_dis"] for n in names]
bars = ax.barh(names, ee, color=[C1, "#9085e9", MUT], height=0.55)
for b_, e_, h_ in zip(bars, ee, eta):
    ax.text(b_.get_width() + 0.3, b_.get_y() + b_.get_height() / 2, f"{e_:.1f} %  (H₂ 전극 η {h_:.1f} mV)", va="center", fontsize=9.5)
ax.set_xlim(60, 88); ax.set_xlabel("왕복 에너지 효율 (%) · C/2, 25 °C"); ax.invert_yaxis(); ax.grid(axis="y", visible=False)
ax.set_title("수소 전극 촉매 비교 (다른 조건 동일)", loc="left"); save(fig, "f_catalyst")

# 5 fault
fig, ax = plt.subplots(1, 3, figsize=(9.6, 3.2))
cols = [C3, C2, "#c73535"]; styles = [dict(lw=3.2, zorder=3), dict(lw=1.6, ls="--", zorder=2), dict(lw=1.4, zorder=1)]
for (k, d), col, st in zip(B["fault"].items(), cols, styles):
    lab = k + ("  → 0.9 V에서 래치" if d["tripped"] else "")
    ax[0].plot(d["t"], d["V"], color=col, label=lab, **st)
    ax[1].plot(d["t"], d["E_h2"], color=col, **st)
    ax[2].plot(d["t"], np.array(d["A_ru"]) * 100, color=col, **st)
ax[0].axhline(0.9, color=MUT, ls=":"); ax[0].set_ylabel("셀 전압 (V)"); ax[0].set_title("과방전 1C", loc="left")
ax[1].axhline(0.4, color="#c73535", ls=":"); ax[1].text(0.02, 0.43, "Ru 산화 개시 0.4 V", color="#c73535", fontsize=8.5); ax[1].set_ylabel("H₂ 전극 전위 (V vs RHE)"); ax[1].set_title("수소 전극 전위", loc="left")
ax[2].set_ylabel("Ru 활성 (%)"); ax[2].set_title("Ru 활성 잔존", loc="left")
for a in ax: a.set_xlabel("시간 (h)")
ax[0].legend(frameon=False, fontsize=8, loc="lower left"); save(fig, "f_fault")

# 6 overcharge
o = B["overcharge"]
fig, ax = plt.subplots(figsize=(6.4, 3.2)); ax.plot(o["t"], o["p"], color=C3, lw=1.8, label="H₂ 압력 (bar abs)")
ax.set_ylabel("압력 (bar abs)"); ax.set_xlabel("시간 (h)")
a2 = ax.twinx(); a2.plot(o["t"], o["T"], color=C4, lw=1.8, label="온도"); a2.set_ylabel("온도 (°C)"); a2.grid(False)
ax.plot(o["t"], np.array(o["f_oer"]) * 5, color=C2, lw=1.2, ls="--", label="O₂ 분율 ×5")
ax.legend(frameon=False, fontsize=9, loc="center right"); ax.set_title("과충전 1C · 2 h (종지 없음): O₂ 재결합으로 압력 포화, 열로 전환", loc="left")
save(fig, "f_overcharge")

# 7 EIS vs SOC
fig, ax = plt.subplots(figsize=(5.6, 4.0))
seq = ["#cfe0f6", "#8db3e6", "#5f95dc", "#2a78d6", "#123d73"]
for (sc, z), col in zip(B["eis"]["soc"].items(), seq):
    ax.plot(np.array(z["re"]) * 1e3, -np.array(z["im"]) * 1e3, "-o", ms=2.5, lw=1.5, color=col, label=f"SOC {float(sc)*100:.0f} %")
ax.set_xlabel("Re Z (mΩ)"); ax.set_ylabel("-Im Z (mΩ)"); ax.set_aspect("equal", adjustable="datalim"); ax.legend(frameon=False, fontsize=9)
ax.set_title("셀 EIS 모델 (10 mHz–10 kHz, 개방 상태)", loc="left"); save(fig, "f_eis")

# 8 pressure ladder
V = B["spec"]["VESSEL"]
fig, ax = plt.subplots(figsize=(6.4, 3.4))
lv = [("예충전 (방전 상태)", V["p_precharge_bar_abs"], C3), ("완충 25 °C", V["p_full_bar_abs_25C"], C3), ("최대 운전", B["spec"]["LIMITS"]["p_max_oper_bar_abs"], C4),
      ("HW 차단 (래치)", V["p_trip_bar_abs"], C2), ("릴리프 밸브", V["p_relief_bar"], C2), ("파열판", V["p_burst_disk_bar"], "#c73535"),
      ("설계 압력", V["p_design_bar"], INK), ("내압 시험 1.5×", V["p_proof_bar"], INK)]
for i, (n, p, c) in enumerate(lv):
    ax.barh(i, p, color=c, height=0.6); ax.text(p + 0.3, i, f"{p:.2f} bar" if p < 5 else f"{p:.1f} bar", va="center", fontsize=9.5)
ax.set_yticks(range(len(lv))); ax.set_yticklabels([n for n, _, _ in lv]); ax.invert_yaxis(); ax.set_xlabel("압력 (bar, 상대/절대 혼용 주의: 운전값은 abs)")
ax.set_xlim(0, 34); ax.grid(axis="y", visible=False); ax.set_title("압력 단계 (안전 계층)", loc="left"); save(fig, "f_pressure")

# 9 OCV & Nernst surface slice
from ruh2 import model as N
ss = np.linspace(0.02, 0.98, 200)
fig, ax = plt.subplots(figsize=(6.4, 3.2))
for p_, col in ((1.0, C3), (2.5, C1), (4.5, C2)):
    ax.plot(ss * 100, [N.ocv(x, p_, 298.15) for x in ss], color=col, lw=1.8, label=f"p(H₂) = {p_} bar")
ax.set_xlabel("NiOOH 분율 s (%)"); ax.set_ylabel("개방전압 (V)"); ax.legend(frameon=False, fontsize=9)
ax.set_title("OCV 모델: E = E° + 0.6·(RT/F)·ln[s/(1-s)] + (RT/2F)·ln p", loc="left"); save(fig, "f_ocv")


# ---------------- Ru vs Pt, countermeasures ----------------
RP = json.load(open(paths.OUT / "rupt.json"))
fig, ax = plt.subplots(1, 2, figsize=(9.6, 3.6))
for m_, col in (("Ru", C1), ("Pt", "#9085e9")):
    rr = RP["sweep"][m_]
    ax[0].plot([r["cost_usd"] for r in rr], [r["EE"] * 100 for r in rr], "-o", color=col, lw=2, ms=5, label=m_ + "/C")
    ax[1].plot([r["load"] for r in rr], [r["eta_2C_mV"] for r in rr], "-o", color=col, lw=2, ms=5, label=m_ + "/C")
    for r in rr:
        if r["load"] in (0.1, 0.5):
            ax[0].annotate(f"{r['load']} mg/cm²", (r["cost_usd"], r["EE"] * 100), textcoords="offset points", xytext=(6, -12 if m_ == "Pt" else 6), fontsize=8.5, color=col)
ax[0].set_xscale("log"); ax[0].set_xlabel("셀당 촉매 금속 비용 (USD, 2026-09 가격)"); ax[0].set_ylabel("왕복 에너지 효율 (%) · C/2")
ax[0].set_title("효율 대 촉매 비용", loc="left"); ax[0].legend(frameon=False)
ax[1].set_xscale("log"); ax[1].set_yscale("log"); ax[1].set_xlabel("담지량 (mg/cm²)"); ax[1].set_ylabel("2C 방전 H₂ 전극 과전압 (mV)")
ax[1].set_title("같은 담지량에서의 반응성", loc="left"); ax[1].legend(frameon=False)
from matplotlib.ticker import FuncFormatter
for a_ in (ax[0].xaxis, ax[1].xaxis, ax[1].yaxis):
    a_.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}")); a_.set_minor_formatter(FuncFormatter(lambda v, _: ""))
save(fig, "f_cost")

fig, ax = plt.subplots(figsize=(7.6, 3.4))
ox = RP["oxidation"]; y = range(len(ox))
cols_ = [("#c73535" if o["A_end"] < 0.5 else C3) for o in ox]
ax.barh(list(y), [o["A_end"] * 100 for o in ox], color=cols_, height=0.55)
for i, o in enumerate(ox):
    ax.text(max(o["A_end"] * 100, 0) + 1.5, i, f"Ru 활성 {o['A_end']*100:.0f} % · 최대 {o['E_max']:.2f} V · {o['stopped_by']}", va="center", fontsize=8.8)
ax.set_yticks(list(y)); ax.set_yticklabels([o["name"] for o in ox], fontsize=9); ax.invert_yaxis(); ax.set_xlim(0, 175)
ax.set_xlabel("과방전 1C 1.4 h 뒤 Ru 활성 잔존 (%)"); ax.grid(axis="y", visible=False); ax.set_title("Ru 산화 대책별 효과 (모델)", loc="left")
save(fig, "f_oxmethods")

fig, ax = plt.subplots(figsize=(7.6, 3.4))
sd_ = RP["selfdis"]; y = range(len(sd_))
ax.barh(list(y), [s_["loss_pct_of_Q"] for s_ in sd_], color=[MUT if i == 0 else ("#c73535" if "40" in s_["name"] else C3) for i, s_ in enumerate(sd_)], height=0.55)
for i, s_ in enumerate(sd_):
    ax.text(s_["loss_pct_of_Q"] + 0.6, i, f"{s_['loss_pct_of_Q']:.1f} %  (시작 {s_['p_start']:.2f} bar)", va="center", fontsize=8.8)
ax.set_yticks(list(y)); ax.set_yticklabels([s_["name"] for s_ in sd_], fontsize=9); ax.invert_yaxis(); ax.set_xlim(0, 52)
ax.set_xlabel("72 h 개방 보관 중 용량 손실 (정격 대비 %)"); ax.grid(axis="y", visible=False); ax.set_title("자가방전 대책별 효과 (모델, 가정 파라미터)", loc="left")
save(fig, "f_sdmethods")


# ---------------- DFT (본 작업 GPAW 결과, ruh2/data/dft.json) ----------------
D = json.load(open(paths.DATA / "dft.json"))["results"]
fig, ax = plt.subplots(figsize=(6.4, 3.0))
xs = [0, 1, 2]
for el, col in (("Ru", C1), ("Pt", "#9085e9")):
    g = D[el]["fcc"]["dG"]
    for x, yv in zip(xs, [0, g, 0]):
        ax.plot([x - 0.3, x + 0.3], [yv, yv], color=col, lw=3)
    ax.plot([0.3, 0.7], [0, g], color=col, ls=":"); ax.plot([1.3, 1.7], [g, 0], color=col, ls=":")
    ax.text(1.33, g, f"{el}({'0001' if el == 'Ru' else '111'}) {g:.2f} eV", color=col, va="center", fontsize=10)
ax.axhspan(-0.50, -0.25, xmin=0.36, xmax=0.64, color=C1, alpha=0.08)
ax.text(1, -0.52, "Ru 문헌 범위 -0.25~-0.50", ha="center", va="top", fontsize=8.5, color=C1)
ax.plot([0.7, 1.3], [-0.09, -0.09], color="#9085e9", lw=1, ls="--"); ax.text(0.68, -0.09, "Pt 문헌 -0.09", ha="right", va="center", fontsize=8.5, color="#9085e9")
ax.set_xticks(xs); ax.set_xticklabels(["H2O + e-", "H*", "1/2 H2"]); ax.set_ylabel("ΔG (eV), U = 0 V vs RHE"); ax.set_ylim(-0.62, 0.12)
ax.set_title("수소 흡착 자유에너지 (본 작업 GPAW PBE, 1/4 ML)", loc="left")
save(fig, "f_dft")
print("figures:", sorted(os.listdir(paths.FIG)))
