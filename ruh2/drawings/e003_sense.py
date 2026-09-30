from schem import *
import math

fig, fr = sheet("RUH2-E-003", "측정 AFE 회로도 / Sensing Front-End")
fr.text(0.55, 11.2, "RUH2-E-003  측정 아날로그 전단 — 전류 · 셀 전압 · 압력 · 온도 · H2", fontsize=15, fontweight="bold", va="top")
S = Sch(fig, (0.45, 2.3, 15.65, 8.6), (0, 72), (1.0, 41.0))
w, t, R, C, gnd, dot, net = S.w, S.t, S.R, S.C, S.gnd, S.dot, S.net
def vdd(p, name): S.add(elm.Vdd().at(p).label(name, fontsize=7.4))
def capg(p, lab, L=1.5):
    C(p, "down", lab, L=L, loc="bottom", fs=7.2); gnd((p[0], p[1] - L)); dot(p)
FC_I = 1 / (2 * math.pi * 100 * 100e-9)
R_TH_P = 10e3 * 20e3 / 30e3
FC_P = 1 / (2 * math.pi * R_TH_P * 100e-9)
def ntc_lsb(T):
    dv = (v_ntc(T + 0.01) - v_ntc(T - 0.01)) / 0.02
    return V_LSB_mV / 1e3 / abs(dv)

# ============ ① current
S.frame(0.3, 21.6, 23.9, 40.9, "① 전류 I_MON — INA240A2 (G=50)")
u8 = S.ic(8.0, 29.0, 5.6, 7.0, "U8 INA240A2", "", left=[("IN+", 5.5), ("IN−", 3.5)], right=[("OUT", 4.5)],
          bottom=[("REF1", 1.3), ("REF2", 2.8), ("GND", 4.6)], top=[("VS", 5.2)])
net((5.0, 34.5), "SH_P", side="left"); w((5.0, 34.5), u8["IN+"])
net((5.0, 32.5), "SH_N", side="left"); w((5.0, 32.5), u8["IN−"])
t(2.2, 36.1, "E-002 R21 Kelvin", fs=7.0, color="#444", ha="left")
vdd(u8["VS"], "+3V3_A")
gnd(u8["GND"])
yref = 26.6
w(u8["REF1"], (9.3, yref), (5.0, yref)); w(u8["REF2"], (10.8, yref), (9.3, yref)); dot((9.3, yref))
vdd((5.0, 30.0), "+3V3_A")
R((5.0, 30.0), "down", "R30 10k", L=2.0, loc="bottom", fs=7.2); dot((5.0, 28.0))
w((5.0, 28.0), (5.0, yref)); dot((5.0, yref))
R((5.0, yref), "down", "R31 10k", L=2.0, loc="bottom", fs=7.2); gnd((5.0, yref - 2.0))
w((5.0, 28.0), (3.0, 28.0)); C((3.0, 28.0), "down", "C31\n100n", L=1.4, loc="top", fs=7.2); gnd((3.0, 26.6)); dot((3.0, 28.0))
t(6.2, yref + 0.15, "REF 1.65 V", fs=7.0, color="#1f5fa8", va="bottom")
w(u8["OUT"], (15.2, u8["OUT"][1]))
R((15.2, 33.5), "right", "R32 100Ω", L=2.2, fs=7.2)
w((17.4, 33.5), (19.6, 33.5)); capg((17.9, 33.5), "C32\n100n", L=1.5)
net((19.6, 33.5), "I_MON")
t(19.7, 31.5, "ADC1_IN1 (PA0)", fs=7.0, color="#1f5fa8")
t(12.0, 24.4, f"V(I_MON) = 1.65 V + {I_GAIN_V_A:.2f} V/A · I", fs=7.6, ha="left")
t(12.0, 23.6, f"FS ±{I_FS:.1f} A · LSB {I_LSB_mA:.2f} mA", fs=7.6, ha="left")
t(12.0, 22.8, f"RC fc = {FC_I/1e3:.1f} kHz (EIS ≤ 5 kHz)", fs=7.6, ha="left")
t(1.0, 22.3, "REF 핀은 저임피던스 입력 → 분배기 오차 주의\n대안: REF1→+3V3_A, REF2→GND (내부 ½)", fs=6.8, color="#8a0000", ha="left", va="bottom")

