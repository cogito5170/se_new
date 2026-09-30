"""시나리오 1-8 + 모델 검사 -> OUT/battery.json.   python3 -m ruh2.experiments"""
import json, math
import numpy as np
from ruh2 import model as N
from ruh2 import spec
from ruh2 import paths
paths.ensure()

OUT = {}
dt = 5.0
Q = spec.CELL["Q_Ah"]


def energy(c):
    ch, dis, h = c["I"] > 0, c["I"] < 0, c["h"]
    return dict(Qin=float((c["I"] * h)[ch].sum() / 3600), Qout=float(-(c["I"] * h)[dis].sum() / 3600),
                Ein=float((c["V"] * c["I"] * h)[ch].sum() / 3600), Eout=float(-(c["V"] * c["I"] * h)[dis].sum() / 3600))


def pack(c, keys=("t", "V", "I", "p", "s", "T", "soc_count", "soc_p", "E_h2_rhe", "A_ru", "eta_ni", "eta_h2", "f_oer", "q"), every=1):
    return {k: [round(float(x), 6) for x in c[k][::every]] for k in keys}


# 1) standard cycle C/2: charge 110 %, rest 1 h, discharge to 1.0 V, rest 30 min
st = N.init()
rows, st = N.run([("cc", 0.5 * Q, {"s_in": 1.10}), ("rest", 0, {"t": 3600}), ("cc", -0.5 * Q, {"V_min": 1.0}), ("rest", 0, {"t": 1800})], st)
c = N.cols(rows)
e = energy(c)
OUT["cycle"] = dict(series=pack(c, every=6), **e, CE=e["Qout"] / e["Qin"], EE=e["Eout"] / e["Ein"],
                    p_max=float(c["p"].max()), T_max=float(c["T"].max() - 273.15))
cyc = c

# independent check A: hydrogen mass balance vs closed form from charge passed
n_series = np.array([N.n_from_p(p, T) for p, T in zip(c["p"], c["T"])])
I = c["I"]
fo = c["f_oer"]
dn_pred = np.cumsum((I / (2 * N.F) - 2 * I * np.where(I > 0, fo, 0) / (4 * N.F) - c["I_rev"] / (2 * N.F) - c["r_sd"] * N.P["Q_C"] / (2 * N.F)) * c["h"])
mb_err = float(np.max(np.abs((n_series - n_series[0]) - np.concatenate([[0], dn_pred[:-1]]))))
# independent check B: pressure <-> NiOOH (closed form, ideal gas): p*298/T - p0 = s * dp_full + (s0 const)
lin = np.polyfit(c["s"], c["p"] * 298.15 / c["T"], 1)
OUT["checks"] = dict(h2_mass_balance_max_err_mol=mb_err, h2_total_mol=float(n_series.max()),
                     p_vs_s_slope_bar=float(lin[0]), p_vs_s_slope_closed_form=float(spec.VESSEL["dp_full_bar_25C"]),
                     p_vs_s_intercept=float(lin[1]))
# independent check C: energy balance: E_in - E_out = heat + stored(chem) change (cycle closes near same s)
heat = float(np.sum(c["q"] * c["h"]) / 3600)                     # Wh (incl. self-discharge & recombination)
OUT["checks"]["energy_in_minus_out_Wh"] = e["Ein"] - e["Eout"]
OUT["checks"]["heat_Wh"] = heat
OUT["checks"]["ds_over_cycle"] = float(c["s"][-1] - c["s"][0])
# independent check D: step-size convergence (dt=5 s vs 1 s) on the discharge capacity
st2 = N.init()
r2, _ = N.run([("cc", 0.5 * Q, {"s_in": 1.10}), ("rest", 0, {"t": 3600}), ("cc", -0.5 * Q, {"V_min": 1.0})], st2, dt=1.0)
c2 = N.cols(r2)
OUT["checks"]["Qout_dt1"] = float(-(c2["I"] * c2["h"])[c2["I"] < 0].sum() / 3600)
OUT["checks"]["Qout_dt5"] = e["Qout"]

