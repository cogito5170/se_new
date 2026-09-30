"""0-D model of the RuH2-P1 Ni–H2 cell (Ru/C hydrogen electrode).

Cell:  (+) NiOOH + H2O + e-  <->  Ni(OH)2 + OH-          (discharge ->)
       (-) 1/2 H2 + OH-      <->  H2O + e-               (HOR on Ru, discharge ->)
       net NiOOH + 1/2 H2 <-> Ni(OH)2
Side:  overcharge OER 4OH- -> O2 + 2H2O + 4e-  ; O2 + 2H2 -> 2H2O on Ru (recombination)
       self-discharge NiOOH + 1/2 H2 -> Ni(OH)2   rate = k_sd(T) * p_H2 * s
       Ru oxidation when the H2 electrode is pushed above ~0.4 V vs RHE (H2 starvation / reversal)

Sign: I > 0 = charge.  Parameters marked [A] are assumptions; [L] literature order (search snippets).
"""
from __future__ import annotations
import math
import numpy as np
from ruh2 import spec

F, R = spec.F, spec.R
C, VES, LIM = spec.CELL, spec.VESSEL, spec.LIMITS

P = dict(
    Q_C=C["Q_Ah"] * 3600.0,
    E0_25=1.320,        # V   OCV at s=0.5, 1 bar H2, 25 C                      [L ~1.32 V]
    dE0dT=-0.5e-3,      # V/K                                                      [A]
    nernst_frac=0.6,    # fraction of ideal RT/F ln(s/(1-s)) (flattened Ni curve)  [A]
    j0_ni=2.0e-3,       # A/cm2 geometric, Ni electrode, at s=0.5                  [A]
    Ea_ni=35e3,         # J/mol                                                    [A]
    j0_h2_spec=3.09e-3, # A/cm2_Ru  Ru/C HOR exchange current (ECSA-normalised)    [L]
    ecsa_m2_g=60.0,     # Ru/C 20 wt% ECSA                                         [A]
    utilisation=0.2,    # fraction of Ru area wetted & gas-accessible in GDE       [A]
    kmt_A_cm2_bar=0.25, # HOR limiting current per bar H2 in the GDE               [A]
    asr_ohm_cm2=1.0,    # separator + electrolyte                                  [A]
    r_contact=0.005,    # ohm tabs/feedthroughs                                    [A]
    oer_s50=0.93, oer_w=0.022, oer_dT=0.004,   # charge-acceptance logistic        [A]
    sd_frac_day_25=0.08,  # self-discharge at s=1, 25 C, full pressure            [A]
    Ea_sd=60e3,           #                                                      [A]
    k_ox=1 / 120.0,       # 1/s Ru activity loss rate above onset                [A]
    E_ox=0.40,            # V vs RHE onset                                       [L]
    k_ni_lim=0.8,         # A/cm2 per unit s: NiOOH-supply limit on discharge     [A]
    dH_cell=-1.47 * F,    # J per mol e- (thermoneutral ~1.47 V)                 [A]
    dH_recomb=-571.6e3,   # J per mol O2 -> liquid water
)
A_H2 = C["h2_area_cm2"]
V_GAS = VES["free_gas_mL"] * 1e-6
P["j0_h2_geo"] = P["j0_h2_spec"] * C["ru_loading_mg_cm2"] * 1e-3 * P["ecsa_m2_g"] * 1e4 * P["utilisation"]  # A/cm2 geo
P["R_ohm"] = P["asr_ohm_cm2"] / A_H2 + P["r_contact"]
# self-discharge constant: at s=1, p=p_full(25C), T=298.15 -> sd_frac_day of capacity per day
P["k_sd25"] = P["sd_frac_day_25"] / 86400.0 / VES["p_full_bar_abs_25C"]      # 1/(s*bar), in units of s per s


def p_bar(n, T):
    return n * R * T / V_GAS / 1e5


