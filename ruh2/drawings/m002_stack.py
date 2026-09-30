from mech import *
from matplotlib.patches import Ellipse
import math

fig, fr = sheet("RUH2-M-002", "전극 스택 / Electrode Stack", scale="표시대로")
ax = mm_axes(fig)
ax.text(14, 285, "RUH2-M-002  전극 스택 — back-to-back 단위 × 4, Ru/C 수소극", fontsize=15, fontweight="bold", va="top")
C_ = CELL
n = C_["n_units"]
LAY = [("gas screen", "가스 스크린", C_["screen_thk_mm"], "#b9bec6"),
       ("Ru/C GDE (−)", "Ru/C 수소극", C_["gde_thk_mm"], "#3a3a3a"),
       ("separator", "분리막", C_["sep_thk_mm"], "#f4f4ee"),
       ("Ni(OH)2 electrode (+)", "Ni(OH)2 양극", C_["ni_thk_mm"], "#7fa34a"),
       ("separator", "분리막", C_["sep_thk_mm"], "#f4f4ee"),
       ("Ru/C GDE (−)", "Ru/C 수소극", C_["gde_thk_mm"], "#3a3a3a"),
       ("gas screen", "가스 스크린", C_["screen_thk_mm"], "#b9bec6")]

def shade(c, f):
    import matplotlib.colors as mc
    r, g, b = mc.to_rgb(c); return (r * f, g * f, b * f)

# ============ (a) exploded view of one unit pair
ax.text(14, 272, "(a) 단위 1개 분해도 — 7층 (두께 과장 ×8, 비축척)", fontsize=10, fontweight="bold", va="top")
cx, rx, ry = 70.0, 46.0, 13.0
hr = rx * C_["disc_id_mm"] / C_["disc_od_mm"]
y = 156.0
for i, (en, ko, thk, col) in enumerate(LAY):
    t = thk * 8
    ax.add_patch(Ellipse((cx, y), 2 * rx, 2 * ry, fc=shade(col, 0.75), ec="k", lw=0.6, zorder=10 + 3 * i))
    ax.add_patch(Rct((cx - rx, y), 2 * rx, t, fc=shade(col, 0.75), ec="none", zorder=10 + 3 * i))
    ax.plot([cx - rx, cx - rx], [y, y + t], color="k", lw=0.6, zorder=11 + 3 * i)
    ax.plot([cx + rx, cx + rx], [y, y + t], color="k", lw=0.6, zorder=11 + 3 * i)
    ax.add_patch(Ellipse((cx, y + t), 2 * rx, 2 * ry, fc=col, ec="k", lw=0.7, zorder=12 + 3 * i,
                         hatch="++" if "screen" in en else None))
    ax.add_patch(Ellipse((cx, y + t), 2 * hr, 2 * hr * ry / rx, fc="white", ec="k", lw=0.5, zorder=12 + 3 * i))
    ly = y + t / 2
    ax.plot([cx + rx + 1, cx + rx + 14], [ly, ly], color="k", lw=0.5, zorder=40)
    ax.text(cx + rx + 15, ly, f"{ko} / {en}", fontsize=7.6, va="center", zorder=40)
    ax.text(cx + rx + 88, ly, f"{thk:.2f} mm", fontsize=7.6, va="center", ha="right", zorder=40, fontweight="bold")
    if "screen" in en:
        for s in (-1,):
            arr(ax, (cx + s * (rx + 16), y + t / 2), (cx + s * (rx + 2), y + t / 2), both=False, ms=8, color="#1f5fa8", lw=1.2)
            ax.patches[-1].set_zorder(60)
    y += t + 10.5
unit_t = sum(l[2] for l in LAY)
ax.text(cx + rx + 88, 150.0, f"7층 합 {unit_t:.2f} mm", fontsize=7.6, ha="right", va="top", color="#8a0000")
ax.text(cx - rx, 139.0, "파란 화살표 = H2 경로: 스크린 외주에서 반경 방향으로 GDE 뒷면에 공급", fontsize=7.2, color="#1f5fa8", va="top")
ax.text(cx - rx, 133.5, f"원판 OD {C_['disc_od_mm']:.0f} / ID {C_['disc_id_mm']:.0f} mm (중앙 구멍 = PTFE 슬리브 타이로드)", fontsize=7.2, va="top")

