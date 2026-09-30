from schem import *
import math

fig, fr = sheet("RUH2-E-004", "MCU · 안전 인터록 회로도 / MCU & Safety Interlock")
fr.text(0.55, 11.2, "RUH2-E-004  STM32G474RE · 하드웨어 트립 비교기 · 래치 · USB 절연 · SWD", fontsize=15, fontweight="bold", va="top")
S = Sch(fig, (0.45, 2.3, 15.65, 8.6), (0, 72), (1.0, 41.0))
w, t, R, C, gnd, dot, net = S.w, S.t, S.R, S.C, S.gnd, S.dot, S.net
def vdd(p, name="+3V3_A"): S.add(elm.Vdd().at(p).label(name, fontsize=7.2))
RED = "#b00000"
R_HYS = 1e6; R_SER = 10e3

# ================= MCU
S.frame(0.3, 12.8, 41.2, 40.9, "① MCU U4 STM32G474RE (LQFP64) · SWD · USB 절연")
L = [("PA0 · ADC1_IN1", "I_MON"), ("PA1 · ADC1_IN2", "V_CELL"), ("PA2 · ADC1_IN3", "P_MON"), ("PA3 · ADC1_IN4", "T_VESSEL"),
     ("PC0 · ADC1_IN6", "T_AMB"), ("PC1 · ADC1_IN7", "H2_MON"), ("PC2 · ADC1_IN8", "I_CHG_FB"), ("PC3 · ADC1_IN9", "5V_MON"),
     None, ("PA4 · DAC1_OUT1", "DAC1_OUT1"), ("PA5 · DAC1_OUT2", "DAC1_OUT2"), None,
     ("VDD/VDDA/VREF+", "+3V3_A"), ("VSS/VSSA", "GND"), ("PB8 · BOOT0", "R 10k → GND")]
Rr = [("PA13 · SWDIO", "SWDIO"), ("PA14 · SWCLK", "SWCLK"), ("PB3 · SWO", "SWO"), ("NRST", "NRST"), None,
      ("PA12 · USB_DP", "USB_DP"), ("PA11 · USB_DM", "USB_DM"), None,
      ("PB0 · TRIP_STAT", "TRIP_STAT"), ("PB1 · MCU_DISC_OFF", "MCU_DISC_OFF"), ("PB4 · CHG_EN", "CHG_EN"),
      ("PB5 · DIS_EN", "DIS_EN"), ("PB6 · LED_RUN", "LED_RUN"), ("PB7 · LED_WARN", "LED_WARN")]
bx0, by0, bw, bh = 5.4, 13.8, 11.4, 24.8
pitch = 1.55
lp = [(n[0], bh - 1.2 - i * pitch) for i, n in enumerate(L) if n]
rp = [(n[0], bh - 1.2 - i * pitch) for i, n in enumerate(Rr) if n]
u4 = S.ic(bx0, by0, bw, bh, "U4  STM32G474RE", "", left=lp, right=rp, stub=0.8, fs=7.0, fill="#f6f0fc")
for n in L:
    if not n: continue
    tip = u4[n[0]]
    if n[1] == "GND":
        w(tip, (tip[0] - 0.8, tip[1])); gnd((tip[0] - 0.8, tip[1]))
    elif n[1].startswith("R 10k"):
        t(tip[0] - 0.15, tip[1], n[1], fs=6.8, ha="right")
    else:
        net(tip, n[1], side="left", fs=7.2)
for n in Rr[8:]:
    if n: net(u4[n[0]], n[1], fs=7.2)
t(bx0 + 0.2, by0 - 0.5, "모든 VDD 핀 100 nF + VDDA 1 µF (생략) · USB 클럭 = HSI48 + CRS (크리스털 불요)", fs=6.6, va="top", color="#444")
# SWD header J6
j6 = S.ic(24.0, 31.6, 4.4, 6.6, "J6 SWD (Cortex 10p)", "", left=[("2 SWDIO", u4["PA13 · SWDIO"][1] - 31.6),
          ("4 SWCLK", u4["PA14 · SWCLK"][1] - 31.6), ("6 SWO", u4["PB3 · SWO"][1] - 31.6), ("10 NRST", u4["NRST"][1] - 31.6)],
          right=[("1 VCC", 5.6), ("3,5,9 GND", 3.8)], stub=0.8, fs=6.8)
