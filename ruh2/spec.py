"""RuH2-P1 prototype: single source of truth for every drawing, model and report table.
Design values are PROPOSALS for a first lab prototype, not validated hardware."""
import math

F, R = 96485.332, 8.314462

CELL = dict(
    name="RuH2-P1",
    chemistry="NiOOH/Ni(OH)2 (+) | 30 wt% KOH | Ru/C H2 electrode (-)",
    Q_Ah=1.0,                       # nominal capacity, C/5, 25 C
    V_nom=1.25, V_charge_max=1.55, V_dis_min=1.00, V_hw_cutoff=0.90,
    n_units=4,                      # back-to-back unit pairs
    disc_od_mm=46.0, disc_id_mm=8.0,
    ni_thk_mm=0.80, gde_thk_mm=0.30, sep_thk_mm=0.25, screen_thk_mm=0.50,
    ru_loading_mg_cm2=0.5, ru_wt_pct_on_C=20, ptfe_wt_pct=30,
    koh_wt_pct=30, koh_mL=4.0,
    ni_areal_mAh_cm2=None,          # filled below
)
a_face = math.pi * ((CELL["disc_od_mm"] / 20) ** 2 - (CELL["disc_id_mm"] / 20) ** 2)   # cm^2
CELL["face_area_cm2"] = a_face
CELL["h2_area_cm2"] = a_face * CELL["n_units"] * 2      # back-to-back: each Ni electrode faces two Ru GDEs
CELL["n_gde"] = CELL["n_units"] * 2
CELL["ni_areal_mAh_cm2"] = CELL["Q_Ah"] * 1000 / CELL["n_units"] / a_face
CELL["ru_total_mg"] = CELL["ru_loading_mg_cm2"] * CELL["h2_area_cm2"]

VESSEL = dict(
    material="316L stainless (tube 2in Sch10S)",
    od_mm=60.3, wall_mm=2.77, inner_len_mm=70.0,
    flange="bolted flange, 6x M6 A4-70, EPDM O-ring (KOH compatible)",
    p_design_bar=20.0, p_proof_bar=30.0, p_relief_bar=8.0, p_burst_disk_bar=12.0,
    p_precharge_bar_abs=1.0, p_trip_bar_abs=6.0,
    ports="1/4in NPT tee: pressure transducer + relief valve + needle valve (fill/vent)",
    feedthrough="2x PTFE-sealed Ni rod feedthrough, 3 mm",
    stack_solid_mL=None, free_gas_mL=None, mass_kg=0.52, cp_J_kgK=520.0, hA_W_K=0.16,
)
id_mm = VESSEL["od_mm"] - 2 * VESSEL["wall_mm"]
VESSEL["id_mm"] = id_mm
v_int = math.pi * (id_mm / 20) ** 2 * VESSEL["inner_len_mm"] / 10          # mL
stack_h_mm = CELL["n_units"] * (CELL["ni_thk_mm"] + 2 * CELL["sep_thk_mm"] + CELL["gde_thk_mm"] * 2 + CELL["screen_thk_mm"])
VESSEL["stack_h_mm"] = stack_h_mm
VESSEL["stack_solid_mL"] = math.pi * (CELL["disc_od_mm"] / 20) ** 2 * stack_h_mm / 10 + 12.0   # + core rod, end plates, insulators
VESSEL["internal_mL"] = v_int
VESSEL["free_gas_mL"] = v_int - VESSEL["stack_solid_mL"] - CELL["koh_mL"]
VESSEL["hoop_stress_MPa_at_design"] = VESSEL["p_design_bar"] * 0.1 * id_mm / (2 * VESSEL["wall_mm"])
VESSEL["allow_316L_MPa"] = 115.0      # ASME II-D S for 316L at ~40 C (order of magnitude; check code table)

n_h2_full = CELL["Q_Ah"] * 3600 / (2 * F)
dp_full_bar = n_h2_full * R * 298.15 / (VESSEL["free_gas_mL"] * 1e-6) / 1e5
VESSEL["dp_full_bar_25C"] = dp_full_bar
VESSEL["p_full_bar_abs_25C"] = VESSEL["p_precharge_bar_abs"] + dp_full_bar

LIMITS = dict(
    T_charge_C=(10, 40), T_discharge_C=(0, 45), T_inhibit_C=45, T_trip_C=55,
    I_max_A=2.0, C_rate_nom=0.5,
    h2_alarm_vol_pct=0.4, h2_trip_vol_pct=1.0, h2_LFL_vol_pct=4.0,
    p_max_oper_bar_abs=5.0,
    ru_oxidation_onset_V_RHE=0.4,
)

BMS = dict(
    name="RuH2-BMS rev A", supply="12 V DC, 1.5 A",
    mcu="STM32G474RE (Cortex-M4F 170 MHz, 12-bit ADC, DAC, COMP)",
    shunt_mohm=10.0, ina_gain=50, ina_part="INA240A2", i_range_A=3.3,
    vcell_amp="OPA2333 difference amp (4-wire Kelvin)",
    p_sensor="0-10 bar abs, 0.5-4.5 V ratiometric (e.g. Honeywell PX3 family)",
    ntc="2x NTC 10k B3950 (vessel wall, ambient)",
    h2_sensor="H2 gas sensor (e.g. Figaro TGS2616-C00) + heater driver",
    power_stage="linear bidirectional: PMOS CC source + NMOS CC sink, op-amp servo from DAC",
    disconnect="back-to-back NMOS + hardware latch (TLV3202 comparators, 74LVC1G74)",
    eis="DAC sine 20 mA pk superposed on DC setpoint, 0.1 Hz-5 kHz, lock-in in firmware",
    usb="USB-CDC via ADuM3160 isolator",
    adc_bits=12, vref=3.3,
)
BMS["i_lsb_mA"] = BMS["vref"] / 4095 / (BMS["shunt_mohm"] * 1e-3 * BMS["ina_gain"]) * 1e3

if __name__ == "__main__":
    import json
    print(json.dumps(dict(CELL=CELL, VESSEL=VESSEL, LIMITS=LIMITS, BMS=BMS), indent=1, ensure_ascii=False))