# ============ ② cell voltage
S.frame(24.2, 21.6, 47.8, 40.9, "② 셀 전압 V_CELL — OPA2333 차동증폭 (G=1)")
yn, yp = 33.6, 32.36
u9 = S.add(elm.Opamp().right().anchor("in1").at((34.0, yn)))
t(35.0, yn + 1.5, "U9A OPA2333", fs=8, bold=True, ha="center", va="bottom")
net((28.2, yn), "VS_N", side="left"); R((28.2, yn), "right", "R35 10k", L=2.4, fs=7.2)
net((28.2, yp), "VS_P", side="left"); R((28.2, yp), "right", "R33 10k", L=2.4, loc="bottom", fs=7.2)
w((30.6, yn), (34.0, yn)); w((30.6, yp), (34.0, yp))
dot((31.6, yp)); R((31.6, yp), "down", "R34 10k", L=2.2, loc="bottom", fs=7.2); gnd((31.6, yp - 2.2))
dot((33.0, yn)); w((33.0, yn), (33.0, 36.0)); R((33.0, 36.0), "right", "R36 10k", L=3.8, fs=7.2)
w((36.8, 36.0), (36.8, u9.out[1])); w(u9.out, (37.4, u9.out[1])); dot((36.8, u9.out[1]))
R((37.4, u9.out[1]), "right", "R37 100Ω", L=2.2, fs=7.2)
w((39.6, u9.out[1]), (42.4, u9.out[1])); capg((40.6, u9.out[1]), "C37\n100n", L=1.5)
net((42.4, u9.out[1]), "V_CELL")
t(42.5, u9.out[1] - 0.9, "ADC1_IN2 (PA1)\n+ U10B 비교기", fs=7.0, color="#1f5fa8", va="top")
t(25.0, 27.0, "V_CELL = VS_P − VS_N  (4 × 10k, 0.1 % 정합)", fs=7.6)
t(25.0, 26.1, f"범위 0–3.3 V · LSB {V_LSB_mV:.3f} mV", fs=7.6)
t(25.0, 25.2, f"CMRR(저항) ≥ (1+G)/(4·0.001) = {2/0.004:.0f} ({20*math.log10(500):.0f} dB)", fs=7.6)
t(25.0, 24.3, f"셀 범위 {CELL['V_hw_cutoff']:.2f}–{CELL['V_charge_max']:.2f} V → ADC 여유 충분", fs=7.6)
t(25.0, 23.0, "U9: +3V3_A 단전원, U9B 예비 (입력 GND, 출력 개방 금지 → 버퍼 접속)", fs=6.9, color="#444")

# ============ ③ pressure
S.frame(48.1, 21.6, 71.7, 40.9, "③ 압력 P_MON — 0–10 bar abs, 0.5–4.5 V")
j2 = S.ic(49.8, 29.8, 3.0, 5.4, "J2 압력센서", "PX3-class, off-board", right=[("1 +5V", 4.3), ("2 GND", 2.7), ("3 OUT", 1.1)], stub=0.8)
w(j2["1 +5V"], (55.0, 34.1)); vdd((55.0, 34.1), "+5V")
w(j2["2 GND"], (54.4, 32.5)); gnd((54.4, 32.5))
R(j2["3 OUT"], "right", "R38 10k", L=2.4, fs=7.2)
w((56.0, 30.9), (60.8, 30.9)); dot((57.0, 30.9))
R((57.0, 30.9), "down", "R39 20k", L=2.2, loc="top", fs=7.2); gnd((57.0, 28.7))
capg((59.0, 30.9), "C38\n100n", L=1.5)
net((60.8, 30.9), "P_MON")
t(60.9, 29.5, "ADC1_IN3 (PA2)\n+ U10A 비교기", fs=7.0, color="#1f5fa8", va="top")
# +5V monitor
vdd((67.8, 36.3), "+5V")
R((67.8, 36.3), "down", "R43\n10k", L=1.8, loc="top", fs=7.0); dot((67.8, 34.5))
R((67.8, 34.5), "down", "R44\n10k", L=1.8, loc="top", fs=7.0); gnd((67.8, 32.7))
w((67.8, 34.5), (68.6, 34.5)); net((68.6, 34.5), "5V_MON", fs=7.0)
t(66.0, 31.6, "ADC1_IN9 (PC3)\n비율 보정용", fs=6.8, color="#1f5fa8", va="top")
t(49.0, 26.9, f"V_out = {P_V0} + {(P_V1-P_V0)/P_FS:.1f}·P [V]  →  V_ADC = ⅔·V_out", fs=7.6)
t(49.0, 26.0, f"0 bar → {p_to_vadc(0):.3f} V · 10 bar → {p_to_vadc(10):.3f} V", fs=7.6)
t(49.0, 25.1, f"트립 {VESSEL['p_trip_bar_abs']:.1f} bar abs → {p_to_vadc(VESSEL['p_trip_bar_abs']):.3f} V · LSB {P_LSB_mbar:.1f} mbar", fs=7.6)
t(49.0, 24.2, f"RC: R_th {R_TH_P/1e3:.2f}k · 100 nF → fc {FC_P:.0f} Hz", fs=7.6)
t(49.0, 23.0, f"주의: 센서 상한 {P_FS:.0f} bar < 파열판 {VESSEL['p_burst_disk_bar']:.0f} bar — 10 bar 초과는 포화", fs=6.9, color="#8a0000")

