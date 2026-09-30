/* nih2.js — JS port of nih2.py (same equations; checked against Python in the build). */
function makeNiH2(SPEC, P) {
  const F = 96485.332, R = 8.314462;
  const C = SPEC.CELL, VES = SPEC.VESSEL, LIM = SPEC.LIMITS;
  const A_H2 = C.h2_area_cm2, V_GAS = VES.free_gas_mL * 1e-6;
  const pbar = (n, T) => n * R * T / V_GAS / 1e5;
  const nfp = (p, T) => p * 1e5 * V_GAS / (R * T);
  function ocv(s, p, T) {
    s = Math.min(Math.max(s, 1e-4), 1 - 1e-4);
    return P.E0_25 + P.dE0dT * (T - 298.15) + P.nernst_frac * R * T / F * Math.log(s / (1 - s)) + R * T / (2 * F) * Math.log(Math.max(p, 1e-4));
  }
  const foer = (s, T) => 1 / (1 + Math.exp(-(s - (P.oer_s50 - P.oer_dT * (T - 298.15))) / P.oer_w));
  function etaNi(I, s, T) {
    const j = I / A_H2, j0 = P.j0_ni * 2 * Math.sqrt(Math.max(s * (1 - s), 1e-4)) * Math.exp(-P.Ea_ni / R * (1 / T - 1 / 298.15));
    return R * T / (0.5 * F) * Math.asinh(j / (2 * j0));
  }
  function etaH2(I, p, T, j0) {
    const j = Math.abs(I) / A_H2, b = R * T / (0.5 * F);
    if (I < 0) {
      const jl = P.kmt_A_cm2_bar * Math.max(p, 0);
      if (j >= 0.999 * jl) return [1.5, 1.5];
      const e = b * Math.asinh(j / (2 * j0)) - R * T / (2 * F) * Math.log(1 - j / jl);
      return [e, e];
    }
    const e = b * Math.asinh(j / (2 * j0)); return [e, -e];
  }
  function step(st, I, dt, Tamb, j0over) {
    const { s, n, T, A_ru } = st, p = pbar(n, T), j0h = (j0over || P.j0_h2_geo) * A_ru;
    let fo = 0, Ini = I, Io2 = 0, Irev = 0;
    if (I > 0) { fo = foer(s, T); Ini = I * (1 - fo); Io2 = I * fo; }
    else { const Ilim = P.k_ni_lim * s * A_H2 * 0.999; if (-I > Ilim) { Ini = -Ilim; Irev = I + Ilim; } }
    let eNi = etaNi(I < 0 ? Ini : I, s, T); let [eH, Eh] = etaH2(I, p, T, Math.max(j0h, 1e-9));
    const E = ocv(s, p, T);
    if (I < 0 && Irev === 0) { const jl = P.k_ni_lim * Math.max(s, 1e-9); eNi += R * T / F * Math.log(Math.max(1 - (-I / A_H2) / jl, 1e-12)); }
    let V = E + eNi + (I > 0 ? eH : -eH) + I * P.R_ohm;
    if (Irev < 0) { V = -0.2 + I * P.R_ohm; Eh = Math.max(Eh, 0.3); }
    const kT = P.k_sd25 * Math.exp(-P.Ea_sd / R * (1 / T - 1 / 298.15)), rsd = kT * p * s;
    const ds = Ini / P.Q_C - rsd, dn = I / (2 * F) - 2 * Io2 / (4 * F) - Irev / (2 * F) - rsd * P.Q_C / (2 * F);
    const q = I * (V - E) - rsd * P.Q_C / F * P.dH_cell - Io2 / (4 * F) * P.dH_recomb;
    const dT = (q - VES.hA_W_K * (T - Tamb)) / (VES.mass_kg * VES.cp_J_kgK);
    const dA = Eh > P.E_ox ? -P.k_ox * A_ru : 0;
    return [{ s: Math.min(Math.max(s + ds * dt, 0), 1), n: Math.max(n + dn * dt, 0), T: T + dT * dt, A_ru: Math.max(A_ru + dA * dt, 0) },
            { V, E, p, I, s, T, A_ru, eta_ni: eNi, eta_h2: eH, E_h2_rhe: Eh, f_oer: fo, q, I_rev: Irev }];
  }
  function init(s0 = 0.02, TC = 25, pre = null) {
    const pc = pre === null ? VES.p_precharge_bar_abs : pre;
    return { s: s0, n: nfp(pc, 298.15) + s0 * P.Q_C / (2 * F), T: TC + 273.15, A_ru: 1, qcount: s0, t: 0 };
  }
  function run(program, st, TambC = 25, dt = 5, protect = true, j0over = null) {
    const Tamb = TambC + 273.15, rows = []; let t = st.t || 0;
    for (const [mode, val, stop] of program) {
      const t0 = t; let qin = 0;
      for (let guard = 0; guard < 2e6; guard++) {
        const I = mode === "cc" ? val : 0, h = (I < 0 && st.s < 0.05) ? dt / 20 : dt;
        const [nw, o] = step(st, I, h, Tamb, j0over);
        o.t = t; o.h = h; st.qcount += I * h / P.Q_C; o.soc_count = st.qcount;
        o.soc_p = (o.p * 298.15 / st.T - VES.p_precharge_bar_abs) / VES.dp_full_bar_25C;
        rows.push(o); t += h; qin += I * h / P.Q_C; Object.assign(st, nw); st.t = t;
        if (protect && (o.p >= VES.p_trip_bar_abs || st.T - 273.15 >= LIM.T_trip_C || (I < 0 && o.V <= C.V_hw_cutoff))) { o.trip = true; return { rows, st, trip: true }; }
        if (stop.V_max && I > 0 && o.V >= stop.V_max) break;
        if (stop.V_min && I < 0 && o.V <= stop.V_min) break;
        if (stop.p_min && I < 0 && o.p <= stop.p_min) break;
        if (stop.s_in && Math.abs(qin) >= stop.s_in) break;
        if (stop.t && t - t0 >= stop.t) break;
      }
    }
    return { rows, st, trip: false };
  }
  return { init, run, step, ocv, pbar, nfp };
}
if (typeof module !== "undefined") module.exports = { makeNiH2 };