for a, b in (("PA13 · SWDIO", "2 SWDIO"), ("PA14 · SWCLK", "4 SWCLK"), ("PB3 · SWO", "6 SWO"), ("NRST", "10 NRST")):
    w(u4[a], j6[b])
w(j6["1 VCC"], (30.2, j6["1 VCC"][1])); vdd((30.2, j6["1 VCC"][1]))
w(j6["3,5,9 GND"], (30.2, j6["3,5,9 GND"][1])); gnd((30.2, j6["3,5,9 GND"][1]))
dot((19.6, u4["NRST"][1])); C((19.6, u4["NRST"][1]), "down", "100n", L=1.0, loc="bottom", fs=6.6); gnd((19.6, u4["NRST"][1] - 1.0))
# ADuM3160
uy0 = u4["PA12 · USB_DP"][1] - 6.2
ux0 = 24.0
u13 = S.ic(ux0, uy0, 8.6, 7.0, "U13 ADuM3160", "", left=[("DD+", 6.2), ("DD−", 4.65), ("VDD2", 3.0), ("SPU,SPD,PIN", 1.8), ("GND2", 0.6)],
           right=[("UD+", 6.2), ("UD−", 4.65), ("VBUS1", 3.0), ("GND1", 0.6)], stub=0.8, fs=6.8, fill="#f2f2f2")
w(u4["PA12 · USB_DP"], u13["DD+"]); w(u4["PA11 · USB_DM"], u13["DD−"])
net(u13["VDD2"], "+3V3_A", side="left", fs=6.6, color="#555")
w(u13["SPU,SPD,PIN"], u13["VDD2"])
gnd(u13["GND2"])
xb = ux0 + 4.3
S.w((xb, uy0 - 1.2), (xb, uy0 + 7.0 + 0.2), color="#888")
t(xb, uy0 - 1.3, "isolation barrier", fs=6.6, ha="center", va="top", color="#666")
t(xb - 0.3, uy0 - 0.6, "MCU 측", fs=6.4, ha="right", color="#666"); t(xb + 0.3, uy0 - 0.6, "PC 측", fs=6.4, ha="left", color="#666")
j5 = S.ic(36.4, uy0, 3.2, 7.0, "J5 USB-B", "", left=[("D+", 6.2), ("D−", 4.65), ("VBUS", 3.0), ("GND", 0.6)], stub=0.8, fs=6.8)
w(u13["UD+"], j5["D+"]); w(u13["UD−"], j5["D−"]); w(u13["VBUS1"], j5["VBUS"]); w(u13["GND1"], j5["GND"])
dot((34.6, u13["GND1"][1])); S.add(elm.GroundChassis().at((34.6, u13["GND1"][1])))
t(35.2, u13["GND1"][1] - 1.0, "GND_ISO", fs=6.4, color="#666", va="top")
t(24.0, 16.2, "USB-CDC: PC 측은 USB VBUS 로 급전.\nMCU 측 GND 와 GND_ISO 는 연결 금지.", fs=6.8, color="#444", va="center")

# ================= comparators
S.frame(41.5, 12.8, 71.7, 40.9, "② 하드웨어 트립 — TLV3202 ×2 · wired-OR · 래치")
chans = [("U10A", "P_MON", "P", False, 36.2), ("U10B", "V_CELL", "V", True, 30.0),
         ("U11A", "T_VESSEL", "T", True, 23.8), ("U11B", "H2_MON", "H2", False, 17.6)]
