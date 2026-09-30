"""RuH2-P1 프로토타입 보고서 -> PDF.  python3 -m ruh2.report
구성은 reportkit/POLICY.md 를 따르고, reportkit.check 를 통과해야 PDF 를 만든다.
읽는 것: OUT/battery.json · OUT/rupt.json (ruh2.experiments · ruh2.rupt), OUT/fig (ruh2.figures),
OUT/drawings (ruh2/drawings/*.py), OUT/video 스틸(ruh2.render --stills), ruh2/data/dft.json.
**파이썬 3.10 에서도 돈다** -- f-string 안에 백슬래시(LaTeX)를 두지 않으려고 수식은 _E 목록으로 뺐다.
"""
import glob
import json
import os
import sys

from reportkit import kit
from ruh2 import paths, spec

paths.ensure()
B = json.load(open(paths.OUT / "battery.json"))
DFT = json.load(open(paths.DATA / "dft.json"))
C, V, LIM, BMS = spec.CELL, spec.VESSEL, spec.LIMITS, spec.BMS
P = B["params"]
cyc, chk = B["cycle"], B["checks"]
cat = B["catalyst"]; catk = list(cat.keys())
sd = B["selfdis"]
RP = json.load(open(paths.OUT / "rupt.json"))
EQ = RP["equal_perf"]; RA = RP["ratios"]; SW = RP["sweep"]
sw = lambda m_, L: next(r for r in SW[m_] if abs(r['load'] - L) < 1e-9)


def m(tex):
    return kit.eq(tex, False)


def M(tex):
    return kit.eq(tex, True)


_자리 = {"fig": paths.FIG, "drawings": paths.DRAW, "video": paths.VIDEO}


def img(path, w="100%", cap=None, num=None):
    if os.path.isabs(path):
        p = path
    else:
        head, _, rest = path.partition("/")
        p = str(_자리.get(head, paths.OUT) / rest)
        if head == "drawings" and os.path.exists(p[:-4] + ".jpg"):
            p = p[:-4] + ".jpg"                      # PDF 크기: 도면은 JPEG 로 싣는다
    if not os.path.exists(p):
        return f"<p class='miss'>[그림 없음: {os.path.basename(p)}]</p>"
    h = f"<figure><img src='file://{p}' style='width:{w}'>"
    if cap:
        h += f"<figcaption><b>그림 {num}.</b> {cap}</figcaption>" if num else f"<figcaption>{cap}</figcaption>"
    return h + "</figure>"


table = kit.table
f1 = lambda x: f"{x:.1f}"; f2 = lambda x: f"{x:.2f}"; f3 = lambda x: f"{x:.3f}"
pct = lambda x: f"{x*100:.1f} %"
HERE = str(paths.OUT)

_E = [
    M(r"\frac{\text{전류}}{\text{질량}}\bigg|_{Ru/Pt} = \underbrace{\frac{j_0^{Ru}}{j_0^{Pt}}}_{" + f"{RA['j0']:.2f}" + r"} \times \underbrace{\frac{\rho_{Pt}}{\rho_{Ru}}}_{" + f"{RA['area_per_mass']:.2f}" + r"\ (\text{같은 입경})} = " + f"{RA['current_per_mass']:.1f}"),
    M(r"\mathrm{Ni(OH)_2 + OH^- \;\underset{\text{방전}}{\overset{\text{충전}}{\rightleftharpoons}}\; NiOOH + H_2O + e^-}"),
    M(r"\mathrm{2H_2O + 2e^- \;\underset{\text{방전 (HOR)}}{\overset{\text{충전 (HER)}}{\rightleftharpoons}}\; H_2 + 2OH^-}"),
    M(r"\mathrm{NiOOH + \tfrac12 H_2 \;\rightleftharpoons\; Ni(OH)_2}\qquad E^\circ \approx 1.32\ \mathrm{V}"),
    m(r"\mathrm{4OH^- \to O_2 + 2H_2O + 4e^-}"),
    m(r"\mathrm{O_2 + 2H_2 \to 2H_2O}"),
    m(r"\mathrm{NiOOH + \tfrac12 H_2 \to Ni(OH)_2}"),
    m(r"\mathrm{Ru + OH^- \to Ru\!-\!OH^* + e^- \to RuO_x}"),
    m(r"\mathrm{Ni\ 전극:\ 2H_2O+2e^- \to H_2 + 2OH^-}"),
    M(r"\mathrm{H_2O + e^- + * \;\rightleftharpoons\; H^* + OH^-}"),
    M(r"\mathrm{H^* + H_2O + e^- \;\rightleftharpoons\; H_2 + OH^- + *}"),
    M(r"\mathrm{2H^* \;\rightleftharpoons\; H_2 + 2*}"),
    M(r"\Delta G_{H^*} = E(\text{slab}+H) - E(\text{slab}) - \tfrac12 E(\mathrm{H_2}) + 0.24\ \mathrm{eV}"),
    M(r"E_\mathrm{OCV}(s,p,T) = E^\circ_{25} + \frac{dE}{dT}(T-298.15) + \nu\,\frac{RT}{F}\ln\frac{s}{1-s} + \frac{RT}{2F}\ln\frac{p_{H_2}}{1\,\mathrm{bar}}"),
    m("s"),
    m(r"\nu=0.6"),
    M(r"n_{H_2}(t) = n_0 + \frac{1}{2F}\int_0^t \Big[I - 2 I_{O_2}^{\text{net}} - Q\,r_{sd}\Big]\,dt,\qquad p = \frac{n_{H_2} R T}{V_\mathrm{gas}}"),
    M(r"\frac{\partial p}{\partial s}\Big|_{25^\circ\mathrm{C}} = \frac{Q}{2F}\cdot\frac{RT}{V_\mathrm{gas}} = " + f"{V['dp_full_bar_25C']:.3f}" + r"\ \mathrm{bar\ per\ 1\,Ah}"),
    m(r"V_\mathrm{gas}=" + f"{V['free_gas_mL']:.1f}" + r"\ \mathrm{mL}"),
    M(r"j = 2 j_0 \sinh\!\Big(\frac{\alpha F \eta}{RT}\Big),\qquad \eta = \frac{RT}{\alpha F}\,\operatorname{arsinh}\frac{j}{2j_0}\quad(\alpha=0.5)"),
    M(r"j_{0,\mathrm{Ni}}(s,T) = j_{0,\mathrm{Ni}}^{50\%}\cdot 2\sqrt{s(1-s)}\cdot e^{-\frac{E_a}{R}\left(\frac1T-\frac1{298}\right)},\qquad j_{0,\mathrm{H_2}}^{geo} = j_0^{\mathrm{Ru}}\cdot L_\mathrm{Ru}\cdot A_\mathrm{ECSA}\cdot u"),
    m(r"3.09\ \mathrm{mA/cm^2_{Ru}} [4] \times 0.5\ \mathrm{mg/cm^2}\times 60\ \mathrm{m^2/g}\,[A] \times 0.2\,[A] = " + f"{P['j0_h2_geo']*1000:.0f}" + r"\ \mathrm{mA/cm^2}"),
    M(r"\eta_\mathrm{HOR} = \frac{RT}{\alpha F}\operatorname{arsinh}\frac{j}{2j_0} - \frac{RT}{2F}\ln\Big(1-\frac{j}{j_L}\Big),\qquad j_L = k_m\,p_{H_2}"),
    M(r"V = E_\mathrm{OCV} + \eta_\mathrm{Ni} \pm \eta_{H_2} + I R_\Omega,\qquad R_\Omega = \frac{ASR}{A_{H_2}} + R_c = " + f"{P['R_ohm']*1000:.1f}" + r"\ \mathrm{m\Omega}"),
    M(r"\eta_\mathrm{supply} = \frac{RT}{F}\ln\Big(1-\frac{j}{k_\mathrm{Ni}\,s}\Big)\ (\text{방전}),\qquad j > k_\mathrm{Ni}\,s\ \Rightarrow\ \text{역전: 나머지 전류는 Ni 전극의 H}_2\text{ 발생}"),
    M(r"f_{O_2}(s,T) = \Big[1+\exp\Big(-\frac{s - (0.93 - 0.004\,(T-298))}{0.022}\Big)\Big]^{-1},\qquad r_{sd} = k_{sd}(T)\,p_{H_2}\,s"),
    M(r"m c_p \frac{dT}{dt} = \underbrace{I\,(V-E_\mathrm{OCV})}_{\text{비가역}} + \underbrace{r_{sd} Q\,|\Delta H_\mathrm{cell}|/F}_{\text{자가방전}} + \underbrace{\tfrac{I_{O_2}}{4F}|\Delta H_\mathrm{rec}|}_{\text{O}_2\text{ 재결합}} - hA\,(T-T_\infty)"),
    M(r"\frac{dA_\mathrm{Ru}}{dt} = -k_{ox}\,A_\mathrm{Ru}\ \ \text{if}\ E_{H_2}>0.4\ \mathrm{V_{RHE}},\qquad Z(\omega)=R_\Omega + \Big[\tfrac{1}{R_{ct,Ni}+Z_W} + j\omega C_{Ni}\Big]^{-1} + \Big[\tfrac1{R_{ct,H}} + j\omega C_{H}\Big]^{-1},\ Z_W=\frac{\sigma(1-j)}{\sqrt\omega}"),
    m(r"\sigma = pD_i/2t")
]

