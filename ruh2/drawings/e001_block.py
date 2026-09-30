from common import *
from matplotlib.patches import FancyArrowPatch

fig, ax = sheet("RUH2-E-001", "시스템 블록도 / System Block Diagram")
C = dict(pwr="#fde9d9", stage="#e3eefb", sens="#e6f4e6", safe="#fbe3e3", mcu="#efe6fa", iso="#f2f2f2", cell="#fff7d6")

def box(x0, y0, x1, y1, title, lines=(), fc="white", fs=10.5, lfs=8.6, ec="k"):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1.3, zorder=2))
    ax.text((x0 + x1) / 2, y1 - 0.1, title, ha="center", va="top", fontsize=fs, fontweight="bold", zorder=3)
    for i, l in enumerate(lines):
        ax.text((x0 + x1) / 2, y1 - 0.42 - i * 0.2, l, ha="center", va="top", fontsize=lfs, zorder=3)

def arrow(p, q, lab=None, where=0.5, off=(0, 0.1), color="k", lw=1.4, both=False, ha="center", va="bottom", fs=8.2, style="-|>"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=("<|-|>" if both else style), mutation_scale=13,
                                 color=color, lw=lw, zorder=4, shrinkA=0, shrinkB=0))
    if lab:
        x = p[0] + (q[0] - p[0]) * where + off[0]; y = p[1] + (q[1] - p[1]) * where + off[1]
        ax.text(x, y, lab, ha=ha, va=va, fontsize=fs, color=color, zorder=5,
                bbox=dict(fc="white", ec="none", pad=0.6))

def poly(pts, color="k", lw=1.4, arrow_end=True, ls="-"):
    xs, ys = zip(*pts)
    ax.plot(xs[:-1] if arrow_end else xs, ys[:-1] if arrow_end else ys, color=color, lw=lw, ls=ls, zorder=4)
    if arrow_end:
        ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=13, color=color,
                                     lw=lw, zorder=4, shrinkA=0, shrinkB=0))

ax.text(0.55, 11.2, "RUH2-E-001  시스템 블록도 — RuH2-BMS rev A 와 RuH2-P1 셀 (Ni-H2, Ru/C 수소극)",
        fontsize=15, fontweight="bold", va="top")
ax.text(0.55, 10.82, "굵은 선 = 전력 경로 (power path)   가는 선 = 신호 (signal)   빨간 선 = 하드웨어 안전 경로 (MCU 비의존)",
        fontsize=9.5, va="top", color="#333")

# ---------------- power row
yb, yt = 9.05, 10.25
box(0.6, yb, 2.2, yt, "J7  12 V IN", [BMS["supply"], "DC jack / 2-pin"], C["pwr"])
box(2.8, yb, 5.3, yt, "입력 보호 Input Protection", ["F1 fuse 3 A", "Q1 PMOS reverse-polarity", "D1 TVS SMBJ15A"], C["pwr"])
box(5.9, yb, 8.1, yt, "U1 Buck 5 V", ["TPS62130-class", "+5V (sensors, op-amps)"], C["pwr"])
box(8.7, yb, 10.9, yt, "U2 LDO 3.3 V", ["TLV75533-class", "+3V3_A (analog/MCU)"], C["pwr"])
box(11.5, yb, 13.7, yt, "U3 Buck 3.3 V PWR", ["TPS62133-class, 3 A", "VPWR 3.3 V (source stage)"], C["pwr"])
arrow((2.2, 9.65), (2.8, 9.65), lw=2.6)
arrow((5.3, 9.65), (5.9, 9.65), "+12V_P", off=(0, 0.08), lw=2.6)
arrow((8.1, 9.65), (8.7, 9.65), "+5V", lw=2.2)
poly([(4.05, 9.05), (4.05, 8.75), (12.6, 8.75), (12.6, 9.05)], lw=2.2)
ax.text(12.0, 8.79, "+12V_P", fontsize=8.2, va="bottom", ha="center", bbox=dict(fc="white", ec="none", pad=0.5), zorder=5)

# ---------------- power stage row
box(2.6, 6.95, 5.0, 8.35, "U5 Setpoint Σ", ["V_SET = DAC1 + DAC2 - V_MID", "DAC1: DC 설정값", "DAC2: EIS sine 20 mA pk",
                                             "0.1 Hz – 5 kHz"], C["stage"], lfs=8.2)
