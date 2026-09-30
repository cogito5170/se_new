from mech import *
import math

fig, fr = sheet("RUH2-M-001", "압력용기 조립도 / Pressure Vessel Assembly", scale="1:1 (A3)")
ax = mm_axes(fig)
ax.text(14, 285, "RUH2-M-001  압력용기 조립도 — 316L 2in Sch10S, 볼트 플랜지, 전극 스택, 관통단자, 1/4\" NPT 배관",
        fontsize=15, fontweight="bold", va="top")

OD, WALL, ID, LIN = VESSEL["od_mm"], VESSEL["wall_mm"], VESSEL["id_mm"], VESSEL["inner_len_mm"]
RO, RI = OD / 2, ID / 2
# proposal dimensions (not in spec.py -> marked 제안)
FL_R, FL_T, CV_T, PCD, BOLT_D, ORING_D, ORING_CS = 50.0, 10.0, 12.0, 84.0, 6.0, 66.0, 3.0
EP_T, EP_R, SO_H, ROD_D, SLV_D = 5.0, 24.0, 22.0, 5.0, CELL["disc_id_mm"]
SH = VESSEL["stack_h_mm"]; SR = CELL["disc_od_mm"] / 2
FT_X = 20.0
cx, zb = 112.0, 92.0          # sheet position of axis and of the bottom inner face (z=0)
Y = lambda z: zb + z

# ---------------- front section A-A
ax.text(cx, Y(-32), "단면 A-A (정면) / SECTION A-A", ha="center", fontsize=9.5, fontweight="bold", va="top")
center_line(ax, (cx, Y(-24)), (cx, Y(LIN + 118)))
for s in (-1, 1):
    rect(ax, cx + s * RI, Y(0), cx + s * RO, Y(LIN))                                  # tube wall
    rect(ax, cx + s * RO, Y(0), cx + s * FL_R, Y(FL_T))                               # bottom flange ring
    rect(ax, cx + s * RO, Y(LIN - FL_T), cx + s * FL_R, Y(LIN))                       # top flange ring
# covers (with holes)
def cover(z0, z1, holes):
    xs = sorted([cx - FL_R, cx + FL_R] + [h for hh in holes for h in hh])
    for a, b in zip(xs[0::2], xs[1::2]):
        rect(ax, a, Y(z0), b, Y(z1))
bolt_holes = [(cx - PCD / 2 - 3.3, cx - PCD / 2 + 3.3), (cx + PCD / 2 - 3.3, cx + PCD / 2 + 3.3)]
cover(-CV_T, 0, bolt_holes)
top_holes = bolt_holes + [(cx - FT_X - 4, cx - FT_X + 4), (cx + FT_X - 4, cx + FT_X + 4), (cx - 5.7, cx + 5.7)]
cover(LIN, LIN + CV_T, top_holes)
# bolt holes through flange rings: blank them + bolts
for zr0, zr1 in ((0, FL_T), (LIN - FL_T, LIN)):
    for a, b in bolt_holes:
        rect(ax, a, Y(zr0), b, Y(zr1), mat="none", lw=0)
for a, b in bolt_holes:
    xm = (a + b) / 2
    rect(ax, xm - 3, Y(-CV_T - 4), xm + 3, Y(FL_T + 5), mat="none", z=4)             # bottom bolt
    rect(ax, xm - 5, Y(-CV_T - 4), xm + 5, Y(-CV_T), mat="none", z=4)                  # head
    rect(ax, xm - 5, Y(FL_T), xm + 5, Y(FL_T + 5), mat="none", z=4)                    # nut
    rect(ax, xm - 3, Y(LIN - FL_T - 5), xm + 3, Y(LIN + CV_T + 4), mat="none", z=4)   # top bolt
    rect(ax, xm - 5, Y(LIN - FL_T - 5), xm + 5, Y(LIN - FL_T), mat="none", z=4)
    rect(ax, xm - 5, Y(LIN + CV_T), xm + 5, Y(LIN + CV_T + 4), mat="none", z=4)
# O-rings (groove in cover face)
for zc, zg in ((-1.3, (-2.4, 0)), (LIN + 1.3, (LIN, LIN + 2.4))):
    for s in (-1, 1):
        x = cx + s * ORING_D / 2
        rect(ax, x - 2.1, Y(zg[0]), x + 2.1, Y(zg[1]), mat="none", lw=0.5, z=4)
        ax.add_patch(Circle((x, Y(zc)), ORING_CS / 2, fc="#222", ec="k", zorder=5))