# ---------------------------------------------------------------- content
S = []
S.append(f"""
<section class="cover">
 <div class="cv-top">프로토타입 보고서 · RUH2-RPT-001 · rev A · 2026-09-29</div>
 <h1>RuH2-P1</h1>
 <h2>Ru 수소 전극을 쓰는 니켈–수소(Ni–H<sub>2</sub>) 배터리<br>프로토타입 설계, 이론, 시뮬레이션, 실험·검증 청사진</h2>
 <div class="cv-box">
  <div><b>셀</b> 1.0 Ah · 공칭 1.25 V · NiOOH | 30 wt% KOH | Ru/C H<sub>2</sub> 전극 · 316L 압력용기 (운전 ≤ 5 bar abs)</div>
  <div><b>BMS</b> RuH2-BMS rev A · STM32G474RE · V/I/p/T/H<sub>2</sub> 계측 · 하드웨어 인터록 · EIS</div>
  <div><b>근거</b> 0-D 전기화학·열 모델(본 작업), GPAW DFT(본 작업), 선행연구 검색 요약</div>
 </div>
 <div class="cv-warn">이 문서의 모든 성능 수치는 <b>가정 파라미터 모델의 출력</b>입니다. 실측이 아닙니다. 설계는 제안이며 제작·시험으로 검증되지 않았습니다. 각 가정은 부록 A에 [A](가정) / [L](문헌) / [C](본 작업 계산)으로 표시했습니다.</div>
</section>""")

S.append(f"""
<section><h2 class="h">요약</h2>
<p>이 보고서는 “Ru 기반 수소 배터리”를 <b>니켈–수소 배터리의 수소 전극 촉매를 Pt 대신 Ru/C로 쓰는 구조</b>로 해석하고, 그 첫 실험실 프로토타입 RuH2-P1을 정의합니다. 수소 배터리라는 이름을 가진 다른 구조(가역 연료전지 URFC, 금속수소화물 전지)도 있지만, Ru가 전극 반응에 직접 참여하고 선행연구가 가장 많은 구조가 Ni–H<sub>2</sub>입니다 [1][3][4].</p>
{table([
 ["용량 (C/2, 25 °C)", f"{cyc['Qout']:.2f} Ah", "모델"],
 ["왕복 에너지 효율 (C/2)", pct(cyc['EE']), "모델 · 충전 110 %"],
 ["쿨롱 효율", pct(cyc['CE']), "과충전 10 % 포함"],
 ["최대 H<sub>2</sub> 압력", f"{cyc['p_max']:.2f} bar abs", f"차단 {V['p_trip_bar_abs']} · 설계 {V['p_design_bar']} bar"],
 ["최대 온도 (C/2)", f"{cyc['T_max']:.1f} °C", f"차단 {LIM['T_trip_C']} °C"],
 ["자가방전 72 h (25 / 40 °C)", f"{sd['25']['loss_72h']*100:.1f} / {sd['40']['loss_72h']*100:.1f} %p", "가정 속도상수 [A]"],
 ["Ru 전극 과전압 (방전 중앙값)", f"{cat[catk[0]]['eta_h2_mV_dis']:.2f} mV", "Ni 전극·옴 손실이 지배"],
 ["Ru 사용량", f"{C['ru_total_mg']:.1f} mg ({C['ru_loading_mg_cm2']} mg/cm² × {C['h2_area_cm2']:.1f} cm²)", "설계값"],
], ["항목", "값", "비고"])}
<h3>이 작업이 찾은 것</h3>
<ul>
<li><b>이 셀에서 Ru의 이점은 효율이 아니라 촉매량과 비용입니다(§A).</b> 같은 성능을 Pt의 약 1/5 질량으로 냅니다. 단, 2026년 현재 질량당 가격은 Pt와 비슷합니다. Ru/C의 HOR 교환전류가 커서 수소 전극 과전압은 1 mV 수준입니다. Pt/C로 바꿔도 왕복효율 차이는 {abs(cat[catk[0]]['EE']-cat[catk[1]]['EE'])*100:.1f}%p에 그칩니다. 반면 비귀금속 NiMoCo(η<sub>10</sub>≈80 mV [1])로 바꾸면 {(cat[catk[0]]['EE']-cat[catk[2]]['EE'])*100:.1f}%p 떨어집니다.</li>
<li><b>설계를 좌우하는 위험은 Ru 산화입니다.</b> Ru는 0.4 V vs RHE를 넘으면 HOR 활성을 잃습니다 [4]. H<sub>2</sub> 예충전 1 bar가 있으면 과방전이 일어나도 수소 전극이 이 전위에 닿지 않습니다. 예충전이 없으면 Ru 활성이 사실상 0이 됩니다(그림 13). 그래서 예충전, 0.9 V 하드웨어 차단, 래치형 인터록을 설계 요구로 넣었습니다.</li>
<li><b>압력이 곧 SOC 게이지입니다.</b> 쿨롱 카운팅은 자가방전을 보지 못합니다. 72 h 뒤 오차가 25 °C에서 {sd['25']['count_soc_err_end']*100:.0f}%p, 40 °C에서 {sd['40']['count_soc_err_end']*100:.0f}%p입니다. 압력은 수소 양을 직접 재므로 이 오차가 없습니다. 단, 모델 안에서 압력–SOC 일치는 화학량론으로 정의상 성립합니다. 실제 셀에서는 누설, 수증기, 온도 구배가 이 관계를 흐립니다(§9 T7에서 교정).</li>
</ul>
<h3>이 작업이 하지 않은 것</h3>
<p>셀과 보드를 만들지 않았고 재지 않았습니다. 모델 파라미터의 대부분은 [A](가정)입니다. §9의 실험 청사진은 그 가정을 하나씩 실측으로 바꾸기 위한 순서입니다.</p>
</section>""")

