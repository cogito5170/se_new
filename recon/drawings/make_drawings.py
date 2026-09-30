"""RECON-R1 engineering drawings: E-001, E-002, S-001, M-001, H-001.

All physical numbers are read from ../spec.py (single source of truth).  Values that are
not in spec.py and are introduced here are drawing-level proposals and are flagged [A]
on the sheet.  Style follows SE/ruh2/drawings (schemdraw + matplotlib, NanumGothic,
A3 landscape, title block, "설계 제안 — 미검증").

    python3 make_drawings.py          -> writes *.png (200 dpi) + *.svg next to this file
"""
import sys, os, math, warnings, logging
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import spec
from spec import PARTS, MECH, DRIVE, POWER, P_AVG, P_PEAK, E_WH, RUNTIME_H, I_PEAK, DATA, MAP

OUTDIR = os.environ.get("RECON_DRAW_OUT") or HERE
os.makedirs(OUTDIR, exist_ok=True)

import matplotlib
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch, FancyArrowPatch, Circle, Polygon, Arc
from matplotlib.axes import Axes as _Axes
plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["svg.fonttype"] = "none"
import schemdraw, schemdraw.elements as elm
schemdraw.config(font="NanumGothic", fontsize=8.5, lw=1.1)

# NanumGothic arrows shrink at small sizes: route through mathtext (same trick as ruh2/drawings/common.py)
_orig_text = _Axes.text
def _text(self, x, y, s, *a, **k):
    if isinstance(s, str) and any(c in s for c in "→←↔"):
        s = s.replace("→", r"$\rightarrow$").replace("←", r"$\leftarrow$").replace("↔", r"$\leftrightarrow$")
    return _orig_text(self, x, y, s, *a, **k)
_Axes.text = _text

DATE = "2026-09-29"
NOTE = "설계 제안 — 미검증 (PROPOSAL, NOT VALIDATED)"
PROJECT = "RECON-R1  지상 정찰 로버 / ground recon rover"
W, H = 16.54, 11.69          # A3 landscape, inch
MM = 25.4
RED, BLUE, GREEN, GREY = "#b00000", "#1f5fa8", "#2a7a2a", "#444"

# ============================================================== derived values (from spec only)
BAT = PARTS["battery"]
V_NOM, V_MIN, V_MAX = BAT["V_nom"], BAT["V_min"], BAT["V_max"]

def pw(key):
    """POWER entry by substring (spec keys are descriptive strings)."""
    ks = [k for k in POWER if key in k]
    assert len(ks) == 1, (key, ks)
    return POWER[ks[0]]

P_JET, P_LID, P_MCU, P_MOT, P_DRV, P_GNSS = (pw("Jetson Orin"), pw("Livox"), pw("STM32"), pw("Motors"),
                                              pw("drivers"), pw("GNSS"))
ETA_DCDC = 0.90                                  # [A] converter efficiency for fuse sizing
I_MOT_BUS = P_MOT[1] / V_MIN                     # motor bus peak at V_min
I_DRV = I_MOT_BUS / 2                            # per MDD20A (2 motors each)
I_JET = P_JET[1] / V_MIN                         # direct pack feed (no DC-DC), worst at V_min
I_LID = P_LID[1] / V_MIN
P_5V = P_MCU[1] + P_DRV[1]                       # upper bound: whole "drivers, fans, relay" line on 5 V
I_5V = P_5V / ETA_DCDC / V_MIN
M = PARTS["motor"]
I_STALL_AT_VBAT = M["stall_A_24V"] * V_NOM / M["rated_V"]   # stall current scales ~ V (R_winding const)

# fuse -> wire gauge (chassis wiring ampacity, in air, bundle-free) [A]
AWG_AMP = {12: 41, 14: 32, 18: 16, 20: 11, 22: 7, 26: 2.2, 28: 1.4}
FUSES = [  # (ref, rating A, design current A, AWG, what)
    ("F1", 30, I_PEAK, 12, "주 퓨즈 (팩 → 전체)"),
    ("F2", 15, I_DRV, 14, "U1 MDD20A (M1, M2)"),
    ("F3", 15, I_DRV, 14, "U2 MDD20A (M3, M4)"),
    ("F4", 5, I_JET, 18, "U3 이상적 다이오드 → Jetson 직결"),
    ("F5", 3, I_5V, 20, "U4 D36V50F5 5 V 레일"),
    ("F6", 3, I_LID, 20, "U8 Livox Mid-360 직결"),
    ("F7", 1, None, 22, "K1 코일 루프 (R5 포함)"),
]
for ref, fa, ia, awg, _ in FUSES:
    assert AWG_AMP[awg] >= fa, (ref, awg)
    if ia is not None:
        assert ia < fa, (ref, ia, fa)

# sensing [A]
RS1_MOHM = 2.0
INA_FS_A = 81.92e-3 / (RS1_MOHM * 1e-3)          # INA226 shunt full scale 81.92 mV [DS]
P_RS1 = I_PEAK ** 2 * RS1_MOHM * 1e-3
RDIV_T, RDIV_B = 100e3, 22e3
K_DIV = RDIV_B / (RDIV_T + RDIV_B)
V_ADC_MAX = V_MAX * K_DIV
assert V_ADC_MAX < 3.3

# MCU pin map (NUCLEO-H753ZI, LQFP144; same pinout as H743ZI2) -- used by E-001, E-002 and H-001
PIN = dict(
    ENC1=("TIM2", "PA15", "PB3", "AF1"), ENC2=("TIM3", "PB4", "PB5", "AF2"),
    ENC3=("TIM4", "PD12", "PD13", "AF2"), ENC4=("TIM8", "PC6", "PC7", "AF3"),
    PWM=[("TIM1_CH1", "PE9"), ("TIM1_CH2", "PE11"), ("TIM1_CH3", "PE13"), ("TIM1_CH4", "PE14")],
    DIR=["PF12", "PF13", "PF14", "PF15"],
    SPI=[("SPI1_SCK", "PA5"), ("SPI1_MISO", "PA6"), ("SPI1_MOSI", "PD7"), ("IMU_CS", "PD14"), ("IMU_INT1", "PG1")],
    PPS=("TIM5_CH1", "PA0"),
    USB=("OTG_FS D-/D+", "PA11/PA12"), UART=("USART2 TX/RX", "PD5/PD6"),
    ESTOP="PE2", MOTOR_EN="PG4", MOT_SENSE=("ADC12_INP15", "PA3"), VBAT=("ADC123_INP10", "PC0"),
    I2C=("I2C1 SCL/SDA", "PB8/PB9"), INA_ALERT="PG3",
)

# mechanical (spec) in mm
L_, W_, HB = MECH["L"] * 1e3, MECH["W"] * 1e3, MECH["H_body"] * 1e3
GC, WR, WB, TR = MECH["ground_clear"] * 1e3, MECH["wheel_r"] * 1e3, MECH["wheelbase"] * 1e3, MECH["track"] * 1e3
LH, LX = MECH["lidar_h"] * 1e3, MECH["lidar_x"] * 1e3
CH, CX, CP = MECH["cam_h"] * 1e3, MECH["cam_x"] * 1e3, MECH["cam_pitch_deg"]
COGH = MECH["cog_h"] * 1e3
DECK = GC + HB                                   # deck top above ground
MAST_TOP = DECK + PARTS["chassis"]["mast_h_mm"]
ROLL_DEG = MECH["roll_over_deg"]
PITCH_DEG = MECH["pitch_over_deg"]
MAX_SLOPE = MECH["max_slope_deg"]
ROLL_CHK = math.degrees(math.atan((TR / 2) / COGH))
PITCH_CHK = math.degrees(math.atan((WB / 2) / COGH))
assert abs(ROLL_CHK - ROLL_DEG) < 0.01 and abs(PITCH_CHK - PITCH_DEG) < 0.01
WHEEL_W = float(PARTS["chassis"]["wheel_w_mm"])
MOTOR_D = 37.0                                   # Pololu "37D" gearmotor can diameter [DS]
LIDAR_BOX = (65.0, 65.0, 60.0)                   # Mid-360 envelope L x W x H mm [DS, verify]
CAM_GROUND = CH / math.tan(math.radians(-CP))    # optical axis hits ground here (ahead of cam)

# K1 coil: 12 V automotive coil + series resistor (chosen over 24 V coil: a 24 V coil will not pull in at 12 V)
K1_COIL_R = 80.0          # [A] 12 V / 150 mA coil
K1_V_MAXCONT = 13.5       # [A] coil continuous max
K1_V_PULLIN = 0.70 * 12   # [A] must-operate 70 % of nominal
_rs = K1_COIL_R * (V_MAX / K1_V_MAXCONT - 1)
K1_RS = min((10, 12, 15, 18, 20, 22, 27, 33), key=lambda r: abs(r - _rs) if r >= _rs else 1e9)   # E12 >= needed
K1_V_HI = V_MAX * K1_COIL_R / (K1_COIL_R + K1_RS)
K1_V_LO = V_MIN * K1_COIL_R / (K1_COIL_R + K1_RS)
K1_P_RS = (V_MAX / (K1_COIL_R + K1_RS)) ** 2 * K1_RS
K1_I = V_MAX / (K1_COIL_R + K1_RS)
assert K1_V_HI <= K1_V_MAXCONT and K1_V_LO >= K1_V_PULLIN, (K1_V_HI, K1_V_LO)
HOLDUP_MS = 470e-6 * (V_MIN - 9.0) / I_JET * 1e3            # C1 ride-through to Jetson 9 V min

# ---- spec consistency checks (reported, not fixed); each is re-evaluated against the live spec
ISSUES = []
if TR < W_ + WHEEL_W:
    ISSUES.append(f"track {TR:.0f} mm < 차체 폭 {W_:.0f} + 휠 폭 {WHEEL_W:.0f}: 바퀴·차체 간섭")
if abs(MAX_SLOPE - min(ROLL_DEG, PITCH_DEG)) > 0.01:
    ISSUES.append(f"max_slope_deg {MAX_SLOPE:.1f}° ≠ min(roll {ROLL_DEG:.1f}°, pitch {PITCH_DEG:.1f}°)")
if GC > WR - MOTOR_D / 2 + 1.0:
    ISSUES.append(f"ground_clear {GC:.0f} mm > 37D 모터 아랫면 {WR - MOTOR_D/2:.1f} mm: 실효 지상고는 모터가 결정")
if abs(PARTS["gnss"]["power_W"] - P_GNSS[0]) > 1e-9:
    ISSUES.append(f"GNSS 전력: PARTS gnss power_W={PARTS['gnss']['power_W']} W ≠ POWER 평균 {P_GNSS[0]} W")
if "camera" in PARTS["dcdc_5"]["role"]:
    ISSUES.append(f"PARTS dcdc_5 role '{PARTS['dcdc_5']['role']}' 에 camera 가 남아 있음: IMX219 는 Jetson CSI 급전 "
                  "(도면의 5 V 부하 목록에서는 뺐음)")
if not (0 <= MAST_TOP - LH <= LIDAR_BOX[2]):
    ISSUES.append(f"마스트 끝 {MAST_TOP:.0f} mm 와 lidar_h {LH:.0f} mm 가 도립 LiDAR 외형({LIDAR_BOX[2]:.0f} mm) 안에서 안 맞음")