# internal: standoff, end plates, stack, rod
for s in (-1, 1):
    rect(ax, cx + s * 2.9, Y(0), cx + s * 7.0, Y(SO_H), mat="ptfe")                   # PTFE standoff tube
z_ep1, z_st, z_ep2 = SO_H, SO_H + EP_T, SO_H + EP_T + SH
for z0 in (z_ep1, z_ep2):
    for s in (-1, 1):
        rect(ax, cx + s * SLV_D / 2, Y(z0), cx + s * EP_R, Y(z0 + EP_T), mat="ptfe")
for s in (-1, 1):
    rect(ax, cx + s * SLV_D / 2, Y(z_st), cx + s * SR, Y(z_st + SH), mat="stack")
    for k in range(1, CELL["n_units"]):
        zz = z_st + k * SH / CELL["n_units"]
        ax.plot([cx + s * SLV_D / 2, cx + s * SR], [Y(zz), Y(zz)], color="#2a3f5c", lw=0.6, zorder=4)
    rect(ax, cx + s * ROD_D / 2, Y(z_st), cx + s * SLV_D / 2, Y(z_st + SH), mat="ptfe")  # sleeve
rect(ax, cx - ROD_D / 2, Y(3), cx + ROD_D / 2, Y(z_ep2 + EP_T + 5), mat="none", z=4)  # tie rod
rect(ax, cx - 4.5, Y(z_ep2 + EP_T), cx + 4.5, Y(z_ep2 + EP_T + 4), mat="none", z=5)   # nut
rect(ax, cx - 4.5, Y(3), cx + 4.5, Y(7), mat="none", z=5)                              # captive nut
# Ni tabs to feedthroughs
zft_in = LIN - 8
ax.plot([cx - SR, cx - SR - 2, cx - FT_X, cx - FT_X], [Y(z_st + 2), Y(z_st + 2), Y(zft_in - 12), Y(zft_in)], color="#b36b00", lw=1.4, zorder=6)
ax.plot([cx + SR, cx + SR + 2, cx + FT_X, cx + FT_X], [Y(z_st + 6), Y(z_st + 6), Y(zft_in - 12), Y(zft_in)], color="#b36b00", lw=1.4, zorder=6)
# feedthroughs
for s in (-1, 1):
    x = cx + s * FT_X
    rect(ax, x - 1.5, Y(zft_in), x + 1.5, Y(LIN + CV_T + 26), mat="none", z=6, ec="#7a4a00")
    rect(ax, x - 4, Y(LIN), x - 1.5, Y(LIN + CV_T), mat="ptfe", z=5); rect(ax, x + 1.5, Y(LIN), x + 4, Y(LIN + CV_T), mat="ptfe", z=5)
    rect(ax, x - 7, Y(LIN + CV_T), x - 1.5, Y(LIN + CV_T + 12), mat="brass", z=5)
    rect(ax, x + 1.5, Y(LIN + CV_T), x + 7, Y(LIN + CV_T + 12), mat="brass", z=5)
    ax.text(x, Y(LIN + CV_T + 27.5), "+" if s < 0 else "−", ha="center", va="bottom", fontsize=10, fontweight="bold",
            color="#b00000" if s < 0 else "#1f3f8a")