xin, xnode, xrb = 51.0, 49.6, 48.4
hyst = {}
for i, (ref, sig, key, sig_plus, y0) in enumerate(chans):
    th = TH[key]
    ytop, ybot = y0 + 0.62, y0 - 0.62
    cmp_ = S.add(elm.Opamp(flip=sig_plus).right().anchor("in1" if not sig_plus else "in2").at((xin, ytop)))
    t(xin + 1.0, (y0 - 1.45) if sig_plus else (y0 + 1.45), f"{ref}", fs=7.6, bold=True, ha="center", va=("top" if sig_plus else "bottom"))
    # signal on top
    if sig_plus:
        net((43.6, ytop), sig, side="left", fs=7.0)
        R((43.6, ytop), "right", f"R{70+i} 10k", L=2.2, fs=6.6)
        w((45.8, ytop), (xin, ytop)); dot((xnode, ytop))
        # hysteresis to + (top)
        w(cmp_.out, (53.9, y0)); w((53.9, y0), (53.9, y0 + 2.0))
        R((53.9, y0 + 2.0), "left", "", L=4.3); w((xnode, y0 + 2.0), (xnode, ytop))
        t(51.75, y0 + 2.35, f"R{74+i} 1M", fs=6.6, ha="center", va="bottom")
        hyst[key] = VREF * R_SER / R_HYS
    else:
        net((43.6, ytop), sig, side="left", fs=7.0)
        w((43.6, ytop), (xin, ytop))
    # threshold on bottom
    net((43.6, ybot), "+3V3_A", side="left", fs=6.8, color="#555")
    rtop_lab = f"R{60+2*i} {fmt_r(th['rtop'])}"
    R((43.6, ybot), "right", rtop_lab, L=2.4, loc="bottom", fs=6.6)
    w((46.0, ybot), (xin, ybot)); dot((xrb, ybot))
    if key == "H2":
        S.add(elm.ResistorVar().at((xrb, ybot)).down().length(1.8))
        t(xrb - 0.3, ybot - 0.9, "RV1\n10k", fs=6.6, ha="right")
    else:
        R((xrb, ybot), "down", "", L=1.8)
        t(xrb - 0.3, ybot - 0.9, f"R{61+2*i}\n{fmt_r(th['rbot'])}", fs=6.6, ha="right")
    gnd((xrb, ybot - 1.8))
    if not sig_plus:
        dot((xnode, ybot))
        w(cmp_.out, (53.9, y0)); w((53.9, y0), (53.9, y0 - 2.0))
        R((53.9, y0 - 2.0), "left", "", L=4.3); w((xnode, y0 - 2.0), (xnode, ybot))
        t(51.75, y0 - 2.35, f"R{74+i} 1M", fs=6.6, ha="center", va="top")
        if key != "H2":
            rth = th["rtop"] * th["rbot"] / (th["rtop"] + th["rbot"])
            hyst[key] = VREF * rth / R_HYS
        else:
            hyst[key] = None
    dot((53.9, y0))
    # diode to FAULT_N bus
    w((53.9, y0), (54.6, y0))
    S.add(elm.Diode().at((57.2, y0)).left().length(2.6))
    t(55.9, y0 + 0.45, f"D{10+i}", fs=6.6, ha="center", va="bottom")
    dot((57.2, y0))
    t(44.0, y0 + (2.3 if sig_plus else 1.45), f"{'sig < th' if sig_plus else 'sig > th'} → 트립", fs=6.6, color=RED, va="bottom")
xbus = 57.2
w((xbus, 17.6), (xbus, 37.6))
t(56.6, 16.2, "BAT54 ×4", fs=6.6, ha="center", color="#444")
R((xbus, 39.4), "down", "", L=1.8)
t(xbus + 0.3, 38.5, "R50 10k", fs=6.6)
net((xbus, 39.4), "+3V3_A", fs=6.6, color="#555")
t(xbus + 0.3, 37.0, "FAULT_N", fs=7.4, bold=True, color=RED)
w((xbus, 27.4), (60.2, 27.4)); dot((xbus, 27.4))
dot((58.8, 27.4)); C((58.8, 27.4), "down", "C50 1u", L=1.2, loc="bottom", fs=6.6); gnd((58.8, 26.2))
t(59.4, 31.6, "C50: POR — 전원 투입 시 약 10 ms LOW → TRIP", fs=6.6, color="#444", va="center")
# latch U12
u12 = S.ic(61.0, 20.5, 4.0, 8.0, "U12 74LVC1G74", "", left=[("/PRE", 6.9), ("D", 5.4), ("CLK", 3.9), ("/CLR", 1.6)],
          right=[("Q", 6.9), ("/Q", 1.6)], stub=0.8, fs=6.8, fill="#fdf0f0")