# ============================================================== sheet frame + title block
def sheet(dno, title, scale="NTS"):
    fig = plt.figure(figsize=(W, H))
    fr = fig.add_axes([0, 0, 1, 1]); fr.set_xlim(0, W); fr.set_ylim(0, H); fr.axis("off")
    fr.add_patch(Rectangle((0.3, 0.3), W - 0.6, H - 0.6, fill=False, lw=1.6))
    tw, th = 6.2, 1.55
    x0, y0 = W - 0.3 - tw, 0.3
    fr.add_patch(Rectangle((x0, y0), tw, th, fill=True, fc="white", ec="k", lw=1.4, zorder=5))
    rows = [y0 + th * f for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
    for y in rows[1:-1]:
        fr.plot([x0, x0 + tw], [y, y], "k", lw=0.8, zorder=6)
    for xx in (2.2, 3.6, 4.6):
        fr.plot([x0 + xx, x0 + xx], [rows[0], rows[2]], "k", lw=0.8, zorder=6)
    def cell(x, y, lab, val, fs=10.5, bold=False):
        fr.text(x + 0.06, y + th * 0.25 - 0.08, lab, fontsize=6.5, va="top", color="#555", zorder=7)
        fr.text(x + 0.06, y + 0.07, val, fontsize=fs, va="bottom", zorder=7, fontweight="bold" if bold else "normal")
    cell(x0, rows[3], "PROJECT", PROJECT, 10)
    cell(x0, rows[2], "TITLE", title, 11, True)
    cell(x0, rows[1], "DWG NO.", dno, 12, True)
    cell(x0 + 2.2, rows[1], "REV", "A", 12, True)
    cell(x0 + 3.6, rows[1], "SCALE", scale, 10)
    cell(x0 + 4.6, rows[1], "SHEET", "1 / 1", 10)
    cell(x0, rows[0], "DATE", DATE, 10)
    cell(x0 + 2.2, rows[0], "SOURCE", "recon/spec.py", 10)
    cell(x0 + 3.6, rows[0], "UNITS", "mm · V · A", 10)
    cell(x0 + 4.6, rows[0], "DRAWN", "Claude", 10)
    fr.text(x0 + tw / 2, rows[4] + 0.1, NOTE, ha="center", va="bottom", fontsize=11.5, color=RED,
            fontweight="bold", zorder=7, bbox=dict(fc="#fff3f3", ec=RED, lw=1.2, boxstyle="round,pad=0.3"))
    return fig, fr

def save(fig, stem):
    fig.savefig(os.path.join(OUTDIR, stem + ".png"), dpi=200)
    fig.savefig(os.path.join(OUTDIR, stem + ".svg"))
    plt.close(fig)
    print("wrote", stem)

def mm_axes(fig):
    ax = fig.add_axes([0, 0, 1, 1], zorder=2)
    ax.set_xlim(0, W * MM); ax.set_ylim(0, H * MM); ax.set_aspect("equal"); ax.axis("off")
    ax.patch.set_alpha(0)
    return ax

def header(ax, text, sub=None, mm=True):
    if mm:
        ax.text(14, 285, text, fontsize=15, fontweight="bold", va="top")
        if sub: ax.text(14, 276.5, sub, fontsize=9.3, va="top", color="#333")
    else:
        ax.text(0.55, 11.2, text, fontsize=15, fontweight="bold", va="top")
        if sub: ax.text(0.55, 10.86, sub, fontsize=9.3, va="top", color="#333")


# ============================================================== schemdraw helper (as ruh2/drawings/schem.py)
class Sch:
    def __init__(self, fig, rect_in, xlim, ylim):
        x0, y0, w, h = rect_in
        self.ax = fig.add_axes([x0 / W, y0 / H, w / W, h / H])
        self.d = schemdraw.Drawing(canvas=self.ax, show=False)
        self.xlim, self.ylim = xlim, ylim
        self.texts, self.boxes, self.frames, self.dashes = [], [], [], []
    def add(self, e): return self.d.add(e)
    def w(self, *pts, color="k", lw=1.1):
        for a, b in zip(pts[:-1], pts[1:]):
            self.d.add(elm.Line(color=color, lw=lw).at(a).to(b))
    def dot(self, p): self.d.add(elm.Dot(radius=0.12).at(p))
    def gnd(self, p): self.d.add(elm.Ground().at(p))
    def t(self, x, y, s, fs=8, ha="left", va="center", color="k", bold=False, box=False, **kw):
        bb = dict(fc="white", ec="none", pad=0.4) if box is True else box if box else None
        self.texts.append((x, y, s, dict(fontsize=fs, ha=ha, va=va, color=color,
                                        fontweight="bold" if bold else "normal", bbox=bb, zorder=10, **kw)))
    def net(self, p, name, side="right", color=BLUE, fs=7.4):
        x, y = p
        self.t(x + (0.15 if side == "right" else -0.15), y, name, fs=fs, ha="left" if side == "right" else "right",
               color=color, box=dict(fc="#eef4fb", ec=color, lw=0.7, boxstyle="round,pad=0.25"))
    def ic(self, x0, y0, w, h, name, part, left=(), right=(), bottom=(), top=(), stub=0.8, fs=7.2, fill="#fafafa"):
        self.boxes.append((x0, y0, w, h, fill))
        pins = {}
        for n, yy in left:
            self.w((x0 - stub, y0 + yy), (x0, y0 + yy)); pins[n] = (x0 - stub, y0 + yy)
            self.t(x0 + 0.15, y0 + yy, n, fs=fs)
        for n, yy in right:
            self.w((x0 + w, y0 + yy), (x0 + w + stub, y0 + yy)); pins[n] = (x0 + w + stub, y0 + yy)
            self.t(x0 + w - 0.15, y0 + yy, n, fs=fs, ha="right")
        for n, xx in bottom:
            self.w((x0 + xx, y0 - stub), (x0 + xx, y0)); pins[n] = (x0 + xx, y0 - stub)
            self.t(x0 + xx, y0 + 0.2, n, fs=fs, ha="center", va="bottom")
        for n, xx in top:
            self.w((x0 + xx, y0 + h), (x0 + xx, y0 + h + stub)); pins[n] = (x0 + xx, y0 + h + stub)
            self.t(x0 + xx, y0 + h - 0.2, n, fs=fs, ha="center", va="top")
        self.t(x0 + w / 2, y0 + h + 0.25, name, fs=8.4, ha="center", va="bottom", bold=True)
        if part:
            self.t(x0 + w / 2, y0 - (stub + 1.3 if bottom else 0.25), part, fs=7.0, ha="center", va="top", color="#333")
        return pins
    def frame(self, x0, y0, x1, y1, title, color="#777"):
        self.frames.append((x0, y0, x1, y1, color))
        self.t(x0 + 0.3, y1 - 0.3, title, fs=9.2, va="top", bold=True, color=color)
    def dash(self, p, q, color="#555"):
        self.dashes.append((p, q, color))
    def finish(self):
        self.d.draw(show=False)
        ax = self.ax
        for (x0, y0, w, h, fill) in self.boxes:
            ax.add_patch(Rectangle((x0, y0), w, h, fc=fill, ec="k", lw=1.2, zorder=3))
        for (x0, y0, x1, y1, c) in self.frames:
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=c, lw=1.0, ls=(0, (5, 3)), zorder=0))
        for p, q, c in self.dashes:
            ax.plot([p[0], q[0]], [p[1], q[1]], color=c, lw=0.9, ls=(0, (3, 2)), zorder=2)
        for x, y, s, kw in self.texts:
            ax.text(x, y, s, **kw)
        ax.set_xlim(*self.xlim); ax.set_ylim(*self.ylim); ax.set_aspect("equal", adjustable="box")
        ax.axis("off")