S.append(f"""
<section><h2 class="h">A. 단점, 그리고 그럼에도 Ru를 쓰는 이유</h2>
<h3>A.1 이 배터리의 단점 (명시)</h3>
{table([
 ["낮은 에너지 밀도", "이 프로토타입은 약 2 Wh/kg(압력용기 질량이 지배). 상용 Ni–H<sub>2</sub>도 55–75 Wh/kg [10]", "전기차·휴대기기에는 부적합. 대형 ESS·백업 전원용"],
 ["큰 자가방전", f"모델 가정 25 °C 72 h에 {sd['25']['loss_72h']*100:.1f} %, 40 °C에 {sd['40']['loss_72h']*100:.1f} %. NiOOH + ½H<sub>2</sub> 직접 반응이며 속도 ∝ p<sub>H2</sub> [9][10]", "장기 대기 저장에 불리 (§8.2 대책)"],
 ["압력용기와 H<sub>2</sub> 취급", "가연 범위 4–75 vol%, 내압 시험·릴리프·파열판·누설 감지 필요", "제작·인허가 비용과 안전 부담"],
 ["Ru 산화", "0.4 V vs RHE 이상에서 HOR 활성 소실 [4]. 과방전·H<sub>2</sub> 결핍 때 발생", "시스템 대책이 필수 (§8.1)"],
 ["Ru 가격 변동", "2025-03 약 $560/oz → 2026-09 약 $1,675–1,750/oz (약 +160 %). 현재 Pt($1,751–1,811/oz)와 질량당 비슷 [16]", "“Ru가 싸다”는 지금은 질량 기준으로 성립하지 않음"],
 ["Ru 공급 구조", "Pt 채굴의 부산물이라 시장이 작고 수요 충격에 민감 [16]", "대량 생산 때 조달 위험"],
 ["효율 이득은 작음", f"같은 담지량 0.5 mg/cm²에서 Ru와 Pt의 왕복효율 차이 {(sw('Ru',0.5)['EE']-sw('Pt',0.5)['EE'])*100:.2f}%p", "Ni 전극과 옴 손실이 지배하기 때문"],
 ["실측 없음", "모델 파라미터 대부분이 [A]. 인용은 검색 요약 수준", "§9 실험으로 교체해야 함"],
], ["단점", "근거 · 크기", "의미"])}
<h3>A.2 그럼에도 Pt 대신 Ru를 쓰는 이유: 반응도</h3>
<p>알칼리 HOR에서 Ru/C의 교환전류가 Pt/C보다 크다는 보고가 있습니다(3.09 대 1.08 mA/cm²<sub>metal</sub>, {RA['j0']:.2f}배) [4]. 일반적인 설명은 두 가지입니다. Ru는 친산소성이 강해 표면 OH를 공급하므로 알칼리에서 느린 Volmer 단계(H* + OH<sup>−</sup> → H<sub>2</sub>O)를 돕고, H 결합이 Pt보다 강해 H* 공급이 원활합니다. 본 작업 DFT에서도 ΔG<sub>H*</sub>는 Ru −0.37, Pt −0.21 eV였습니다. 다만 “H 결합이 강할수록 좋다”는 뜻은 아니며, 알칼리에서 활성을 정하는 서술자는 아직 논쟁 중입니다.</p>
<h3>A.3 그럼에도 Pt 대신 Ru를 쓰는 이유: 촉매 비용</h3>
<p>2026년 9월 기준 질량당 가격이 거의 같으므로, 비용 이득은 가격이 아니라 <b>같은 성능에 필요한 금속 양</b>에서 나옵니다.</p>
{_E[0]}
{table([
 ["같은 성능 (j<sub>0</sub><sup>geo</sup> 동일)", f"Ru {EQ['L_ru']} mg/cm² · ${EQ['cost_ru']:.2f}", f"Pt {EQ['L_pt']:.2f} mg/cm² · ${EQ['cost_pt']:.2f}", f"Ru가 {EQ['saving']*100:.0f} % 저렴"],
 ["같은 담지량 0.1 mg/cm²", f"η(2C) {sw('Ru',0.1)['eta_2C_mV']:.1f} mV · 효율 {sw('Ru',0.1)['EE']*100:.1f} %", f"η(2C) {sw('Pt',0.1)['eta_2C_mV']:.1f} mV · 효율 {sw('Pt',0.1)['EE']*100:.1f} %", "비용 거의 같음, Ru가 과전압 약 1/4"],
 ["Ru 0.1 대 Pt 0.5 mg/cm²", f"${sw('Ru',0.1)['cost_usd']:.2f} · η(C/2) {sw('Ru',0.1)['eta_05C_mV']:.2f} mV", f"${sw('Pt',0.5)['cost_usd']:.2f} · η(C/2) {sw('Pt',0.5)['eta_05C_mV']:.2f} mV", "같은 성능을 1/5 질량으로"],
 ["원자 1개당 가격", f"Ru 101.07 g/mol", "Pt 195.08 g/mol", f"같은 USD로 Ru 원자 {RA['atoms_per_usd']:.1f}배"],
], ["비교", "Ru/C", "Pt/C", "결론"])}
{img("fig/f_cost.png", "96%", "왼쪽: 셀당 촉매 금속 비용과 왕복효율(C/2, 모델). 오른쪽: 같은 담지량에서 2C 방전 때 H<sub>2</sub> 전극 과전압. Pt의 ECSA는 같은 입경을 가정해 Ru의 1/1.73로 두었다.", 17)}
<p><b>이 결론이 깨지는 조건.</b> (1) j<sub>0</sub> 비 2.86이 한 연구의 값이라 재현되지 않으면 비용 이득은 면적 효과만 남아 약 {(1-1/RA['area_per_mass'])*100:.0f} %로 줄어듭니다. (2) Ru/C는 400분 안정성 시험에서 전류가 56.5 % 감소했다는 보고가 있습니다(3 %Pt–Ru/C는 19.3 %) [4]. 그만큼 활성이 떨어지면 반응도 이점이 사라집니다. (3) Ru 가격이 더 오르면 이득이 비례해서 줄어듭니다. 셀당 Ru 비용은 2025년 가격이면 ${RP['price_scenarios']['Ru 2025-03 ≈ $560/oz']:.2f}, 지금 ${RP['price_scenarios']['Ru 2026-09 ≈ $1,713/oz']:.2f}, 가격이 두 배가 되면 ${RP['price_scenarios']['Ru ×2 충격']:.2f}입니다. (4) 이 1 Ah 셀에서 촉매비는 용기·전자부 대비 작습니다. 비용 이득이 의미를 갖는 것은 대형화했을 때입니다.</p>
</section>""")

# 2 prior art
S.append(f"""
<section><h2 class="h">1. 선행연구와 이 프로토타입의 위치</h2>
{table([
 ["Ni–H<sub>2</sub> 우주용 셀", "NASA RP-1314 핸드북 [2]", "IPV 설계, 압력=SOC, 안전 절차가 확립됨. 본 설계의 뼈대"],
 ["저가 촉매 Ni–H<sub>2</sub>", "Chen·Cui, PNAS 2018 [1]", "Pt → NiMoCo, 고면적 Ni 양극(~35 mAh/cm²). 비교 기준으로 사용"],
 ["Ru계 양방향 HER/HOR", "Ru/Ni<sub>3</sub>N–NF, J. Mater. Chem. A 2023 [3]", "Ru 촉매를 Ni–H<sub>2</sub>에 쓰는 직접 선행연구"],
 ["Ru의 알칼리 HOR과 비활성화", "Nat. Commun. 2024 [4]", "Ru/C j<sub>0</sub> 3.09 vs Pt/C 1.08 mA/cm², 0.4 V 이상에서 활성 소실"],
 ["상용화", "EnerVenue [11]", "30,000 사이클 설계, 20년/20,000 사이클 보증 보도"],
 ["Ru 표면 DFT", "JACS 2016 [5], Nat. Commun. 2020/2024 [6][7]", "ΔG<sub>H*</sub>(Ru(0001)) −0.25 ~ −0.50 eV 보고"],
], ["층위", "가장 가까운 선행연구", "본 작업과의 관계"])}
<p><b>새로운 점과 새롭지 않은 점.</b> Ru 촉매 Ni–H<sub>2</sub> 자체는 새롭지 않습니다 [3]. 이 보고서가 더하는 것은 세 가지입니다. (1) 1 Ah 저압 실험실 셀의 전체 치수 설계와 압력 안전 계층, (2) Ru의 약점(산화)을 막는 BMS 인터록 회로, (3) 모델 파라미터 하나하나를 실측으로 교정하는 실험 순서입니다. 이는 공학 통합이며, 소재 발견이라고 주장하지 않습니다.</p>
<p class="small"><b>조사 한계.</b> 원문 사이트(PMC, Stanford, 출판사)가 이 환경에서 차단되어 인용은 모두 검색 결과의 제목과 요약만 보고 달았습니다(참고문헌의 [조각] 표시). 인용한 수치는 원문으로 다시 확인해야 합니다. Scopus와 Web of Science는 보지 않았습니다.</p>
</section>""")