# ============ ④ NTC
S.frame(0.3, 1.2, 23.9, 21.2, "④ 온도 T_VESSEL / T_AMB — NTC 10k B3950")
for i, (nm, adc, yy) in enumerate((("T_VESSEL", "ADC1_IN4 (PA3) + U11A", 16.0), ("T_AMB", "ADC1_IN6 (PC0)", 8.8))):
    x = 4.0
    vdd((x, yy + 2.6), "+3V3_A")
    R((x, yy + 2.6), "down", f"R4{1+i} 10k 0.1%", L=2.2, loc="top", fs=7.0)
    dot((x, yy + 0.4)); w((x, yy + 0.4), (x + 5.4, yy + 0.4))
    capg((x + 1.8, yy + 0.4), f"C4{1+i} 100n", L=1.5)
    net((x + 5.4, yy + 0.4), nm, fs=7.4)
    t(x + 5.5, yy - 0.5, adc, fs=6.8, color="#1f5fa8", va="top")
    w((x, yy + 0.4), (x, yy - 0.6))
    S.add(elm.Thermistor().at((x, yy - 0.6)).down().length(2.0).label(f"NTC{1+i}", loc="top", fontsize=7.0))
    gnd((x, yy - 2.6))
t(1.0, 4.2, "NTC 는 J3 (1-2: 용기벽, 3-4: 주변) 로 연결 — off-board", fs=6.9, color="#444")
# temperature table
tx, ty = 14.8, 18.9
t(tx, ty, "T °C   R_NTC     V", fs=7.2, bold=True, family="NanumGothicCoding")
for k, T in enumerate((0, 10, 25, 45, 55)):
    t(tx, ty - 0.8 * (k + 1), f"{T:>4}   {r_ntc(T)/1e3:5.2f}k  {v_ntc(T):.3f}", fs=7.2, family="NanumGothicCoding",
      color="#b00000" if T == LIMITS['T_trip_C'] else "k")
t(tx, ty - 5.2, f"LSB: {ntc_lsb(25)*1e3:.0f} m°C @25 °C\n     {ntc_lsb(55)*1e3:.0f} m°C @55 °C", fs=7.0, va="top")
t(1.0, 2.6, f"V = 3.3·R_NTC/(10k+R_NTC), R_NTC = 10k·exp(B(1/T − 1/298.15)), B = {B:.0f}", fs=6.9, color="#444")

# ============ ⑤ H2
S.frame(24.2, 1.2, 47.8, 21.2, "⑤ H2 누설 H2_MON — TGS2616-C00 class")
j4 = S.ic(34.0, 12.0, 3.2, 6.0, "J4", "", left=[("1", 5.0), ("2", 3.0), ("3", 1.0)],
          right=[("1 ", 5.0), ("2 ", 3.0), ("3 ", 1.0)], stub=0.8)
t(29.0, 18.8, "sensor (off-board)", fs=6.9, color="#444", ha="center")
w((27.5, 17.0), j4["1"]); dot((30.2, 17.0))
S.add(elm.ResistorVar().at((27.5, 17.0)).down().length(4.0).label("R_S", loc="top", fontsize=7.0))
w((27.5, 13.0), j4["3"])
S.add(elm.Resistor().at((30.2, 17.0)).down().length(2.0).label("R_H\nheater", loc="bottom", fontsize=6.8))
w((30.2, 15.0), j4["2"])
t(27.5, 10.6, "J4: 1 = +5V (V_H, V_C), 2 = heater RTN, 3 = V_OUT", fs=6.8, color="#444")
w(j4["1 "], (38.8, 17.0)); vdd((38.8, 17.0), "+5V")
w(j4["2 "], (38.8, 15.0)); gnd((38.8, 15.0))
w(j4["3 "], (40.4, 13.0)); dot((39.6, 13.0))
R((39.6, 13.0), "down", "RL 10k\n(조정)", L=2.2, loc="bottom", fs=6.8); gnd((39.6, 10.8))
R((40.4, 13.0), "right", "R45 10k", L=2.2, fs=7.0)
w((42.6, 13.0), (46.6, 13.0)); dot((43.0, 13.0))
R((43.0, 13.0), "down", "R46 20k", L=2.2, loc="bottom", fs=7.0); gnd((43.0, 10.8))
capg((45.3, 13.0), "C46\n100n", L=1.5)
w((46.6, 13.0), (46.6, 15.6)); net((46.5, 15.6), "H2_MON", side="left", fs=7.2)
t(44.8, 16.4, "ADC1_IN7 (PC1) + U11B", fs=6.8, color="#1f5fa8", va="bottom", ha="center")
t(25.0, 7.4, "V_RL = 5 V · RL / (R_S + RL) · ⅔ → H2 증가 시 R_S 감소, 출력 증가", fs=7.2)
t(25.0, 6.5, f"경보 {LIMITS['h2_alarm_vol_pct']:.1f} vol% (펌웨어) · 트립 {LIMITS['h2_trip_vol_pct']:.1f} vol% (하드웨어, E-004 RV1)", fs=7.2)
t(25.0, 5.6, f"LFL {LIMITS['h2_LFL_vol_pct']:.0f} vol% 의 {LIMITS['h2_trip_vol_pct']/LIMITS['h2_LFL_vol_pct']*100:.0f} % 에서 트립", fs=7.2)
t(25.0, 4.4, "교정 필수: 시험가스로 RL · 임계값을 맞춘다. 예열 중 출력이 높음 →", fs=6.9, color="#8a0000")
t(25.0, 3.6, "전원 투입 후 예열 시간(데이터시트) 경과 뒤 SW1 로 재무장", fs=6.9, color="#8a0000")