# ============================================================== E-001 power distribution
def e001():
    fig, fr = sheet("RCN-E-001", "전원 분배 회로도 / Power Distribution")
    header(fr, "RCN-E-001  전원 분배 회로도 — 4S 팩 · 주 퓨즈 · E-stop/무선킬 → 모터 접촉기 · 상시 로직 버스 · 전압/전류 감시",
           "굵은 수치 = spec.py 계산값.  모터 버스만 K1 로 끊고 로직 버스는 SW1 이 켜져 있는 동안 계속 살아 로그를 남긴다.  "
           "초록 = 전선 굵기.  [A] = 이 도면에서 둔 가정.", mm=False)
    S = Sch(fig, (0.45, 2.3, 15.65, 8.35), (0, 72), (1.0, 40.0))
    w, t, dot, gnd, net = S.w, S.t, S.dot, S.gnd, S.net
    ym = 31.0
    S.frame(0.3, 20.0, 55.0, 39.9, "① 주 전원 경로 · 모터 버스 (K1 하류만 차단)")
    S.frame(0.3, 1.2, 55.0, 19.8, "② 로직 버스 — SW1 ON 동안 상시 (E-stop 과 무관)")
    S.frame(55.3, 1.2, 71.7, 39.9, "③ 전류 · 퓨즈 · 전선 (spec 계산)")

    # battery
    bt = S.ic(0.9, 23.6, 4.4, 9.0, "BT1 + BMS", "", right=[("P+", ym - 23.6), ("P-", 1.2)], stub=0.8, fill="#fff7d6")
    t(3.1, 29.4, f"4S Li-ion", fs=7.2, ha="center"); t(3.1, 28.2, f"{V_NOM:g} V nom", fs=7.2, ha="center", bold=True)
    t(3.1, 27.0, f"{V_MIN:g}-{V_MAX:g} V", fs=7.2, ha="center"); t(3.1, 25.8, f"{BAT['Ah']:g} Ah", fs=7.2, ha="center")
    w(bt["P-"], (6.8, bt["P-"][1])); gnd((6.8, bt["P-"][1]))
    t(7.2, bt["P-"][1] + 0.4, "GND (별형 접지점)", fs=6.6, color=GREY)
    S.add(elm.Fuse().at(bt["P+"]).right().length(2.6).label("F1 30 A", fontsize=7.6))
    x = bt["P+"][0] + 2.6
    S.add(elm.Switch().at((x, ym)).right().length(2.4).label("SW1 주전원", fontsize=7.4))
    x += 2.4
    q1 = S.ic(x + 1.4, ym - 1.4, 4.2, 2.8, "Q1 역극성 보호", "LM74700-Q1 + N-FET", left=[("IN", 1.4)], right=[("OUT", 1.4)],
              stub=0.8, fs=6.6, fill="#f2f2f2")
    w((x, ym), q1["IN"])
    t(bt["P+"][0] + 0.2, ym - 0.9, "12 AWG", fs=6.8, color=GREEN)
    t(bt["P+"][0] + 0.2, ym - 1.9, f"I_PEAK {I_PEAK:.1f} A", fs=7.2, bold=True, color=RED)
    xt = q1["OUT"][0] + 1.2
    w(q1["OUT"], (xt + 1.2, ym)); dot((xt, ym))
    S.add(elm.DiodeTVS().at((xt, ym - 2.6)).up().length(2.6).label("D1\nSMBJ20A", loc="bottom", fontsize=6.8))
    gnd((xt, ym - 2.6))
    xs0 = xt + 1.2
    S.add(elm.Resistor().at((xs0, ym)).right().length(3.0).label(f"RS1 {RS1_MOHM:g} mΩ [A]", fontsize=7.0))
    xs1 = xs0 + 3.0
    XB = xs1 + 2.4                                    # +VBAT_SW node
    w((xs1, ym), (XB, ym)); dot((xs0, ym)); dot((xs1, ym)); dot((XB, ym))
    ina = S.ic(xs0 - 0.6, 23.2, 4.2, 3.2, "U5 INA226", "", top=[("IN+", 0.6), ("IN-", 3.6)], left=[("I2C", 1.0)],
               stub=0.6, fs=6.6, fill="#e6f4e6")
    w(ina["IN+"], (xs0, ym)); w(ina["IN-"], (xs1, ym))
    net(ina["I2C"], f"I2C1 {PIN['I2C'][1]}", side="left", fs=6.6)
    t(xs0 + 1.5, 22.6, f"FS ±{INA_FS_A:.1f} A · {P_RS1:.2f} W @ I_PEAK", fs=6.4, ha="center", va="top", color=GREY)
    t(XB + 0.3, ym + 0.5, "+VBAT_SW", fs=7.6, bold=True, color=BLUE, va="bottom")

    # coil / safety loop
    yc = 37.2
    w((XB, ym), (XB, yc))
    S.add(elm.Fuse().at((XB, yc)).right().length(2.4).label("F7 1 A", fontsize=7.0))
    x = XB + 2.4
    S.add(elm.Button(nc=True).at((x, yc)).right().length(3.0).label("S1 E-stop NC", fontsize=6.6))
    t(x + 1.5, yc - 1.3, "제2 NC →\nESTOP_SENSE " + PIN["ESTOP"], fs=6.0, ha="center", color=RED)
    x += 3.0
    S.add(elm.Switch().at((x, yc)).right().length(2.8).label("K2 433 MHz 킬", fontsize=6.6))
    t(x + 1.4, yc - 1.0, "하트비트형", fs=6.0, ha="center", color=RED)
    x += 2.8
    S.add(elm.Resistor().at((x, yc)).right().length(1.8).label(f"R5 {K1_RS} Ω", fontsize=6.2))
    t(x + 0.9, yc - 1.0, "1 W", fs=6.0, ha="center")
    x += 1.8
    xc0 = x
    S.add(elm.Inductor2(loops=2).at((x, yc)).right().length(2.4).label("K1 코일", loc="bottom", fontsize=7.0))
    xc1 = x + 2.4
    w((xc0, yc), (xc0, yc + 1.5)); w((xc1, yc), (xc1, yc + 1.5)); dot((xc0, yc)); dot((xc1, yc))
    S.add(elm.Diode().at((xc1, yc + 1.5)).left().length(2.4))
    t((xc0 + xc1) / 2, yc + 2.0, "D2 SS14", fs=6.4, ha="center", va="bottom")
    xq = xc1 + 1.6
    w((xc1, yc), (xq, yc))
    q2 = S.add(elm.NFet().anchor("drain").at((xq, yc)).reverse())
    gnd(q2.source)
    t(xq + 0.6, yc + 0.5, "Q2 AO3400", fs=6.4, va="bottom")
    g = q2.gate
    w(g, (g[0] - 0.3, g[1]), (g[0] - 0.3, yc - 2.0), (xq + 1.4, yc - 2.0))
    net((xq + 1.4, yc - 2.0), f"MOTOR_EN {PIN['MOTOR_EN']} (100k 풀다운)", side="right", fs=6.4, color=RED)
    t(XB - 0.2, yc - 1.4, "22 AWG\n루프", fs=6.2, color=GREEN, ha="right")

    # K1 contact + motor bus
    xk = xc0
    w((XB, ym), (xk, ym))
    S.add(elm.Switch().at((xk, ym)).right().length(2.4).label("K1 30 A 접점", loc="bottom", fontsize=7.0))
    S.dash((xk + 1.2, yc - 0.6), (xk + 1.2, ym + 0.6))
    xv = xk + 2.4
    xd = xv + 1.2
    w((xv, ym), (xd + 1.6, ym)); dot((xd, ym))
    S.add(elm.Resistor().at((xd, ym)).down().length(2.2).label("R3\n100k", loc="bottom", fontsize=6.4))
    dot((xd, ym - 2.2))
    S.add(elm.Resistor().at((xd, ym - 2.2)).down().length(2.2).label("R4\n22k", loc="bottom", fontsize=6.4))
    gnd((xd, ym - 4.4))
    w((xd, ym - 2.2), (xd - 0.8, ym - 2.2))
    net((xd - 0.8, ym - 2.2), f"MOT_SENSE {PIN['MOT_SENSE'][1]}", side="left", fs=6.4, color=RED)
    t(xv - 0.1, ym + 0.5, "+VMOT", fs=7.4, bold=True, color=BLUE, va="bottom", ha="left")
    xbr = xd + 1.6
    for i, (yb, fref, uref, ms) in enumerate(((ym, "F2", "U1", ("M1 좌전", "M2 좌후")),
                                              (24.4, "F3", "U2", ("M3 우전", "M4 우후")))):
        if i:
            w((xbr, ym), (xbr, yb)); dot((xbr, ym))
        w((xbr, yb), (xbr + 0.4, yb))
        S.add(elm.Fuse().at((xbr + 0.4, yb)).right().length(2.4)
              .label(f"{fref} 15 A", fontsize=7.0))
        t(xbr + 1.6, yb - 0.8, f"{I_DRV:.1f} A pk · 14 AWG", fs=6.4, ha="center", va="top", color=GREEN)
        xu = xbr + 4.2
        u = S.ic(xu, yb - 3.0, 5.4, 5.6, f"{uref} MDD20A", "", left=[("B+", 3.0), ("B-", 0.7)],
                 right=[("M1A", 5.0), ("M1B", 3.4), ("M2A", 2.2), ("M2B", 0.6)], stub=0.8, fs=6.4, fill="#e3eefb")
        w((xbr + 2.8, yb), u["B+"])
        gp = (u["B-"][0] - 0.3, u["B-"][1]); w(u["B-"], gp); gnd(gp)
        t(xu + 2.7, yb - 0.3, "PWM/DIR x2\n← E-002", fs=6.0, ha="center", color=GREY)
        xm = u["M1A"][0] + 1.0
        for (a, b, lab) in (("M1A", "M1B", ms[0]), ("M2A", "M2B", ms[1])):
            pa, pb = u[a], u[b]
            w(pa, (xm, pa[1])); w(pb, (xm, pb[1]))
            S.add(elm.Motor().at((xm, pa[1])).down().length(pa[1] - pb[1]))
            t(xm + 0.7, (pa[1] + pb[1]) / 2, lab, fs=6.6)
    t(XB + 3.6, 20.3, f"모터 버스 피크 {I_MOT_BUS:.1f} A = POWER 모터 {P_MOT[1]:.1f} W / V_min {V_MIN:g} V · 모터선 18 AWG",
      fs=6.4, color=GREY, va="bottom")

    # VBAT divider + logic bus
    w((XB, ym), (XB, 5.0))
    yv = 28.6
    w((XB, yv), (XB + 1.4, yv)); dot((XB, yv))
    S.add(elm.Resistor().at((XB + 1.4, yv)).down().length(2.0).label("R1 100k", loc="bottom", fontsize=6.4))
    dot((XB + 1.4, yv - 2.0))
    S.add(elm.Resistor().at((XB + 1.4, yv - 2.0)).down().length(2.0).label("R2 22k", loc="bottom", fontsize=6.4))
    gnd((XB + 1.4, yv - 4.0))
    w((XB + 1.4, yv - 2.0), (XB + 3.4, yv - 2.0))
    net((XB + 3.4, yv - 2.0), f"VBAT_SENSE {PIN['VBAT'][1]}", fs=6.4, color=RED)
    rows = [
        (16.5, "F4 5 A", f"{I_JET:.2f} A · 18 AWG", "U3 이상적 다이오드", "LTC4359 + N-FET", "U6 Jetson Orin Nano Super",
         [f"DC 잭 9-20 V 입력 · {P_JET[1]:g} W pk", f"팩 {V_MIN:g}-{V_MAX:g} V 직결 (DC-DC 없음)"]),
        (10.3, "F5 3 A", f"{I_5V:.2f} A · 20 AWG", "U4 5 V 강압", "Pololu D36V50F5", "+5V 부하",
         ["U7 NUCLEO-H753ZI (E5V)", "ICM-42688-P (Nucleo 3V3)", "엔코더 Vcc x4 · 팬 5 V"]),
        (4.2, "F6 3 A", f"{I_LID:.2f} A · 20 AWG", None, None, "U8 Livox Mid-360",
         ["9-27 V 직결 · " + f"{P_LID[1]:g} W pk (0 °C 이하 자가가열)"]),
    ]
    for (y, fl, cur, un, up, ln, lines) in rows:
        w((XB, y), (XB + 0.6, y)); dot((XB, y))
        S.add(elm.Fuse().at((XB + 0.6, y)).right().length(2.4).label(fl, fontsize=7.0))
        t(XB + 1.8, y - 0.7, cur, fs=6.4, ha="center", va="top", color=GREEN)
        x = XB + 3.0
        if un:
            u = S.ic(x + 1.0, y - 1.6, 5.0, 3.2, un, up, left=[("IN", 1.6)], right=[("OUT", 1.6)], stub=0.8, fs=6.4,
                     fill="#fde9d9")
            w((x, y), u["IN"]); x = u["OUT"][0]
            if "LTC" in up:
                S.add(elm.Inductor2(loops=2).at((x, y)).right().length(2.0).label("L1 [A]", fontsize=6.4))
                x += 2.0
                xc = x + 0.8
                w((x, y), (xc, y)); dot((xc, y))
                S.add(elm.Capacitor(polar=True).at((xc, y)).down().length(1.8)
                      .label("C1 470 uF\n홀드업", loc="bottom", fontsize=6.2))
                gnd((xc, y - 1.8))
                x = xc
                t(x + 0.3, y + 0.3, "+VJET", fs=7.0, bold=True, color=BLUE, va="bottom")
            else:
                t(x + 0.3, y + 0.3, "+5V", fs=7.0, bold=True, color=BLUE, va="bottom")
        x2 = XB + 18.0
        hh = 1.3 + 1.05 * len(lines)
        ld = S.ic(x2, y - hh / 2, 11.6, hh, ln, "", left=[("", hh / 2)], stub=0.8, fs=6.4, fill="#efe6fa")
        w((x, y), ld[""])
        for i, l in enumerate(lines):
            t(x2 + 5.8, y + hh / 2 - 0.85 - i * 1.05, l, fs=6.4, ha="center")
    t(XB + 0.4, 2.0, "로직 GND 는 모두 BT1 P- 별형 접지점으로 복귀.  GNSS(ZED-F9P) 는 Jetson USB 5 V 급전.  "
      "IMX219 는 CSI 케이블 3.3 V 급전.", fs=6.5, color=GREY)

    # ③ table
    x0 = 55.8
    y = 38.3
    t(x0, y, "퓨즈 · 설계전류 · 전선", fs=8.2, bold=True, va="top"); y -= 1.5
    t(x0, y, "ref  정격   설계 I     AWG (허용)", fs=6.6, va="top", color="#555", family="NanumGothicCoding"); y -= 1.05
    for ref, fa, ia, awg, what in FUSES:
        ist = f"{(ia if ia is not None else K1_I):5.2f} A"
        t(x0, y, f"{ref:3s} {fa:3d} A  {ist}  {awg:2d} ({AWG_AMP[awg]:g} A)", fs=6.6, va="top", family="NanumGothicCoding")
        t(x0 + 0.4, y - 0.95, what, fs=6.2, va="top", color=GREY); y -= 1.85
    y -= 0.3
    t(x0, y, "spec.py 로부터", fs=8.2, bold=True, va="top"); y -= 1.4
    for s in (f"P_AVG {P_AVG:.1f} W · P_PEAK {P_PEAK:.1f} W",
              f"I_PEAK = P_PEAK / V_min = {I_PEAK:.1f} A",
              f"E = {E_WH:.0f} Wh (85 %) → {RUNTIME_H:.2f} h",
              f"η_DCDC {ETA_DCDC:.2f} [A] (5 V 레일 산정용)",
              f"5 V 레일 상한 {P_5V:.1f} W [A: 구동기·팬 줄 전부]",
              f"분압 100k/22k: {V_MAX:g} V → {V_ADC_MAX:.2f} V",
              f"INA226 RS1 {RS1_MOHM:g} mΩ: FS ±{INA_FS_A:.1f} A"):
        t(x0, y, s, fs=6.5, va="top"); y -= 1.0
    y -= 0.3
    t(x0, y, "안전 동작", fs=8.2, bold=True, va="top", color=RED); y -= 1.4
    for s in ("K1 코일 = S1 · K2 · Q2 직렬: 어느 하나",
              "  개방 → 모터 버스 차단, 로직은 산다",
              "Q2 게이트 100k 풀다운: MCU 리셋·IWDG",
              "  → MOTOR_EN=0 → K1 개방 (Jetson 무관)",
              "K2: 페일세이프 모멘터리/하트비트형 수신기",
              "  (링크 상실 → 개방, 토글형 금지) [확인]",
              f"K1 12 V 코일 {K1_COIL_R:g} Ω [A] + R5 {K1_RS} Ω 직렬 선택:",
              f"  {V_MAX:g} V → 코일 {K1_V_HI:.1f} V (≤ {K1_V_MAXCONT:g}), R5 {K1_P_RS:.2f} W",
              f"  {V_MIN:g} V → 코일 {K1_V_LO:.1f} V (≥ 흡인 {K1_V_PULLIN:.1f}) [A]",
              "MOT_SENSE = K1 상태 되읽기 (ADC)"):
        t(x0, y, s, fs=6.4, va="top", color=RED if not s.startswith("  ") and "MOT" not in s else "k"); y -= 1.0
    S.finish()
    save(fig, "RCN-E-001_power")


# ============================================================== mm-sheet helpers (E-002, S-001, M-001, H-001)
def box(ax, x0, y0, x1, y1, title, lines=(), fc="white", fs=9.0, lfs=7.0, ec="k", lw=1.1, title_top=True, lh=4.0):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0.3,rounding_size=1.5",
                                fc=fc, ec=ec, lw=lw, zorder=2))
    ax.text((x0 + x1) / 2, y1 - 1.5, title, ha="center", va="top", fontsize=fs, fontweight="bold", zorder=3)
    for i, l in enumerate(lines):
        ax.text((x0 + x1) / 2, y1 - 6.2 - i * lh, l, ha="center", va="top", fontsize=lfs, zorder=3)

