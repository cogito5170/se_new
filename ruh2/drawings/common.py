"""Shared sheet frame, title block and derived design values for RuH2 drawings.
All numbers come from ../spec.py; derived values are computed here."""
import sys, os, math, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import spec
from spec import CELL, VESSEL, LIMITS, BMS
# 산출물은 저장소 밖(무시되는 자리)에 쓴다 -- ruh2.paths 와 같은 규칙
OUTDIR = os.environ.get("RUH2_DRAW_OUT") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "inbox", "ruh2", "drawings")
os.makedirs(OUTDIR, exist_ok=True)
import matplotlib, logging
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["svg.fonttype"] = "none"   # keep text as text in SVG

DATE = "2026-09-29"
NOTE = "설계 제안 — 미검증 (PROPOSAL, NOT VALIDATED)"
W, H = 16.54, 11.69          # A3 landscape, inch

# ---------------------------------------------------------------- E96 helpers
E96 = [1.00,1.02,1.05,1.07,1.10,1.13,1.15,1.18,1.21,1.24,1.27,1.30,1.33,1.37,1.40,1.43,1.47,1.50,
       1.54,1.58,1.62,1.65,1.69,1.74,1.78,1.82,1.87,1.91,1.96,2.00,2.05,2.10,2.15,2.21,2.26,2.32,
       2.37,2.43,2.49,2.55,2.61,2.67,2.74,2.80,2.87,2.94,3.01,3.09,3.16,3.24,3.32,3.40,3.48,3.57,
       3.65,3.74,3.83,3.92,4.02,4.12,4.22,4.32,4.42,4.53,4.64,4.75,4.87,4.99,5.11,5.23,5.36,5.49,
       5.62,5.76,5.90,6.04,6.19,6.34,6.49,6.65,6.81,6.98,7.15,7.32,7.50,7.68,7.87,8.06,8.25,8.45,
       8.66,8.87,9.09,9.31,9.53,9.76]
def e96_near(r):
    dec = 10 ** math.floor(math.log10(r))
    return min((v * dec for v in E96 + [10.0]), key=lambda x: abs(x - r))

def divider(vth, vsup, safe="up"):
    """E96 pair (R_top to vsup, R_bot to GND), both 10k..97.6k, closest to vth on the SAFE side:
    safe='up' -> actual >= ideal (trip early for 'sig < th'), 'down' -> actual <= ideal."""
    vals = [v * 1e4 for v in E96]
    best = None
    for rt in vals:
        for rb in vals:
            va = vsup * rb / (rt + rb)
            if (safe == "up" and va < vth) or (safe == "down" and va > vth):
                continue
            if best is None or abs(va - vth) < abs(best[2] - vth):
                best = (rt, rb, va)
    return best

def fmt_r(r):
    if r >= 1e6: return f"{r/1e6:g}M"
    if r >= 1e3: return f"{r/1e3:g}k"
    return f"{r:g}Ω"

# ---------------------------------------------------------------- derived values
VREF = BMS["vref"]                      # 3.3 V ADC / comparator reference rail
V5 = 5.0                                # pressure-sensor & H2-sensor supply
P_FS = 10.0                             # bar abs, sensor range (spec: 0-10 bar abs)
P_V0, P_V1 = 0.5, 4.5                   # sensor output span (spec)
K_PDIV = 20e3 / (10e3 + 20e3)           # 10k/20k divider
def p_to_vadc(p): return (P_V0 + (P_V1 - P_V0) * p / P_FS) * K_PDIV
def vadc_to_p(v): return (v / K_PDIV - P_V0) / (P_V1 - P_V0) * P_FS

B, R25, T25 = 3950.0, 10e3, 298.15
def r_ntc(tc): return R25 * math.exp(B * (1 / (tc + 273.15) - 1 / T25))
def v_ntc(tc): return VREF * r_ntc(tc) / (10e3 + r_ntc(tc))   # NTC low side, 10k to 3.3 V
def t_from_vntc(v):
    r = 10e3 * v / (VREF - v)
    return 1 / (math.log(r / R25) / B + 1 / T25) - 273.15

TH = {}
v = p_to_vadc(VESSEL["p_trip_bar_abs"])
rt, rb, va = divider(v, VREF, "down")
TH["P"] = dict(sig="P_MON", ideal=v, rtop=rt, rbot=rb, act=va, trip_eq=f"{vadc_to_p(va):.2f} bar abs",
               sense="sig > th", target=f"{VESSEL['p_trip_bar_abs']:.1f} bar abs")
v = v_ntc(LIMITS["T_trip_C"])
rt, rb, va = divider(v, VREF, "up")
TH["T"] = dict(sig="T_VESSEL", ideal=v, rtop=rt, rbot=rb, act=va, trip_eq=f"{t_from_vntc(va):.1f} °C",
               sense="sig < th", target=f"{LIMITS['T_trip_C']} °C", rntc=r_ntc(LIMITS["T_trip_C"]))
v = CELL["V_hw_cutoff"]
rt, rb, va = divider(v, VREF, "up")
TH["V"] = dict(sig="V_CELL", ideal=v, rtop=rt, rbot=rb, act=va, trip_eq=f"{va:.3f} V",
               sense="sig < th", target=f"{CELL['V_hw_cutoff']:.2f} V")
TH["H2"] = dict(sig="H2_MON", ideal=None, rtop=10e3, rbot=None, act=None, trip_eq="calibrate",
                sense="sig > th", target=f"{LIMITS['h2_trip_vol_pct']:.1f} vol% H2")