def n_from_p(p, T):
    return p * 1e5 * V_GAS / (R * T)


def ocv(s, p, T):
    s = min(max(s, 1e-4), 1 - 1e-4)
    return (P["E0_25"] + P["dE0dT"] * (T - 298.15)
            + P["nernst_frac"] * R * T / F * math.log(s / (1 - s))
            + R * T / (2 * F) * math.log(max(p, 1e-4)))


def f_oer(s, T):
    """fraction of charging current that goes to O2 (poor charge acceptance near full / hot)."""
    c = P["oer_s50"] - P["oer_dT"] * (T - 298.15)
    return 1 / (1 + math.exp(-(s - c) / P["oer_w"]))


def eta_ni(I, s, T):
    j = I / A_H2
    j0 = P["j0_ni"] * 2 * math.sqrt(max(s * (1 - s), 1e-4)) * math.exp(-P["Ea_ni"] / R * (1 / T - 1 / 298.15))
    return R * T / (0.5 * F) * math.asinh(j / (2 * j0)), j0


def eta_h2(I, p, T, j0_geo):
    """H2 electrode overpotential magnitude (V) and its potential vs RHE (V).
    Discharge (I<0): HOR, limited by H2 transport ~ p.  Charge (I>0): HER, no transport limit."""
    j = abs(I) / A_H2
    b = R * T / (0.5 * F)
    if I < 0:
        jl = P["kmt_A_cm2_bar"] * max(p, 0.0)
        if j >= 0.999 * jl:
            return 1.5, 1.5                      # starved: potential runs away (Ru oxidation region)
        eta = b * math.asinh(j / (2 * j0_geo)) - R * T / (2 * F) * math.log(1 - j / jl)
        return eta, eta                           # anodic: + vs RHE
    eta = b * math.asinh(j / (2 * j0_geo))
    return eta, -eta


def step(state, I, dt, T_amb, j0_h2_override=None):
    s, n, T, A_ru = state["s"], state["n"], state["T"], state["A_ru"]
    p = p_bar(n, T)
    j0h = (j0_h2_override or P["j0_h2_geo"]) * A_ru
    # --- currents
    I_rev = 0.0
    if I > 0:
        fo = f_oer(s, T)
        I_ni = I * (1 - fo)
        I_o2 = I * fo
    else:
        fo, I_ni, I_o2 = 0.0, I, 0.0
        I_lim = P["k_ni_lim"] * s * A_H2 * 0.999          # NiOOH can only supply this much current
        if -I > I_lim:                                   # reversal: the rest is H2 evolution on the Ni electrode
            I_ni, I_rev = -I_lim, I + I_lim
    # --- voltage
    e_ni, j0n = eta_ni(I_ni if I < 0 else I, s, T)
    e_h, E_h2_rhe = eta_h2(I, p, T, max(j0h, 1e-9))
    E = ocv(s, p, T)
    if I < 0 and I_rev == 0.0:
        jl = P["k_ni_lim"] * max(s, 1e-9)
        e_ni += R * T / F * math.log(max(1 - (-I / A_H2) / jl, 1e-12))   # negative: supply limit near s -> 0
    V = E + e_ni + (e_h if I > 0 else -e_h) + I * P["R_ohm"]
    if I_rev < 0:
        V = -0.2 + I * P["R_ohm"]                 # reversed cell
        E_h2_rhe = max(E_h2_rhe, 0.3)
    # --- chemistry
    kT = P["k_sd25"] * math.exp(-P["Ea_sd"] / R * (1 / T - 1 / 298.15))
    r_sd = kT * p * s                             # fraction of capacity per second
    ds = I_ni / P["Q_C"] - r_sd
    dn = (I / (2 * F)                               # HER (charge) or HOR (discharge) moles H2/s
          - 2 * I_o2 / (4 * F)                    # O2 recombination consumes 2 H2 per O2
          - I_rev / (2 * F)                       # reversal: H2 evolved on the Ni electrode (I_rev < 0 -> +)
          - r_sd * P["Q_C"] / (2 * F))            # self-discharge consumes 1/2 H2 per NiOOH
    # --- heat (W)
    q_irr = I * (V - E)
    q_sd = -r_sd * P["Q_C"] / F * P["dH_cell"]    # exothermic
    q_rec = -I_o2 / (4 * F) * P["dH_recomb"]
    q = q_irr + q_sd + q_rec
    dT = (q - VES["hA_W_K"] * (T - T_amb)) / (VES["mass_kg"] * VES["cp_J_kgK"])
    dA = -P["k_ox"] * A_ru if E_h2_rhe > P["E_ox"] else 0.0
    new = dict(s=min(max(s + ds * dt, 0.0), 1.0), n=max(n + dn * dt, 0.0), T=T + dT * dt, A_ru=max(A_ru + dA * dt, 0.0))
    out = dict(V=V, E=E, p=p, I=I, s=s, T=T, A_ru=A_ru, eta_ni=e_ni, eta_h2=e_h, E_h2_rhe=E_h2_rhe,
               f_oer=fo, r_sd=r_sd, q=q, q_rec=q_rec, I_rev=I_rev)
    return new, out