def line(ax, pts, color="k", lw=0.9, ls="-", arrow=False, both=False, z=4, ms=8):
    xs, ys = zip(*pts)
    if not arrow:
        ax.plot(xs, ys, color=color, lw=lw, ls=ls, zorder=z, solid_capstyle="butt")
        return
    ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, ls=ls, zorder=z)
    ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="<|-|>" if both else "-|>", mutation_scale=ms,
                                 color=color, lw=lw, zorder=z, shrinkA=0, shrinkB=0, ls=ls))

def lab(ax, x, y, s, fs=6.8, ha="center", va="bottom", color="k", bold=False, bg=True, **kw):
    ax.text(x, y, s, ha=ha, va=va, fontsize=fs, color=color, fontweight="bold" if bold else "normal", zorder=6,
            bbox=dict(fc="white", ec="none", pad=0.25) if bg else None, **kw)


# ============================================================== E-002 signal / time sync
def e002():
    fig, fr = sheet("RCN-E-002", "신호 · 시간동기 배선도 / Signal & Time Sync")
    ax = mm_axes(fig)
    header(ax, "RCN-E-002  신호 · 시간동기 배선도 — STM32H753 (NUCLEO-H753ZI) · Jetson Orin Nano · 센서 · 구동기",
           "핀은 LQFP144 대체기능(AF) 기준 [DS 확인 필요].  파랑 = 데이터, 빨강 = 안전, 주황 = 시간(PPS/PTP).  "
           "엔코더·IMU 샘플은 MCU TIM5 틱으로 찍고, TIM5 가 PPS 를 캡처해 UTC 로 환산한다.")
    ORG = "#d9730d"
    # MCU
    mx0, mx1, my0, my1 = 128, 190, 62, 262
    ax.add_patch(Rectangle((mx0, my0), mx1 - mx0, my1 - my0, fc="#efe6fa", ec="k", lw=1.3, zorder=2))
    ax.text((mx0 + mx1) / 2, my1 + 1.5, "U7  STM32H753ZI (NUCLEO-H753ZI)", ha="center", va="bottom", fontsize=9.5,
            fontweight="bold")
    inner = ["Cortex-M7 480 MHz", "IWDG (독립 워치독)", "TIM5 32-bit: PPS 캡처", "= 모든 샘플의 시간축",
             "fw C 결정 커널 · 휠 PID", "Jetson 하트비트 감시", "→ 끊기면 MOTOR_EN=0"]
    for i, s in enumerate(inner):
        ax.text(157, 182 - i * 5.2, s, ha="left", va="top", fontsize=6.9, zorder=3,
                color=RED if "MOTOR_EN" in s or "하트비트" in s else "k")
    def mpin(side, y, name, color="k"):
        if side == "L":
            line(ax, [(mx0 - 5, y), (mx0, y)], color=color, z=3)
            ax.text(mx0 + 1.2, y, name, fontsize=6.4, va="center", ha="left", zorder=3)
            return (mx0 - 5, y)
        line(ax, [(mx1, y), (mx1 + 5, y)], color=color, z=3)
        ax.text(mx1 - 1.2, y, name, fontsize=6.4, va="center", ha="right", zorder=3)
        return (mx1 + 5, y)

    # IMU
    iy = [252, 247.5, 243, 238.5, 234]
    box(ax, 40, 229, 88, 262, "U9 ICM-42688-P", [], fc="#e6f4e6", fs=8.2)
    ax.text(64, 250, f"SPI · {PARTS['imu']['rate_Hz']} Hz ODR", fontsize=6.6, ha="center", va="top")
    ax.text(64, 245.5, "Nucleo 3V3 급전 · 선 ≤ 10 cm", fontsize=6.4, ha="center", va="top", color=GREY)
    imu_pins = ["SCLK", "SDO", "SDI", "CS", "INT1"]
    for (sig, pn), y, ip in zip(PIN["SPI"], iy, imu_pins):
        p = mpin("L", y, f"{pn}  {sig}")
        line(ax, [(88, y if y < 240 else y), p], color=BLUE)
        ax.text(86.8, y, ip, fontsize=6.2, ha="right", va="center", zorder=3)
    lab(ax, 64, 227.5, "INT1 = 데이터 준비 → EXTI 타임스탬프", fs=6.0, color=GREY, va="top")

    # encoders
    ey = 218
    for k in range(4):
        tim, pa, pb, af = PIN[f"ENC{k+1}"]
        y0 = ey - k * 17
        box(ax, 40, y0 - 13, 88, y0 + 1, f"E{k+1} 엔코더 (M{k+1})", [], fc="#e6f4e6", fs=7.6)
        ax.text(64, y0 - 5.2, f"{M['encoder_cpr_motor']} CPR x {M['gear']}:1 = {DRIVE['ticks_per_rev']}/rev",
                fontsize=6.2, ha="center", va="top")
        for j, (pn, ch) in enumerate(((pa, "A"), (pb, "B"))):
            y = y0 - 7.5 - j * 4
            p = mpin("L", y, f"{pn}  {tim}_CH{j+1}")
            line(ax, [(88, y), p], color=BLUE)
            ax.text(86.8, y, ch, fontsize=6.2, ha="right", va="center", zorder=3)
    lab(ax, 64, 150.2, f"엔코더 Vcc 5 V (3.5 V 이상 필요) · 출력 5 V → FT 핀  ·  {DRIVE['dist_per_tick_mm']:.3f} mm/tick",
        fs=6.0, color=GREY, va="top")

    # drivers
    for k in range(2):
        y0 = 136 - k * 25
        box(ax, 40, y0 - 21, 88, y0 + 1, f"U{k+1} Cytron MDD20A", [], fc="#e3eefb", fs=7.8)
        ax.text(64, y0 - 5.5, f"M{2*k+1}/M{2*k+2} · 3.3 V 로직 · PWM 20 kHz [A]", fontsize=6.2, ha="center", va="top", color=GREY)
        for j in range(2):
            ch = 2 * k + j
            tn, pn = PIN["PWM"][ch]
            for jj, (nm, pin, lb) in enumerate(((f"PWM{j+1}", pn, tn), (f"DIR{j+1}", PIN["DIR"][ch], "GPIO"))):
                y = y0 - 10 - j * 6 - jj * 3
                p = mpin("L", y, f"{pin}  {lb}")
                line(ax, [(88, y), p], color=BLUE)
                ax.text(86.8, y, nm, fontsize=6.0, ha="right", va="center", zorder=3)

    # safety block
    box(ax, 18, 60, 92, 86, "안전 · 전원 감시 (E-001)", [], fc="#fbe3e3", fs=7.8)
    srows = [(79.5, PIN["ESTOP"], "ESTOP_SENSE ← S1 제2 NC (풀업)"),
             (75.9, PIN["MOTOR_EN"], "MOTOR_EN → Q2 → K1 코일"),
             (72.3, PIN["MOT_SENSE"][1], "MOT_SENSE ← K1 하류 분압"),
             (68.7, PIN["VBAT"][1], "VBAT_SENSE ← 팩 분압"),
             (65.1, PIN["I2C"][1], "I2C1 ↔ U5 INA226 (+ALERT " + PIN["INA_ALERT"] + ")")]
    for y, pn, s in srows:
        ax.text(20, y - 0.5, s, fontsize=6.1, va="center", zorder=3)
        p = mpin("L", y - 0.5, pn, color=RED)
        line(ax, [(92, y - 0.5), p], color=RED)

    # Jetson
    jx0, jx1, jy0, jy1 = 250, 312, 124, 262
    ax.add_patch(Rectangle((jx0, jy0), jx1 - jx0, jy1 - jy0, fc="#fde9d9", ec="k", lw=1.3, zorder=2))
    ax.text((jx0 + jx1) / 2, jy1 + 1.5, "U6  Jetson Orin Nano Super 8 GB", ha="center", va="bottom", fontsize=9.5,
            fontweight="bold")
    for i, s in enumerate(["LIO / EKF · 2.5D 지도", "A* · pure pursuit", "로깅 NVMe",
                           "chrony: PPS(GPIO) + NMEA", "ptp4l: eth0 PTP 마스터", "phc2sys: 시스템시계 → PHC"]):
        ax.text((jx0 + jx1) / 2, 184 - i * 5.2, s, ha="center", va="top", fontsize=7.2, zorder=3,
                color=ORG if i >= 3 else "k")
    def jpin(side, y, name):
        if side == "L":
            line(ax, [(jx0 - 5, y), (jx0, y)], z=3); ax.text(jx0 + 1.2, y, name, fontsize=6.4, va="center", zorder=3)
            return (jx0 - 5, y)
        line(ax, [(jx1, y), (jx1 + 5, y)], z=3); ax.text(jx1 - 1.2, y, name, fontsize=6.4, va="center", ha="right", zorder=3)
        return (jx1 + 5, y)
    # MCU <-> Jetson
    a = mpin("R", 244, f"{PIN['USB'][1]}  USB {PIN['USB'][0]}"); b = jpin("L", 244, "USB-A (CDC ACM)")
    line(ax, [a, b], color=BLUE, arrow=True, both=True)
    lab(ax, 220, 245, "명령 · 텔레메트리 · 하트비트", fs=6.2, color=BLUE)
    a = mpin("R", 232, f"{PIN['UART'][1]}  {PIN['UART'][0]}"); b = jpin("L", 232, "40p UART1 (8/10)")
    line(ax, [a, b], color=BLUE, arrow=True, both=True)
    lab(ax, 220, 233, "예비 링크 3.3 V", fs=6.2, color=BLUE)
    lab(ax, 220, 220, "USB 는 GND 공유: 루프 주의,\n같은 별형 접지점", fs=6.0, color=GREY, va="top")
    # peripherals right
    box(ax, 342, 222, 406, 262, "U8 Livox Mid-360", [PARTS["lidar"]["rate"], f"FOV {PARTS['lidar']['fov']}",
                                                     "IEEE 1588 PTPv2 슬레이브"], fc="#e6f4e6", fs=8.2, lfs=6.6)
    a = jpin("R", 240, "RJ45 eth0 (1 GbE)")
    line(ax, [a, (342, 240)], color=BLUE, arrow=True, both=True)
    lab(ax, 327, 241, "100BASE-TX", fs=6.2, color=BLUE)
    lab(ax, 327, 234.5, "PTP (UDP 319/320)", fs=6.2, color=ORG, va="top")
    box(ax, 342, 176, 406, 208, "Pi Camera v2 (IMX219)", [PARTS["camera"]["res"].split("(")[1].rstrip(")"),
                                                           "CSI 15p → 22p 어댑터"], fc="#e6f4e6", fs=8.2, lfs=6.6)
    a = jpin("R", 192, "CAM0 CSI-2 2-lane (22p)")
    line(ax, [(342, 192), a], color=BLUE, arrow=True)
    lab(ax, 327, 193, "MIPI CSI-2", fs=6.2, color=BLUE)
    box(ax, 342, 128, 406, 162, "ZED-F9P (SparkFun GPS-RTK2)", [f"{PARTS['gnss']['rate_Hz']} Hz · RTK "
                                                                f"{PARTS['gnss']['acc_m_rtk']*100:g} cm", "확장 (실외)"],
        fc="#e6f4e6", fs=7.8, lfs=6.6)
    a = jpin("R", 150, "USB-A")
    line(ax, [(342, 150), a], color=BLUE, arrow=True, both=True)
    lab(ax, 327, 151, "USB (UBX/NMEA)", fs=6.2, color=BLUE)
    # PPS fan-out
    ppsx = 374
    line(ax, [(ppsx, 128), (ppsx, 118), (236, 118), (236, 104), (230, 104)], color=ORG, lw=1.2)
    lab(ax, ppsx + 2, 123, "PPS 3.3 V, 1 Hz", fs=6.2, color=ORG, ha="left", va="center")
    box(ax, 204, 92, 230, 112, "U10", ["74LVC2G34", "PPS 2분기"], fc="white", fs=7.6, lfs=6.2)
    a = mpin("R", 100, f"{PIN['PPS'][1]}  {PIN['PPS'][0]}", color=ORG)
    line(ax, [(204, 100), a], color=ORG, lw=1.2, arrow=True)
    lab(ax, 199, 102, "입력 캡처", fs=6.0, color=ORG, ha="right")
    b = jpin("L", 132, "40p GPIO (pps-gpio)")
    line(ax, [(217, 112), (217, 132), b], color=ORG, lw=1.2, arrow=True)
    lab(ax, 218, 124, "33 Ω 직렬 · 동일 길이", fs=6.0, color=ORG, ha="left", va="center")
    a = mpin("R", 84, "IWDG · NRST", color=RED)
    lab(ax, 196, 84, "IWDG 만료 → 리셋 → 핀 Hi-Z → Q2 풀다운 → K1 개방", fs=6.0, color=RED, ha="left", va="center")

    # time sync scheme panel
    px0, py0, px1, py1 = 255, 62, 410, 113
    ax.add_patch(Rectangle((px0, py0), px1 - px0, py1 - py0, fc="#fff8ef", ec=ORG, lw=1.0, zorder=1))
    ax.text(px0 + 2, py1 - 2, "시간동기 방식 (하나의 시간축 = GNSS UTC, 없으면 Jetson 시스템시계)", fontsize=7.6,
            fontweight="bold", va="top", color=ORG)
    sync = [
        "1. ZED-F9P PPS → Jetson GPIO: chrony refclock PPS + NMEA(gpsd SHM) 로 시스템시계를 UTC 에 고정",
        "2. Jetson → Mid-360: ptp4l (eth0 마스터), phc2sys 로 시스템시계 → NIC PHC. 점 타임스탬프 = PTP 시각",
        "    · Orin Nano NIC 하드웨어 타임스탬프 지원 여부 확인 필요. 없으면 SW 타임스탬프 (정밀도 ↓)",
        "3. PPS → MCU TIM5_CH1 캡처: 엔코더·IMU 샘플 = TIM5 틱. 매 PPS 마다 (틱, UTC 초) 쌍을 USB 로 보고",
        "    Jetson 이 틱→UTC 1차 보정 (오프셋 + 드리프트)",
        "4. GNSS 없음(실내): PPS 대신 USB 핑-퐁 4-타임스탬프 (NTP 식) 로 틱↔시스템시계 오프셋 추정",
        "5. 카메라: V4L2 버퍼 타임스탬프 (CLOCK_MONOTONIC) → 시스템시계 변환. 노출 중앙 보정은 [A]",
        f"데이터율 (spec DATA): LiDAR {DATA['lidar_Bps']/1e6:.1f} MB/s · 카메라 {DATA['cam_Bps']/1e6:.2f} MB/s · "
        f"IMU {DATA['imu_Bps']/1e3:.0f} kB/s · 엔코더 {DATA['enc_Bps']/1e3:.1f} kB/s · GNSS {DATA['gnss_Bps']/1e3:.0f} kB/s",
    ]
    for i, s in enumerate(sync):
        ax.text(px0 + 2, py1 - 8 - i * 5.1, s, fontsize=6.3, va="top", zorder=3,
                color="k" if i < 7 else BLUE)
    save(fig, "RCN-E-002_signal")