w((60.2, 27.4), u12["/PRE"])
w(u12["D"], (59.6, u12["D"][1]), (59.6, u12["CLK"][1]), u12["CLK"]); dot((59.6, u12["CLK"][1]))
w((59.6, u12["CLK"][1]), (59.6, 23.2)); gnd((59.6, 23.2))
t(u12["/Q"][0] + 0.2, u12["/Q"][1], "NC", fs=6.6)
# reset
w(u12["/CLR"], (60.4, u12["/CLR"][1]), (60.4, 18.6), (62.4, 18.6))
dot((62.4, 18.6))
R((62.4, 18.6), "up", "", L=1.3); t(62.7, 19.25, "R51 10k", fs=6.4); w((62.4, 19.9), (65.4, 19.9)); net((65.4, 19.9), "+3V3_A", fs=6.2, color="#555")
S.add(elm.Button().at((62.4, 18.6)).down().length(2.0))
t(62.9, 17.6, "SW1 RESET\n(재무장)", fs=6.8, bold=True, color=RED, va="center")
gnd((62.4, 16.6))
C((60.4, 18.6), "down", "", L=1.2); gnd((60.4, 17.4)); dot((60.4, 18.6))
t(60.2, 17.6, "C51\n100n", fs=6.2, ha="right", va="center")
# Q -> TRIP
w(u12["Q"], (67.2, u12["Q"][1])); net((67.2, u12["Q"][1]), "TRIP", fs=7.6, color=RED)
t(66.0, u12["Q"][1] - 0.9, "→ E-002 Q7 게이트\n→ PB0 TRIP_STAT (R53 1k)\n→ LED3 적색 (R54 1k)", fs=6.6, color=RED, va="top")
t(61.0, 15.7, "/PRE·/CLR 동시 LOW → Q = H (고장 우선)\nMCU 는 /PRE·/CLR 에 연결 없음 → 해제 불가",
  fs=6.6, color=RED, va="top")

# ================= LEDs (bottom-left)
S.frame(0.3, 1.2, 21.4, 12.4, "③ 상태 LED")
leds = [("LED_RUN", "R60 1k", "LED1 녹색 RUN", 10.0), ("LED_WARN", "R61 1k", "LED2 황색 경고 (H2 0.4 %, 45 °C)", 7.4),
        ("+3V3_A", "R62 2.2k", "LED4 녹색 전원", 4.8)]
for nm, rl, ll, y in leds:
    net((4.2, y), nm, side="left", fs=7.0, color="#555" if nm.startswith("+") else "#1f5fa8")
    R((4.2, y), "right", rl, L=2.2, fs=6.6)
    S.add(elm.LED().at((6.4, y)).right().length(2.0))
    w((8.4, y), (9.0, y)); gnd((9.0, y))
    t(10.0, y, ll, fs=6.8)
t(0.9, 2.4, "LED3 TRIP 은 래치 Q 가 직접 구동 (MCU 무관)", fs=6.6, color="#444")

# ================= threshold table
S.frame(21.7, 1.2, 71.7, 12.4, "④ 트립 임계값 — spec.py 에서 계산 (E96, 안전측 반올림)")
slope_T = abs(v_ntc(LIMITS["T_trip_C"] + 0.01) - v_ntc(LIMITS["T_trip_C"] - 0.01)) / 0.02
slope_P = (P_V1 - P_V0) / P_FS * K_PDIV
def heq(k):
    h = hyst[k]
    if h is None: return "교정"
    if k == "P": return f"{h*1e3:.0f} mV ≈ {h/slope_P*1e3:.0f} mbar"
    if k == "T": return f"{h*1e3:.0f} mV ≈ {h/slope_T:.1f} °C"
    return f"{h*1e3:.0f} mV"