box(5.6, 7.65, 8.3, 8.5, "충전 CC Source (charge)", ["U6A servo + Q3 PMOS", f"Rs1 {RS_CHG*1e3:.0f} mΩ + U7 INA181A1"], C["stage"], lfs=8.2)
box(5.6, 6.55, 8.3, 7.45, "방전 CC Sink (discharge)", ["U6B servo + Q4 NMOS", f"Rs2 {RS_DIS*1e3:.0f} mΩ, low side"], C["stage"], lfs=8.2)
arrow((5.0, 8.2), (5.6, 8.2), "V_SET", off=(0, 0.05), fs=7.6)
arrow((5.0, 7.2), (5.6, 7.2), "V_SET/20", off=(0, 0.05), fs=7.2)
poly([(12.6, 8.75), (12.6, 8.62), (8.9, 8.62), (8.9, 8.3), (8.3, 8.3)], lw=2.2)
ax.text(10.7, 8.58, "VPWR 3.3 V", fontsize=8.2, ha="center", va="top", zorder=5, bbox=dict(fc="white", ec="none", pad=0.5))
ax.plot([8.3, 8.75], [7.9, 7.9], "k", lw=2.6, zorder=4); ax.plot([8.3, 8.75], [6.85, 6.85], "k", lw=2.6, zorder=4)
ax.plot([8.75, 8.75], [6.85, 7.9], "k", lw=2.6, zorder=4)
ax.plot(8.75, 7.4, "ko", ms=6, zorder=5)
arrow((8.75, 7.4), (9.5, 7.4), both=True, lw=2.6)
ax.text(8.83, 7.3, "VSTAGE", fontsize=7.8, va="top", zorder=5, bbox=dict(fc="white", ec="none", pad=0.3))
box(9.5, 6.6, 11.9, 8.15, "Disconnect", ["Q5/Q6 back-to-back NMOS", "gate: +12V_P pull-up", "Q7/Q8 pull-down (trip / MCU)"], C["safe"], lfs=8.1)
box(12.3, 7.05, 13.5, 7.75, "R_SH 10 mΩ", ["shunt, 4-terminal"], C["stage"], fs=9.5, lfs=7.8)
arrow((11.9, 7.4), (12.3, 7.4), both=True, lw=2.6)
arrow((13.5, 7.4), (14.3, 7.4), "FORCE+", off=(0, 0.08), both=True, lw=2.6, fs=7.4)

# ---------------- vessel / cell column
ax.add_patch(FancyBboxPatch((14.1, 3.0), 2.0, 5.3, boxstyle="round,pad=0.02,rounding_size=0.1", fc=C["cell"], ec="k", lw=1.6, zorder=1))
ax.text(15.1, 8.22, "시험 용기 Test Vessel", ha="center", va="top", fontsize=10, fontweight="bold")
ax.text(15.1, 7.95, "316L, 설계 20 bar", ha="center", va="top", fontsize=8)
box(14.3, 6.4, 15.9, 7.7, "J1 Cell RuH2-P1", [f"{CELL['Q_Ah']:.0f} Ah Ni-H2", "4-wire Kelvin", "F+ / F- / S+ / S-"], "white", fs=9, lfs=7.8)
box(14.3, 5.35, 15.9, 6.15, "J2 Pressure", ["0–10 bar abs", "0.5–4.5 V"], "white", fs=9, lfs=7.8)
box(14.3, 4.3, 15.9, 5.1, "J3 NTC ×2", ["10k B3950", "wall / ambient"], "white", fs=9, lfs=7.8)
box(14.3, 3.2, 15.9, 4.05, "J4 H2 sensor", ["TGS2616-C00 class", "(enclosure air)"], "white", fs=9, lfs=7.8)

# ---------------- signal conditioning column (output net named in each box)
cond = [("U8 INA240A2 (G=50)", r"$\rightarrow$ I_MON", 6.3), ("P: 10k/20k ÷ + RC", r"$\rightarrow$ P_MON", 5.75),
        ("U9 OPA2333 diff amp", r"$\rightarrow$ V_CELL", 5.2), ("NTC: 10k to 3.3 V ÷ ×2", r"$\rightarrow$ T_VESSEL, T_AMB", 4.65),
        ("H2: heater 5 V + R_L", r"$\rightarrow$ H2_MON", 3.62)]