# ============================================================== S-001 system block diagram
def s001():
    fig, fr = sheet("RCN-S-001", "시스템 블록도 / System Block Diagram")
    ax = mm_axes(fig)
    header(ax, "RCN-S-001  시스템 블록도 — 센싱 → 추정 → 지도 → 결정 집행부 → 유도 → 제어 → 구동",
           "굵은 선 = 주 데이터 흐름 (spec DATA 율)   가는 선 = 명령/상태   빨간 선 = 안전 경로 (Jetson 을 거치지 않음)   "
           "배경 = 연산 배치")
    C = dict(sen="#e6f4e6", est="#e3eefb", map="#e3eefb", dec="#fff7d6", gui="#e3eefb", ctl="#efe6fa",
             act="#fde9d9", safe="#fbe3e3")
    # placement bands
    ax.add_patch(Rectangle((82, 150), 250, 118, fc="#fdf1e6", ec="#d9a066", lw=0.9, ls=(0, (5, 3)), zorder=0))
    ax.text(84, 266, "Jetson Orin Nano Super — Ubuntu / ROS 2 (호스트)", fontsize=8.4, fontweight="bold",
            color="#a0602a", va="top")
    ax.add_patch(Rectangle((82, 64), 250, 82, fc="#f6f0fc", ec="#9a7ac4", lw=0.9, ls=(0, (5, 3)), zorder=0))
    ax.text(84, 144, "STM32H753 — 베어메탈 fw (실시간 · 안전)", fontsize=8.4, fontweight="bold", color="#6a4a9a",
            va="top")
    ax.add_patch(Rectangle((338, 64), 72, 204, fc="#fbfbfb", ec="#999", lw=0.9, ls=(0, (5, 3)), zorder=0))
    ax.text(340, 266, "하드웨어", fontsize=8.4, fontweight="bold", color="#666", va="top")
    ax.text(10, 266, "센서", fontsize=8.4, fontweight="bold", color="#666", va="top")

    # sensors
    sens = [("LiDAR Mid-360", f"{DATA['lidar_Bps']/1e6:.1f} MB/s · 10 Hz", 238),
            ("카메라 IMX219", f"{DATA['cam_Bps']/1e6:.2f} MB/s (H.264)", 212),
            ("GNSS ZED-F9P (확장)", f"{DATA['gnss_Bps']/1e3:.0f} kB/s · PPS", 186),
            ("IMU ICM-42688-P", f"{DATA['imu_Bps']/1e3:.0f} kB/s · {PARTS['imu']['rate_Hz']} Hz", 120),
            ("엔코더 x4", f"{DATA['enc_Bps']/1e3:.1f} kB/s · 100 Hz", 94)]
    for n, r, y in sens:
        box(ax, 10, y - 9, 66, y + 9, n, [r], fc=C["sen"], fs=7.8, lfs=6.6)
    # estimation / map / logging on host
    box(ax, 90, 196, 150, 250, "추정 / Estimation", ["LIO (LiDAR-관성 오도메트리)", "+ EKF 융합:", "휠 오도메트리 · IMU · GNSS",
                                                   "출력: 자세 6-DoF + 공분산"], fc=C["est"], fs=8.4, lfs=6.5)
    box(ax, 160, 196, 220, 250, "지도 / Mapping", ["2.5D 고도 격자", f"셀 {MAP['cell']:g} m · {MAP['size_m']:g} m 창",
                                                f"칸마다 높이 + 분산 (var ≥ {MAP['var_min']:g})",
                                                f"관측 ≤ {MAP['max_obs_range']:g} m"], fc=C["map"], fs=8.4, lfs=6.5)
    raw_gb_h = DATA["raw_Bps"] * 3600 / 1e9
    box(ax, 90, 156, 150, 186, "로깅 NVMe 512 GB", [f"원시 {DATA['raw_Bps']/1e6:.1f} MB/s = {raw_gb_h:.1f} GB/h",
                                                   f"임무 {RUNTIME_H:.2f} h → {raw_gb_h*RUNTIME_H:.0f} GB"],
        fc="#f2f2f2", fs=8.0, lfs=6.5)
    # decision executive
    ex0, ex1 = 230, 290
    ax.add_patch(FancyBboxPatch((ex0 - 3, 153), ex1 - ex0 + 6, 110, boxstyle="round,pad=0.3,rounding_size=2",
                                fc="#fffdf2", ec="#b89a2a", lw=1.2, zorder=1))
    ax.text((ex0 + ex1) / 2, 261, "결정 집행부 / Decision executive", fontsize=8.2, fontweight="bold", ha="center",
            va="top")
    ax.text((ex0 + ex1) / 2, 256.5, "fw C 커널 (같은 소스: 호스트 · MCU 빌드)", fontsize=6.2, ha="center", va="top",
            color=GREY)
    steps = [("증거 Evidence", "지도·자세 → 사실/신뢰도"), ("가드 Guard", "전제조건 · 불변식 검사"),
             ("BT / HFSM", "임무 단계 · 행동 트리"), ("효용 정책 Utility", "후보 목표 점수화"),
             ("중재 Arbitration", "우선순위 · 단일 명령")]
    sy = 244
    for i, (n, d) in enumerate(steps):
        y = sy - i * 18.5
        box(ax, ex0, y - 7, ex1, y + 7, n, [d], fc=C["dec"], fs=7.6, lfs=6.2, lh=3.5)
        if i:
            line(ax, [(250, y + 11.5), (250, y + 7.3)], arrow=True, lw=1.0)
    # safety supervisor on MCU
    box(ax, ex0, 100, ex1, 138, "안전 감시 Safety supervisor", ["MCU 에서 실행 (최종 관문)", "속도·기울기·하트비트 한계",
                                                             f"v ≤ {DRIVE['v_cmd_max']:g} m/s · ω ≤ {DRIVE['w_cmd_max']:g} rad/s",
                                                             f"경사 한계 {MECH['slope_limit_deg']:g}° [A] (전복 {MAX_SLOPE:.1f}°)"],
        fc=C["safe"], fs=7.8, lfs=6.2, lh=3.8)
    line(ax, [(250, 163 - 7), (250, 150), (250, 138.3)], arrow=True, lw=1.3)
    lab(ax, 252, 146, "(v, ω) 명령 · USB", fs=6.2, ha="left", va="center", color=BLUE)
    # guidance / controller / actuator
    box(ax, 296, 212, 330, 250, "유도 Guidance", ["A* (격자 비용 =", "경사 + 분산)", "pure pursuit", "→ (v, ω)"],
        fc=C["gui"], fs=7.8, lfs=6.2, lh=3.8)
    box(ax, 296, 100, 330, 138, "제어 Controller", ["차동 역기구학", "휠 PID x4", f"{DRIVE['ticks_per_rev']} tick/rev"],
        fc=C["ctl"], fs=7.8, lfs=6.2, lh=3.8)
    box(ax, 344, 96, 404, 142, "구동 Actuator", ["MDD20A x2 (PWM/DIR)", "37D 50:1 모터 x4",
                                               f"무부하 {DRIVE['v_noload']:.2f} m/s @ {V_NOM:g} V"],
        fc=C["act"], fs=8.0, lfs=6.4, lh=4.0)
    box(ax, 344, 70, 404, 90, "K1 모터 접촉기 (E-001)", [], fc=C["safe"], fs=7.6)
    box(ax, 344, 160, 404, 196, "E-stop S1 · 433 MHz 킬 K2", ["하드와이어 직렬 → K1 코일", "소프트웨어 무관"],
        fc=C["safe"], fs=7.6, lfs=6.4)

    # data flow
    thick = dict(lw=2.0, arrow=True)
    line(ax, [(66, 238), (90, 238)], **thick); lab(ax, 78, 239, "점군", fs=6.2)
    line(ax, [(66, 212), (90, 212)], **thick); lab(ax, 78, 213, "영상", fs=6.2)
    line(ax, [(66, 186), (76, 186), (76, 204), (90, 204)], lw=1.0, arrow=True)
    line(ax, [(66, 120), (74, 120), (74, 200), (90, 200)], lw=1.0, arrow=True, color="#6a4a9a")
    line(ax, [(66, 94), (78, 94), (78, 198), (90, 198)], lw=1.0, arrow=True, color="#6a4a9a")
    lab(ax, 84, 118, "MCU 경유 · TIM5 시각\nUSB-CDC", fs=6.0, color="#6a4a9a", ha="left", va="center")
    line(ax, [(150, 223), (160, 223)], **thick); lab(ax, 155, 226, "자세", fs=6.2)
    line(ax, [(220, 223), (227, 223)], **thick)
    line(ax, [(120, 196), (120, 186)], lw=1.2, arrow=True)
    line(ax, [(85, 238), (85, 171), (90, 171)], lw=1.0, arrow=True, color=GREY)
    lab(ax, 105, 190.5, "원시 로그", fs=6.0, color=GREY)
    line(ax, [(ex1, 166), (320, 166), (320, 212)], lw=1.2, arrow=True)
    lab(ax, 321, 196, "목표\n· 모드", fs=6.0, ha="left", va="center")
    line(ax, [(304, 212), (304, 176), (ex1, 176)], lw=1.2, arrow=True, color=BLUE)
    lab(ax, 305, 190, "(v, ω)\n후보", fs=6.0, color=BLUE, ha="left", va="center")
    line(ax, [(ex1, 119), (296, 119)], lw=1.4, arrow=True); lab(ax, 293, 121, "(v, ω)", fs=6.2)
    line(ax, [(330, 119), (344, 119)], lw=1.8, arrow=True); lab(ax, 337, 121, "PWM", fs=6.2)
    line(ax, [(374, 96), (374, 90)], lw=2.0, color=RED)
    lab(ax, 376, 93, "모터 전원", fs=6.0, color=RED, ha="left", va="center")
    line(ax, [(344, 110), (335, 110), (335, 105), (330, 105)], lw=1.0, arrow=True, color="#6a4a9a")
    lab(ax, 336, 108, "엔코더", fs=5.8, color="#6a4a9a", ha="left", va="bottom", bg=False)
    # safety path (red)
    line(ax, [(374, 160), (374, 150), (408, 150), (408, 80), (404, 80)], lw=1.6, color=RED, arrow=True)
    lab(ax, 406, 154, "코일 개방", fs=6.0, color=RED, ha="right", va="bottom")
    line(ax, [(260, 100), (260, 80)], lw=1.6, color=RED)
    line(ax, [(230, 80), (344, 80)], lw=1.6, color=RED, arrow=True)
    lab(ax, 300, 81, "MOTOR_EN → Q2 → K1 코일", fs=6.2, color=RED)
    line(ax, [(210, 150), (210, 126), (ex0, 126)], lw=1.2, color=RED, ls=(0, (4, 2)), arrow=True)
    lab(ax, 196, 131, "하트비트 (USB) 끊김\n→ 정지", fs=6.0, color=RED, ha="center", va="center")
    box(ax, 100, 72, 200, 100, "IWDG 독립 워치독", ["MCU 멈춤 → 리셋 → 핀 Hi-Z", "→ Q2 풀다운 → K1 개방"],
        fc=C["safe"], fs=7.6, lfs=6.4)
    line(ax, [(200, 86), (230, 86), (230, 80)], lw=1.6, color=RED)
    ax.text(12, 62, "안전 경로 3겹 (모두 Jetson 우회):\n① S1/K2 하드와이어 → K1 코일\n② MCU 안전감시 → MOTOR_EN\n"
            "③ IWDG → 리셋 → 풀다운", fontsize=6.8, color=RED, va="bottom", zorder=5, linespacing=1.6)
    save(fig, "RCN-S-001_system")