# 3 theory
S.append(f"""
<section><h2 class="h">2. 원리와 반응식</h2>
<h3>2.1 전극 반응 (알칼리, 30 wt% KOH)</h3>
<div class="eqbox">
<div class="eqlab">양극 (+) · Ni 전극</div>{_E[1]}
<div class="eqlab">음극 (−) · Ru 수소 전극</div>{_E[2]}
<div class="eqlab">전지 반응</div>{_E[3]}
</div>
<h3>2.2 부반응 (설계가 다뤄야 하는 것)</h3>
{table([
 ["과충전 산소 발생 (Ni 전극)", _E[4], "SOC가 높고 온도가 높을수록 커짐"],
 ["산소 재결합 (Ru 표면)", _E[5], "O<sub>2</sub>를 소비해 과충전을 열로 바꿈 (압력 포화)"],
 ["자가방전", _E[6], "속도 ∝ p<sub>H2</sub>·s [9][10]"],
 ["Ru 산화 (고장)", _E[7], "E > 0.4 V vs RHE에서 HOR 활성 소실 [4]"],
 ["전지 역전 (과방전)", _E[8], "H<sub>2</sub> 예충전 셀은 H<sub>2</sub>를 재소비해 견딤 [2]"],
], ["반응", "식", "의미"])}
<h3>2.3 수소 전극 메커니즘 (알칼리)</h3>
<div class="eqbox">
<div class="eqlab">Volmer</div>{_E[9]}
<div class="eqlab">Heyrovsky</div>{_E[10]}
<div class="eqlab">Tafel</div>{_E[11]}
</div>
<p>알칼리에서는 물 해리(Volmer)가 느린 단계가 되기 쉽습니다. Ru는 Pt보다 친산소성(oxophilic)이 강해 OH를 잘 잡습니다. 이 성질은 물 해리를 돕지만, 같은 이유로 높은 전위에서 스스로 산화되기도 합니다 [4]. 흡착 세기는 Sabatier 원리의 서술자 ΔG<sub>H*</sub>로 봅니다.</p>
{_E[12]}
<p class="small">+0.24 eV는 영점에너지와 엔트로피 보정의 관행값입니다 [8, 기억 인용 · 원문 미확인].</p>
{img("fig/f_dft.png", "78%", "본 작업 DFT(GPAW, PBE)로 계산한 ΔG<sub>H*</sub>. 대조군 Pt(111)이 문헌값 −0.09 eV보다 0.12 eV 낮게 나왔으므로, 이 계산 설정의 오차는 약 0.1 eV 규모다.", 1)}
{img("video/atom_t008.5.png", "92%", "원자 반응 영상의 한 장면(Volmer 단계). H*가 DFT 이완 위치인 fcc hollow, 최상층 위 1.07 Å에 흡착해 있다. H<sub>2</sub>O·OH<sup>−</sup>의 위치는 모식적 배치다.", 2)}
</section>""")

S.append(f"""
<section><h2 class="h">3. 수학 모델</h2>
<h3>3.1 열역학: 개방전압</h3>
{_E[13]}
<p>{_E[14]}는 NiOOH 분율(양극 SOC)입니다. {_E[15]}은 Ni 전극의 평탄한 곡선을 흉내 내는 계수입니다 [A]. 압력 항 덕분에 같은 SOC에서도 H<sub>2</sub>가 많으면 전압이 약간 오릅니다(그림 3).</p>
{img("fig/f_ocv.png", "70%", "OCV 모델. 압력 항의 기여는 1→4.5 bar에서 약 +19 mV다.", 3)}
<h3>3.2 압력–SOC 관계 (이상기체)</h3>
{_E[16]}
{_E[17]}
<p>자유 기체 체적 {_E[18]}, 예충전 {V['p_precharge_bar_abs']} bar abs에서 완충 압력은 {V['p_full_bar_abs_25C']:.2f} bar abs(25 °C)입니다. 압력계로 1 %의 SOC를 읽으려면 {V['dp_full_bar_25C']*10:.0f} mbar 분해능이 필요합니다. BMS의 압력 채널 분해능 3.0 mbar로 충분합니다.</p>
<h3>3.3 전극 동역학 (Butler–Volmer)</h3>
{_E[19]}
{_E[20]}
<p>Ru 수소 전극의 기하면적 교환전류는 {_E[21]}입니다. 1C(7.8 mA/cm²)에서 과전압은 1 mV 이하입니다. HOR에는 H<sub>2</sub> 공급 한계를 둡니다.</p>
{_E[22]}
<h3>3.4 셀 전압, 충전 수용, 자가방전</h3>
{_E[23]}
{_E[24]}
<p class="small">NiOOH가 바닥나면 방전 전류를 공급할 수 없어 전압이 급락합니다. 첫 판 모델에는 이 항이 없어서 1.0 V 종지를 잡기 전에 셀이 역전됐고, 웹 시뮬레이터에서 표준 사이클이 인터록 트립으로 표시되는 것을 보고 찾아 고쳤습니다. k<sub>Ni</sub> = 0.8 A/cm²는 [A]입니다.</p>
{_E[25]}
<h3>3.5 열 수지</h3>
{_E[26]}
<p>가역열(엔트로피 항)은 넣지 않았습니다. 그 결과 에너지 수지가 사이클당 {abs(chk['heat_Wh']-chk['energy_in_minus_out_Wh']-abs(chk['ds_over_cycle'])*1.47):.3f} Wh(약 3 %) 맞지 않습니다(§7.1).</p>
<h3>3.6 Ru 산화와 임피던스</h3>
{_E[27]}
<h3>3.7 DFT 방법</h3>
<p>GPAW(PAW, 평면파 350 eV), PBE, 4×4×1 k점, Fermi–Dirac 0.1 eV, 2×2 표면(1/4 ML), 4층 슬랩(하부 2층 고정), 진공 7 Å×2, BFGS fmax 0.05 eV/Å. 격자상수는 실험값을 썼습니다(Ru a=2.706, c=4.282 Å; Pt a=3.924 Å). 수렴 테스트는 하지 않았습니다.</p>
{table([[e, s, f3(v['dE']), f3(v['dG'])] for e in ("Ru", "Pt") for s, v in DFT['results'][e].items()], ["표면", "자리", "ΔE<sub>H</sub> (eV)", "ΔG<sub>H*</sub> (eV)"])}
</section>""")

# 4 design
S.append(f"""
<section><h2 class="h">4. 하드웨어 설계와 사양</h2>
<h3>4.1 셀 사양</h3>
{table([
 ["화학계", C['chemistry'], ""],
 ["공칭 용량 / 전압", f"{C['Q_Ah']} Ah / {C['V_nom']} V", "C/5, 25 °C"],
 ["충전 상한 / 방전 종지 / HW 차단", f"{C['V_charge_max']} / {C['V_dis_min']} / {C['V_hw_cutoff']} V", "HW 차단은 래치"],
 ["전극 스택", f"back-to-back {C['n_units']} unit, 원판 Ø{C['disc_od_mm']}/Ø{C['disc_id_mm']} mm", f"적층 높이 {V['stack_h_mm']:.1f} mm"],
 ["Ni 전극", f"{C['ni_thk_mm']} mm, {C['ni_areal_mAh_cm2']:.1f} mAh/cm²", "Co 도핑 Ni(OH)<sub>2</sub> 페이스트 / Ni 폼"],
 ["Ru/C 수소 전극 (GDE)", f"{C['n_gde']}장 × {C['face_area_cm2']:.2f} cm² = {C['h2_area_cm2']:.1f} cm², {C['gde_thk_mm']} mm", f"{C['ru_wt_pct_on_C']} wt% Ru/C, PTFE {C['ptfe_wt_pct']} wt%"],
 ["Ru 담지 / 총량", f"{C['ru_loading_mg_cm2']} mg/cm² / {C['ru_total_mg']:.1f} mg", ""],
 ["분리막 / 가스 스크린", f"{C['sep_thk_mm']} mm / {C['screen_thk_mm']} mm", "지르코니아 직물 또는 친수화 PP 부직포 / Ni 메시"],
 ["전해질", f"{C['koh_wt_pct']} wt% KOH, {C['koh_mL']} mL", "결핍(starved) 설계"],
], ["항목", "값", "비고"])}
<h3>4.2 압력용기</h3>
{table([
 ["재질 / 치수", f"{V['material']}, OD {V['od_mm']} × t {V['wall_mm']} mm, ID {V['id_mm']:.2f} mm, 내부 길이 {V['inner_len_mm']} mm", ""],
 ["내부 / 스택+부속 / 자유 기체 체적", f"{V['internal_mL']:.1f} / {V['stack_solid_mL']:.1f} / {V['free_gas_mL']:.1f} mL", ""],
 ["플랜지 · 실링", V['flange'], ""],
 ["포트", V['ports'] + " + 파열판", "M-001"],
 ["피드스루", V['feedthrough'], ""],
 ["후프 응력 @설계 20 bar", f"{V['hoop_stress_MPa_at_design']:.1f} MPa (허용 {V['allow_316L_MPa']} MPa, 여유 ×{V['allow_316L_MPa']/V['hoop_stress_MPa_at_design']:.1f})", _E[28]],
 ["질량 / 열용량 / 방열", f"{V['mass_kg']} kg / {V['cp_J_kgK']} J/kg·K / hA {V['hA_W_K']} W/K", "[A]"],
], ["항목", "값", "근거"])}
{img("fig/f_pressure.png", "74%", "압력 안전 계층. 운전값에서 설계값까지 네 단계의 독립 장치가 있다.", 4)}
<h3>4.3 BMS (RuH2-BMS rev A)</h3>
{table([
 ["MCU", BMS['mcu']], ["전원", BMS['supply'] + " → 5 V buck → 3.3 V LDO, 전력단용 3.3 V 3 A buck 별도"],
 ["전류 계측", f"{BMS['shunt_mohm']} mΩ 션트 + {BMS['ina_part']} (G={BMS['ina_gain']}), ±{BMS['i_range_A']} A, {BMS['i_lsb_mA']:.2f} mA/LSB"],
 ["전압 계측", BMS['vcell_amp'] + ", 0.806 mV/LSB"], ["압력", BMS['p_sensor'] + ", 3.0 mbar/LSB"], ["온도", BMS['ntc']], ["H<sub>2</sub> 누설", BMS['h2_sensor']],
 ["전력단", BMS['power_stage']], ["차단", BMS['disconnect']], ["EIS", BMS['eis']], ["통신", BMS['usb']],
], ["블록", "사양 (예시 부품 · 데이터시트 확인 필요)"])}
{table([
 ["과압", "6.0 bar abs", "11.5k/16.2k (E96)", "1.930 V", "5.99 bar", "≈83 mbar"],
 ["셀 저전압", "0.90 V", "28k/10.5k", "0.900 V", "0.900 V", "33 mV"],
 ["과온 (NTC 2.98 kΩ)", "55 °C", "35.7k/10.7k", "0.761 V", "54.8 °C", "≈1.5 °C"],
 ["H<sub>2</sub> 누설", "1.0 vol%", "10k + 트리머", "교정", "시험가스로 교정", "-"],
], ["인터록 채널", "목표", "분압", "기준전압", "실제 트립", "히스테리시스"])}
<p class="small">위 표의 분압값은 도면 E-004 계산값입니다. 비교기 출력은 wired-OR로 74LVC1G74 래치에 들어가고, 래치는 차단 MOSFET 게이트를 내립니다. MCU는 래치 상태를 읽기만 하고 해제할 수 없으며, 해제는 수동 리셋 버튼으로만 합니다.</p>
</section>""")

