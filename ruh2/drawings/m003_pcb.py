from mech import *
from matplotlib.patches import Circle, FancyBboxPatch

fig, fr = sheet("RUH2-M-003", "PCB 배치 계획 / PCB Placement Plan", scale="2:1 (A3)")
ax = mm_axes(fig)
ax.text(14, 285, "RUH2-M-003  RuH2-BMS rev A — PCB 배치 계획 (윗면, 100 × 80 mm, 4층 제안)", fontsize=15, fontweight="bold", va="top")
S, ox, oy = 2.0, 42.0, 78.0          # 2:1
P = lambda x, y: (ox + x * S, oy + y * S)
BW, BH = 100.0, 80.0

def zone(x0, y0, x1, y1, fc, ec, title, sub=""):
    a, b = P(x0, y0); c, d = P(x1, y1)
    ax.add_patch(FancyBboxPatch((a, b), c - a, d - b, boxstyle="round,pad=0,rounding_size=2", fc=fc, ec=ec, lw=1.2,
                                ls=(0, (5, 2)), alpha=0.55, zorder=2))
    dx = 16 if x0 == 0 and y1 == 80 else 2
    ax.text(a + dx, d - 2, title, fontsize=8.8, fontweight="bold", color=ec, va="top", zorder=8)
    if sub:
        ax.text(a + dx, d - 7.2, sub, fontsize=6.8, color=ec, va="top", zorder=8)

def part(x, y, w, h, ref, val="", fc="white", rot=False, fs=6.8):
    a, b = P(x - w / 2, y - h / 2)
    ax.add_patch(Rct((a, b), w * S, h * S, fc=fc, ec="k", lw=0.8, zorder=5))
    cxp, cyp = P(x, y)
    txt = ref if not val else f"{ref}\n{val}"
    ax.text(cxp, cyp, txt, ha="center", va="center", fontsize=fs, zorder=6, linespacing=1.0,
            rotation=90 if rot else 0)

def conn(x, y, w, h, ref, lab, side):
    part(x, y, w, h, ref, "", fc="#ffe9a8", fs=7.4)
    cxp, cyp = P(x, y)
    off = {"left": (-(w / 2 * S + 1.5), 0, "right", "center"), "right": (w / 2 * S + 1.5, 0, "left", "center"),
           "bottom": (0, -(h / 2 * S + 1.5), "center", "top"), "top": (0, h / 2 * S + 1.5, "center", "bottom")}[side]
    ax.text(cxp + off[0], cyp + off[1], lab, ha=off[2], va=off[3], fontsize=7.0, zorder=9, fontweight="bold",
            color="#6b4a00", bbox=dict(fc="white", ec="none", pad=0.3))

# board
a, b = P(0, 0); c, d = P(BW, BH)
ax.add_patch(Rct((a, b), c - a, d - b, fc="#2f6b3b", ec="k", lw=1.6, zorder=1, alpha=0.12))
ax.add_patch(Rct((a, b), c - a, d - b, fill=False, ec="k", lw=1.6, zorder=9))
for hx, hy in ((3.5, 3.5), (BW - 3.5, 3.5), (3.5, BH - 3.5), (BW - 3.5, BH - 3.5)):
    ax.add_patch(Circle(P(hx, hy), 1.6 * S, fc="white", ec="k", lw=0.8, zorder=9))
    ax.add_patch(Circle(P(hx, hy), 3.0 * S, fill=False, ec="#999", lw=0.5, ls=":", zorder=9))
# dims
dim_h(ax, a, c, b, b, b - 9, f"{BW:.0f}", fs=8, above=False)
dim_v(ax, b, d, a, a, a - 9, f"{BH:.0f}", fs=8, left=True)
ax.text(a, b - 17, "M3 취부공 ×4 (가장자리 3.5 mm), 축척 2:1 — 도면 치수 mm (보드 좌표)", fontsize=7, va="top")