# ============================================================== M-001 mechanical
def m001():
    import textwrap
    SC = 5.0                          # 1:5
    fig, fr = sheet("RCN-M-001", "기구 외형도 / Mechanical Layout", scale="1:5 (A3)")
    ax = mm_axes(fig)
    header(ax, "RCN-M-001  기구 외형도 — 측면 · 정면 · 평면, 센서 배치, LiDAR 도립 시야, 무게중심, 정적 전복각",
           "치수 mm (실물), 도면 축척 1:5.  좌표 원점 = 차체 중심 바로 아래 지면, +x 전방.  빨강 = spec.py 불일치 / 한계.  "
           "[A] = 이 도면의 가정 (spec 에 없음)")
    s = 1 / SC
    def arr(p, q, color="k", lw=0.55, both=True):
        ax.add_patch(FancyArrowPatch(p, q, arrowstyle="<|-|>" if both else "-|>", mutation_scale=6, lw=lw, color=color,
                                     shrinkA=0, shrinkB=0, zorder=8))
    def dimh(x1, x2, yf, yd, text, color="k"):
        for xx in (x1, x2):
            ax.plot([xx, xx], [yf, yd + (1.2 if yd > yf else -1.2)], color=color, lw=0.4, zorder=8)
        arr((x1, yd), (x2, yd), color=color)
        ax.text((x1 + x2) / 2, yd + 0.7, text, ha="center", va="bottom", fontsize=6.6, color=color, zorder=9,
                bbox=dict(fc="white", ec="none", pad=0.2))
    def dimv(y1, y2, xf, xd, text, color="k", left=True, ty=None):
        for yy in (y1, y2):
            ax.plot([xf, xd + (-1.2 if xd < xf else 1.2)], [yy, yy], color=color, lw=0.4, zorder=8)
        arr((xd, y1), (xd, y2), color=color)
        ax.text(xd + (-0.8 if left else 0.8), (y1 + y2) / 2 if ty is None else ty, text, ha="right" if left else "left", va="center",
                fontsize=6.6, color=color, zorder=9, bbox=dict(fc="white", ec="none", pad=0.2))
    def R(x0, y0, x1, y1, fc="white", ec="k", lw=0.9, z=3, **kw):
        ax.add_patch(Rectangle((min(x0, x1), min(y0, y1)), abs(x1 - x0), abs(y1 - y0), fc=fc, ec=ec, lw=lw, zorder=z, **kw))
    def cl(p, q):
        ax.plot([p[0], q[0]], [p[1], q[1]], color="#555", lw=0.45, ls=(0, (10, 2, 2, 2)), zorder=7)
    def cog(x, y):
        r = 2.6
        ax.add_patch(Circle((x, y), r, fc="white", ec="k", lw=0.8, zorder=9))
        for a0 in (0, 180):
            ax.add_patch(matplotlib.patches.Wedge((x, y), r, a0, a0 + 90, fc="k", ec="none", zorder=10))
    def ground(x0, x1, y):
        ax.plot([x0, x1], [y, y], color="k", lw=1.0, zorder=4)
        for xx in np.arange(x0 + 2, x1, 4):
            ax.plot([xx, xx - 2], [y, y - 2], color="k", lw=0.4, zorder=4)
    BODY, WHEEL, MAST, LID, CAMC = "#dfe6ee", "#555", "#c9c9c9", "#9fc59f", "#9fb8d9"
    LB = LIDAR_BOX
    fov_lo, fov_hi = MECH["lidar_fov_deg"]
    inv = MECH.get("lidar_inverted", False)
    MW = 20.0                                     # mast section [A]
    mast_x0, mast_x1 = LX - LB[0] / 2 - MW, LX - LB[0] / 2   # mast behind LiDAR, cantilever plate over it [A]
    lid_z0, lid_z1 = (MAST_TOP - LB[2], MAST_TOP) if inv else (LH - LB[2] / 2, LH + LB[2] / 2)
    # FOV clearance checks (computed)
    def ray_z(dx, ang): return LH + dx * math.tan(math.radians(ang))
    clear_front = ray_z(L_ / 2 - LX, fov_lo) - DECK
    clear_rear = ray_z(L_ / 2 + LX, fov_lo) - DECK
    ang_cam = math.degrees(math.atan2(CH + 12 - LH, CX - LX))
    cam_in_fov = fov_lo <= ang_cam <= fov_hi
    mast_occl = 2 * math.degrees(math.atan((MW / 2) / (LB[0] / 2 + MW / 2)))
    BLIND_INV, BLIND_UP = MECH["lidar_blind_r_inverted"] * 1e3, MECH["lidar_blind_r_upright"] * 1e3

    # ---------------- side view
    sx, sy = 100, 96
    X = lambda x: sx + x * s; Z = lambda z: sy + z * s
    ax.text(X(0), Z(MAST_TOP) + 22, "측면도 / SIDE (좌측에서 봄, 전방 →)", ha="center", fontsize=9, fontweight="bold")
    xr_min, xr_max = -300, 660
    # FOV wedge (both directions)
    for sgn in (1, -1):
        dmax = (xr_max - LX) if sgn > 0 else (LX - xr_min)
        d_lo = min(dmax, (LH / math.tan(math.radians(-fov_lo))) if fov_lo < 0 else dmax)
        pts = [(X(LX), Z(LH)), (X(LX + sgn * d_lo), Z(ray_z(d_lo, fov_lo))),
               (X(LX + sgn * dmax), Z(ray_z(dmax, fov_lo)) if d_lo >= dmax else sy),
               (X(LX + sgn * dmax), Z(ray_z(dmax, fov_hi)))]
        ax.add_patch(Polygon(pts, closed=True, fc="#cfe8cf", ec="none", alpha=0.55, zorder=1))
        for ang in (fov_lo, fov_hi):
            d = d_lo if ang == fov_lo else dmax
            ax.plot([X(LX), X(LX + sgn * d)], [Z(LH), Z(ray_z(d, ang))], color=GREEN, lw=0.7, zorder=5)
    ground(X(xr_min), X(xr_max), sy)
    R(X(-L_ / 2), Z(GC), X(L_ / 2), Z(DECK), fc=BODY)
    for xw in (-WB / 2, WB / 2):
        ax.add_patch(Circle((X(xw), Z(WR)), WR * s, fc=WHEEL, ec="k", lw=0.9, zorder=4, alpha=0.85))
        ax.add_patch(Circle((X(xw), Z(WR)), MOTOR_D / 2 * s, fc="none", ec="w", lw=0.6, zorder=5, ls="--"))
        cl((X(xw), Z(WR) - 15), (X(xw), Z(WR) + 15))
    R(X(mast_x0), Z(DECK), X(mast_x1), Z(MAST_TOP + 6), fc=MAST)
    R(X(mast_x0), Z(MAST_TOP), X(LX + LB[0] / 2 + 4), Z(MAST_TOP + 6), fc=MAST, z=4)
    R(X(LX - LB[0] / 2), Z(lid_z0), X(LX + LB[0] / 2), Z(lid_z1), fc=LID, z=5)
    ax.plot(X(LX), Z(LH), "+", color="k", ms=6, zorder=9)
    ax.text(X(LX + LB[0] / 2) + 2, Z(lid_z0) - 1, "Mid-360 도립 (거꾸로)" if inv else "Mid-360", fontsize=6.4,
            va="top", zorder=9)
    cw, chh = 25, 24
    ax.add_patch(Rectangle((X(CX) - cw * s / 2, Z(CH) - chh * s / 2), cw * s, chh * s, angle=CP, rotation_point="center",
                           fc=CAMC, ec="k", lw=0.8, zorder=6))
    R(X(CX - 6), Z(DECK), X(CX + 2), Z(CH - chh / 2), fc=MAST)
    Lr = CAM_GROUND
    ax.plot([X(CX), X(min(xr_max, CX + Lr))], [Z(CH), Z(CH + (min(xr_max, CX + Lr) - CX) * math.tan(math.radians(CP)))],
            color=BLUE, lw=0.7, ls=(0, (6, 2)), zorder=6)
    cog(X(0), Z(COGH))
    ax.text(X(0) + 3.5, Z(COGH) + 2.5, "CoG", fontsize=6.2, va="bottom", zorder=9)
    # dims
    dimh(X(-L_ / 2), X(L_ / 2), sy, sy - 16, f"L {L_:.0f}")
    dimh(X(-WB / 2), X(WB / 2), sy, sy - 9, f"wheelbase {WB:.0f}")
    dimh(X(LX), X(LX + BLIND_INV), sy, sy - 23, f"사각 반경 {BLIND_INV:.0f}", color=GREEN)
    dimv(sy, Z(GC), X(-L_ / 2), X(-L_ / 2) - 6, f"지상고 {GC:.0f}")
    dimv(Z(GC), Z(DECK), X(-L_ / 2), X(-L_ / 2) - 17, f"H {HB:.0f}")
    dimv(sy, Z(LH), X(-L_ / 2), X(-L_ / 2) - 28, f"lidar_h {LH:.0f}")
    dimv(Z(DECK), Z(MAST_TOP), X(mast_x0), X(-L_ / 2) + 6, f"mast {PARTS['chassis']['mast_h_mm']}", left=False)
    dimv(sy, Z(CH), X(L_ / 2), X(L_ / 2) + 7, f"cam_h {CH:.0f}", left=False)
    dimh(X(0), X(CX), Z(CH) + 10, Z(CH) + 20, f"cam_x {CX:.0f}")
    dimh(X(0), X(LX), Z(MAST_TOP + 6), Z(MAST_TOP) + 12, f"lidar_x {LX:.0f}")
    cl((X(0), sy - 4), (X(0), Z(DECK) + 6))
    ax.text(X(430), Z(ray_z(380, fov_hi)) + 3, f"+{fov_hi:g}°", color=GREEN, fontsize=6.8, zorder=9)
    ax.text(X(LX + BLIND_INV) + 2, sy + 3, f"{fov_lo:g}°", color=GREEN, fontsize=6.8, zorder=9)
    ax.text(X(CX + 200), Z(CH - 70), f"카메라 광축 {CP:g}°\n지면 {CAM_GROUND/1000:.2f} m 앞", fontsize=6.2,
            color=BLUE, ha="left", va="top", zorder=9)

    # ---------------- front view
    fx = 286
    FX = lambda y: fx + y * s
    ax.text(fx, Z(MAST_TOP) + 22, "정면도 / FRONT (전방에서 봄)", ha="center", fontsize=9, fontweight="bold")
    ground(FX(-W_ / 2 - 60), FX(W_ / 2 + 60), sy)
    R(FX(-W_ / 2), Z(GC), FX(W_ / 2), Z(DECK), fc=BODY)
    for yw in (-TR / 2, TR / 2):
        R(FX(yw - WHEEL_W / 2), sy, FX(yw + WHEEL_W / 2), Z(2 * WR), fc=WHEEL, z=4, alpha=0.8)
        cl((FX(yw), sy - 3), (FX(yw), Z(2 * WR) + 3))
    R(FX(-MW / 2), Z(DECK), FX(MW / 2), Z(MAST_TOP + 6), fc=MAST, z=2)
    R(FX(-LB[1] / 2 - 4), Z(MAST_TOP), FX(LB[1] / 2 + 4), Z(MAST_TOP + 6), fc=MAST, z=4)
    R(FX(-LB[1] / 2), Z(lid_z0), FX(LB[1] / 2), Z(lid_z1), fc=LID, z=5)
    R(FX(-12), Z(CH - 12), FX(12), Z(CH + 12), fc=CAMC, z=6)
    cog(FX(0), Z(COGH))
    cl((FX(0), sy - 4), (FX(0), Z(MAST_TOP + 6) + 5))
    cx_, cy_ = FX(TR / 2), sy
    ax.plot([FX(0), cx_], [Z(COGH), cy_], color=RED, lw=0.9, zorder=8)
    ax.plot([cx_, cx_], [cy_, Z(COGH) + 8], color=RED, lw=0.5, ls="--", zorder=8)
    ang = math.degrees(math.atan2(Z(COGH) - cy_, FX(0) - cx_))
    ax.add_patch(Arc((cx_, cy_), 24, 24, theta1=90, theta2=ang, color=RED, lw=0.8, zorder=8))
    ax.text(cx_ - 22, cy_ + 4, f"{ROLL_DEG:.1f}°", color=RED, fontsize=7.6, fontweight="bold", zorder=9)
    dimh(FX(-TR / 2), FX(TR / 2), sy, sy - 9, f"track {TR:.0f}")
    dimh(FX(-W_ / 2), FX(W_ / 2), sy, sy - 17, f"W {W_:.0f}")
    dimv(sy, Z(COGH), FX(-W_ / 2), FX(-W_ / 2) - 7, f"cog_h {COGH:.0f}")
    if TR < W_ + WHEEL_W:
        ax.text(FX(0), sy - 24, "빗금 = 바퀴·차체 간섭", fontsize=6.4, color=RED, ha="center", va="top")
    for yw in (-TR / 2, TR / 2):
        y_in = max(-W_ / 2, yw - WHEEL_W / 2); y_out = min(W_ / 2, yw + WHEEL_W / 2)
        if y_out > y_in:
            R(FX(y_in), Z(GC), FX(y_out), Z(2 * WR), fc="none", ec=RED, lw=0.7, z=6, hatch="////")

    # ---------------- top view (rotated: forward = up)
    tx, ty = 358, 206
    TX = lambda yl: tx - yl * s; TY = lambda x: ty + x * s
    ax.text(tx, TY(L_ / 2) + 21, "평면도 / TOP (전방 ↑)", ha="center", fontsize=9, fontweight="bold")
    R(TX(W_ / 2), TY(-L_ / 2), TX(-W_ / 2), TY(L_ / 2), fc=BODY)
    for xw in (-WB / 2, WB / 2):
        for yw in (-TR / 2, TR / 2):
            R(TX(yw - WHEEL_W / 2), TY(xw - WR), TX(yw + WHEEL_W / 2), TY(xw + WR), fc=WHEEL, z=4, alpha=0.8)
            y_in = max(-W_ / 2, yw - WHEEL_W / 2); y_out = min(W_ / 2, yw + WHEEL_W / 2)
            if y_out > y_in:
                R(TX(y_in), TY(xw - WR), TX(y_out), TY(xw + WR), fc="none", ec=RED, lw=0.7, z=5, hatch="////")
    R(TX(MW / 2), TY(mast_x0), TX(-MW / 2), TY(mast_x1), fc=MAST, z=5)
    ax.add_patch(Circle((TX(0), TY(LX)), LB[0] / 2 * s, fc=LID, ec="k", lw=0.8, zorder=6))
    ax.plot(TX(0), TY(LX), "+", color="k", ms=5, zorder=9)
    R(TX(12), TY(CX - 12), TX(-12), TY(CX + 12), fc=CAMC, z=6)
    cog(TX(0), TY(0))
    cl((TX(0), TY(-L_ / 2) - 4), (TX(0), TY(L_ / 2) + 4))
    dimh(TX(W_ / 2), TX(-W_ / 2), TY(L_ / 2), TY(L_ / 2) + 7, f"W {W_:.0f}")
    dimh(TX(TR / 2), TX(-TR / 2), TY(WB / 2 + WR), TY(L_ / 2) + 14, f"track {TR:.0f}")
    dimv(TY(-L_ / 2), TY(L_ / 2), TX(W_ / 2), TX(W_ / 2) - 6, f"L {L_:.0f}")
    dimv(TY(-WB / 2), TY(WB / 2), TX(TR / 2 + WHEEL_W / 2), TX(W_ / 2) - 22, f"WB {WB:.0f}", left=False, ty=TY(-WB / 2) + 8)
    ax.text(tx, TY(-L_ / 2) - 3, f"휠 Ø{2*WR:.0f} · 폭 {WHEEL_W:.0f} (spec)" + ("\n빗금 = 간섭" if TR < W_ + WHEEL_W else ""), fontsize=6.2,
            ha="center", va="top", color=RED)

    # ---------------- notes (lower-left strip + right column)
    nx, ny = 14, 60
    ax.text(nx, ny, "정적 전복각 · 시야 (spec 계산)", fontsize=8.2, fontweight="bold", va="top")
    nl = [f"횡: atan((track/2)/cog_h) = atan({TR/2:.0f}/{COGH:.0f}) = {ROLL_DEG:.1f}° (spec roll_over_deg)",
          f"종: atan((wheelbase/2)/cog_h) = atan({WB/2:.0f}/{COGH:.0f}) = {PITCH_DEG:.1f}° (spec pitch_over_deg, CoG x=0 [A])"
          f"  → 지배 한계 max_slope_deg {MAX_SLOPE:.1f}°",
          f"운용 경사 한계 slope_limit_deg {MECH['slope_limit_deg']:g}° [A] → tip_margin {MECH['tip_margin']:.1f}°",
          f"LiDAR {'도립' if inv else '정립'}: FOV {fov_lo:g}..+{fov_hi:g}° → 사각 반경 {BLIND_INV/1000:.2f} m "
          f"(정립이면 {BLIND_UP/1000:.1f} m)",
          f"-{abs(fov_lo):g}° 광선의 차체 여유: 전 {clear_front:.0f} · 후 {clear_rear:.0f} mm 위 (가림 없음)"
          if min(clear_front, clear_rear) > 0 else "-52° 광선이 차체에 가림!",
          f"카메라 상단 방향 {ang_cam:.0f}° → FOV {'안 (가림!)' if cam_in_fov else '밖 (가림 없음)'} · "
          f"마스트 후방 가림 ~{mast_occl:.0f}° [A: 마스트 {MW:.0f} mm]",
          f"질량 {MECH['mass_kg']:g} kg [A] · Mid-360 외형 {LB[0]:.0f}x{LB[1]:.0f}x{LB[2]:.0f} [DS 확인] · 37D 모터 Ø{MOTOR_D:.0f}"]
    for i, t_ in enumerate(nl):
        ax.text(nx, ny - 6 - i * 4.6, t_, fontsize=6.3, va="top", color=RED if "지배" in t_ or "가림!" in t_ else "k")
    nx2, ny2 = 337, 147
    mech_issues = [i for i in ISSUES if any(k in i for k in ("track", "max_slope", "ground_clear", "마스트"))]
    ax.text(nx2, ny2, "spec.py 점검" + (" — 열린 불일치" if mech_issues else " — 기구 불일치 없음"), fontsize=8.0,
            fontweight="bold", va="top", color=RED if mech_issues else GREEN)
    if inv:
        mech_issues.append(f"(정합) 도립: 마스트 끝 {DECK:.0f}+{PARTS['chassis']['mast_h_mm']} = {MAST_TOP:.0f} = LiDAR "
                           f"바닥면, 광학중심 {LH:.0f} → 바닥면에서 {MAST_TOP-LH:.0f} mm 여야 함 [DS 확인]")
    yy = ny2 - 6
    for t_ in mech_issues:
        for j, ln in enumerate(textwrap.wrap(t_, 40)):
            ax.text(nx2, yy, ("• " if j == 0 else "   ") + ln, fontsize=6.0, va="top",
                    color="k" if t_.startswith("(정합)") else RED)
            yy -= 3.8
        yy -= 1.0
    assert yy > 66, yy
    save(fig, "RCN-M-001_mech")