draw = [("E-001_block", "시스템 블록도"), ("E-002_power", "전원·선형 양방향 전력단·차단·션트 회로도"), ("E-003_sense", "계측 AFE 회로도"),
        ("E-004_mcu_safety", "MCU·안전 인터록 회로도"), ("M-001_vessel", "압력용기 조립도 (단면 A-A)"), ("M-002_stack", "전극 스택 상세"), ("M-003_pcb", "PCB 배치도 (2:1)")]
for k, (f, t) in enumerate(draw):
    S.append(f"<section class='land'>{img('drawings/' + f + '.png', '100%', f'RUH2-{f} · {t}', 5 + k)}</section>")

# 5 recipe
S.append(f"""
<section><h2 class="h">5. 제작 레시피</h2>
<p class="small">화학 합성과 소결은 흄후드, 보호안경, 내화학 장갑(니트릴 이중 또는 부틸), 실험복을 갖추고 하십시오. 온도와 시간은 문헌 요약 [12]에서 가져온 출발점이며 최적화되지 않았습니다.</p>
<h3>5.1 Ru/C 20 wt% 촉매 (폴리올 환원, 1 g 배치)</h3>
<ol>
<li>Vulcan XC-72R 0.80 g을 에틸렌글리콜(EG) 80 mL에 넣고 30분 초음파 분산합니다.</li>
<li>RuCl<sub>3</sub>·xH<sub>2</sub>O를 Ru 0.20 g에 해당하는 양만큼 EG 20 mL에 녹입니다. Ru 함량은 로트 분석서로 확인하며, 대개 0.5 g 안팎입니다.</li>
<li>용액을 합치고 N<sub>2</sub> 버블링을 하면서 30분 교반한 뒤, 환류 냉각기를 달고 170 °C에서 3 h 유지합니다 [12].</li>
<li>냉각한 뒤 여과하고, AgNO<sub>3</sub> 시험으로 Cl<sup>−</sup>가 검출되지 않을 때까지 DI수로 씻은 다음 에탄올로 씻습니다. 80 °C 진공에서 12 h 건조합니다.</li>
<li>선택: 5 % H<sub>2</sub>/Ar, 250 °C, 1 h로 표면 산화물을 환원합니다.</li>
<li>QC 합격 기준: ICP-OES Ru 20±2 wt%, XRD에서 hcp Ru 피크 확인, TEM 평균 입경 2–5 nm, Cu-UPD로 ECSA를 측정해 모델 가정 60 m²/g를 교체합니다.</li>
</ol>
<h3>5.2 Ru/C 가스확산 수소 전극 (GDE)</h3>
<ol>
<li>잉크: Ru/C 100 mg, PTFE 분산액(60 wt%)을 고형분 대비 30 wt%, IPA:DI = 1:1 4 mL를 섞고 30분 초음파 처리합니다.</li>
<li>기재: Ni 메시(약 100 mesh)에 다공성 PTFE 배면막을 붙입니다(가스 쪽). 에어브러시로 Ru {C['ru_loading_mg_cm2']} mg/cm²(Ru/C 2.5 mg/cm²)가 될 때까지 분무하고, 무게로 담지량을 확인합니다.</li>
<li>5 MPa로 압착한 뒤 Ar 분위기에서 330–350 °C, 15분 소결합니다(PTFE 소결). 공기 중에서는 탄소 지지체와 Ru가 산화되므로 금지합니다.</li>
<li>Ø{C['disc_od_mm']} / Ø{C['disc_id_mm']} mm로 타발하고, 전극 번호별 무게를 기록합니다. 필요한 수량은 {C['n_gde']}장에 예비분을 더한 것입니다.</li>
</ol>
<h3>5.3 Ni(OH)<sub>2</sub> 양극</h3>
<ol>
<li>페이스트: Co·Zn 도핑 구형 Ni(OH)<sub>2</sub> 90 wt%, CoO 5 wt%, PTFE 3 wt%, CMC 2 wt%에 물을 더합니다.</li>
<li>Ni 폼(1.6 mm)에 충전하고 건조한 뒤 {C['ni_thk_mm']} mm로 롤 압연합니다.</li>
<li>원판 하나에 활물질 약 0.96 g을 넣습니다(289 mAh/g × 이용률 0.9 → 250 mAh/원판, {C['ni_areal_mAh_cm2']:.1f} mAh/cm²).</li>
<li>Ni 탭을 스폿 용접합니다.</li>
</ol>
<h3>5.4 전해질과 조립</h3>
<ol>
<li>30 wt% KOH: DI수 70 g에 KOH 30 g을 얼음 중탕에서 천천히 넣습니다(발열). CO<sub>2</sub>가 차단되는 PP 용기에 보관합니다.</li>
<li>적층 순서는 M-002를 따릅니다: [스크린 | GDE | 분리막 | Ni | 분리막 | GDE] × {C['n_units']}. PTFE 타이로드와 엔드플레이트로 고정하고, 탭을 Ni 로드 피드스루에 용접합니다.</li>
<li>전해질을 진공 함침한 뒤 과잉분을 배출합니다(결핍 설계, 총 {C['koh_mL']} mL). 수소 전극 기공이 물에 잠기지 않게 하는 것이 목적입니다.</li>
<li>플랜지: EPDM O-ring, M6 A4-70 볼트 6개를 대각선 순서로 체결합니다. 토크는 O-ring 압축률 20–25 %를 기준으로 정하며, 예시값 7–9 N·m은 확인이 필요합니다.</li>
<li>누설 시험과 H<sub>2</sub> 예충전은 §6과 §9 T4의 절차를 따릅니다.</li>
</ol>
</section>""")