def init(s0=0.02, T_C=25.0, precharge_bar=None):
    T = T_C + 273.15
    pc = VES["p_precharge_bar_abs"] if precharge_bar is None else precharge_bar
    n = n_from_p(pc, 298.15) + s0 * P["Q_C"] / (2 * F)
    return dict(s=s0, n=n, T=T, A_ru=1.0, q_in=0.0, q_out=0.0, qcount=s0)


def run(program, state, T_amb_C=25.0, dt=5.0, protect=True, j0_h2_override=None, log_every=1):
    """program: list of (mode, value, stop) — mode 'cc' current A, 'rest'; stop dict keys:
    V_max, V_min, t, s_in (charge input as fraction of Q), p_rise_stop."""
    T_amb = T_amb_C + 273.15
    rows, t = [], state.get("t", 0.0)
    for mode, val, stop in program:
        t0, qin0 = t, 0.0
        while True:
            I = val if mode == "cc" else 0.0
            h = dt / 20 if (I < 0 and state["s"] < 0.05) else dt   # resolve the end-of-discharge knee
            new, o = step(state, I, h, T_amb, j0_h2_override)
            o["t"] = t
            # coulomb counter (what a naive BMS would think)
            state["qcount"] = state["qcount"] + I * h / P["Q_C"]
            o["soc_count"] = state["qcount"]
            o["soc_p"] = (o["p"] * 298.15 / state["T"] - VES["p_precharge_bar_abs"]) / VES["dp_full_bar_25C"]
            if len(rows) % log_every == 0:
                rows.append(o)
            o["h"] = h
            t += h
            qin0 += I * h / P["Q_C"]
            state.update(new)
            state["t"] = t
            if protect:
                if o["p"] >= VES["p_trip_bar_abs"] or state["T"] - 273.15 >= LIM["T_trip_C"] or (I < 0 and o["V"] <= C["V_hw_cutoff"]):
                    rows[-1]["trip"] = True
                    break
            if "V_max" in stop and I > 0 and o["V"] >= stop["V_max"]:
                break
            if "V_min" in stop and I < 0 and o["V"] <= stop["V_min"]:
                break
            if "p_min" in stop and I < 0 and o["p"] <= stop["p_min"]:
                o["stop_p"] = True
                break
            if "s_in" in stop and abs(qin0) >= stop["s_in"]:
                break
            if "t" in stop and t - t0 >= stop["t"]:
                break
    return rows, state


def cols(rows):
    keys = rows[0].keys()
    return {k: np.array([r.get(k, np.nan) if not isinstance(r.get(k), bool) else float(r[k]) for r in rows]) for k in keys}