# ============================================================== H-001 harness table
def h001():
    fig, fr = sheet("RCN-H-001", "하네스 · 커넥터 표 / Harness & Connectors")
    ax = mm_axes(fig)
    header(ax, "RCN-H-001  하네스 · 커넥터 표",
           "전선 굵기는 E-001 퓨즈 정격 ≤ 허용전류 [A: 섀시 배선, 공기 중].  신호선은 E-002 핀맵.  "
           "커넥터 형식은 제안 — 실제 부품 핀아웃과 대조 필요.")
    P = PIN
    enc = lambda k: f"{P['ENC'+str(k)][1]}/{P['ENC'+str(k)][2]} ({P['ENC'+str(k)][0]})"
    rows = [
        ("ID", "명칭", "커넥터 (EN)", "핀", "AWG", "From → To", "설계전류 / 비고"),
        ("J1", "배터리 주전원", "XT60 (M/F)", "2", "12", "BT1 P+/P- → F1 30 A 홀더", f"I_PEAK {I_PEAK:.1f} A"),
        ("J2", "주전원 스위치 SW1", "링단자 M5 x2", "2", "12", "F1 → SW1 → Q1", "30 A 정격 스위치"),
        ("J3", "K1 접촉기 접점", "링단자 M5 x2", "2", "12", "+VBAT_SW → K1 → +VMOT", f"{I_MOT_BUS:.1f} A pk"),
        ("J4", "K1 코일", "6.3 mm 탭 x2", "2", "22", "F7 → S1 → K2 → R5 → K1 → Q2", f"{K1_I:.2f} A · R5 {K1_RS} Ω 1 W · D2 병렬"),
        ("J5", "E-stop S1", "나사 단자 (NC x2 블록)", "4", "22", "코일루프 / ESTOP_SENSE " + P["ESTOP"], "제2 NC = 상태 입력"),
        ("J6", "433 MHz 수신기 K2", "JST-XH 4p", "4", "22", "+VBAT_SW, GND, COM, NO", "링크 상실 → 개방 [확인]"),
        ("J7/J8", "MDD20A 전원 (U1/U2)", "나사 단자 2p", "2", "14", "F2/F3 15 A → B+ / B-", f"{I_DRV:.1f} A pk 각"),
        ("J9/J10", "MDD20A 신호 (U1/U2)", "Dupont 2.54 5p", "5", "26",
         "PWM1 DIR1 PWM2 DIR2 GND → Nucleo", f"{P['PWM'][0][1]}.. {P['DIR'][0]}.."),
        ("M1-M4", "모터 전원", "JST-VH 2p", "2", "18", "MDD20A MxA/MxB → 37D 모터",
         f"스톨 {M['stall_A_24V']} A@24 V · {I_STALL_AT_VBAT:.1f} A@{V_NOM:g} V"),
        ("E1", "엔코더 좌전", "JST-XH 4p", "4", "26", "5V GND A B → " + enc(1), "Vcc 5 V (≥ 3.5 V)"),
        ("E2", "엔코더 좌후", "JST-XH 4p", "4", "26", "5V GND A B → " + enc(2), "FT 핀"),
        ("E3", "엔코더 우전", "JST-XH 4p", "4", "26", "5V GND A B → " + enc(3), "FT 핀"),
        ("E4", "엔코더 우후", "JST-XH 4p", "4", "26", "5V GND A B → " + enc(4), "FT 핀"),
        ("J11", "Jetson DC 입력", "5.5/2.5 배럴", "2", "18", "F4 → U3 LTC4359 → L1/C1 → U6 DC 잭", f"{I_JET:.2f} A @ {V_MIN:g} V"),
        ("J12", "Mid-360 전원·Eth", "M12 → 3분기 케이블 (Livox)", "8", "20",
         "F6 → 9-27 V, RJ45 → Jetson eth0", f"{I_LID:.2f} A · 100BASE-TX"),
        ("J13", "5 V 레일", "나사 단자 / 솔더", "2", "20", "F5 → U4 D36V50F5 → Nucleo E5V", f"{I_5V:.2f} A @ 12 V"),
        ("J14", "IMU SPI", "Dupont 2.54 8p", "8", "28",
         "3V3 GND SCLK SDO SDI CS INT1 → " + "/".join(p for _, p in P["SPI"]), "≤ 10 cm, 꼬임 GND"),
        ("J15", "MCU ↔ Jetson USB", "USB micro-B ↔ USB-A", "4", "-", "Nucleo CN13 (" + P["USB"][1] + ") → Jetson", "CDC ACM"),
        ("J16", "MCU ↔ Jetson UART", "Dupont 2.54 3p", "3", "26", P["UART"][1] + " ↔ 40p 8/10, GND", "예비"),
        ("J17", "카메라 CSI", "FFC 15p → 22p 0.5 mm", "22", "-", "IMX219 → Jetson CAM0", "≤ 30 cm"),
        ("J18", "GNSS USB", "USB-C ↔ USB-A", "4", "-", "ZED-F9P → Jetson", "5 V 급전"),
        ("J19", "PPS", "JST-SH 3p", "3", "28", "F9P PPS → U10 → " + P["PPS"][1] + " / Jetson GPIO", "33 Ω 직렬"),
        ("J20", "INA226 · 감시", "JST-SH 4p (Qwiic)", "4", "28", "I2C1 " + P["I2C"][1] + " + ALERT " + P["INA_ALERT"], "3.3 V"),
        ("J21", "감시 분압", "JST-XH 3p", "3", "26",
         "VBAT → " + P["VBAT"][1] + ", MOT_SENSE → " + P["MOT_SENSE"][1] + ", GND", f"{V_ADC_MAX:.2f} V max"),
        ("J22", "MOTOR_EN", "JST-XH 2p", "2", "26", P["MOTOR_EN"] + " → Q2 게이트, GND", "100k 풀다운"),
        ("J23", "팬 x2", "JST-PH 2p", "2", "26", "+5V → 팬", "5 V"),
    ]
    colw = [16, 38, 50, 9, 11, 118, 60]
    x0 = 14
    rh = 7.2
    n = len(rows)
    ytop = 262
    xs = [x0]
    for c in colw: xs.append(xs[-1] + c)
    ax.add_patch(Rectangle((x0, ytop - rh), xs[-1] - x0, rh, fc="#eef4fb", ec="none", zorder=1))
    for i, r in enumerate(rows):
        y = ytop - (i + 0.5) * rh
        if i and r[4] in ("12", "14"):
            ax.add_patch(Rectangle((x0, ytop - (i + 1) * rh), xs[-1] - x0, rh, fc="#fff3e6", ec="none", zorder=1))
        for j, c in enumerate(r):
            ax.text(xs[j] + 1.2, y, c, fontsize=7.0 if i else 7.6, va="center", zorder=6,
                    fontweight="bold" if (i == 0 or j == 0) else "normal",
                    color=RED if (i and j == 6 and "확인" in c) else "k")
    for i in range(n + 1):
        ax.plot([x0, xs[-1]], [ytop - i * rh] * 2, color="k", lw=0.9 if i in (0, 1, n) else 0.35, zorder=5)
    for xx in xs:
        ax.plot([xx, xx], [ytop - n * rh, ytop], color="k", lw=0.5, zorder=5)
    yb = ytop - n * rh - 4
    assert yb > 62, yb
    ax.text(x0, yb, "주황 줄 = 대전류 (12/14 AWG).  모든 GND 는 BT1 P- 별형 접지점으로.  '-' = 규격 케이블 (굵기 해당 없음).",
            fontsize=6.8, va="top", color=GREY)
    save(fig, "RCN-H-001_harness")