# 6 handling
S.append(f"""
<section><h2 class="h">6. 취급 파라미터와 안전</h2>
{table([
 ["충전 전류 / 방전 전류", f"≤ 0.5 C 권장, 최대 {LIM['I_max_A']} A", "선형 전력단 발열 한계 (E-002)"],
 ["충전 종지", "압력 기반: Δp가 완충 예상치의 105 %에 도달하거나 V ≥ 1.55 V", "O<sub>2</sub> 재결합 과충전은 열로 바뀜 (그림 14)"],
 ["방전 종지 / HW 차단", f"{C['V_dis_min']} V / {C['V_hw_cutoff']} V (래치)", "Ru 산화 방지"],
 ["온도 (충전 / 방전 / 충전 금지 / 차단)", f"{LIM['T_charge_C'][0]}–{LIM['T_charge_C'][1]} / {LIM['T_discharge_C'][0]}–{LIM['T_discharge_C'][1]} / {LIM['T_inhibit_C']} / {LIM['T_trip_C']} °C", "고온에서 충전 수용이 떨어짐"],
 ["압력 (운전 / 차단 / 릴리프 / 파열판)", f"≤ {LIM['p_max_oper_bar_abs']} / {V['p_trip_bar_abs']} / {V['p_relief_bar']} / {V['p_burst_disk_bar']} bar", "그림 4"],
 ["H<sub>2</sub> 경보 / 차단", f"{LIM['h2_alarm_vol_pct']} / {LIM['h2_trip_vol_pct']} vol% (LFL {LIM['h2_LFL_vol_pct']} %의 10 % / 25 %)", "[13] 참조"],
 ["H<sub>2</sub> 예충전", f"{V['p_precharge_bar_abs']} bar abs, N<sub>2</sub> 퍼지 3회 후", "역화 방지기, 흄후드"],
 ["보관", "방전 상태, 10–25 °C, H<sub>2</sub> 예충전 유지", "자가방전은 압력과 온도에 비례"],
], ["파라미터", "값", "이유"])}
<ul>
<li><b>KOH 30 wt%</b>는 강염기로 피부와 눈에 부식성입니다. 보안경 대신 고글과 안면보호구를 쓰고, 세안기 위치를 확인하고, 흘리면 대량의 물로 씻습니다.</li>
<li><b>H<sub>2</sub></b>의 가연 범위는 공기 중 4–75 vol%입니다. 점화에너지가 매우 낮으므로 정전기와 스파크를 관리하고 방폭 환경에서 다룹니다. 시험 셀은 환기되는 방호함 안에 둡니다.</li>
<li><b>압력</b>: 내압 시험(30 bar 수압)을 통과하지 않은 용기에는 가스를 넣지 않습니다. 릴리프 밸브의 방출구는 안전한 방향을 향하게 합니다.</li>
<li><b>전기</b>: 셀 전류는 작지만 단락 전류는 수십 A가 될 수 있습니다. 3 A 퓨즈를 셀 쪽 가까이에 둡니다.</li>
</ul>
</section>""")

# 7 results
S.append(f"""
<section><h2 class="h">7. 시뮬레이션 결과</h2>
<p>시간 간격 5 s(방전 말단 0.25 s)로 적분했습니다. 실행 방법은 부록 B에 있습니다.</p>
{img("fig/f_cycle.png", "86%", "C/2 표준 사이클. 휴지 중 압력이 조금 떨어지는 것이 자가방전이다.", 12)}
<div class="two">{img("fig/f_rate.png", "100%", "율 특성.", None)}{img("fig/f_catalyst.png", "100%", "수소 전극 촉매 비교.", None)}</div>
{img("fig/f_fault.png", "100%", "과방전 1C. 예충전 H<sub>2</sub>가 있으면 역전이 일어나도 수소 전극이 0.4 V에 닿지 않는다. 예충전이 없으면 Ru 활성이 사라진다. 보호(0.9 V 래치)는 역전 자체를 막는다.", 13)}
<div class="two">{img("fig/f_overcharge.png", "100%", "그림 14. 과충전 1C 2 h.", None)}{img("fig/f_selfdis.png", "100%", "그림 15. 72 h 자가방전: 압력 SOC와 쿨롱 카운팅 비교.", None)}</div>
{img("fig/f_eis.png", "60%", "SOC별 셀 EIS(모델). Ru 원호는 약 1 mΩ 이하로 보이지 않는다. 보이는 원호는 Ni 전극이다.", 16)}
{table([[k, f"{v['Qout']:.3f} Ah", f"{v['Vavg']:.3f} V"] for k, v in B['rate'].items()], ["C-rate", "방전 용량", "평균 전압"])}
{table([[f"{k} °C", f"{v['s_after_charge']*100:.1f} %", f"{v['Qout']:.3f} Ah"] for k, v in B['temp'].items()], ["주위 온도", "110 % 충전 후 NiOOH", "방전 용량"])}
<h3>7.1 모델 검사 (재기 전에 사소한 설명부터)</h3>
{table([
 ["H<sub>2</sub> 질량수지", f"최대 오차 {chk['h2_mass_balance_max_err_mol']:.1e} mol / 총 {chk['h2_total_mol']:.4f} mol", "같은 식을 적분한 것이라 <b>구현 검사</b>일 뿐 물리 검증이 아님"],
 ["압력–SOC 기울기", f"{chk['p_vs_s_slope_bar']:.4f} vs 닫힌 식 {chk['p_vs_s_slope_closed_form']:.4f} bar/Ah", "정의상 일치. 실측(T7)만 의미가 있음"],
 ["에너지 수지", f"입력−출력 {chk['energy_in_minus_out_Wh']:.3f} Wh + 화학 방출 {abs(chk['ds_over_cycle'])*1.47:.3f} vs 열 {chk['heat_Wh']:.3f} Wh", "잔차 약 3 %: 가역열 미반영"],
 ["시간 간격 수렴", f"dt 5 s {chk['Qout_dt5']:.4f} vs 1 s {chk['Qout_dt1']:.4f} Ah", "0.01 % 차이"],
 ["JS 이식 대조", "브라우저 모델 vs Python, 사이클 전체 |ΔV|, |Δp| &lt; 5×10<sup>−7</sup>", "인터랙티브 시뮬레이션이 같은 모델임을 확인"],
], ["검사", "결과", "해석"])}
</section>""")

