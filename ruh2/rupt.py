"""python3 -m ruh2.rupt  -> OUT/rupt.json
Ru vs Pt (cost, activity), Ru-oxidation countermeasures, self-discharge countermeasures.
Prices: search snippets 2026-09 [조각]; activity: Nat. Commun. 2024 snippet [조각]; densities: handbook values."""
import json, math, copy
import numpy as np
from ruh2 import model as N
from ruh2 import spec
from ruh2 import paths
paths.ensure()

OUT = {}
Q = spec.CELL["Q_Ah"]
A_H2 = spec.CELL["h2_area_cm2"]
OZ = 31.1035
PRICE = {"Ru": dict(usd_oz=(1675, 1750), date="2026-09-17 / 09-28"), "Pt": dict(usd_oz=(1751, 1811), date="2026-09-28 / 09-18")}
RHO = {"Ru": 12.37, "Pt": 21.45}                  # g/cm3
J0SPEC = {"Ru": 3.09e-3, "Pt": 1.08e-3}          # A/cm2 of metal surface (alkaline HOR) [조각]
ECSA_RU = N.P["ecsa_m2_g"]                        # 60 m2/g [A]
ECSA = {"Ru": ECSA_RU, "Pt": ECSA_RU * RHO["Ru"] / RHO["Pt"]}   # same particle size -> area/mass ~ 1/rho
UT = N.P["utilisation"]

def j0geo(metal, load_mg):
    return J0SPEC[metal] * load_mg * 1e-3 * ECSA[metal] * 1e4 * UT

def cycle(j0=None, **run_kw):
    st = N.init()
    r, _ = N.run([("cc", 0.5 * Q, {"s_in": 1.10}), ("rest", 0, {"t": 3600}), ("cc", -0.5 * Q, {"V_min": 1.0})], st, j0_h2_override=j0, **run_kw)
    c = N.cols(r)
    ch, dis = c["I"] > 0, c["I"] < 0
    Ein = (c["V"] * c["I"] * c["h"])[ch].sum(); Eout = -(c["V"] * c["I"] * c["h"])[dis].sum()
    return dict(EE=Eout / Ein, eta_dis_mV=float(np.median(c["eta_h2"][dis]) * 1e3))

# ---- 1. cost vs activity sweep
loads = [0.02, 0.05, 0.1, 0.2, 0.5, 1.0]
sweep = {}
for mtl in ("Ru", "Pt"):
    rows = []
    for L in loads:
        mass_mg = L * A_H2
        cost = mass_mg / 1000 / OZ * np.mean(PRICE[mtl]["usd_oz"])
        r = cycle(j0=j0geo(mtl, L))
        # 2C discharge overpotential of the H2 electrode (closed form, BV)
        j2c = 2.0 * Q / A_H2
        eta2c = N.R * 298.15 / (0.5 * N.F) * math.asinh(j2c / (2 * j0geo(mtl, L))) * 1e3
        rows.append(dict(load=L, mass_mg=mass_mg, cost_usd=cost, EE=r["EE"], eta_05C_mV=r["eta_dis_mV"], eta_2C_mV=eta2c))
    sweep[mtl] = rows
OUT["sweep"] = sweep
ratio_area = RHO["Pt"] / RHO["Ru"]; ratio_j0 = J0SPEC["Ru"] / J0SPEC["Pt"]
OUT["ratios"] = dict(area_per_mass=ratio_area, j0=ratio_j0, current_per_mass=ratio_area * ratio_j0,
                     molar_mass=dict(Ru=101.07, Pt=195.08), atoms_per_usd=(195.08 / 101.07) * (np.mean(PRICE["Pt"]["usd_oz"]) / np.mean(PRICE["Ru"]["usd_oz"])))