# port + fittings
zp0 = LIN + CV_T
rect(ax, cx - 6.85, Y(zp0), cx + 6.85, Y(zp0 + 16), mat="none", z=5)                  # nipple 1/4 NPT (OD 13.7)
rect(ax, cx - 2.3, Y(zp0 - CV_T), cx + 2.3, Y(zp0 + 16), mat="none", z=6, lw=0.5)      # bore
zt = zp0 + 16
rect(ax, cx - 10, Y(zt), cx + 10, Y(zt + 18), mat="none", z=5)                         # tee
rect(ax, cx + 10, Y(zt + 4), cx + 22, Y(zt + 14), mat="none", z=5)                    # tee branch
rect(ax, cx + 22, Y(zt + 1), cx + 30, Y(zt + 17), mat="none", z=5)                    # burst disk holder
ax.plot([cx + 26, cx + 26], [Y(zt + 1), Y(zt + 17)], color="#b00000", lw=1.6, zorder=6)
zc = zt + 18
rect(ax, cx - 5, Y(zc), cx + 5, Y(zc + 6), mat="none", z=5)                            # nipple
zx = zc + 6
rect(ax, cx - 10, Y(zx), cx + 10, Y(zx + 18), mat="none", z=5)                         # cross
rect(ax, cx - 22, Y(zx + 4), cx - 10, Y(zx + 14), mat="none", z=5)                    # left branch
rect(ax, cx - 72, Y(zx - 3.5), cx - 22, Y(zx + 21.5), mat="none", z=5)                # pressure transducer
ax.plot([cx - 80, cx - 72], [Y(zx + 9), Y(zx + 9)], color="k", lw=2.0, zorder=5)
rect(ax, cx + 10, Y(zx + 4), cx + 20, Y(zx + 14), mat="none", z=5)
poly(ax, [(cx + 20, Y(zx - 2)), (cx + 44, Y(zx - 2)), (cx + 44, Y(zx + 20)), (cx + 20, Y(zx + 20))], mat="none", z=5)   # relief valve
rect(ax, cx + 28, Y(zx + 20), cx + 36, Y(zx + 32), mat="none", z=5)
rect(ax, cx - 5, Y(zx + 18), cx + 5, Y(zx + 30), mat="none", z=5)                    # needle valve body
rect(ax, cx - 3, Y(zx + 30), cx + 3, Y(zx + 40), mat="none", z=5)
rect(ax, cx - 12, Y(zx + 40), cx + 12, Y(zx + 44), mat="none", z=5)                   # handle
ax.plot([cx + 44, cx + 50], [Y(zx + 9), Y(zx + 9)], color="k", lw=1.0, zorder=5)
ax.text(cx + 51, Y(zx + 9), "vent", fontsize=6.8, va="center")

# ---------------- dimensions (front)
dim_v(ax, Y(0), Y(LIN), cx - RI, cx - RI, cx - 60, f"{LIN:.0f}\n내부 길이", left=True)
dim_h(ax, cx - RI, cx + RI, Y(48), Y(48), Y(52), f"Ø{ID:.2f} (ID)", fs=7.2)
dim_h(ax, cx - RO, cx + RO, Y(-CV_T), Y(-CV_T), Y(-17), f"Ø{OD:.1f} (OD)", fs=7.2, above=False) if False else None
dim_h(ax, cx - FL_R, cx + FL_R, Y(-CV_T - 4), Y(-CV_T - 4), Y(-22), f"Ø{2*FL_R:.0f} 플랜지 (제안)", fs=7.2, above=False)
dim_v(ax, Y(z_st), Y(z_st + SH), cx + SR, cx + SR, cx + 37, f"{SH:.1f} 스택", left=False)
dim_v(ax, Y(0), Y(z_st), cx + 7, cx + 7, cx + 45, f"{z_st:.0f}", left=False)

# ---------------- leaders (front)
L = []
leader(ax, (cx + RI + 1.2, Y(52)), (cx + 72, Y(50)), f"① 316L 관 OD {OD} × t {WALL} (2in Sch10S)")
leader(ax, (cx + 44, Y(LIN - 5)), (cx + 72, Y(60)), "② 플랜지 링 ×2 (용접, 316L)")
leader(ax, (cx + 40, Y(LIN + 8)), (cx + 72, Y(80)), f"③ 블라인드 커버 ×2, t {CV_T:.0f} (제안)")
leader(ax, (cx + ORING_D / 2, Y(LIN + 1.3)), (cx + 72, Y(70)), f"④ EPDM O-ring Ø{ORING_D:.0f}×{ORING_CS:.0f} (KOH 호환)")
leader(ax, (cx + PCD / 2, Y(-CV_T - 2)), (cx + 72, Y(-8)), "⑤ M6 A4-70 ×6 (각 플랜지), PCD 84")
leader(ax, (cx + 15, Y(z_st + 4)), (cx + 72, Y(26)), f"⑥ 전극 스택 {CELL['n_units']} 단위 (M-002)")
leader(ax, (cx + 16, Y(z_ep2 + 2.5)), (cx + 72, Y(38)), f"⑦ PTFE 엔드플레이트 ×2, t {EP_T:.0f}")
leader(ax, (cx + 5, Y(10)), (cx + 72, Y(12)), f"⑧ PTFE 스탠드오프 + M5 타이로드 (PTFE 슬리브 Ø{SLV_D:.0f})")
leader(ax, (cx - SR - 1, Y(z_st + 2)), (cx - 72, Y(z_st + 16)), "⑨ Ni 탭 → 관통단자", ha="right")
leader(ax, (cx - FT_X - 5, Y(LIN + CV_T + 6)), (cx - 72, Y(LIN + 14)), "⑩ PTFE 밀봉 관통단자 ×2\n    Ni 봉 Ø3", ha="right")
leader(ax, (cx - 6.85, Y(zp0 + 12)), (cx - 72, Y(zp0 + 22)), "⑪ 1/4\" NPT 니플", ha="right")
leader(ax, (cx + 26, Y(zt + 17)), (cx + 72, Y(zt + 14)), f"⑫ 파열판 {VESSEL['p_burst_disk_bar']:.0f} bar (tee 분기)")
leader(ax, (cx - 50, Y(zx + 21.5)), (cx - 72, Y(zx + 30)), "⑬ 압력센서 0–10 bar abs\n    0.5–4.5 V (J2)", ha="right")
leader(ax, (cx + 40, Y(zx + 20)), (cx + 72, Y(zx + 26)), f"⑭ 안전밸브 {VESSEL['p_relief_bar']:.0f} bar")
leader(ax, (cx + 10, Y(zx + 42)), (cx + 72, Y(zx + 40)), "⑮ 니들밸브 (충전 / 배기)")
leader(ax, (cx - 5, Y(zx + 9)), (cx - 30, Y(zx + 32)), "cross", ha="right", fs=6.6)