rows = [("ch", "목표", "신호 변환", "이상 Vth", "R_top / R_bot", "실제 Vth", "실제 트립", "히스테리시스")]
rows.append(("U10A P", TH["P"]["target"], "(0.5+0.4P)·⅔", f"{TH['P']['ideal']:.4f} V", f"{fmt_r(TH['P']['rtop'])} / {fmt_r(TH['P']['rbot'])}",
             f"{TH['P']['act']:.4f} V", TH["P"]["trip_eq"], heq("P")))
rows.append(("U10B V", TH["V"]["target"], "V_CELL (G=1)", f"{TH['V']['ideal']:.4f} V", f"{fmt_r(TH['V']['rtop'])} / {fmt_r(TH['V']['rbot'])}",
             f"{TH['V']['act']:.4f} V", TH["V"]["trip_eq"], heq("V")))
rows.append(("U11A T", TH["T"]["target"], f"NTC {TH['T']['rntc']/1e3:.2f}k / 10k", f"{TH['T']['ideal']:.4f} V", f"{fmt_r(TH['T']['rtop'])} / {fmt_r(TH['T']['rbot'])}",
             f"{TH['T']['act']:.4f} V", TH["T"]["trip_eq"], heq("T")))
rows.append(("U11B H2", TH["H2"]["target"], "R_L·⅔, 센서 의존", "교정", "10k / RV1 10k", "교정", "calibrate", "교정"))
cx = [22.2, 27.0, 32.8, 39.6, 45.2, 51.8, 57.4, 63.0, 71.2]
top, rh = 10.6, 1.45
for i, r in enumerate(rows):
    y = top - i * rh - rh / 2
    for j, c in enumerate(r):
        t(cx[j] + 0.2, y, c, fs=6.9, bold=(i == 0), color=(RED if (j == 6 and i > 0) else "k"))
S.tbl = (cx, top, rh, len(rows))
t(22.2, 2.3, "전원 = +3V3_A (ADC VREF+ 와 공통 → 비율 오차 상쇄). 압력센서는 +5V 비율식이라 +5V ±x % 가 그대로 트립 오차가 된다 (E-003 5V_MON).",
  fs=6.5, color="#444")
S.finish()
cx, top, rh, n = S.tbl
ax = S.ax
for i in range(n + 1):
    ax.plot([cx[0], cx[-1]], [top - i * rh] * 2, color="k", lw=0.9 if i in (0, 1, n) else 0.5)
for x in cx:
    ax.plot([x, x], [top, top - n * rh], color="k", lw=0.6)
ax.add_patch(Rectangle((cx[0], top - rh), cx[-1] - cx[0], rh, fc="#fbe3e3", ec="none", zorder=0))
fr.text(0.55, 2.05, "주 Notes", fontsize=9, fontweight="bold", va="top")
for i, n_ in enumerate([
        "1. 비교기 출력 HIGH = 정상, LOW = 고장. 어느 한 채널 LOW → 다이오드로 FAULT_N LOW → /PRE → Q = TRIP.",
        "2. 히스테리시스 ≈ 3.3 V × R_src / 1 MΩ (R_src: + 입력 쪽 테브난 저항). 채터링 방지용, 실측 조정.",
        "3. H2 채널 RV1 은 시험가스(1.0 vol% H2 in air)로 교정 후 고정. 교정 전에는 트립 기능 없음으로 취급.",
        "4. 핀 배정은 제안 — ST 데이터시트 (LQFP64 핀 표) 로 확인. TLV3202 는 push-pull 이라 직접 wired-OR 불가 → D10–D13."]):
    fr.text(0.55, 1.78 - i * 0.3, n_, fontsize=7.8, va="top")
save(fig, "E-004_mcu_safety")
print({k: v for k, v in hyst.items()})