for t, o, yc in cond:
    ax.add_patch(FancyBboxPatch((11.0, yc - 0.22), 2.6, 0.44, boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc=C["sens"], ec="k", lw=1.2, zorder=2))
    ax.text(11.08, yc, t, fontsize=8.4, fontweight="bold", va="center", zorder=3)
    ax.text(13.55, yc, o, fontsize=7.4, va="center", ha="right", color="#1f5fa8", zorder=3)
poly([(12.3, 7.05), (12.3, 6.52)], lw=1.2)
ax.text(12.36, 6.8, "shunt Kelvin", fontsize=7.4, va="center")
poly([(14.3, 6.55), (13.95, 6.55), (13.95, 5.2), (13.6, 5.2)], lw=1.2)
ax.text(14.0, 6.28, "S+/S-", fontsize=7.0, va="center", zorder=6, bbox=dict(fc="#fff7d6", ec="none", pad=0.2))
arrow((14.3, 5.75), (13.6, 5.75), lw=1.2)
arrow((14.3, 4.65), (13.6, 4.65), lw=1.2)
arrow((14.3, 3.62), (13.6, 3.62), lw=1.2)
ax.text(12.3, 3.1, "REF 1.65 V · RC 100 Ω/100 nF anti-alias", fontsize=7.4, ha="center", va="center", color="#333")

# ---------------- analog bus
for _, _, y in cond:
    ax.plot([10.55, 11.0], [y, y], color="#1f5fa8", lw=1.2, zorder=4)
ax.plot([10.55, 10.55], [3.62, 6.3], color="#1f5fa8", lw=3, zorder=4)
poly([(10.55, 6.3), (10.55, 6.12), (4.95, 6.12), (4.95, 5.5), (4.6, 5.5)], color="#1f5fa8", lw=3)
ax.text(7.9, 6.16, "ANALOG BUS → ADC1_IN1…IN9", fontsize=8.0, color="#1f5fa8", ha="center", va="bottom",
        bbox=dict(fc="white", ec="none", pad=0.4), zorder=5)
ax.plot([5.3, 5.3], [6.12, 3.59], color="#1f5fa8", lw=1.4, zorder=4)
ax.plot(5.3, 6.12, "o", color="#1f5fa8", ms=5, zorder=5)

# ---------------- safety interlock
ax.add_patch(FancyBboxPatch((5.6, 2.55), 4.6, 3.1, boxstyle="round,pad=0.02,rounding_size=0.1", fc=C["safe"], ec="#b00000", lw=1.6, zorder=1))
ax.text(7.9, 5.58, "하드웨어 인터록 Safety Interlock", ha="center", va="top", fontsize=10.5, fontweight="bold", color="#8a0000")
rows = [("P_MON > th", f"과압 {VESSEL['p_trip_bar_abs']:.1f} bar abs"),
        ("T_VESSEL < th", f"과온 {LIMITS['T_trip_C']} °C"),
        ("V_CELL < th", f"저전압 {CELL['V_hw_cutoff']:.2f} V"),
        ("H2_MON > th", f"H2 ≥ {LIMITS['h2_trip_vol_pct']:.1f} vol%")]
ax.text(6.95, 5.25, "U10/U11 TLV3202 ×2", fontsize=8.4, ha="center", va="top", fontweight="bold")
for i, (a, b) in enumerate(rows):
    y = 4.85 - i * 0.42
    ax.add_patch(Rectangle((5.75, y - 0.17), 2.4, 0.34, fc="white", ec="#b00000", lw=0.9, zorder=3))
    ax.text(5.82, y, a, fontsize=7.6, va="center", zorder=4)
    ax.text(8.1, y, b, fontsize=7.6, va="center", ha="right", zorder=4, color="#8a0000")
    ax.plot([8.15, 8.45], [y, y], color="#b00000", lw=1.2, zorder=4)
    arrow((5.3, y), (5.75, y), color="#1f5fa8", lw=1.1)
ax.plot([8.45, 8.45], [3.59, 4.85], color="#b00000", lw=1.2, zorder=4)
ax.text(8.5, 5.1, "diode wired-OR (FAULT_N)", fontsize=7.2, color="#8a0000", va="center")
arrow((8.45, 4.2), (8.7, 4.2), color="#b00000", lw=1.2)
box(8.7, 3.75, 10.05, 4.9, "U12 Latch", ["74LVC1G74", "/PRE = FAULT_N", "Q = TRIP"], "white", fs=9, lfs=7.4, ec="#b00000")
poly([(9.8, 4.9), (9.8, 5.9), (10.25, 5.9), (10.25, 6.6)], color="#b00000", lw=1.8)
ax.text(9.72, 5.75, "TRIP", fontsize=8, color="#b00000", ha="right", va="center",
        bbox=dict(fc="white", ec="none", pad=0.3), zorder=6)