# ============ ADC table
S.frame(48.1, 1.2, 71.7, 21.2, "⑥ ADC 채널 배정 (STM32G474RE, VREF+ = 3.3 V)")
rows = [("채널", "핀", "넷", "범위 / LSB"),
        ("ADC1_IN1", "PA0", "I_MON", f"±{I_FS:.1f} A / {I_LSB_mA:.2f} mA"),
        ("ADC1_IN2", "PA1", "V_CELL", f"0–3.3 V / {V_LSB_mV:.3f} mV"),
        ("ADC1_IN3", "PA2", "P_MON", f"0–10 bar / {P_LSB_mbar:.1f} mbar"),
        ("ADC1_IN4", "PA3", "T_VESSEL", f"NTC / {ntc_lsb(55)*1e3:.0f} m°C @55"),
        ("ADC1_IN6", "PC0", "T_AMB", f"NTC / {ntc_lsb(25)*1e3:.0f} m°C @25"),
        ("ADC1_IN7", "PC1", "H2_MON", "0–3.3 V / 교정"),
        ("ADC1_IN8", "PC2", "I_CHG_FB", f"0–3.3 A / {V_LSB_mV/K_CHG:.2f} mA"),
        ("ADC1_IN9", "PC3", "5V_MON", "÷2 / 1.61 mV")]
cx = [48.8, 54.4, 58.2, 62.8, 71.2]
top = 19.2; rh = 1.45
for i, r in enumerate(rows):
    y = top - i * rh
    for j, c in enumerate(r):
        t(cx[j] + 0.25, y - rh / 2, c, fs=7.4, bold=(i == 0), va="center")
S.tbl = (cx, top, rh, len(rows))
t(48.8, top - len(rows) * rh - 0.6, "핀은 제안 — STM32G474 데이터시트 핀 표로 확인할 것.\n12-bit, 1 LSB = 3.3 V/4095. 샘플시간 ≥ 47.5 cyc (RC 100 nF 가 전하 공급)",
  fs=6.8, va="top", color="#444")
S.finish()
cx, top, rh, n = S.tbl
ax = S.ax
for i in range(n + 1):
    ax.plot([cx[0], cx[-1]], [top - i * rh] * 2, color="k", lw=0.9 if i in (0, 1, n) else 0.5)
for x in cx:
    ax.plot([x, x], [top, top - n * rh], color="k", lw=0.6)
ax.add_patch(Rectangle((cx[0], top - rh), cx[-1] - cx[0], rh, fc="#eef4fb", ec="none", zorder=0))

fr.text(0.55, 2.05, "주 Notes", fontsize=9, fontweight="bold", va="top")
for i, n_ in enumerate([
        "1. 모든 IC 는 VS 핀에 100 nF 디커플링 (도면 생략). AGND 는 J1-2 PGND 스타점과 한 점 접속.",
        "2. 안티앨리어스 RC 의 C 는 C0G/NP0 권장. 트립 비교기 입력은 같은 RC 뒤에서 분기 (E-004).",
        "3. 수치는 spec.py 에서 계산 — 전류 LSB = 3.3/4095/(10 mΩ·50).",
        "4. 압력센서 출력은 +5V 비율식: ADC 는 3.3 V 기준이므로 5V_MON 으로 보정한다."]):
    fr.text(0.55, 1.78 - i * 0.3, n_, fontsize=8, va="top")
save(fig, "E-003_sense")