OUT["price"] = PRICE; OUT["ecsa"] = ECSA
# equal-performance catalyst cost: Pt loading that gives the same j0_geo as Ru at 0.5 mg/cm2
L_pt_eq = 0.5 * (J0SPEC["Ru"] * ECSA["Ru"]) / (J0SPEC["Pt"] * ECSA["Pt"])
c_ru = 0.5 * A_H2 / 1000 / OZ * np.mean(PRICE["Ru"]["usd_oz"]); c_pt = L_pt_eq * A_H2 / 1000 / OZ * np.mean(PRICE["Pt"]["usd_oz"])
OUT["equal_perf"] = dict(L_ru=0.5, L_pt=L_pt_eq, cost_ru=c_ru, cost_pt=c_pt, saving=1 - c_ru / c_pt)
# price-shock sensitivity: Ru at the 2025 level ($560/oz) and at 2x today's
OUT["price_scenarios"] = {k: 0.5 * A_H2 / 1000 / OZ * v for k, v in (("Ru 2025-03 ≈ $560/oz", 560), ("Ru 2026-09 ≈ $1,713/oz", 1712.5), ("Ru ×2 충격", 3425))}

# ---- 2. Ru-oxidation countermeasures (1C over-discharge 1.4 h)
def fault(pre, prot, pmin=None, eox=None):
    old = N.P["E_ox"]
    if eox: N.P["E_ox"] = eox
    s = N.init(precharge_bar=pre)
    _, s = N.run([("cc", 0.5 * Q, {"s_in": 1.05}), ("rest", 0, {"t": 600})], s)
    stop = {"t": 1.4 * 3600}
    if pmin: stop["p_min"] = pmin
    r, s = N.run([("cc", -1.0 * Q, stop)], s, protect=prot)
    N.P["E_ox"] = old
    c = N.cols(r)
    return dict(A_end=float(c["A_ru"][-1]), E_max=float(np.max(c["E_h2_rhe"])), V_min=float(np.min(c["V"])),
                stopped_by=("HW 0.9 V" if any(x.get("trip") for x in r) else ("p_min" if any(x.get("stop_p") for x in r) else "시간 종료")))
OX = [("대책 없음 (예충전 0, 보호 없음)", dict(pre=0.0, prot=False)),
      ("① H₂ 예충전 1 bar만", dict(pre=None, prot=False)),
      ("② HW 0.9 V 차단만", dict(pre=0.0, prot=True)),
      ("③ 압력 하한 정지 p < 0.3 bar만", dict(pre=0.0, prot=False, pmin=0.3)),
      ("④ 내산화 Ru (Pt 도핑, 개시 0.8 V)만", dict(pre=0.0, prot=False, eox=0.8)),
      ("①+② (본 설계)", dict(pre=None, prot=True))]
OUT["oxidation"] = [dict(name=n, **fault(**kw)) for n, kw in OX]

# ---- 3. self-discharge countermeasures (72 h open circuit)
def sd(T_C=25.0, vgas_factor=1.0, s_store=1.0, k_factor=1.0):
    oldV, oldk = N.V_GAS, N.P["k_sd25"]
    N.V_GAS = oldV * vgas_factor; N.P["k_sd25"] = oldk * k_factor
    s = N.init(T_C=T_C)
    _, s = N.run([("cc", 0.5 * Q, {"s_in": s_store})], s, T_amb_C=T_C)
    s0 = s["s"]
    r, s = N.run([("rest", 0, {"t": 72 * 3600})], s, T_amb_C=T_C, dt=60.0)
    N.V_GAS, N.P["k_sd25"] = oldV, oldk
    c = N.cols(r)
    return dict(loss_pct_of_Q=float((s0 - c["s"][-1]) * 100), rel_loss=float((s0 - c["s"][-1]) / s0 * 100), p_start=float(c["p"][0]))
SD = [("기준: 25 °C, 완충 보관", dict()),
      ("① 보관 온도 10 °C", dict(T_C=10.0)),
      ("② 자유 기체 체적 ×2 (압력 ↓)", dict(vgas_factor=2.0)),
      ("③ 50 % SOC로 보관", dict(s_store=0.5)),
      ("④ 친수성 분리막: H₂ 확산 ½ (가정)", dict(k_factor=0.5)),
      ("①+②+④", dict(T_C=10.0, vgas_factor=2.0, k_factor=0.5)),
      ("참고: 40 °C 보관", dict(T_C=40.0))]
OUT["selfdis"] = [dict(name=n, **sd(**kw)) for n, kw in SD]
json.dump(OUT, open(paths.OUT / "rupt.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(OUT["ratios"], indent=1)); print(OUT["equal_perf"]); print(OUT["price_scenarios"])
for r in OUT["oxidation"]: print(r)
for r in OUT["selfdis"]: print(r)
for m in ("Ru", "Pt"):
    for r in sweep[m]: print(m, r)