# ============================================================== A-001 assembly sequence
def a001():
    fig, fr = sheet("RCN-A-001", "조립 순서도 / Assembly Sequence")
    ax = mm_axes(fig)
    header(ax, "RCN-A-001  조립 순서도 — 단계마다 조립 후 측정, 합격해야 다음 단계",
           "합격 기준의 수치는 spec.py 계산값.  [A] = 이 도면의 가정 허용차.  배터리는 10단계 전까지 연결하지 않고 전류제한 "
           "벤치 전원으로 대신한다.  측정값은 기록지에 남긴다.")
    vdiv = V_NOM * K_DIV
    tpr = DRIVE["ticks_per_rev"]
    steps = [
        ("1", "프레임", "2020 압출재 프레임 + 3 mm 알루미늄 데크 조립\n모서리 브래킷 체결, 데크 접지 러그 1개",
         f"외형 {L_:.0f} x {W_:.0f} x {HB:.0f} mm ±1 [A] · 대각선 차 ≤ 1 mm [A]\n"
         "데크 ↔ 프레임 도통 < 1 Ω (섀시 접지 한 점)", "M-001"),
        ("2", "모터 · 휠", "37D 50:1 모터 x4 브래킷 체결, 휠 Ø120 장착\n엔코더 케이블 E1-E4 라벨링",
         f"wheelbase {WB:.0f} · track {TR:.0f} mm ±1 [A] · 지상고 ≥ {GC:.0f} mm (모터 하단)\n"
         "손으로 돌려 걸림 없음 · 모터 단자 ↔ 케이스 절연 > 1 MΩ", "M-001"),
        ("3", "전원 버스", "BT1 자리 · F1 · SW1 · Q1 · D1 · RS1 · 버스 · F2-F7 배선\n(배터리 미연결, 퓨즈 빼 둔 상태)",
         f"+VBAT_SW ↔ GND > 1 MΩ · 주경로 도통 < 50 mΩ [A]\n벤치 {V_NOM:g} V / 0.5 A 제한: 역극성 인가 시 전류 < 1 mA · "
         f"VBAT_SENSE = {vdiv:.2f} V (x{K_DIV:.3f})", "E-001"),
        ("4", "E-stop 체인", "F7 → S1 → K2 → R5 → K1 코일 → Q2, D2 병렬\nK1 접점 → +VMOT → F2/F3 (MDD20A 아직 미연결)",
         f"벤치 {V_MAX:g} V: 코일 전압 {K1_V_HI:.1f} V (≤ {K1_V_MAXCONT:g}) · {V_MIN:g} V: {K1_V_LO:.1f} V 에서 흡인\n"
         f"S1 눌림 / K2 링크 끊김 / MOTOR_EN=0 각각 → +VMOT 0 V · MOT_SENSE 0 ↔ {vdiv:.2f} V", "E-001"),
        ("5", "MCU", "NUCLEO-H753ZI 장착, U4 D36V50F5 → E5V\nINA226 · 분압 · ESTOP_SENSE · MOTOR_EN 배선, fw 적재",
         f"+5V = 5.00 ±0.10 V [A] · 3V3 = 3.30 ±0.05 V · INA226 전류 = 벤치 표시 ±2 % [A]\n"
         "IWDG 시험: 디버거로 정지 → 리셋 → MOTOR_EN=0 → K1 개방 확인", "E-001/E-002"),
        ("6", "Jetson", "Orin Nano 장착, F4 → LTC4359 → L1/C1 → DC 잭\nNVMe · USB-CDC 로 MCU 연결",
         f"+VJET = 팩 전압 - 이상적 다이오드 강하 (< 50 mV [A]) · 부팅 {P_JET[1]:g} W 부하에서 리셋 없음\n"
         f"C1 홀드업 {HOLDUP_MS:.2f} ms ({V_MIN:g} → 9 V @ {I_JET:.2f} A) · 하트비트 끊으면 MCU 가 정지", "E-001/E-002"),
        ("7", "LiDAR 마스트 (도립)", f"마스트 {PARTS['chassis']['mast_h_mm']} mm 세우고 상판 아래 Mid-360 거꾸로 체결\n"
         "F6 → 9-27 V, eth0 · ptp4l 설정",
         f"광학중심 높이 {LH:.0f} ±5 mm [A] · 바닥 첫 링 반경 ≈ {MECH['lidar_blind_r_inverted']:.2f} m\n"
         "ptp4l 오프셋 수렴 (HW 타임스탬프 지원 여부 기록 — 미확인)", "M-001/E-002"),
        ("8", "카메라", "IMX219 브래킷 (피치 " + f"{CP:g}°), CSI 15→22 핀 케이블로 CAM0",
         f"높이 {CH:.0f} · x {CX:.0f} mm · 바닥 표적이 영상 중심에 오는 거리 ≈ {CAM_GROUND/1000:.2f} m (±0.2 [A])\n"
         "1280x720@30 스트림 · V4L2 타임스탬프 단조 증가", "M-001"),
        ("9", "하네스", "H-001 표대로 전선·커넥터 제작, 묶음 고정\n대전류(12/14 AWG) 와 신호선 분리 배선",
         "선마다 끝-끝 도통 < 1 Ω, 이웃 핀 절연 > 1 MΩ · 당김 시험 [A]\n"
         "엔코더 Vcc = 5 V (≥ 3.5 V 필요), A/B 는 5 V 허용 핀에만 (E-002)", "H-001"),
        ("10", "기동 점검", "배터리 연결, 바퀴 띄운 상태에서 순서대로",
         f"엔코더: 전진 1회전 = +{tpr} 카운트 x4 (부호 동일) · {DRIVE['dist_per_tick_mm']:.3f} mm/tick\n"
         f"IMU: 정지 +z ≈ +9.81 m/s^2 · 좌회전 yaw rate > 0 · PPS 1 Hz 캡처\n"
         f"부하 중 S1 눌러 모터 정지 · 경사 {MECH['slope_limit_deg']:g}° 경보 동작", "전체"),
    ]
    head = ("No", "단계", "작업", "검증 측정 · 합격 기준", "도면")
    colw = [12, 32, 112, 214, 22]
    x0, ytop, rh0 = 14, 262, 8.0
    xs = [x0]
    for c in colw: xs.append(xs[-1] + c)
    heights = [rh0] + [max(r[2].count("\n"), r[3].count("\n")) * 4.3 + 10.2 for r in steps]
    ys = [ytop]
    for h in heights: ys.append(ys[-1] - h)
    assert ys[-1] > 62, ys[-1]
    ax.add_patch(Rectangle((x0, ys[1]), xs[-1] - x0, rh0, fc="#eef4fb", ec="none", zorder=1))
    for i, r in enumerate([head] + steps):
        yc = (ys[i] + ys[i + 1]) / 2
        if i and i % 2 == 0:
            ax.add_patch(Rectangle((x0, ys[i + 1]), xs[-1] - x0, heights[i], fc="#fafafa", ec="none", zorder=1))
        for j, c in enumerate(r):
            ax.text(xs[j] + 1.5, yc, c, fontsize=(7.8 if i == 0 else (9 if j == 0 else 6.9)), va="center", zorder=6,
                    fontweight="bold" if (i == 0 or j in (0, 1)) else "normal", linespacing=1.45,
                    color=(RED if (i and j == 3 and ("시험" in c or "S1" in c)) else "k"))
    for i, y in enumerate(ys):
        ax.plot([x0, xs[-1]], [y, y], color="k", lw=0.9 if i in (0, 1, len(ys) - 1) else 0.35, zorder=5)
    for xx in xs:
        ax.plot([xx, xx], [ys[-1], ytop], color="k", lw=0.5, zorder=5)
    ax.text(x0, ys[-1] - 3, "빨간 칸 = 안전 기능 시험 포함 (실패 시 다음 단계 금지).  모든 전기 측정은 SW1 OFF 에서 배선, "
            "ON 은 측정 순간에만.", fontsize=6.8, va="top", color=GREY)
    save(fig, "RCN-A-001_assembly")


import numpy as np

if __name__ == "__main__":
    print("I_PEAK", round(I_PEAK, 2), "I_MOT_BUS", round(I_MOT_BUS, 2), "I_JET", round(I_JET, 2),
          "I_5V", round(I_5V, 2), "I_LID", round(I_LID, 2))
    print("K1 R5", K1_RS, round(K1_V_HI, 2), round(K1_V_LO, 2), "holdup ms", round(HOLDUP_MS, 2), "ROLL", round(ROLL_DEG, 2), "PITCH", round(PITCH_DEG, 2), "MAST_TOP", MAST_TOP, "CAM_GROUND", round(CAM_GROUND))
    for f in (e001, e002, s001, m001, h001, a001):
        f()
    print("\nspec.py issues:")
    for i in ISSUES:
        print(" -", i)