S.append(f"""
<section><h2 class="h">8. Ru 산화와 자가방전을 막는 방법</h2>
<h3>8.1 Ru 산화 방지</h3>
<p>Ru가 산화되는 상황은 거의 하나입니다. 수소 전극에 H<sub>2</sub>가 부족한데 방전 전류가 계속 흐르면, 전극 전위가 0.4 V vs RHE를 넘습니다(H<sub>2</sub> 결핍 또는 셀 역전). 그래서 대책은 이 상황을 만들지 않는 시스템 대책이 먼저이고, 소재 대책은 여유를 넓히는 보조 수단입니다.</p>
{table([
 ["① H<sub>2</sub> 예충전 (1 bar abs)", "방전 끝에도 H<sub>2</sub>가 남아 수소 전극이 산화 전위로 못 감. 역전이 일어나도 Ni 전극에서 생긴 H<sub>2</sub>를 다시 소비", "시스템 (본 설계)"],
 ["② 하드웨어 0.9 V 래치 차단", "Ni 전극 고갈로 전압이 꺾이는 순간 차단. MCU가 해제할 수 없음", "회로 (E-004, 본 설계)"],
 ["③ 압력 하한 방전 정지", "p가 예충전값 근처로 내려오면 방전을 끝냄. H<sub>2</sub> 결핍을 직접 감시", "펌웨어 (추가 제안)"],
 ["④ Ni 제한 설계 (H<sub>2</sub> 과잉)", "용량을 Ni 전극이 정하도록 해 H<sub>2</sub>가 항상 남게 함. 예충전과 같은 원리", "셀 설계"],
 ["⑤ 과충전 제한 (압력 기반 종지)", "과충전 O<sub>2</sub>가 Ru 표면에서 재결합하는 동안 Ru가 O<sub>2</sub>에 노출됨. 과충전량을 줄임", "BMS"],
 ["⑥ 방전 상태·약 1.0 V 보관", "NASA 경험: 약 1.0 V에서는 전극 산화물 환원도 촉매 산화도 일어나지 않음(Pt 기준) [17]", "운용"],
 ["⑦ 조립 전 H<sub>2</sub> 환원 처리", "공기 중에서 생긴 Ru 표면 산화물을 5 % H<sub>2</sub>/Ar, 250 °C로 환원 (§5.1)", "공정"],
 ["⑧ 내산화 Ru 소재", "Pt 단원자 도핑(3 %Pt–Ru/C는 0.8 V까지 안정) [4], Ru<sub>7</sub>Ni<sub>3</sub> 합금, W 도핑 [18]", "소재 (T2b에서 비교)"],
], ["대책", "원리", "구분"])}
{img("fig/f_oxmethods.png", "86%", "과방전 1C 1.4 h 뒤 Ru 활성 잔존(모델). 시스템 대책(①②③)은 하나만 있어도 산화를 막는다. 내산화 소재(④, 개시 전위 0.4→0.8 V)만으로는 H<sub>2</sub>가 완전히 떨어진 경우 전위가 계속 올라가 막지 못한다.", 18)}
<p class="small">모델 한계: Ru 산화는 개시 전위 이상에서 1차 속도로 활성이 준다고 단순화했습니다([A] k<sub>ox</sub>). 산화 후 회복(재환원)은 넣지 않았습니다. 실제 개시 전위와 회복 가능성은 T2b에서 잽니다.</p>
<h3>8.2 자가방전 저감</h3>
<p>자가방전은 NiOOH + ½H<sub>2</sub> → Ni(OH)<sub>2</sub>의 직접 반응이고, 속도는 H<sub>2</sub> 압력, NiOOH 양, 온도에 따라 커집니다 [9][10]. 촉매 선택(Ru 또는 Pt)과는 무관합니다. 따라서 대책은 세 변수를 줄이거나 H<sub>2</sub>가 Ni 전극에 닿는 경로를 막는 것입니다.</p>
{table([
 ["① 낮은 온도 보관", "반응 속도의 아레니우스 의존 (가정 E<sub>a</sub> 60 kJ/mol). NASA 경험 보관 온도 0–4 °C 부근 [17]", "운용"],
 ["② 수소 압력 낮추기", "자유 기체 체적을 늘리거나 금속수소화물 병용. 수소화물 병용 셀은 자가방전이 약 절반이라는 보고 [17]", "셀 설계 (부피·밀도 손해)"],
 ["③ 부분 충전 보관", "속도 ∝ s. 필요할 때 충전", "운용"],
 ["④ 친수성 분리막", "전해질 보유량을 늘려 기공을 채우고 H<sub>2</sub> 확산을 막음 [17]", "소재"],
 ["⑤ 압력 SOC로 보정", "자가방전 자체는 줄지 않지만 잔량을 정확히 알 수 있음 (쿨롱 카운팅은 모름)", "BMS"],
], ["대책", "원리", "구분"])}
{img("fig/f_sdmethods.png", "86%", "72 h 개방 보관 손실(모델). ④의 “H<sub>2</sub> 확산 절반”은 효과 크기를 가정한 값이다. 조합(①+②+④)은 18.3 %를 1.9 %로 줄이지만, 각 효과는 가정 파라미터(E<sub>a</sub>, 압력 비례)에 기댄 추정이다.", 19)}
<p class="small">검증: T8(25/40 °C 자가방전)로 E<sub>a</sub>와 압력 의존을 먼저 재야 이 그림의 숫자가 의미를 가집니다.</p>
</section>""")

# 8 test plan
S.append(f"""
<section><h2 class="h">9. 실험·검증 청사진</h2>
<p>순서가 곧 원칙입니다. 앞 단계를 통과하지 못하면 다음 단계로 넘어가지 않습니다. 각 단계는 모델의 [A] 파라미터를 하나 이상 실측값으로 바꿉니다.</p>
{table([
 ["T1", "촉매 QC", "ICP-OES, XRD, TEM, Cu-UPD", "Ru 20±2 wt%, 2–5 nm", "ECSA 60 m²/g [A]"],
 ["T2", "반전지 RDE (1 M KOH, H<sub>2</sub> 포화)", "HOR/HER 분극, 미소분극, Koutecky–Levich", "j<sub>0</sub> ≥ 1 mA/cm²<sub>Ru</sub>", "j<sub>0</sub>=3.09 [L]"],
 ["T2b", "Ru 산화 창", "CV 상한을 0.2→0.8 V로 올려 가며 HOR 잔존율 측정", "개시 전위 결정", "0.4 V [L], k<sub>ox</sub> [A]"],
 ["T3", "GDE 반전지", "가스확산 반전지, 7.8 mA/cm²", "η &lt; 20 mV", "이용률 0.2 [A], k<sub>m</sub> [A]"],
 ["T4", "용기", "수압 30 bar 10분 → 5 % H<sub>2</sub>/N<sub>2</sub> 6 bar 누설 탐지, 압력 강하", "&lt; 0.01 bar/24 h", "V<sub>gas</sub>"],
 ["T5", "BMS 벤치", "정밀 저항·더미 부하·전압원 주입. EIS는 RC 더미 회로를 LCR 미터와 교차 대조", "I &lt; 0.5 %FS, V &lt; 1 mV, p &lt; 10 mbar, 4채널 래치 동작, Z 오차 &lt; 2 %", "계측 사슬"],
 ["T6", "화성·용량", "C/10 160 % 충전 × 3회, 이어서 C/5 방전", "≥ 0.9 Ah", "Q, Ni 이용률"],
 ["T7", "압력–SOC 교정", "C/5 단계 충전, 각 단계 휴지 후 p·T 기록", "기울기 3.48 bar/Ah ±10 % (온도 보정)", "V<sub>gas</sub>, 누설"],
 ["T8", "자가방전", "25/40 °C, 72 h 개방, 압력 추적", "k<sub>sd</sub>, E<sub>a</sub> 추정", "8 %/day, 60 kJ/mol [A]"],
 ["T9", "율·온도", "0.2–2 C, 10/25/40 °C", "모델 대비 오차 표", "j<sub>0,Ni</sub>, ASR [A]"],
 ["T10", "EIS", "SOC 10–90 %, 10 mHz–5 kHz", "R<sub>Ω</sub>, R<sub>ct,Ni</sub>, σ 추정", "C<sub>Ni</sub>, σ [A]"],
 ["T11", "수명", "C/2 × 500 사이클, 25 °C", "용량 유지율, 압력 드리프트", "-"],
 ["T12", "사후 분석", "XPS(RuO<sub>x</sub>), TEM(소결), 전해질 ICP(Ru 용출)", "열화 메커니즘 분리", "-"],
 ["T13", "고장 주입", "보호 켠 상태에서 과방전, 과온 모의, 압력 모의(N<sub>2</sub>)", "모든 경로 래치", "-"],
], ["단계", "대상", "방법", "합격 기준", "교체하는 모델 파라미터"], "small")}
<p><b>검증 규율.</b> 모든 측정값에 독립 대조를 하나씩 붙입니다(예: 압력 SOC와 쿨롱 SOC와 방전 용량, EIS R<sub>Ω</sub>와 전류 계단 응답의 순간 강하). 결과를 보고하기 전에 사소한 설명을 먼저 배제합니다(누설, 온도 드리프트, 센서 영점). 이 셀 구조에서는 Ru의 상태가 셀 전압과 EIS에 거의 나타나지 않습니다(과전압 ~1 mV). 그래서 Ru 건강 상태는 T2b와 T12처럼 전극 단위로 따로 봐야 합니다. 셀 단위 신호만으로 Ru 상태를 추정한다고 주장하지 않습니다.</p>
<h3>장비 목록</h3>
<p class="small">EIS 가능 포텐쇼스탯, RDE, Hg/HgO 기준전극, 흄후드, 환류 장치, 진공 오븐, 튜브로(Ar), 유압 프레스, 에어브러시, 스폿 용접기, 수압 시험 펌프, H<sub>2</sub> 레귤레이터와 역화 방지기, H<sub>2</sub> 탐지기, 정밀 저울, ICP-OES·XRD·TEM·XPS(공동 기기).</p>
</section>""")