# ============ (b) section of the full stack
sx, sz = 2.0, 6.0
x0, yb = 318.0, 118.0
X = lambda x: x0 + x * sx
Z = lambda z: yb + z * sz
R = C_["disc_od_mm"] / 2; r = C_["disc_id_mm"] / 2
ax.text(222, 272, f"(b) 스택 단면 — {n} 단위 (가로 2:1, 세로 6:1)", fontsize=10, fontweight="bold", va="top")
# bottom end plate (shown 2 mm, broken)
EPs = 2.0
rect(ax, X(-R - 1), Z(-EPs), X(R + 1), Z(0), mat="ptfe", z=3)
ax.text(X(-R - 1), Z(-EPs) - 1.2, "PTFE 엔드플레이트 t 5 (부분)", fontsize=6.8, ha="left", va="top")
seq = []
for k in range(n):
    seq += [LAY[0], LAY[1], LAY[2], LAY[3], LAY[4], LAY[5]]        # spec.py: one screen per unit
z = 0.0
tabs_p, tabs_n, screens = [], [], []
for (en, ko, thk, col) in seq:
    for s in (-1, 1):
        ax.add_patch(Rct((X(s * r) if s > 0 else X(-R), Z(z)), (R - r) * sx, thk * sz, fc=col, ec="k", lw=0.35,
                         hatch="++" if "screen" in en else None, zorder=4))
    if "Ni(OH)2" in en: tabs_p.append(z + thk / 2)
    if "GDE" in en: tabs_n.append(z + thk / 2)
    if "screen" in en: screens.append(z + thk / 2)
    z += thk
H = z
rect(ax, X(-R - 1), Z(H), X(R + 1), Z(H + EPs), mat="ptfe", z=3)
for gx in (-16, -8, 8, 16):
    ax.add_patch(Rct((X(gx) - 2, Z(H)), 4, 3, fc="white", ec="k", lw=0.4, zorder=5))
ax.text(X(-R - 1), Z(H + EPs) + 1.2, "PTFE 엔드플레이트 + 가스 홈", fontsize=6.8, ha="left", va="bottom")
# central sleeve + rod
rect(ax, X(-r), Z(-EPs), X(r), Z(H + EPs), mat="ptfe", z=4)
rect(ax, X(-2.5), Z(-EPs - 1), X(2.5), Z(H + EPs + 1), mat="none", z=5)
ax.text(X(0), Z(H / 2), "M5\n타이로드", fontsize=6.2, ha="center", va="center", zorder=6, rotation=90)
# tabs
for zt in tabs_p:
    ax.plot([X(-R), X(-R) - 14], [Z(zt), Z(zt)], color="#4f7a1e", lw=1.2, zorder=6)
for zt in tabs_n:
    ax.plot([X(R), X(R) + 14], [Z(zt), Z(zt)], color="#222", lw=1.0, zorder=6)
ax.plot([X(-R) - 14, X(-R) - 14], [Z(min(tabs_p)), Z(max(tabs_p))], color="#4f7a1e", lw=2.2, zorder=6)
ax.plot([X(R) + 14, X(R) + 14], [Z(min(tabs_n)), Z(max(tabs_n))], color="#222", lw=2.2, zorder=6)
leader(ax, (X(-R) - 14, Z(max(tabs_p))), (X(-R) - 22, Z(H) + 16), "Ni 탭 (+) ×4\n→ FT+ (M-001 ⑩)", ha="right", fs=7.2)
leader(ax, (X(R) + 14, Z(max(tabs_n))), (X(R) + 20, Z(H) + 16), "Ni 탭 (−) ×8\n→ FT−", fs=7.2)
# gas arrows into screens
for zs in screens:
    for s in (-1, 1):
        arr(ax, (X(s * (R + 9)), Z(zs) - 2.2), (X(s * (R - 3)), Z(zs)), both=False, ms=6, color="#1f5fa8", lw=0.8)