# zones
zone(0, 46, 36, 80, "#fde2cf", "#b35a00", "① 12 V 입력 · 스위칭 전원", "U1/U3 buck — 노이즈원")
zone(36, 46, 100, 80, "#dbe8fa", "#1f4f8f", "② 선형 전력단 · 방열판 · 차단", f"Q3 ≈{P_Q_CHG:.1f} W / Q4 ≈{P_Q_DIS:.1f} W")
zone(21.5, 0, 56, 44, "#ece0f7", "#5b2c83", "④ 디지털 · MCU", "U4, U12 래치, SW1, LED")
zone(58, 0, 100, 44, "#dff1df", "#23702f", "③ 아날로그 AFE · 비교기", "스위칭 전원에서 최대한 멀리")
zone(0, 0, 18, 44, "#eeeeee", "#555555", "⑤ 절연", "")
# isolation barrier
bx = 18.8
ax.add_patch(Rct(P(bx - 0.4, 0), 1.6 * S, 44 * S, fc="#ffffff", ec="#b00000", lw=1.0, hatch="////", zorder=4))
ax.text(*P(bx + 0.4, 31), "절연 ≥ 4 mm", rotation=90, ha="center", va="center", fontsize=6.6,
        color="#b00000", zorder=9, bbox=dict(fc="white", ec="none", pad=0.2))

# ① power
conn(1.8, 70, 3.6, 9, "J7", "12 V IN", "left")
part(9, 72, 6, 3.5, "F1", "3 A")
part(9, 66, 5, 4.5, "Q1", "")
part(16, 70, 5, 5, "D1", "SMBJ15A", fs=5.8)
part(24, 71, 6, 6, "U1", "5 V")
part(24, 62, 6, 5, "L1", "")
part(31, 71, 6, 6, "U3", "3.3 V")
part(31, 62, 6, 5, "L2", "")
part(12, 55, 7, 4, "U2 LDO", "", fs=6.2)
part(26, 52, 14, 4, "C bulk", "", fs=6.2)

# ② linear stage / heatsink
hs = (48, 57, 82, 74)
ax.add_patch(Rct(P(hs[0], hs[1]), (hs[2] - hs[0]) * S, (hs[3] - hs[1]) * S, fc="#c9d2dc", ec="#333", lw=1.0,
                 hatch="||", zorder=3))
ax.text(*P((hs[0] + hs[2]) / 2, hs[3] - 1.4), "방열판 영역 (heatsink, 양면 thermal via)", ha="center", va="top", fontsize=7.2,
        zorder=8, bbox=dict(fc="white", ec="none", pad=0.3))
part(56, 65, 9, 8, "Q3", "P-ch DPAK", fs=6.2)
part(72, 65, 9, 8, "Q4", "N-ch DPAK", fs=6.2)
part(64, 60.5, 4, 2.5, "Rs1", "", fs=5.8)
part(79.5, 60.5, 4, 2.5, "Rs2", "", fs=5.8)
part(43, 53.5, 7, 4, "U6", "servo", fs=6.0)
part(52, 53.5, 6, 4, "U7", "", fs=6.2)
part(43, 49, 7, 3.5, "U5", "", fs=6.2)
part(86, 72, 5, 4, "Q5", "", fs=6.2)
part(86, 66, 5, 4, "Q6", "", fs=6.2)
part(80, 50.5, 5, 3, "Q7/8", "", fs=5.4)
part(90, 58, 7, 3, "R21", "", fs=6.0)
part(88, 51.5, 5, 3.5, "U8", "", fs=6.2)
conn(98.2, 66, 3.6, 12, "J1", "CELL 4-wire", "right")
star = P(95.5, 58)
ax.plot(*star, marker="*", ms=13, color="#b00000", zorder=10, mec="k", mew=0.5)
ax.annotate("스타 GND (J1-2)", xy=star, xytext=(star[0] + 12, star[1] - 16), fontsize=7.2, color="#b00000", zorder=10,
            arrowprops=dict(arrowstyle="-", lw=0.6, color="#b00000"), bbox=dict(fc="white", ec="none", pad=0.3))