# 2) rate capability (after identical C/5 charge)
rate = {}
for cr in (0.2, 0.5, 1.0, 2.0):
    s = N.init()
    _, s = N.run([("cc", 0.2 * Q, {"s_in": 1.10}), ("rest", 0, {"t": 3600})], s)
    r, _ = N.run([("cc", -cr * Q, {"V_min": 1.0})], s)
    cc_ = N.cols(r)
    rate[str(cr)] = dict(Qout=float(-(cc_["I"] * cc_["h"]).sum() / 3600), Vavg=float((cc_["V"] * cc_["I"] * cc_["h"]).sum() / (cc_["I"] * cc_["h"]).sum()),
                         curve=dict(q=[float(x) for x in (np.cumsum(-cc_["I"] * cc_["h"]) / 3600)[::4]], V=[float(x) for x in cc_["V"][::4]]))
OUT["rate"] = rate

# 3) temperature: charge acceptance
temp = {}
for Tc in (10, 25, 40):
    s = N.init(T_C=Tc)
    r, s = N.run([("cc", 0.5 * Q, {"s_in": 1.10})], s, T_amb_C=Tc)
    r2_, s = N.run([("rest", 0, {"t": 1800}), ("cc", -0.5 * Q, {"V_min": 1.0})], s, T_amb_C=Tc)
    cc_ = N.cols(r2_)
    temp[str(Tc)] = dict(Qout=float(-(cc_["I"] * cc_["h"])[cc_["I"] < 0].sum() / 3600), s_after_charge=float(N.cols(r)["s"][-1]))
OUT["temp"] = temp

# 4) self-discharge storage 72 h: pressure SOC vs coulomb count
sd = {}
for Tc in (25, 40):
    s = N.init(T_C=Tc)
    _, s = N.run([("cc", 0.5 * Q, {"s_in": 1.0})], s, T_amb_C=Tc)
    r, s = N.run([("rest", 0, {"t": 72 * 3600})], s, T_amb_C=Tc, dt=60.0)
    cc_ = N.cols(r)
    sd[str(Tc)] = dict(t_h=[float(x) for x in (cc_["t"] - cc_["t"][0])[::30] / 3600], s_true=[float(x) for x in cc_["s"][::30]],
                       soc_p=[float(x) for x in cc_["soc_p"][::30]], soc_count=[float(x) for x in cc_["soc_count"][::30]],
                       loss_72h=float(cc_["s"][0] - cc_["s"][-1]),
                       pressure_soc_err_end=float(abs(cc_["soc_p"][-1] - cc_["s"][-1])),
                       count_soc_err_end=float(abs(cc_["soc_count"][-1] - cc_["s"][-1])))
OUT["selfdis"] = sd

# 5) H2 catalyst comparison at C/2: Ru/C (this design), Pt/C, NiMoCo (literature eta10 ~80 mV HER)
def j0_from_eta10(eta10):
    b = N.R * 298.15 / (0.5 * N.F)
    return 0.010 / (2 * math.sinh(eta10 / b))

cat = {}
for name, j0 in (("Ru/C (본 설계)", None), ("Pt/C (Ru/C의 j0 x 1.08/3.09)", N.P["j0_h2_geo"] * 1.08 / 3.09),
                 ("NiMoCo (eta10≈80 mV)", j0_from_eta10(0.080))):
    s = N.init()
    r, _ = N.run([("cc", 0.5 * Q, {"s_in": 1.10}), ("rest", 0, {"t": 3600}), ("cc", -0.5 * Q, {"V_min": 1.0})], s, j0_h2_override=j0)
    cc_ = N.cols(r)
    en = energy(cc_)
    cat[name] = dict(EE=en["Eout"] / en["Ein"], Qout=en["Qout"], eta_h2_mV_dis=float(np.median(cc_["eta_h2"][cc_["I"] < 0]) * 1e3),
                     j0_geo=float(j0 or N.P["j0_h2_geo"]))
OUT["catalyst"] = cat