ax.text(X(R) + 8, Z(-EPs) - 4, "H2 → 스크린 (반경 방향)", fontsize=7.0, color="#1f5fa8", va="top")
# dimensions
dim_v(ax, Z(0), Z(H), X(R) + 30, X(R) + 30, X(R) + 34, f"{H:.1f} mm\n(spec {VESSEL['stack_h_mm']:.1f})", left=False)
pitch = H / n
dim_v(ax, Z(0), Z(pitch), X(-R) - 26, X(-R) - 26, X(-R) - 30, f"단위\n{pitch:.1f} mm", left=True)
dim_h(ax, X(-R), X(R), Z(-EPs), Z(-EPs), Z(-EPs) - 10, f"Ø{C_['disc_od_mm']:.0f}", fs=7.2, above=False)
dim_h(ax, X(-r), X(r), Z(H + EPs), Z(H + EPs), Z(H + EPs) + 10, f"Ø{C_['disc_id_mm']:.0f}", fs=7.2)
# legend
lx, ly = 222, 250
for i, (en, ko, thk, col) in enumerate(LAY[:4]):
    ax.add_patch(Rct((lx + i * 46, ly), 6, 4, fc=col, ec="k", lw=0.5, hatch="++" if "screen" in en else None))
    ax.text(lx + i * 46 + 7.5, ly + 2, ko, fontsize=7.0, va="center")

# ============ (c) table
Ru_C = C_["ru_total_mg"] / (C_["ru_wt_pct_on_C"] / 100)
ptfe = Ru_C * C_["ptfe_wt_pct"] / (100 - C_["ptfe_wt_pct"])
rows = [("항목", "값", "식 (spec.py)"),
        ("원판 한 면 면적", f"{C_['face_area_cm2']:.2f} cm²", "π/4·(4.6² − 0.8²)"),
        ("H2 전극 면적 (spec)", f"{C_['h2_area_cm2']:.2f} cm²", f"면적 × n_gde ({C_['n_gde']})"),
        ("Ni 면적 용량", f"{C_['ni_areal_mAh_cm2']:.2f} mAh/cm²", "Q / n / 면적"),
        ("Ru 담지량", f"{C_['ru_loading_mg_cm2']:.2f} mg/cm²", ""),
        ("Ru 총량 (spec)", f"{C_['ru_total_mg']:.1f} mg", "담지량 × H2 면적"),
        ("Ru/C 촉매 질량", f"{Ru_C:.0f} mg", f"Ru {C_['ru_wt_pct_on_C']} wt% on C"),
        ("PTFE 결착제", f"{ptfe:.0f} mg", f"촉매층의 {C_['ptfe_wt_pct']} wt%"),
        ("전류밀도 @C/5 · @I_max", f"{C_['Q_Ah']/5*1000/C_['h2_area_cm2']:.1f} · {LIMITS['I_max_A']*1000/C_['h2_area_cm2']:.0f} mA/cm²", "spec H2 면적 기준"),
        ("스택 높이 (spec)", f"{VESSEL['stack_h_mm']:.1f} mm", "n·(Ni+2sep+2GDE+1scr)"),
]
table(ax, 14, 58, [50, 44, 50], rows, rh=5.3, fs=7.0, title="(c) 면적 · 용량 · 촉매 (spec.py 계산)", red_rows=())

ax.text(172, 125, "설계 노트 — 스택 높이 9.6 mm", fontsize=8.6, fontweight="bold", color="#1f3f8a", va="top")
for i, s_ in enumerate([
        f"• 스크린 공유: 맨 아래 1 + 사이 {n-1} = {n}장.",
        f"• 최상단 GDE 는 스크린 대신 PTFE 엔드플레이트의 가스 홈으로 급기.",
        f"• 그래서 높이 = {n}×(Ni + 2 sep + 2 GDE + 1 scr) = {n}×{pitch:.1f} = {H:.1f} mm (spec).",
        f"• (a) 의 7층은 단위 하나를 따로 뗀 그림 — 양끝 스크린 2장은",
        f"   조립하면 이웃 단위와 공유되어 {unit_t:.2f} mm 가 아니라 {pitch:.1f} mm 피치가 된다.",
        f"• GDE 는 단위당 2장 (back-to-back) → n_gde = {C_['n_gde']}, 면적 {C_['h2_area_cm2']:.1f} cm²."]):
    ax.text(172, 118 - i * 5.6, s_, fontsize=7.3, va="top", color="#222")
save(fig, "M-002_stack")