# ③ AFE
part(66, 34, 6, 4, "U9", "OPA2333", fs=5.8)
part(66, 26, 6, 4, "U10", "TLV3202", fs=5.8)
part(66, 18, 6, 4, "U11", "TLV3202", fs=5.8)
part(77, 30, 10, 12, "분배기 · RC", "R30–R46", fs=6.0)
part(90, 36, 5, 4, "RV1", "H2 trim", fs=5.6)
conn(66, 1.8, 8, 3.6, "J2", "압력", "bottom")
conn(80, 1.8, 8, 3.6, "J3", "NTC ×2", "bottom")
conn(98.2, 22, 3.6, 9, "J4", "H2 센서", "right")

# ④ digital
part(38, 24, 14, 14, "U4", "STM32G474RE\nLQFP64", fs=6.4)
part(51, 30, 4, 3, "U12", "", fs=5.8)
part(51, 22, 5, 5, "SW1", "RESET", fs=5.4)
conn(38, 1.8, 10, 3.6, "J6", "SWD", "bottom")
for i, (lab, col) in enumerate((("RUN", "#2e9e3e"), ("WARN", "#e0b000"), ("TRIP", "#d02020"), ("PWR", "#2e9e3e"))):
    ax.add_patch(Circle(P(26 + i * 5, 9), 1.3 * S, fc=col, ec="k", lw=0.6, zorder=6))
    ax.text(*P(26 + i * 5, 5.6), lab, ha="center", va="top", fontsize=5.8, zorder=7)

# ⑤ isolation
part(bx + 0.4, 14, 7, 9, "U13", "", fs=6.6)
conn(1.8, 14, 3.6, 8, "J5", "USB", "left")
ax.text(*P(9, 30), "PC 측\nGND_ISO", ha="center", va="center", fontsize=7, color="#555", zorder=8)

# signal flow hints
def flow(p, q, lab, col="#1f5fa8", f=0.5):
    ax.add_patch(FancyArrowPatch(P(*p), P(*q), arrowstyle="-|>", mutation_scale=9, lw=1.0, color=col, zorder=7,
                                 connectionstyle="arc3,rad=0.0", shrinkA=0, shrinkB=0))
    m = P(p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)
    ax.text(m[0], m[1] + 1.2, lab, fontsize=6.2, color=col, ha="center", va="bottom", zorder=8,
            bbox=dict(fc="white", ec="none", pad=0.2, alpha=0.8))
flow((88, 49.5), (80, 37), "SH_P/N → U8 → I_MON")
flow((62, 26), (54, 26), "FAULT")
pts = [P(51, 31.6), P(51, 45.0), P(78.5, 45.0)]
ax.plot([q[0] for q in pts], [q[1] for q in pts], color="#b00000", lw=1.0, zorder=7)
ax.add_patch(FancyArrowPatch(P(78.5, 45.0), P(78.5, 49.0), arrowstyle="-|>", mutation_scale=9, lw=1.0, color="#b00000", zorder=7, shrinkA=0, shrinkB=0))
ax.text(*P(64, 45.3), "TRIP → Q7/Q8 (게이트 차단)", fontsize=6.2, color="#b00000", ha="center", va="bottom", zorder=8,
        bbox=dict(fc="white", ec="none", pad=0.2))