# 6) fault: deep discharge with/without protection and precharge -> Ru oxidation
fault = {}
for label, pc, prot in (("보호 ON, H2 예충전 1 bar", None, True), ("보호 OFF, H2 예충전 1 bar", None, False),
                        ("보호 OFF, 예충전 0 bar", 0.0, False)):
    s = N.init(precharge_bar=pc)
    _, s = N.run([("cc", 0.5 * Q, {"s_in": 1.05}), ("rest", 0, {"t": 600})], s)
    r, s = N.run([("cc", -1.0 * Q, {"t": 1.4 * 3600})], s, protect=prot)
    cc_ = N.cols(r)
    fault[label] = dict(t=[float(x) for x in (cc_["t"] - cc_["t"][0])[::6] / 3600], V=[float(x) for x in cc_["V"][::6]],
                        E_h2=[float(x) for x in cc_["E_h2_rhe"][::6]], A_ru=[float(x) for x in cc_["A_ru"][::6]],
                        p=[float(x) for x in cc_["p"][::6]], A_ru_end=float(cc_["A_ru"][-1]), tripped=any(x.get("trip") for x in r))
OUT["fault"] = fault

# 7) overcharge 1C for 2 h, no termination except hardware trips
s = N.init()
r, s = N.run([("cc", 1.0 * Q, {"t": 2 * 3600})], s)
cc_ = N.cols(r)
OUT["overcharge"] = dict(t=[float(x) for x in cc_["t"][::12] / 3600], p=[float(x) for x in cc_["p"][::12]], T=[float(x) for x in cc_["T"][::12] - 273.15],
                         s=[float(x) for x in cc_["s"][::12]], f_oer=[float(x) for x in cc_["f_oer"][::12]], p_max=float(cc_["p"].max()), T_max=float(cc_["T"].max() - 273.15))

# 8) EIS of the cell vs SOC (small-signal, analytic)
def Zcell(f, s, T=298.15):
    w = 2 * np.pi * f
    _, j0n = N.eta_ni(0.0, s, T)
    Rn = N.R * T / (0.5 * N.F) / (2 * j0n) / N.A_H2 * 1.0          # d eta/dI at I=0
    Rh = N.R * T / (0.5 * N.F) / (2 * N.P["j0_h2_geo"]) / N.A_H2
    Cn = 0.8 * N.A_H2          # F  (Ni electrode pseudo-/double-layer, 0.8 F/cm2 geo) [A]
    Ch = 30e-6 * N.A_H2 * 60   # F  Ru/C double layer x roughness                      [A]
    sigma = 0.004 / max(math.sqrt(s * (1 - s)), 0.05)   # ohm s^-1/2  proton diffusion in Ni(OH)2 [A]
    Zw = sigma * (1 - 1j) / np.sqrt(w)
    Zn = 1 / (1 / (Rn + Zw) + 1j * w * Cn)
    Zh = 1 / (1 / Rh + 1j * w * Ch)
    return N.P["R_ohm"] + Zn + Zh

fe = np.logspace(-2, 4, 49)
OUT["eis"] = dict(f=fe.tolist(), soc={str(s): dict(re=Zcell(fe, s).real.tolist(), im=Zcell(fe, s).imag.tolist()) for s in (0.1, 0.3, 0.5, 0.7, 0.9)})

OUT["params"] = {k: v for k, v in N.P.items()}
OUT["spec"] = dict(CELL=spec.CELL, VESSEL=spec.VESSEL, LIMITS=spec.LIMITS, BMS=spec.BMS)
json.dump(OUT, open(paths.OUT / "battery.json", "w"), ensure_ascii=False)
print(json.dumps({k: OUT[k] for k in ("checks",)}, indent=1))
print({k: v for k, v in OUT["cycle"].items() if k != "series"})
print({k: round(v["Qout"], 3) for k, v in OUT["rate"].items()}, {k: round(v["Vavg"], 3) for k, v in OUT["rate"].items()})
print(OUT["temp"])
print({k: {kk: vv for kk, vv in v.items() if not isinstance(vv, list)} for k, v in OUT["selfdis"].items()})
print(OUT["catalyst"])
print({k: (v["A_ru_end"], v["tripped"], min(v["V"]), max(v["E_h2"])) for k, v in OUT["fault"].items()})
print(OUT["overcharge"]["p_max"], OUT["overcharge"]["T_max"])