# ---------------- end view (top)
ex, ey = 322.0, 208.0
ax.text(ex, ey - FL_R - 9, "평면도 (커버 윗면) / TOP VIEW", ha="center", fontsize=9.5, fontweight="bold", va="top")
ax.add_patch(Circle((ex, ey), FL_R, fc="#eef1f5", ec="k", lw=1.0, zorder=3))
for r, ls in ((RO, "--"), (RI, "--")):
    ax.add_patch(Circle((ex, ey), r, fill=False, ec="#666", lw=0.6, ls=ls, zorder=4))
ax.add_patch(Circle((ex, ey), PCD / 2, fill=False, ec="#555", lw=0.5, ls=(0, (12, 3, 2, 3)), zorder=4))
for k in range(6):
    a = math.radians(30 + 60 * k)
    ax.add_patch(Circle((ex + PCD / 2 * math.cos(a), ey + PCD / 2 * math.sin(a)), 5.0, fc="white", ec="k", lw=0.8, zorder=5))
    ax.add_patch(Circle((ex + PCD / 2 * math.cos(a), ey + PCD / 2 * math.sin(a)), 3.0, fc="#ccc", ec="k", lw=0.5, zorder=6))
for s, lab, col in ((-1, "FT+", "#b00000"), (1, "FT−", "#1f3f8a")):
    ax.add_patch(Circle((ex + s * FT_X, ey), 7.0, fc="#f2e2b8", ec="k", lw=0.8, zorder=5))
    ax.add_patch(Circle((ex + s * FT_X, ey), 1.5, fc="#7a4a00", ec="k", lw=0.5, zorder=6))
    ax.text(ex + s * FT_X, ey - 9, lab, ha="center", va="top", fontsize=7.5, color=col, fontweight="bold", zorder=7)
ax.add_patch(Circle((ex, ey), 10, fc="white", ec="k", lw=0.8, zorder=5))
ax.text(ex, ey + 12, "1/4\" NPT", ha="center", va="bottom", fontsize=7, zorder=7, bbox=dict(fc="#eef1f5", ec="none", pad=0.2))
center_line(ax, (ex - FL_R - 8, ey), (ex + FL_R + 8, ey)); center_line(ax, (ex, ey - FL_R - 6), (ex, ey + FL_R + 6))
for s in (-1, 1):
    ax.text(ex + s * (FL_R + 11), ey + 1.5, "A", ha="center", va="bottom", fontsize=9, fontweight="bold")
    arr(ax, (ex + s * (FL_R + 11), ey), (ex + s * (FL_R + 11), ey - 7), both=False, ms=8)
    ax.plot([ex + s * (FL_R + 6), ex + s * (FL_R + 11)], [ey, ey], color="k", lw=1.4, zorder=8)
leader(ax, (ex + PCD / 2 * math.cos(math.radians(30)) + 3, ey + PCD / 2 * math.sin(math.radians(30)) + 3),
       (ex + 48, ey + 50), "6× Ø6.6 / PCD 84 (제안)")