# ---------------- Kelvin inset
ix, iy = 290.0, 170.0
ax.text(ix, 272, "상세 K — 션트 Kelvin 배선 (4배 확대, 개념도)", fontsize=9.5, fontweight="bold", va="top")
ax.add_patch(Rct((ix, 210), 20, 30, fc="#d9a066", ec="k", lw=0.8, zorder=4))              # left pad (current)
ax.add_patch(Rct((ix + 60, 210), 20, 30, fc="#d9a066", ec="k", lw=0.8, zorder=4))
ax.add_patch(Rct((ix + 16, 214), 48, 22, fc="#666", ec="k", lw=0.8, zorder=5))
ax.text(ix + 40, 225, "R21 10 mΩ (2512 / 4-term)", color="white", ha="center", va="center", fontsize=6.8, zorder=6)
ax.add_patch(Rct((ix - 30, 214), 30, 22, fc="#e8b37a", ec="none", zorder=3)); ax.text(ix - 15, 225, "Q6 측\n(큰 동박)", ha="center", va="center", fontsize=6.6, zorder=6)
ax.add_patch(Rct((ix + 80, 214), 30, 22, fc="#e8b37a", ec="none", zorder=3)); ax.text(ix + 95, 225, "J1 F+ 측\n(큰 동박)", ha="center", va="center", fontsize=6.6, zorder=6)
for xk in (ix + 17.5, ix + 62.5):
    ax.plot([xk, xk], [212, 190], color="#1f5fa8", lw=1.6, zorder=6)
ax.plot([ix + 17.5, ix + 38.5, ix + 38.5], [190, 190, 176], color="#1f5fa8", lw=1.6, zorder=6)
ax.plot([ix + 62.5, ix + 41.5, ix + 41.5], [190, 190, 176], color="#1f5fa8", lw=1.6, zorder=6)
ax.plot([ix + 17.5, ix + 38.5], [190, 190], color="#1f5fa8", lw=1.6, zorder=6)
ax.add_patch(Rct((ix + 30, 164), 20, 12, fc="white", ec="k", lw=0.8, zorder=6)); ax.text(ix + 40, 170, "U8\nINA240A2", ha="center", va="center", fontsize=6.6, zorder=7)
ax.text(ix + 12, 196, "SH_P", fontsize=6.8, color="#1f5fa8", ha="right"); ax.text(ix + 68, 196, "SH_N", fontsize=6.8, color="#1f5fa8")
arr(ax, (ix - 28, 244), (ix + 108, 244), both=False, ms=9, color="#b35a00", lw=1.4)
ax.text(ix + 40, 246, f"전류 경로 ≤ {LIMITS['I_max_A']:.0f} A (두꺼운 동박)", fontsize=6.8, ha="center", va="bottom", color="#b35a00")
for i, s in enumerate(["• 센스 선은 패드 안쪽 가장자리에서 인출, 전류 동박과 공유 금지",
                       "• SH_P/SH_N 은 붙여서 나란히 (차동쌍), 아래층은 AGND 연속면",
                       "• U8 은 R21 에서 10 mm 이내, 전력단 방열판 쪽 열원과 떨어뜨림"]):
    ax.text(ix - 30, 158 - i * 5.5, s, fontsize=7.0, va="top")

# ---------------- notes
ax.text(290, 136, "배치 규칙 / Placement rules", fontsize=9, fontweight="bold", va="top")
rules = ["1. ③ AFE 는 ① buck(U1/U3, L1/L2) 에서 30 mm 이상 떨어뜨림.",
         "2. 4층: L2 = GND 연속면. AGND/PGND 분리하지 않고 한 면,",
         "    전력 귀환은 ② 안에서 J1-2 스타점으로만 모인다.",
         "3. ⑤ 절연: U13 이 경계를 가로지름, 그 아래 전 층 구리 없음.",
         f"4. 방열판: 최대 {P_Q_CHG:.1f} W (충전 시 Q3), Ta 40 °C·",
         f"    방열판 70 °C 가정 → Rth ≤ {30/P_Q_CHG:.1f} K/W (가정값).",
         "5. 커넥터: J1 · J4 오른쪽, J2 · J3 · J6 아래, J5 · J7 왼쪽.",
         "6. 부품 위치는 계획 — 치수는 보드 좌표 (mm), 확정 아님."]
for i, s in enumerate(rules):
    ax.text(290, 129 - i * 5.6, s, fontsize=7.2, va="top")
save(fig, "M-003_pcb")