box(8.7, 2.7, 10.05, 3.45, "SW1 RESET", ["수동 재무장 /CLR"], "white", fs=8.6, lfs=7.4, ec="#b00000")
arrow((9.375, 3.45), (9.375, 3.75), color="#b00000", lw=1.2)
ax.text(5.75, 2.95, "MCU 는 TRIP 을 읽기만 함 — 해제 불가\nMCU reads TRIP_STAT, cannot clear", fontsize=7.4, va="center", color="#8a0000")

# ---------------- MCU
box(1.2, 2.55, 4.6, 5.9, "U4 STM32G474RE", ["Cortex-M4F 170 MHz", "ADC1 12-bit ×8 ch", "DAC1_OUT1/OUT2 (PA4/PA5)",
                                             "GPIO: CHG_EN, DIS_EN,", "MCU_DISC_OFF, TRIP_STAT", "USB FS (PA11/PA12)", "SWD (J6)",
                                             "firmware lock-in (EIS)"], C["mcu"], fs=11, lfs=8.6)
arrow((3.0, 5.9), (3.0, 6.95), "DAC1_OUT1/2", where=0.5, off=(-0.06, 0), ha="right", va="center", color="#1f5fa8", lw=1.3, fs=7.4)
poly([(4.1, 5.9), (4.1, 6.8), (5.6, 6.8)], color="#1f5fa8", lw=1.1)
poly([(5.3, 6.8), (5.3, 7.9), (5.6, 7.9)], color="#1f5fa8", lw=1.1)
ax.plot(5.3, 6.8, "o", color="#1f5fa8", ms=4, zorder=5)
ax.text(4.16, 6.5, "CHG_EN\nDIS_EN", fontsize=7.0, color="#1f5fa8", va="center")
poly([(4.4, 5.9), (4.4, 6.3), (10.75, 6.3), (10.75, 6.6)], color="#555", lw=1.1)
ax.text(9.2, 6.34, "MCU_DISC_OFF (열기만 가능)", fontsize=7.0, color="#444", va="bottom", ha="center",
        bbox=dict(fc="white", ec="none", pad=0.2), zorder=5)
poly([(8.7, 4.05), (8.55, 4.05), (8.55, 2.3), (4.2, 2.3), (4.2, 2.55)], color="#b00000", lw=1.0)
ax.text(6.9, 2.34, "TRIP_STAT (read only)", fontsize=7.4, color="#8a0000", va="bottom", ha="center")

# ---------------- USB isolation
ax.plot([0.5, 5.4], [2.05, 2.05], color="#666", lw=1.4, ls=(0, (6, 3)))
ax.text(5.45, 2.05, "절연 경계 isolation barrier", fontsize=7.8, va="center", color="#444")
box(1.2, 0.55, 3.4, 1.85, "U13 ADuM3160", ["USB 2.0 FS isolator", "+ isolated 5 V (VBUS)"], C["iso"], fs=9.5, lfs=7.8)
box(4.0, 0.55, 5.6, 1.85, "J5 USB / PC", ["USB-CDC", "virtual COM"], C["iso"], fs=9.5, lfs=7.8)
arrow((2.3, 2.55), (2.3, 1.85), "USB_DP/DM", where=0.5, off=(0.08, 0), ha="left", va="center", both=True, fs=7.6)
arrow((3.4, 1.2), (4.0, 1.2), both=True)

# notes
ax.text(6.0, 1.8, "주 Notes", fontsize=9, fontweight="bold", va="top")
notes = [f"1. 전류: ±{I_FS:.1f} A FS, LSB {I_LSB_mA:.2f} mA",
         "    (INA240A2 G=50, 10 mΩ, REF 1.65 V)",
         "2. 트립 = 비교기 + 래치만으로 동작 (펌웨어 무관).",
         "    전원 투입 시 래치 = TRIP (POR) → SW1 로 재무장",
         "3. EIS 는 |I_DC| ≥ 20 mA 에서만 (단방향 단)",
         "4. 부품명은 class 표기. 핀 배정은 E-004"]
for i, n in enumerate(notes):
    ax.text(6.0, 1.52 - i * 0.2, n, fontsize=7.6, va="top")
save(fig, "E-001_block")