dim_h(ax, ex - FL_R, ex + FL_R, ey - FL_R, ey - FL_R, ey - FL_R - 4, f"Ø{2*FL_R:.0f}", fs=7.2, above=False) if False else None
ax.text(ex + FL_R + 2, ey - FL_R + 2, f"Ø{2*FL_R:.0f}\n외곽", fontsize=6.8, va="bottom")
ax.text(ex - FL_R - 2, ey - FL_R + 2, f"점선: 관 OD {OD} / ID {ID:.2f}", fontsize=6.6, va="bottom", ha="right", color="#555")

# ---------------- table
P = VESSEL
T_trip_K = LIMITS["T_trip_C"] + 273.15
p_full_Ttrip = P["p_full_bar_abs_25C"] * T_trip_K / 298.15
A_seal = math.pi / 4 * ORING_D ** 2
F_bolt = P["p_design_bar"] * 0.1 * A_seal / 6 / 1e3
rows = [("항목", "값", "근거 (spec.py)"),
        ("내부 체적", f"{P['internal_mL']:.1f} mL", f"π/4·{ID:.2f}²·{LIN:.0f}"),
        ("스택 고체 + 부속", f"{P['stack_solid_mL']:.1f} mL", "스택 원판 + 12 mL"),
        ("KOH 전해액", f"{CELL['koh_mL']:.1f} mL", f"{CELL['koh_wt_pct']} wt%"),
        ("자유 기체 체적", f"{P['free_gas_mL']:.1f} mL", "내부 − 고체 − KOH"),
        ("초기 충전압 (방전 상태)", f"{P['p_precharge_bar_abs']:.1f} bar abs", "H2 예충전"),
        ("만충 Δp @25 °C", f"{P['dp_full_bar_25C']:.2f} bar", f"{CELL['Q_Ah']:.0f} Ah → n = Q/2F"),
        ("만충 압력 @25 °C", f"{P['p_full_bar_abs_25C']:.2f} bar abs", "초기 + Δp"),
        (f"만충 압력 @{LIMITS['T_trip_C']} °C", f"{p_full_Ttrip:.2f} bar abs", "등적 T 비례 (계산)"),
        ("운전 상한 / 트립", f"{LIMITS['p_max_oper_bar_abs']:.1f} / {P['p_trip_bar_abs']:.1f} bar abs", "LIMITS / E-004"),
        ("안전밸브 / 파열판", f"{P['p_relief_bar']:.0f} / {P['p_burst_disk_bar']:.0f} bar", "⑭ / ⑫"),
        ("설계 / 내압시험", f"{P['p_design_bar']:.0f} / {P['p_proof_bar']:.0f} bar", ""),
        ("후프 응력 @설계", f"{P['hoop_stress_MPa_at_design']:.1f} MPa", "p·ID/(2t)"),
        ("허용 응력 316L", f"{P['allow_316L_MPa']:.0f} MPa (여유 ×{P['allow_316L_MPa']/P['hoop_stress_MPa_at_design']:.1f})", "ASME II-D, 표 확인 필요"),
        ("볼트 1개 하중 @설계", f"{F_bolt:.2f} kN", f"O-ring Ø{ORING_D:.0f} 기준 (제안)")]
table(ax, 268, 62, [46, 47, 46], rows, rh=5.0, fs=6.9, title="용기 · 압력 요약 (spec.py 계산)", red_rows=())

ax.text(14, 52, "주 Notes", fontsize=9, fontweight="bold", va="top")
for i, n in enumerate([
        "1. 치수 단위 mm. '제안' 표시 치수 (플랜지 · 커버 · PCD · O-ring · 엔드플레이트) 는 spec.py 에 없는 설계 제안값.",
        "2. 스택·타이로드·엔드플레이트는 PTFE 로 용기와 전기 절연. 용기는 GND_ISO 가 아닌 보드 PGND 와도 분리 (부동).",
        "3. 초도 조립 후 내압시험 30 bar (물, 스택 미장착), 이후 H2 누설시험. 파열판 12 bar < 설계 20 bar.",
        "4. 압력센서 상한 10 bar: 안전밸브 8 bar 까지는 측정 가능, 파열판 12 bar 영역은 포화 (E-003).",
        f"5. 압력센서(⑬)는 내압(proof) 정격 ≥ 범위의 2× (≥ 20 bar) 필수 — 파열판 {VESSEL['p_burst_disk_bar']:.0f} bar 가 센서 범위 10 bar 를 넘기 때문."]):
    ax.text(14, 46 - i * 6.2, n, fontsize=7.4, va="top")
save(fig, "M-001_vessel")
print(p_full_Ttrip, F_bolt)