# current channel
I_GAIN_V_A = BMS["shunt_mohm"] * 1e-3 * BMS["ina_gain"]      # V/A
I_FS = (VREF / 2) / I_GAIN_V_A                                # ± A
I_LSB_mA = BMS["i_lsb_mA"]
V_LSB_mV = VREF / 4095 * 1e3
P_LSB_mbar = V_LSB_mV / 1e3 / K_PDIV / (P_V1 - P_V0) * P_FS * 1e3
P_SHUNT_W = (BMS["shunt_mohm"] * 1e-3) * LIMITS["I_max_A"] ** 2

# power stage (proposal values, computed)
RS_CHG = 0.05; G_CHG = 20                      # INA181A1 on Rs1
K_CHG = RS_CHG * G_CHG                          # V/A feedback
RS_DIS = 0.05
K_DIS_DIV = 1.0e3 / (19.1e3 + 1.0e3)            # 19.1k/1.0k divider on V_SET
K_DIS = K_DIS_DIV / RS_DIS                      # A per V of V_SET
V_PWR = 3.3
P_Q_CHG = (V_PWR - RS_CHG * LIMITS["I_max_A"] - CELL["V_nom"]) * LIMITS["I_max_A"]   # worst ~ low cell
P_Q_DIS = CELL["V_charge_max"] * LIMITS["I_max_A"]
EIS_mV = 20.0 * K_CHG                           # 20 mA pk (spec) -> V_SET mV pk

def sheet(dno, title, scale="NTS"):
    fig = plt.figure(figsize=(W, H))
    # frame
    fr = fig.add_axes([0, 0, 1, 1]); fr.set_xlim(0, W); fr.set_ylim(0, H); fr.axis("off")
    fr.add_patch(Rectangle((0.3, 0.3), W - 0.6, H - 0.6, fill=False, lw=1.6))
    # title block
    tw, th = 6.2, 1.55
    x0, y0 = W - 0.3 - tw, 0.3
    fr.add_patch(Rectangle((x0, y0), tw, th, fill=True, fc="white", ec="k", lw=1.4, zorder=5))
    rows = [y0 + th * f for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
    for y in rows[1:-1]:
        fr.plot([x0, x0 + tw], [y, y], "k", lw=0.8, zorder=6)
    fr.plot([x0 + 2.2, x0 + 2.2], [rows[0], rows[2]], "k", lw=0.8, zorder=6)
    fr.plot([x0 + 3.6, x0 + 3.6], [rows[0], rows[2]], "k", lw=0.8, zorder=6)
    fr.plot([x0 + 4.6, x0 + 4.6], [rows[0], rows[2]], "k", lw=0.8, zorder=6)
    def cell(x, y, lab, val, fs=10.5, bold=False):
        fr.text(x + 0.06, y + th * 0.25 - 0.08, lab, fontsize=6.5, va="top", color="#555", zorder=7)
        fr.text(x + 0.06, y + 0.07, val, fontsize=fs, va="bottom", zorder=7,
                fontweight="bold" if bold else "normal")
    cell(x0, rows[3], "PROJECT", "RuH2-P1  Ni-H2 cell (Ru/C) + RuH2-BMS rev A", 10)
    cell(x0, rows[2], "TITLE", title, 11, True)
    cell(x0, rows[1], "DWG NO.", dno, 12, True)
    cell(x0 + 2.2, rows[1], "REV", "A", 12, True)
    cell(x0 + 3.6, rows[1], "SCALE", scale, 10)
    cell(x0 + 4.6, rows[1], "SHEET", "1 / 1", 10)
    cell(x0, rows[0], "DATE", DATE, 10)
    cell(x0 + 2.2, rows[0], "SOURCE", "spec.py", 10)
    cell(x0 + 3.6, rows[0], "LANG", "KO / EN", 10)
    cell(x0 + 4.6, rows[0], "DRAWN", "Claude", 10)
    fr.text(x0 + tw / 2, rows[4] + 0.1, NOTE, ha="center", va="bottom", fontsize=11.5,
            color="#b00000", fontweight="bold", zorder=7,
            bbox=dict(fc="#fff3f3", ec="#b00000", lw=1.2, boxstyle="round,pad=0.3"))
    return fig, fr

def save(fig, stem):
    fig.savefig(os.path.join(OUTDIR, stem + ".png"), dpi=200)
    fig.savefig(os.path.join(OUTDIR, stem + ".svg"))
    plt.close(fig)
    print("wrote", stem)

if __name__ == "__main__":
    for k, t in TH.items():
        print(k, {a: (round(b, 4) if isinstance(b, float) else b) for a, b in t.items()})
    print("I_FS ±A", I_FS, "I_LSB mA", I_LSB_mA, "V_LSB mV", V_LSB_mV, "P_LSB mbar", P_LSB_mbar)
    print("P_shunt W", P_SHUNT_W, "P_Q_CHG", P_Q_CHG, "P_Q_DIS", P_Q_DIS, "K_DIS", K_DIS, "EIS mV", EIS_mV)
    print("stack layer-sum check:", 4*(0.8+0.5+0.6)+5*0.5, "spec", VESSEL["stack_h_mm"])

# NanumGothic's arrow glyphs shrink to '›' at small sizes: route arrows through mathtext (DejaVu)
from matplotlib.axes import Axes as _Axes
_orig_text = _Axes.text
def _text(self, x, y, s, *a, **k):
    if isinstance(s, str):
        if any(c in s for c in "→←↔"):
            s = s.replace("−", "-").replace("→", r"$\rightarrow$").replace("←", r"$\leftarrow$").replace("↔", r"$\leftrightarrow$")
    return _orig_text(self, x, y, s, *a, **k)
_Axes.text = _text