# 9 applications
S.append(f"""
<section><h2 class="h">10. 응용 분야와 한계</h2>
{table([
 ["계통 연계 ESS, 재생에너지 평활화", "사이클 수명이 매우 길고(상용 30,000 사이클 설계 보도 [11]) 수계 전해질이라 열폭주가 없음", "Wh/kg·Wh/L이 낮아 설치 면적이 큼"],
 ["통신·데이터센터 백업", "넓은 온도 범위와 압력 기반 SOC로 정비가 쉬움", "자가방전이 커서 장기 대기 손실이 큼"],
 ["오프그리드 태양광, 마이크로그리드", "매일 사이클과 긴 수명", "초기 비용 (압력용기, 촉매)"],
 ["우주 (역사적 주력)", "NASA 핸드북의 설계 유산 [2]", "현재는 Li-ion이 대체 중"],
 ["연구·교육 플랫폼 (본 프로토타입)", "촉매 비교, 압력 SOC, EIS, 안전 인터록을 한 셀에서 실험", "1 Ah 실험실 규모"],
], ["분야", "Ni–H<sub>2</sub>(Ru)가 맞는 이유", "제약"])}
<p><b>적합하지 않은 곳.</b> 전기차와 휴대기기입니다. 이 프로토타입의 비에너지는 용기 질량이 지배해 셀 기준 약 {1.25*cyc['Qout']/(V['mass_kg']+0.08):.1f} Wh/kg입니다. 상용 Ni–H<sub>2</sub>(55–75 Wh/kg [10])와 비교할 수준이 아니며, 그 차이는 대형화와 공용 압력용기(CPV)에서 줄어듭니다.</p>
</section>""")

# 10 visuals
still = sorted(glob.glob(f"{HERE}/video/frames_batt_*.png"))
S.append(f"""
<section><h2 class="h">11. 3D 렌더와 영상</h2>
<p>함께 제출하는 영상 두 편은 다음과 같습니다. (1) <b>ru_atomic_reactions.mp4</b>(66 s): Ru(0001) 위의 Volmer, Tafel, HOR, Ru 산화, Ni(OH)<sub>2</sub>↔NiOOH. (2) <b>ruh2_battery_simulation.mp4</b>(70 s): 셀과 BMS 전경, 절개·분해 스택, C/2 사이클 재생. 인터랙티브 3D와 실시간 시뮬레이터는 별도 웹 페이지로 제공합니다.</p>
<div class="two">{img(still[0] if still else "video/battery_t003.0.png", "100%", "전경: 용기, 포트, BMS, PC", None)}{img(still[1] if len(still) > 1 else "video/battery_t010.5.png", "100%", "절개도와 분해 스택", None)}</div>
<div class="two">{img(still[2] if len(still) > 2 else "video/battery_t030.0.png", "100%", "충전: 압력 상승", None)}{img("video/atom_t044.0.png", "100%", "고장 모드: Ru 산화", None)}</div>
</section>""")

# appendix
rows = []
lab = {"E0_25": "[L]", "j0_h2_spec": "[L]", "E_ox": "[L]"}
for k, v in P.items():
    if isinstance(v, (int, float)):
        rows.append([k, f"{v:.4g}", lab.get(k, "[C]" if k in ("j0_h2_geo", "R_ohm", "k_sd25", "Q_C") else "[A]")])
S.append(f"""
<section><h2 class="h">부록 A. 모델 파라미터</h2>
{table(rows, ["기호", "값", "출처"], "small")}
<h2 class="h">부록 B. 실행 방법</h2>
<pre>python3 -m ruh2.make 보고서        # 데이터 → 그림 → 도면 → 스틸 → 이 PDF (정책 검사 통과해야 나옴)
python3 -m ruh2.make 웹            # 한 파일 인터랙티브 페이지
python3 -m ruh2.render battery     # 배터리 영상 (atom: 원자 반응)
python3 -m ruh2.analysis 전부       # 모델 분석 글 (봇 도구 ruh2_battery 와 같은 것)
python3 -m reportkit 문서.md        # 다른 주제의 보고서도 같은 정책으로
사양은 ruh2/spec.py 한 곳. 산출물은 inbox/ruh2/ (커밋 안 함). 디스코드: ruh2_battery · ruh2_make · report_pdf 도구</pre>
<h2 class="h">참고문헌</h2>
<p class="small">확인 수준: [전문] 본문을 읽음 · [조각] 검색 결과의 제목과 요약만 봄 · [기억] 검색으로 확인하지 않은 기억 인용. 이 보고서의 인용에 [전문]은 없습니다.</p>
<ol class="refs">
<li>W. Chen, Y. Jin, J. Zhao, N. Liu, Y. Cui, “Nickel-hydrogen batteries for large-scale energy storage,” <i>PNAS</i> 115(46), 11694–11699 (2018). doi:10.1073/pnas.1809344115 [조각]</li>
<li>J. D. Dunlop, M. R. Gopalakrishna, T. Y. Yi, <i>NASA Handbook for Nickel-Hydrogen Batteries</i>, NASA RP-1314 (1993). [조각]</li>
<li>“Ruthenium nanoparticles supported on Ni<sub>3</sub>N nanosheets as bifunctional catalysts…,” <i>J. Mater. Chem. A</i> 11, 849–857 (2023). doi:10.1039/D2TA08355H [조각]</li>
<li>“Unveiling the nature of Pt-induced anti-deactivation of Ru for alkaline hydrogen oxidation,” <i>Nat. Commun.</i> (2024). nature.com/articles/s41467-024-45873-0 [조각]</li>
<li>J. Zheng et al., “High Electrocatalytic Hydrogen Evolution Activity of an Anomalous Ruthenium Catalyst,” <i>JACS</i> (2016). doi:10.1021/jacs.6b11291 [조각]</li>
<li>“Ruthenium anchored on carbon nanotube electrocatalyst for hydrogen production with enhanced Faradaic efficiency,” <i>Nat. Commun.</i> (2020). s41467-020-15069-3 [조각]</li>
<li>“Rationally designed Ru catalysts supported on TiN…,” <i>Nat. Commun.</i> (2024). s41467-024-50691-5 [조각]</li>
<li>J. K. Nørskov et al., “Trends in the exchange current for hydrogen evolution,” <i>J. Electrochem. Soc.</i> 152, J23 (2005). [기억]</li>
<li>“Self-Discharge of the Nickel Electrode in the Presence of Hydrogen,” <i>J. Electrochem. Soc.</i> doi:10.1149/1.1391944 [조각]</li>
<li>“Analysis of Pressure Variations in a Low-Pressure Nickel-Hydrogen Battery,” PMC3298376; Wikipedia “Nickel–hydrogen battery” (1.25 V, 55–75 Wh/kg, &gt;20,000 cycles). [조각]</li>
<li>Energy-Storage.news, “EnerVenue … 30,000-cycle nickel-hydrogen battery” (2023–2026 보도). [조각]</li>
<li>Ru/C 폴리올 합성(EG, 170 °C 3 h): <i>J. Power Sources</i> (2007) S0378775307005319 외 검색 요약. [조각]</li>
<li>ISO/TR 15916:2015 Basic considerations for the safety of hydrogen systems (폐지, ISO/TS 15916:2026으로 대체). [조각]</li>
<li>J. Enkovaara et al., “Electronic structure calculations with GPAW,” <i>J. Phys.: Condens. Matter</i> 22, 253202 (2010); A. H. Larsen et al., “The atomic simulation environment,” <i>J. Phys.: Condens. Matter</i> 29, 273002 (2017); J. P. Perdew, K. Burke, M. Ernzerhof, <i>PRL</i> 77, 3865 (1996). [기억]</li>
<li>TBISTAT open-source EIS potentiostat, <i>PLOS ONE</i> (2022). [조각]</li>
<li>루테늄·백금 가격: dailymetalprice.com, mining.com “Ruthenium prices hit record high as AI boom squeezes supply”, Umicore 가격 페이지 (2026-09 검색). 출처 사이에 수치가 다소 다름. [조각]</li>
<li>US 특허 4800140 “Apparatus and method for preventing degradation of nickel hydrogen cells and batteries”(보관 약 1.0 V); PMC3375848(수소화물 병용 시 자가방전 약 절반); 친수성 분리막 특허(US 6623809 등). [조각]</li>
<li>“Design of Ru-Ni diatomic sites…” (PMC9159574), Ru<sub>7</sub>Ni<sub>3</sub>/C, W 도핑 Ru (<i>Nat. Commun.</i> 2025, s41467-025-56240-y). [조각]</li>
</ol>
</section>""")


body = "\n".join(S)


def main(strict=True):
    out = paths.OUT / "RuH2-P1_prototype_report.pdf"
    r = kit.build_html(body, out, "RuH2-P1 프로토타입 보고서", strict=strict, footer="RuH2-P1 프로토타입 보고서 · 설계 제안 · 미검증")
    print(r)
    return r


if __name__ == "__main__":
    r = main(strict="--force" not in sys.argv)
    raise SystemExit(0 if r.get("ok") else 1)
