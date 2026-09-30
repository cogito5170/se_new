"""RuH2-P1 시나리오를 돌려 **짧은 글**로 돌려준다. 봇 도구 `ruh2_battery` 가 부른다.

    python3 -m ruh2.analysis 사이클          # 표준 C/2 사이클
    python3 -m ruh2.analysis 전부            # 모든 항목

항목: 사양 · 사이클 · 율 · 자가방전 · 촉매 · 고장 · 과충전 · ru_pt · 산화대책 · 자가방전대책 · 지식

규율(CLAUDE.md '재고 나서 보고하기 전에'): 여기서 나오는 수는 **가정 파라미터 모델**의
출력이다. 글마다 그 사실과, 그 수가 사소하게 나오는 이유(예: 압력-SOC 일치는 정의상)를
같이 적는다. 가격·교환전류는 검색 요약 수준의 인용이다([조각]).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

from ruh2 import model as N
from ruh2 import spec

Q = spec.CELL["Q_Ah"]
A_H2 = spec.CELL["h2_area_cm2"]
OZ = 31.1035
# 2026-09 검색 요약 [조각]: Ru 1,675-1,750, Pt 1,751-1,811 USD/oz. 1년 전 Ru ~560.
PRICE = {"Ru": 1712.5, "Pt": 1781.0}
RHO = {"Ru": 12.37, "Pt": 21.45}                 # g/cm3
J0SPEC = {"Ru": 3.09e-3, "Pt": 1.08e-3}         # A/cm2_metal, 알칼리 HOR [조각, Nat. Commun. 2024]
머리 = "[모델 출력 · 가정 파라미터 · 실측 아님]"


def _cols(rows):
    return N.cols(rows)


def _energy(c):
    ch, dis, h = c["I"] > 0, c["I"] < 0, c["h"]
    return dict(Qin=float((c["I"] * h)[ch].sum() / 3600), Qout=float(-(c["I"] * h)[dis].sum() / 3600),
                Ein=float((c["V"] * c["I"] * h)[ch].sum() / 3600), Eout=float(-(c["V"] * c["I"] * h)[dis].sum() / 3600))


def 사이클(c_rate=0.5, temp_c=25.0, precharge=True, protect=True, j0=None):
    st = N.init(T_C=temp_c, precharge_bar=None if precharge else 0.0)
    r, _ = N.run([("cc", c_rate * Q, {"s_in": 1.10}), ("rest", 0, {"t": 3600}),
                  ("cc", -c_rate * Q, {"V_min": 1.0}), ("rest", 0, {"t": 1800})],
                 st, T_amb_C=temp_c, protect=protect, j0_h2_override=j0)
    c = _cols(r); e = _energy(c)
    return dict(**e, CE=e["Qout"] / e["Qin"], EE=e["Eout"] / e["Ein"], p_max=float(c["p"].max()),
                T_max=float(c["T"].max() - 273.15), V_min=float(c["V"].min()),
                trip=any(x.get("trip") for x in r), A_end=float(c["A_ru"][-1]),
                eta_h2_mV=float(np.median(c["eta_h2"][c["I"] < 0]) * 1e3))


def _j0geo(metal, load):
    ecsa = N.P["ecsa_m2_g"] * (1.0 if metal == "Ru" else RHO["Ru"] / RHO["Pt"])   # 같은 입경 가정
    return J0SPEC[metal] * load * 1e-3 * ecsa * 1e4 * N.P["utilisation"]


def ru_pt():
    rows = []
    for L in (0.05, 0.1, 0.5):
        for m in ("Ru", "Pt"):
            r = 사이클(j0=_j0geo(m, L))
            eta2c = N.R * 298.15 / (0.5 * N.F) * math.asinh(2 * Q / A_H2 / (2 * _j0geo(m, L))) * 1e3
            rows.append((m, L, L * A_H2 / 1000 / OZ * PRICE[m], r["EE"], eta2c))
    L_pt = 0.5 * _j0geo("Ru", 1) / _j0geo("Pt", 1)
    c_ru = 0.5 * A_H2 / 1000 / OZ * PRICE["Ru"]; c_pt = L_pt * A_H2 / 1000 / OZ * PRICE["Pt"]
    return rows, L_pt, c_ru, c_pt


def 고장(precharge, protect, p_min=None, e_ox=None):
    old = N.P["E_ox"]
    if e_ox:
        N.P["E_ox"] = e_ox
    try:
        s = N.init(precharge_bar=None if precharge else 0.0)
        _, s = N.run([("cc", 0.5 * Q, {"s_in": 1.05}), ("rest", 0, {"t": 600})], s)
        stop = {"t": 1.4 * 3600}
        if p_min:
            stop["p_min"] = p_min
        r, _ = N.run([("cc", -1.0 * Q, stop)], s, protect=protect)
    finally:
        N.P["E_ox"] = old
    c = _cols(r)
    how = "HW 0.9 V 래치" if any(x.get("trip") for x in r) else ("압력 하한 정지" if any(x.get("stop_p") for x in r) else "시간 끝까지")
    return float(c["A_ru"][-1]), float(np.max(c["E_h2_rhe"])), how


def 자가방전(temp_c=25.0, vgas=1.0, s_store=1.0, k=1.0, hours=72):
    oldV, oldk = N.V_GAS, N.P["k_sd25"]
    N.V_GAS, N.P["k_sd25"] = oldV * vgas, oldk * k
    try:
        s = N.init(T_C=temp_c)
        _, s = N.run([("cc", 0.5 * Q, {"s_in": s_store})], s, T_amb_C=temp_c)
        s0 = s["s"]
        r, _ = N.run([("rest", 0, {"t": hours * 3600})], s, T_amb_C=temp_c, dt=60.0)
    finally:
        N.V_GAS, N.P["k_sd25"] = oldV, oldk
    c = _cols(r)
    return float((s0 - c["s"][-1]) * 100), float(c["soc_count"][-1] - c["s"][-1])


# ---------------------------------------------------------------- 글
def 글_사양():
    C, V, L, B = spec.CELL, spec.VESSEL, spec.LIMITS, spec.BMS
    return "\n".join([
        "RuH2-P1 사양 (설계 제안 · 미검증)",
        f"- 셀: {C['chemistry']} · {C['Q_Ah']} Ah · 공칭 {C['V_nom']} V (충전 {C['V_charge_max']} / 종지 {C['V_dis_min']} / HW {C['V_hw_cutoff']} V)",
        f"- 스택: back-to-back {C['n_units']} unit, Ø{C['disc_od_mm']}/{C['disc_id_mm']} mm, {V['stack_h_mm']:.1f} mm · Ru/C 전극 {C['n_gde']}장 {C['h2_area_cm2']:.1f} cm² · Ru {C['ru_loading_mg_cm2']} mg/cm² = {C['ru_total_mg']:.1f} mg",
        f"- 용기: 316L OD {V['od_mm']}×{V['wall_mm']} mm, 내부 {V['inner_len_mm']} mm, 자유기체 {V['free_gas_mL']:.1f} mL · 예충전 {V['p_precharge_bar_abs']} → 완충 {V['p_full_bar_abs_25C']:.2f} bar abs(25 °C)",
        f"- 압력 계층: 운전 ≤{L['p_max_oper_bar_abs']} · HW 차단 {V['p_trip_bar_abs']} · 릴리프 {V['p_relief_bar']} · 파열판 {V['p_burst_disk_bar']} · 설계 {V['p_design_bar']} · 내압시험 {V['p_proof_bar']} bar · 후프응력 {V['hoop_stress_MPa_at_design']:.1f} MPa (허용 {V['allow_316L_MPa']})",
        f"- BMS: {B['mcu']} · {B['shunt_mohm']} mΩ+{B['ina_part']} ({B['i_lsb_mA']:.2f} mA/LSB) · 압력 0-10 bar · NTC ×2 · H₂ 센서 · 인터록(과압 6 bar, 0.9 V, 55 °C, H₂ 1 vol%) → 래치, 수동 리셋",
    ])


def 글_사이클(c_rate=0.5, temp_c=25.0, precharge=True, protect=True):
    r = 사이클(c_rate, temp_c, precharge, protect)
    return (f"{머리}\n표준 사이클 {c_rate} C · {temp_c} °C (110 % 충전 → 1 h 휴지 → 1.0 V 방전)\n"
            f"- 입력/출력 {r['Qin']:.3f}/{r['Qout']:.3f} Ah · 쿨롱효율 {r['CE']*100:.1f} % · 왕복 에너지효율 {r['EE']*100:.1f} %\n"
            f"- 최대 압력 {r['p_max']:.2f} bar abs · 최대 온도 {r['T_max']:.1f} °C · 최저 전압 {r['V_min']:.3f} V · 인터록 {'트립' if r['trip'] else '정상'}\n"
            f"- Ru 전극 과전압(방전 중앙값) {r['eta_h2_mV']:.2f} mV -- 손실은 Ni 전극·옴이 지배. Ru 활성 끝 {r['A_end']*100:.0f} %")


def 글_ru_pt():
    rows, L_pt, c_ru, c_pt = ru_pt()
    줄 = [머리, "Ru vs Pt (수소 전극 촉매) -- 질량당 가격은 2026-09 현재 거의 같다 [조각]",
          f"- 전류/질량 비 = j0비 {J0SPEC['Ru']/J0SPEC['Pt']:.2f} × 면적/질량비 {RHO['Pt']/RHO['Ru']:.2f}(같은 입경) = {J0SPEC['Ru']/J0SPEC['Pt']*RHO['Pt']/RHO['Ru']:.1f}배",
          f"- 같은 성능: Ru 0.5 mg/cm² ${c_ru:.2f} vs Pt {L_pt:.2f} mg/cm² ${c_pt:.2f} → Ru {100*(1-c_ru/c_pt):.0f} % 저렴"]
    for m, L, cost, ee, e2 in rows:
        줄.append(f"  {m} {L} mg/cm²: ${cost:.2f} · 효율 {ee*100:.1f} % · 2C 과전압 {e2:.1f} mV")
    줄.append("- 깨지는 조건: j0비 2.86 불재현(→이득 ~42 %), Ru/C 400분 활성 −56.5 % 보고, Ru 가격 추가 상승, 1 Ah 셀에선 촉매비가 용기보다 작음")
    return "\n".join(줄)


def 글_산화대책():
    표 = [("대책 없음(예충전 0, 보호 없음)", dict(precharge=False, protect=False)),
         ("① H₂ 예충전 1 bar", dict(precharge=True, protect=False)),
         ("② HW 0.9 V 래치", dict(precharge=False, protect=True)),
         ("③ 압력 하한 정지 p<0.3 bar", dict(precharge=False, protect=False, p_min=0.3)),
         ("④ 내산화 Ru(개시 0.8 V)만", dict(precharge=False, protect=False, e_ox=0.8)),
         ("①+② 본 설계", dict(precharge=True, protect=True))]
    줄 = [머리, "Ru 산화 대책 -- 과방전 1C 1.4 h 뒤 Ru 활성 잔존"]
    for n, kw in 표:
        a, e, how = 고장(**kw)
        줄.append(f"- {n}: Ru {a*100:.0f} % · H₂ 전극 최대 {e:.2f} V vs RHE · {how}")
    줄.append("해석: 시스템 대책(①②③) 하나면 막는다. 소재 대책(④)만으로는 H₂ 완전 결핍을 못 막는다(전위가 계속 오른다).")
    줄.append("추가: 압력 기반 충전 종지(O₂ 노출↓), 약 1.0 V·방전 보관, 조립 전 5 % H₂/Ar 환원, Pt 단원자 도핑·Ru₇Ni₃·W 도핑 [조각]")
    return "\n".join(줄)


def 글_자가방전대책():
    표 = [("기준 25 °C 완충", {}), ("① 10 °C 보관", dict(temp_c=10.0)), ("② 자유기체 ×2(압력↓)", dict(vgas=2.0)),
         ("③ 50 % SOC 보관", dict(s_store=0.5)), ("④ 친수성 분리막 H₂확산 ½(가정)", dict(k=0.5)),
         ("①+②+④", dict(temp_c=10.0, vgas=2.0, k=0.5)), ("참고 40 °C", dict(temp_c=40.0))]
    줄 = [머리, "자가방전 대책 -- 72 h 개방 손실 (정격 대비 %)"]
    for n, kw in 표:
        loss, cnt = 자가방전(**kw)
        줄.append(f"- {n}: {loss:.1f} %")
    줄.append("원리: NiOOH + ½H₂ → Ni(OH)₂, 속도 ∝ p·s·exp(−Ea/RT). 촉매(Ru/Pt)와 무관. Ea 60 kJ/mol·8 %/day 는 가정 → T8 시험으로 먼저 잴 것")
    줄.append("사소한 설명: 모델 안에서 압력 SOC 가 진값과 정확히 맞는 것은 화학량론상 정의다. 실제 셀은 누설·수증기·온도 구배가 낀다")
    return "\n".join(줄)


def 글_율():
    줄 = [머리, "율 특성 (C/5 충전 110 % 후 방전, 25 °C)"]
    for cr in (0.2, 0.5, 1.0, 2.0):
        s = N.init()
        _, s = N.run([("cc", 0.2 * Q, {"s_in": 1.10}), ("rest", 0, {"t": 3600})], s)
        r, _ = N.run([("cc", -cr * Q, {"V_min": 1.0})], s)
        c = _cols(r)
        qo = float(-(c["I"] * c["h"]).sum() / 3600); va = float((c["V"] * c["I"] * c["h"]).sum() / (c["I"] * c["h"]).sum())
        줄.append(f"- {cr} C: {qo:.3f} Ah · 평균 {va:.3f} V")
    return "\n".join(줄)


def 글_과충전():
    s = N.init()
    r, _ = N.run([("cc", 1.0 * Q, {"t": 2 * 3600})], s)
    c = _cols(r)
    return (f"{머리}\n과충전 1C 2 h (종지 없음): 최대 압력 {c['p'].max():.2f} bar · 최대 온도 {c['T'].max()-273.15:.1f} °C\n"
            "O₂ 가 Ru 표면에서 H₂ 와 재결합해 압력은 포화되고 과충전 에너지는 열이 된다")


def 글_실험설계():
    표 = [("T1", "촉매 QC", "ICP-OES·XRD·TEM·Cu-UPD", "Ru 20±2 wt%, 2–5 nm", "ECSA 60 m²/g [A]"),
         ("T2", "반전지 RDE 1 M KOH(H₂ 포화)", "HOR/HER 분극·미소분극·Koutecky–Levich", "j0 ≥ 1 mA/cm²_Ru", "j0 3.09 [L]"),
         ("T2b", "Ru 산화 창", "CV 상한 0.2→0.8 V, HOR 잔존율", "개시 전위", "0.4 V [L], k_ox [A]"),
         ("T3", "GDE 반전지", "가스확산 반전지 7.8 mA/cm²", "η < 20 mV", "이용률 0.2 [A], k_m [A]"),
         ("T4", "용기", "수압 30 bar 10분 → 5 % H₂/N₂ 6 bar 누설", "< 0.01 bar/24 h", "V_gas"),
         ("T5", "BMS 벤치", "정밀 저항·더미 부하, EIS 는 RC 더미를 LCR 미터와 교차", "I<0.5 %FS, V<1 mV, p<10 mbar, 4채널 래치, Z<2 %", "계측 사슬"),
         ("T6", "화성·용량", "C/10 160 % ×3 → C/5 방전", "≥ 0.9 Ah", "Q, Ni 이용률"),
         ("T7", "압력–SOC 교정", "C/5 단계 충전, 휴지 후 p·T", "3.48 bar/Ah ±10 %", "V_gas, 누설"),
         ("T8", "자가방전", "25/40 °C 72 h 개방, 압력 추적", "k_sd, Ea 추정", "8 %/day, 60 kJ/mol [A]"),
         ("T9", "율·온도", "0.2–2 C × 10/25/40 °C", "모델 대비 오차표", "j0_Ni, ASR [A]"),
         ("T10", "EIS", "SOC 10–90 %, 10 mHz–5 kHz", "R_Ω, R_ct,Ni, σ", "C_Ni, σ [A]"),
         ("T11", "수명", "C/2 ×500, 25 °C", "용량 유지율·압력 드리프트", "-"),
         ("T12", "사후 분석", "XPS(RuOx)·TEM·전해질 ICP", "열화 메커니즘 분리", "-"),
         ("T13", "고장 주입", "보호 켠 채 과방전·과온·압력 모의", "모든 경로 래치", "-")]
    줄 = ["실험·검증 청사진 (앞 단계를 통과해야 다음으로. 각 단계는 모델의 [A] 파라미터를 실측으로 바꾼다)"]
    줄 += [f"- {a}: {b} — {c} — 합격 {d} — 교체 {e}" for a, b, c, d, e in 표]
    줄.append("단계적 제작 권장: ①비커 반전지(대기압, 상용 Ru/C) → ②개방형 풀셀(NiMH용 Ni(OH)₂ + Ru/C GDE) → ③압력 셀(RuH2-P1, 기관 안전 승인·내압 시험)")
    줄.append("규율: 측정마다 독립 대조 하나(압력 SOC ↔ 쿨롱 SOC ↔ 방전 용량 등), 보고 전에 사소한 설명(누설·온도 드리프트·영점)을 먼저 배제")
    return "\n".join(줄)


def 글_지식():
    p = Path(__file__).with_name("knowledge.md")
    t = p.read_text(encoding="utf-8")
    return t[:3500] + ("\n…(전문: ruh2/knowledge.md)" if len(t) > 3500 else "")


항목 = {"사양": 글_사양, "사이클": 글_사이클, "율": 글_율, "과충전": 글_과충전, "ru_pt": 글_ru_pt,
       "산화대책": 글_산화대책, "자가방전대책": 글_자가방전대책, "실험설계": 글_실험설계, "지식": 글_지식}
별칭 = {"spec": "사양", "cycle": "사이클", "rate": "율", "overcharge": "과충전", "rupt": "ru_pt", "ru vs pt": "ru_pt",
       "비용": "ru_pt", "반응도": "ru_pt", "oxidation": "산화대책", "산화": "산화대책", "selfdischarge": "자가방전대책",
       "자가방전": "자가방전대책", "knowledge": "지식", "요약": "지식", "고장": "산화대책", "실험": "실험설계", "검증": "실험설계", "test": "실험설계"}


def 부르기(무엇: str = "사이클", **kw) -> str:
    k = (무엇 or "사이클").strip()
    k = 별칭.get(k.lower(), k)
    if k == "전부":
        return "\n\n".join(f() for n, f in 항목.items() if n != "지식")
    if k not in 항목:
        return f"모르는 항목 {무엇!r}. 가능: {' · '.join(항목)} · 전부"
    f = 항목[k]
    return f(**kw) if k == "사이클" else f()


if __name__ == "__main__":
    print(부르기(sys.argv[1] if len(sys.argv) > 1 else "사이클"))
