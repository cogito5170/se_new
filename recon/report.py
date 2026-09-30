"""RECON-R1 설계·검증 청사진 보고서 (reportkit 정책을 따른다: 저장소의 reportkit 을 읽기 전용으로 import).
python3 -m recon.make 보고서  ->  inbox/recon/report/RECON-R1_blueprint.pdf
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))
from reportkit import kit  # noqa: E402
from recon import paths  # noqa: E402
import spec  # noqa: E402

RUNS, FIG, DWG, OUT = paths.RUNS, paths.FIG, paths.DRAW, paths.ANALYSIS
sys.path.insert(0, str(ROOT / "sim"))
from scenarios import SCENARIOS  # noqa: E402

m = lambda t: kit.eq(t, False)   # noqa: E731
M = lambda t: kit.eq(t, True)    # noqa: E731
T = kit.table


def meta(i):
    p = RUNS / i / "meta.json"
    return json.loads(p.read_text()) if p.exists() else None


def pct(x):
    return "-" if x is None else f"{x * 100:.1f}%"


def cm(x):
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.1f} cm"


BOM = json.loads((ROOT / "hw/bom_verified.json").read_text())
MC = json.loads((OUT / "mc.json").read_text()) if (OUT / "mc.json").exists() else []
FIL = json.loads((OUT / "filters.json").read_text()) if (OUT / "filters.json").exists() else []
MS = {i: meta(i) for i in SCENARIOS}


def mc_stat(method, key, sc=1.0):
    v = [(r[key] or 0) * sc for r in MC if r["method"] == method]
    if not v:
        return "-"
    mu = sum(v) / len(v); sd = (sum((x - mu) ** 2 for x in v) / len(v)) ** 0.5
    return f"{mu:.1f} ± {sd:.1f}"


def mc_mean(method, key):
    v = [(r[key] or 0) for r in MC if r["method"] == method]
    return sum(v) / len(v) if v else float("nan")


def fil_mean(k, key):
    v = [r[k][key] for r in FIL]
    return sum(v) / len(v) if v else float("nan")


P, MECH, DR = spec.PARTS, spec.MECH, spec.DRIVE
body = []
add = body.append

# ------------------------------------------------------------------ 표지
add(f"""<div class='cover'><div class='cv-top'>RCN-DOC-001 · rev A · 2026-09-29 · SE agent (저장소 읽기 전용 실행)</div>
<h1>RECON-R1</h1><h2>자율 정보·정찰 데이터 수집 로버<br>설계·제작·검증 청사진</h2>
<div class='cv-box'><div>스키드 조향 4륜 · 450×350×150 mm · {MECH['mass_kg']} kg [A] · 4S Li-ion 10 Ah ({spec.E_WH:.0f} Wh 가용)</div>
<div>Livox Mid-360(뒤집어 장착) + IMU 1 kHz + 엔코더 3200 tick/rev + IMX219 (+ RTK GNSS 확장)</div>
<div>Jetson Orin Nano Super (추정·지도·J) + STM32H753 (PID·안전·SE fw 결정 커널)</div>
<div>2.5D 고도지도(셀마다 칼만 평균·분산·관측수·시각·신뢰) · 정보이득 목적함수 J · 비LLM 결정 executive</div></div>
<div class='cv-warn'><b>이 문서의 수치는 세 가지 출처뿐이다:</b> 데이터시트 검색 조각 [조각] · 설계 가정 [A] · 가상 시험장 시뮬레이션 [C].
실측 [M] 은 하나도 없다. 로버는 아직 만들어지지 않았다. 시뮬레이션은 <b>실험 전 논리 검증</b>이지 실제 데이터를 대신하지 않는다
— 무엇을 실험으로 확인해야 하는지는 §8 청사진과 §12 에 적었다.</div></div>""")

# ------------------------------------------------------------------ 요약
b04 = MS.get("B04") or {}
k04 = b04.get("kpi", {})
T05 = MS.get("T05") or {}
add("<section><h2>요약</h2>")
add("<p>사용자 요구(0–21 절, Step 1–12)를 이 문서의 절에 1:1 로 대응시킨 표가 부록 A 에 있다. 아래 수치의 출처는 괄호 안에 적었다: "
    "<b>시뮬레이션 [C]</b>(이 작업의 가상 시험장 모델 출력) · <b>가정 [A]</b> · <b>문헌/데이터시트 조각 [조각]</b>.</p>")
rows = [
    ["부품비(가격 확인된 품목만)", f"${BOM['total_usd']['min']:,.0f} – ${BOM['total_usd']['typical']:,.0f} (GNSS 제외 ${BOM['total_usd']['min_without_gnss']:,.0f} –)", "[조각] 검색 가격, 퓨즈·E-stop·프레임·배송 제외"],
    ["전력 · 운용시간", f"평균 {spec.P_AVG:.1f} W · 최대 {spec.P_PEAK:.0f} W · {spec.RUNTIME_H:.2f} h", "[A] 부하표 · 시뮬 실측 평균은 §6.1"],
    ["원시 데이터율", f"{spec.DATA['raw_Bps'] / 1e6:.2f} MB/s (512 GB 에 {512e9 / spec.DATA['raw_Bps'] / 3600:.0f} h)", "[조각] Mid-360 점률 × 26 B/점 [A]"],
    ["LiDAR 사각 반경", f"뒤집음 {MECH['lidar_blind_r_inverted']:.2f} m (바로 세우면 {MECH['lidar_blind_r_upright']:.1f} m)", "[C] 기하 · FOV [조각]"],
    ["정적 전복 한계", f"{MECH['max_slope_deg']:.1f}° (앞뒤) · 정책 한계 25°", "[A] 무게중심 16 cm"],
]
if MC:
    rows += [["제안 vs 프런티어 커버리지 (240 s, 5 시드)", f"{mc_stat('proposed', 'coverage', 100)} % vs {mc_stat('frontier', 'coverage', 100)} %", "[C] 같은 세계·시드·안전층"],
             ["관심구역 σ≤2 cm 달성", f"{mc_stat('proposed', 'aoi_cov', 100)} % vs 프런티어 {mc_stat('frontier', 'aoi_cov', 100)} %", "[C]"]]
if FIL:
    rows += [["슬립(진흙) 지도 오차: 엔코더만 vs 제안", f"{fil_mean('odom', 'map_rmse_m') * 100:.1f} cm vs {fil_mean('proposed', 'map_rmse_m') * 100:.1f} cm (위치 {fil_mean('odom', 'final_err_m'):.2f} m vs {fil_mean('proposed', 'final_err_m') * 100:.1f} cm)", "[C] 3 시드, LIO 는 대용 모델"]]
rows += [["결정 커널 크기", "커널 10 + recon 프로파일 .text 9,323 B · Agent 2,400 B RAM · malloc 0", "[C] gcc -O2 -ffreestanding 실측(호스트)"]]
add(T(rows, ["항목", "값", "출처"]))
add("""<h3>찾은 것 세 가지</h3><ol>
<li><b>LiDAR 를 뒤집어 다는 것이 지상 매핑의 첫 조건이다.</b> Mid-360 의 수직 시야 -7..+52° 를 그대로 60 cm 높이에 달면 반경 4.9 m 안의 지면이 안 보인다. 뒤집으면 0.47 m 로 준다. [C·기하]</li>
__FIND2__
<li><b>재방문(REVISIT)은 대부분의 시나리오에서 선택되지 않았다.</b> 한 번 지나가며 σ 가 목표 아래로 내려갔기 때문이다. 재방문 가치는 목적함수에서 저절로 나오게 두었고, 억지로 가중치를 올리지 않았다(§6.4). 이것은 우리 지도 모델이 프레임 간 오차를 독립으로 보아 σ 를 과소평가할 수 있다는 점과 함께 읽어야 한다.</li></ol>
<h3>하지 않은 것</h3><ul><li>로버를 만들지 않았고 실측이 없다. 데이터시트 본문도 읽지 못했다(모두 검색 조각).</li>
<li>LIO(FAST-LIO2 등)를 실제로 돌리지 않았다 — 정보행렬 기반 대용 모델이다. ARM 크로스빌드·타이밍 분석을 하지 않았다.</li>
<li>카메라 영상은 상태 표시용 렌더일 뿐, 영상 기반 인지·정보량은 모델에 없다.</li></ul></section>""".replace("__FIND2__",
    "<li><b>엔코더만으로 만든 지도는 슬립 지반에서 무너지고, 필터가 자기 불확실도를 과신하면 LIO 가 있어도 무너진다.</b> 같은 원시 데이터로 필터 네 개를 돌렸다(§6.2). "
    + (f"지도 RMSE: 엔코더만 {fil_mean('odom', 'map_rmse_m') * 100:.1f} cm · EKF+LIO {fil_mean('ekf_lio', 'map_rmse_m') * 100:.1f} cm · 제안 {fil_mean('proposed', 'map_rmse_m') * 100:.1f} cm (3 시드, 모델). " if FIL else "")
    + "첫 판의 제안 필터는 σ 0.9 cm 라고 믿으며 3.3 m 틀렸다 — 연속 기각을 발산으로 읽는 장치를 넣고서야 이 차이가 났다.</li>"))

# ------------------------------------------------------------------ 단점
add("<section><h2>A. 단점과 한계 (좋은 점보다 먼저)</h2>")
add(T([
    ["시뮬레이션이 실제를 대신하지 않는다", "지형·슬립·LiDAR(선 3,600/프레임, 실제 약 20,000)·LIO 가 모두 모델", "모든 결과 수치는 '이 모델 안에서' 의 값. §8 TEST 로 교체해야 한다"],
    ["LIO 대용 모델", "참 자세 + 거리 0.3 % 표류 + 면 법선 정보행렬 잡음", "실제 LIO 의 퇴화·실패 양상(긴 복도, 비·먼지)을 다 담지 못한다"],
    ["σ 과소평가 가능성", "셀 칼만이 프레임 간 오차를 독립으로 본다", "재방문 가치를 과소평가한다. 실측 σ 보정(TEST-07)이 필요"],
    ["2.5D 격자의 벽 번짐", "수직면 점이 이웃 셀로 번져 벽 옆 지면이 높게 읽힌다", "벽 ±0.2 m 는 RMSE 에서 따로 잰다(edge RMSE). 수직 구조가 많은 곳은 복셀이 낫다(§3.6)"],
    ["Mid-360 단종 표시", "DJI Store 에 discontinued [조각]", "Mid-360S 로 교체 예정 — 치수·전력 같음 [조각], 확인 필요"],
    ["부품 확인 수준", "데이터시트 사이트가 이 환경에서 차단", "모든 사양이 [조각]. 구매 전 데이터시트 대조 필수"],
    ["14.4 V 로 24 V 모터 구동", "속도·토크가 정격의 60 % [조각 환산]", "최고 0.75 m/s, 등판 토크 여유 감소. 12 V 권선판(#4753)이 대안"],
    ["433 MHz 킬은 소비자 부품", "신호 상실 시 차단 보장 없음 [조각]", "하트비트형으로만 쓰고, 주 안전은 유선 E-stop + MCU 워치독"],
    ["재방문 시연 약함", "30 시나리오 중 REVISIT 선택이 드묾", "재방문이 필요한 조건(열화·자세 불확실)에서만 나타난다 — 그대로 보고"],
    ["동적 장애물 예측 없음", "P05: 옆에서 0.5 m/s 로 가로지른 사람과 43.5 s 에 접촉, AVOID 는 1.2 s 늦게 나왔다 [C]", "위험은 지도(현재 위치)만 본다 — 움직임 예측·사람 주변 정지 반경이 필요(§7)"],
    ["단일 로버·단일 목표", "다중 로버, 의미 인지(물체 인식) 없음", "정보 = 기하 불확실도 감소로만 정의"],
], ["단점", "근거", "의미·대응"]))
add("</section>")

# ------------------------------------------------------------------ 선행연구
add("<section><h2>1. 선행연구와 이 설계의 위치</h2>")
add("<p>확인 수준: 논문 본문을 읽은 것은 없다. 공식 저장소 README 의 인용 블록을 직접 읽은 것과 검색 조각뿐이다. "
    "<b>조사 한계</b>: 탐사+불확실도 고도맵+소형 스키드 로버를 한 시스템으로 묶은 논문을 찾는 검색은 하지 않았다 — 그러니 '가장 가까운 선행연구' 는 확정되지 않았다.</p>")
add(T([
    ["프런티어 탐사", "Yamauchi 1997 [1]", "기준선 B03 으로 그대로 구현", "새것 아님"],
    ["정보이득 탐사·NBV", "Stachniss 2005 [2], Bircher 2016 [3]", "J = 기대 정보이득 - 에너지·시간·위험 비용", "새것 아님(형태). 목표 σ 로 자른 '결정 관련 정보' 정의는 이 작업의 선택"],
    ["불확실도 고도지도", "Fankhauser 2014/2018 [4][5], Miki 2022 [6]", "셀 칼만 + 자세 불확실도 팽창(단순형)", "새것 아님"],
    ["LIO", "FAST-LIO2 [7], LIO-SAM [8]", "실기에서 쓸 추정기. 여기선 대용 모델", "—"],
    ["3D 표현", "OctoMap [9], Voxblox [10]", "표현 비교 대상(§3.6)", "—"],
    ["지하 탐사 시스템", "GBPlanner [11], TARE [12], CERBERUS [13]", "대형 시스템 기준점", "이 설계는 훨씬 작고 단일 층 계획"],
    ["스키드 슬립", "Yi 2007/2009 [14][15], Mandow 2007 [16]", "요 효율 χ·종방향 슬립 모델, 엔코더↔LIO 슬립 추정", "새것 아님"],
    ["비LLM 결정 커널", "SE 저장소 fw/ (SAR 프로파일)", "PolicySpec 하나로 로버 도메인 재사용", "저장소 내 재사용 — 논문 기여 아님"],
], ["층위", "가장 가까운 것", "이 설계에서", "새것인가"]))
add("</section>")

# ------------------------------------------------------------------ 원리
add("<section><h2>2. 원리와 이론 (수학 모델)</h2>")
add("<h3>2.1 무엇을 '정보' 라고 부르나</h3><p>셀 c 의 고도를 가우스 " + m(r"h_c\sim\mathcal N(\mu_c,\sigma_c^2)") +
    " 로 둔다. 관측 한 번의 정보량은 엔트로피 감소이고, <b>임무가 요구하는 목표 σ<sub>t</sub> 아래로 줄이는 것은 가치 0</b> 으로 자른다(결정 관련 정보):</p>")
add("<div class='eqbox'>" + M(r"g_c=\tfrac12\log_2\frac{\max(\sigma_c^2,\sigma_{t,c}^2)}{\max(\sigma_{c,\mathrm{post}}^2,\sigma_{t,c}^2)},\qquad \sigma_{c,\mathrm{post}}^2=\frac{\sigma_c^2\,\sigma_m^2}{\sigma_c^2+\sigma_m^2}") +
    "<div class='eqlab'>σ<sub>t</sub> = 5 cm (기본), 관심구역 2 cm [A] · σ<sub>m</sub> ≈ 3 cm/√3 (한 번 지나가며 여러 프레임) [A] · 미지 셀 σ = 1 m</div></div>")
add("<h3>2.2 목적함수 J</h3>" + "<div class='eqbox'>" +
    M(r"U(g)=\underbrace{\sum_c K(\lVert c-g\rVert)\,g_c}_{IG(g)\ [\mathrm{kbit}]}-\lambda_E E(g)-\lambda_T T(g)-\lambda_R R(g),\qquad J=\frac{U}{U+U_0}\ (U>0)") +
    M(r"K(r)=e^{-(r/4\,\mathrm m)^2}\ (0.5\le r\le 8\ \mathrm m),\quad E=\frac{T\,(P_\mathrm{base}+\bar P_\mathrm{drive})}{3600},\quad T=\frac{d_\mathrm{Dijkstra}}{v_\mathrm{nom}}") +
    "<div class='eqlab'>λ<sub>E</sub>=2 kbit/Wh · λ<sub>T</sub>=0.1 kbit/s · λ<sub>R</sub>=5 kbit · U<sub>0</sub>=5 kbit [A, 튜닝값] · R = 목표 셀 주행위험 · 후보 세 종류: 탐사(미지 셀 g), 재방문(아는 셀 g), 정지관측(4 s 누적, 반경 10 m 커널)</div></div>")
add("<p>모든 항이 원시 데이터에서 계산된다: g<sub>c</sub> 는 LiDAR 점으로 갱신된 지도 분산에서, d 는 그 지도로 만든 비용지도의 Dijkstra 거리에서, R 은 같은 지도의 기울기·계단·불확실도에서. "
    "<b>이 결론이 깨지는 조건</b>: K 가 가림(occlusion)을 무시하므로 벽 뒤 IG 를 과대평가한다 — 실제로는 광선 추적 IG 가 필요하다.</p>")
add("<h3>2.3 셀 칼만 갱신과 자세 불확실도 팽창</h3><div class='eqbox'>" +
    M(r"\sigma_{z}^2=\underbrace{\frac{\sigma_r^2}{n_\mathrm{eff}}}_{\text{독립}}+\underbrace{(r\,\sigma_\mathrm{att})^2+\sigma_{pz}^2+s^2\left(\sigma_{xy}^2+r^2\sigma_\theta^2\right)+(s\,\Delta/2)^2}_{\text{이 프레임 공통(상관)}}") +
    M(r"\mu\leftarrow\frac{\mu\,\sigma_z^2+\bar z\,\sigma^2}{\sigma^2+\sigma_z^2},\qquad \sigma^2\leftarrow\frac{\sigma^2\sigma_z^2}{\sigma^2+\sigma_z^2},\qquad |\bar z-\mu|>3\sqrt{\sigma^2+\sigma_z^2}+5\,\mathrm{cm}\Rightarrow\sigma^2\mathrel{+}=(\bar z-\mu)^2") +
    "<div class='eqlab'>σ<sub>r</sub>=2 cm [조각] · σ<sub>att</sub>=0.2° [A] · n<sub>eff</sub>≤4 · s = 셀 기울기 · Δ = 0.1 m 셀 · 마지막 식 = 변화 검출(사람·오정합) → 불확실도로 되돌림 (Fankhauser 식의 단순형)</div></div>")
add("<p>첫 판은 모든 항을 점 수로 나눠 σ 를 1 cm 대로 과소평가했다. 자세 오차는 한 프레임의 모든 점에 공통이라 나눌 수 없다 — 그렇게 고쳤다.</p>")
add("<h3>2.4 스키드 조향 운동학과 슬립</h3><div class='eqbox'>" +
    M(r"v=\tfrac{v_L+v_R}{2}(1-s),\quad \omega=\chi\frac{v_R-v_L}{B},\quad s=s_\mathrm{terr}+0.9\max(0,\sin\theta_\mathrm{pitch})+\epsilon") +
    M(r"\hat s=1-\frac{\lVert\Delta p_\mathrm{LIO}\rVert_{1\,\mathrm s}}{\Delta d_\mathrm{enc}}\quad(\Delta d_\mathrm{enc}>0.12\,\mathrm m,\ \sigma_\mathrm{LIO}<5\,\mathrm{cm})") +
    f"<div class='eqlab'>B = {MECH['track']} m · χ(요 효율) 단단한 땅 0.80, 모래 0.60, 진흙 0.55 [A] · s<sub>terr</sub> 0.03/0.25/0.35 [A] · 첫 판은 0.1 s 미분으로 LIO 잡음을 슬립으로 읽었다(참 0.04 → 추정 0.21)</div></div>")
add("<h3>2.5 자세 EKF</h3><div class='eqbox'>" +
    M(r"\mathbf x=[x,y,\theta,b_g]^\top,\quad \theta_{k+1}=\theta_k+(\omega_\mathrm{gyro}-b_g)\Delta t,\quad Q_{v}=\left((0.03+2\hat s)\,|\Delta d|\right)^2") +
    M(r"\text{LIO: } z=[x,y,\theta]+w,\ R=\begin{bmatrix}(H_n+I)^{-1}&0\\0&\sigma_\theta^2\end{bmatrix},\ H_n=\tfrac{1}{40\,\sigma_r^2}\sum_i n_{h,i}n_{h,i}^\top;\qquad \mathrm{NIS}>16.3\Rightarrow\text{기각}") +
    "<div class='eqlab'>n<sub>h</sub> = 점의 면 법선 수평 성분 — 평평한 들판은 H 가 작아 x,y 가 약하게 관측된다(실제 LIO 퇴화와 같은 방향) · /40 = 점 상관 보정 [A]</div></div>")
add("<h3>2.6 모터·전력</h3><div class='eqbox'>" +
    M(r"\omega_w=\frac{V-I R_m}{k_e},\quad I=\frac{\tau}{k_t}+I_0,\quad \tau=r\frac{mg}{4}(C_{rr}\cos\theta+\sin\theta)+r\,\mu_\mathrm{lat}\frac{mgL}{4B}\,\mathbb 1_{|\omega|>0.02}") +
    "<div class='eqlab'>k<sub>e</sub>=1.146 V·s/rad, R<sub>m</sub>=8 Ω (24 V 정격에서 역산) [조각 환산] · k<sub>t</sub>=0.70 N·m/A (정지토크 2.1 N·m [A]) · C<sub>rr</sub>=0.05, μ<sub>lat</sub>=0.45 [A]</div></div></section>")

# ------------------------------------------------------------------ 설계
add("<section><h2>3. 설계와 사양</h2><h3>3.1 시스템 구조 — 층마다 입출력·주기·계산·메모리 (Step 1)</h3>")
add(T([
    ["센서 드라이버", "Jetson/MCU", "원시 점·IMU·틱·영상·GNSS", "10 Hz / 1 kHz / 100 Hz / 30 Hz / 10 Hz", "livox_ros_driver2, SPI DMA, 타이머 캡처", "링버퍼 ~64 MB"],
    ["시간 동기", "Jetson+MCU", "PTP(LiDAR), PPS→MCU TIM5 캡처, chrony", "1 Hz PPS", "오프셋 추정", "-"],
    ["상태추정", "Jetson", "IMU+틱+점 → 자세 x,y,θ,b_g, 공분산", "10 Hz 갱신 / 50 Hz 예측", "FAST-LIO2 + EKF 4상태", "~200 MB (LIO 지도)"],
    ["지도", "Jetson", "점+자세 공분산 → 고도·분산·수·시각", "10 Hz", "bincount 적분 300×300", "셀당 14 B → 1.3 MB"],
    ["증거층", "Jetson", "건강 5, 슬립, 기울기, 위험, J 후보 3", "1 Hz(J) / 10 Hz", "Dijkstra 150², FFT 합성곱", "~20 MB"],
    ["결정 커널 (SE fw)", "MCU", "Blackboard → 행동 id", "10 Hz", "BT 17 노드 + argmax 9", "2,400 B RAM · 9.3 KB .text"],
    ["유도", "Jetson", "행동+목표 → 경로 → v, ω", "1 Hz 재계획 / 50 Hz 추종", "순수추종 L=1.0 m", "-"],
    ["제어기", "MCU", "v, ω → 바퀴 4 PWM", "50 Hz", "PID + 역기전력 앞먹임", "-"],
    ["안전감독", "MCU + 하드웨어", "E-stop·킬·워치독·MOTOR_EN", "하드웨어 즉시", "접촉기 코일 직렬", "-"],
    ["기록·압축·통신", "Jetson", "원시 로그 · 타일 델타 → 링크", "연속 / 1 Hz", "zlib, 정보밀도 정렬", "NVMe 512 GB"],
], ["층", "위치", "입력 → 출력", "주기", "계산", "메모리"], "small"))
add(kit.fig(FIG / "decision_arch.png", "결정 executive 와 유도·제어·구동의 분리. 빨간 화살표: 하드웨어 안전이 소프트웨어를 거치지 않고 구동기를 끊는다."))
add(kit.drawing(DWG / "RCN-S-001_system.png", "RCN-S-001 시스템 블록도 — 데이터율(spec.DATA), 계산 배치, Jetson 을 우회하는 안전 경로 세 개."))

# BOM
add("<h3>3.2 BOM — 실제 구매 가능한 부품 (Step 2)</h3>")
rows = []
for p in BOM["parts"]:
    pr = p.get("price_usd")
    if isinstance(pr, dict):
        prs = f"{pr.get('unit_min') if pr.get('unit_min') is not None else '-'} / {pr.get('unit_typical') if pr.get('unit_typical') is not None else '-'}"
    else:
        prs = "-" if pr is None else str(pr)
    if p["key"] == "dcdc_19":
        continue                                            # 설계에서 뺐다 (Jetson 팩 직결)
    rows.append([p["key"], p["name"][:58], p.get("qty", 1), prs, (p.get("vendor") or "-")[:60], p.get("confidence", "[조각]")])
add(T(rows, ["key", "부품", "수량", "단가 USD (min/typ)", "판매처", "확인"], "small"))
add(f"<p class='small'>합계(가격 확인 품목만) ${BOM['total_usd']['min']:,.0f} / ${BOM['total_usd']['typical']:,.0f}. 합계 제외: {', '.join(BOM['total_usd']['excludes'])}. "
    "이 품목들의 추정치(퓨즈·홀더 $25, E-stop+접촉기 $45, 2020 프레임·데크 $90, 허브 $30, 케이블·커넥터·충전기 $120 [A])를 더하면 약 <b>$2,540–2,830</b>. "
    "표의 dcdc_19 는 설계에서 뺐다(Jetson 은 팩 직결 + LTC4359 이상다이오드). MCU 는 NUCLEO-H753ZI 로 바꿨다(H743ZI2 NRND [조각]).</p>")

# 센서
add("<h3>3.3 센서 — 최소 세트와 확장 세트 (Step 3)</h3>")
add(T([
    ["LiDAR Mid-360 (최소)", "10 Hz, 20만 점/s", "360°×59°", "0.1–40 m (10 % 반사)", "≤2 cm@10 m, ≤3 cm@0.2 m", "PTP 동기", "5.2 MB/s", "6.5 W (저온 14)", "265 g", "Ethernet", "$749–979"],
    ["IMU ICM-42688-P (최소)", "1 kHz", "±2000 °/s", "-", "0.0028 °/s/√Hz", "<1 ms", "32 kB/s", "3 mW", "~5 g", "SPI", "$27"],
    ["엔코더 64 CPR×50 (최소)", "100 Hz 보고", f"{DR['dist_per_tick_mm']:.3f} mm/tick", "-", "양자화 ±0.06 mm", "타이머", "2.4 kB/s", "-", "모터 포함", "4×TIM", "모터 포함"],
    ["카메라 IMX219 (최소)", "30 Hz", "1280×720", "-", "-", "~70 ms (H.264)", "~69 kB/s", "0.25–1 W", "3 g", "CSI (15→22 핀)", "$17"],
    ["GNSS ZED-F9P (확장)", "10 Hz", "-", "-", "RTK 1 cm / 단독 1.5–2 m", "PPS", "1 kB/s", "0.4 W", "~20 g", "UART+PPS", "$327–370"],
    ["Mid-360 내장 IMU", "200 Hz", "-", "-", "미확인", "PTP", "-", "-", "-", "Ethernet", "$0"],
], ["센서", "주기", "분해능", "범위", "정확도·잡음", "지연", "대역", "전력", "무게", "인터페이스", "가격"], "small"))
add("<p><b>최소 세트</b>(LiDAR+IMU+엔코더+카메라)는 GNSS 없이 LIO 로 자세를 잇는다 — 30 시나리오 중 27개가 이 세트다. <b>확장 세트</b>(+GNSS)는 실외 절대좌표와 PPS 시각을 준다(F06). 모든 값 [조각].</p>")
add(kit.fig(FIG / "lidar_mount.png", "Mid-360 장착 방향 비교. 바로 세우면 60 cm 높이에서 반경 4.9 m 안의 지면이 안 보인다. 뒤집으면 0.47 m. 뒤집은 장착의 허용 여부는 데이터시트 확인 대상."))

# 데이터 스키마
add("<h3>3.4 원시 데이터 스키마와 시각 동기 (Step 4)</h3>")
add(T([
    ["lidar_frame", "t_ns(u64, PTP) · seq(u32) · n(u32) · 점[x,y,z(i32 mm), refl(u8), tag(u8), line(u8), dt_us(u32)]", "PTP (Jetson PHC 마스터)", "26 B/점 [A]"],
    ["imu_sample", "t_ns · gyro[3] f32 · acc[3] f32 · temp f32 · src(u8: 외부/내장)", "MCU TIM5 틱 → PPS 로 UTC 환산", "32 B"],
    ["wheel_ticks", "t_ns · ticks[4] i32 · duty[4] i16 · I_motor[2] i16", "MCU 틱", "24 B"],
    ["cam_frame", "t_ns(노출 중앙) · seq · H.264 NAL", "V4L2 단조 시각 → chrony", "~2.3 kB/프레임"],
    ["gnss_fix", "t_ns · lat,lon,h f64 · σ[3] · fix(u8) · nsat", "PPS 에지", "~100 B"],
    ["pose_est", "t_ns · x,y,θ,b_g · P(4×4) · slip · src_mask", "Jetson", "96 B"],
    ["map_tile", "t_ns · tile(i,j) · mask(bits) · Δh(i16 cm) · Δq_σ(i16) · zlib", "Jetson", "가변 (§3.8)"],
    ["decision", "t_ns · health[5] · J[3]+xy · bt · arb · act · safety · mode · events", "MCU 10 Hz", "64 B"],
], ["메시지", "필드", "시각 원천", "크기"], "small"))
add("<p>시각 동기: GNSS PPS(없으면 Jetson PHC)를 74LVC2G34 로 나눠 MCU TIM5_CH1 과 Jetson GPIO 에 넣는다. MCU 는 PPS 에지 사이 틱 수로 발진기 오차를 추정해 모든 샘플을 UTC ns 로 바꾼다. LiDAR 는 ptp4l/phc2sys 로 PTP. "
    "합격 기준: 세 시계 사이 오프셋 < 1 ms (TEST-01 의 준비 단계). Orin Nano 이더넷의 하드웨어 PTP 타임스탬프 지원 여부는 <b>미확인</b>.</p>")
add(kit.drawing(DWG / "RCN-E-002_signal.png", "RCN-E-002 신호·시간동기 배선도 — NUCLEO-H753ZI 핀 배정(엔코더 TIM2/3/4/8, PWM TIM1, IMU SPI1, PPS TIM5), Jetson 연결."))

# 잡음
add("<h3>3.5 잡음 모델과 필터 비교 설계 (Step 5)</h3>")
add(kit.fig(FIG / "noise_models.png", "잡음 모델: 셀 고도 측정 σ(거리·기울기·자세), 자이로 편향 랜덤워크, 엔코더 양자화. 전부 가정 파라미터."))
add(T([
    ["LiDAR", "거리 가우스 σ 2 cm + 먼지 시 4배·35 % 손실·8 % 허공 점(80 % 태그)", "지도 분산, 건강(태그 비율·지면 되돌림 비율)"],
    ["IMU", "편향 N(0, 0.05°/s) + 랜덤워크 0.002°/s/√s + 백색 0.014°/s; 고장 시 0.03°/s² 램프", "EKF 편향 상태, 건강(|b̂|>0.6°/s)"],
    ["엔코더", "3200 tick/rev 양자화; 고장 시 한 바퀴 값 고정", "짝 바퀴 비교로 격리"],
    ["바퀴-지면", "종 슬립 s, 요 효율 χ, 계단 5 cm 이상 못 넘음", "슬립 추정, AVOID"],
    ["GNSS", "RTK σ 2 cm, 수관 아래 고정 없음", "게이트 13.8(2자유도 99.9 %)"],
], ["센서", "모델", "쓰는 곳"], "small"))
add("<p>필터 비교(바퀴 슬립 지도 왜곡 실험): <b>같은 원시 데이터 스트림</b>으로 네 추정기(F1 엔코더, F2 +자이로, F3 EKF+LIO, F4 제안: 편향 상태+슬립 적응 Q+NIS 게이트+GNSS)를 동시에 돌리고, 각 자세로 따로 지도를 쌓아 참 지형과 비교한다(결과 §6.2).</p>")

# 표현 비교
add("<h3>3.6 3D 지도 표현 비교와 선정 (Step 6)</h3>")
cmp = (b04.get("compression") or [])
vox = k04.get("voxels")
add(T([
    ["원시 점 누적", "최고", "없음(점 자체)", "없음", f"{spec.DATA['lidar_Bps'] / 1e6:.1f} MB/s 누적", "기록용"],
    ["2.5D 고도 격자 + 분산 (선정)", "셀 0.1 m", "셀마다 σ", "좋음(행 한 번)", "14 B/셀 → 30×30 m 에 1.3 MB", "주행·계획·통신"],
    ["복셀 점유 (OctoMap 류)", "0.1 m", "점유 확률", "보통", f"B04 에서 점유 복셀 {vox:,}개 [C]" if vox else "-", "수직 구조·돌출"],
    ["TSDF/메시 (Voxblox 류)", "0.05–0.1 m", "가중치", "느림", "복셀의 수 배", "시각화·충돌"],
], ["표현", "해상도", "불확실도", "계획 속도", "크기", "용도"], "small"))
add("<p><b>선정: 2.5D 고도 격자.</b> 지상 로버의 결정(주행 가능성·정보이득)은 지면 높이와 그 σ 로 충분하고, 셀마다 σ 를 들고 있어 J 를 바로 계산한다. "
    "<b>깨지는 조건</b>: 돌출·다리 밑·동굴처럼 한 (x,y)에 높이가 둘 이상인 곳, 벽 옆(번짐 — §6 edge RMSE). 그런 현장은 복셀을 같이 쓴다.</p>")
add("<h3>3.7 셀마다 불확실도 (Step 7)</h3><p>셀 상태 = (μ 높이, σ², 관측 수, 마지막 시각, 신뢰 = clip(1-σ/0.2)). σ 는 §2.3 식으로 자세 공분산을 받아 팽창하고, 시간에 따라 q = 2×10<sup>-6</sup> m²/s 로 자라며(동적 환경 가정), 변화 검출 시 되돌아 커진다. "
    "영상과 PDF 의 3D 지도 색이 이 σ 다(파랑 2 cm → 빨강 30 cm, 검정 = 미지).</p>")
add("<h3>3.8 압축 — 바이트당 결정 관련 정보 최대화 (Step 8)</h3><p>16×16 셀 타일마다 직전 전송본과의 델타(2 cm 또는 σ 19 % 이상 바뀐 셀만)를 1 cm 고도(i16)·로그 σ(8 bit, 약 2 % 단계)로 양자화해 zlib. "
    "이번 초의 링크 예산 안에서 <b>정보이득(bit)/바이트</b>가 큰 타일부터 보낸다. 대역이 줄면 영상 썸네일을 먼저 끊는다.</p>")
if cmp:
    add(T([[r[0], f"{r[1] / 1e6:,.3f} MB", ("-" if not r[2] else f"{r[2] * 100:.2f} cm"), ("-" if (r[3] != r[3] or not r[3]) else f"{r[3] * 100:.2f} cm")] for r in cmp],
          ["표현·부호화 (B04 최종 지도)", "크기", "고도 오차 RMSE", "σ 복원 오차"], "small"))

# 정책
add("<h3>3.9 데이터 수집 정책 — 상태 · 행동 · 목적 (Step 9)</h3>")
add(T([
    ["s<sub>t</sub> 자세", "x̂, ŷ, θ̂, b̂<sub>g</sub>, σ<sub>pose</sub>", "EKF"],
    ["s<sub>t</sub> 지도", "μ, σ², n, t (300×300)", "LiDAR 점"],
    ["s<sub>t</sub> 차량", "배터리 비율, 귀환 필요 비율(Dijkstra×1.5), 기울기/25°, 슬립 ŝ", "BMS·INA226, 지도, IMU, 엔코더+LIO"],
    ["s<sub>t</sub> 센서", "건강 5 (LiDAR·IMU·엔코더·카메라·GNSS)", "자가진단·잔차"],
    ["s<sub>t</sub> 운용", "저장 사용률, 링크 끊긴 시간, 커버리지", "OS·링크"],
], ["상태", "성분", "원천"], "small"))
add(T([
    ["EXPLORE", "J 탐사 최대 셀로 이동", "LiDAR 건강 ≥0.5, J>0, 귀환 모드 아님"],
    ["OBSERVE", "정지 4 s 스캔(비반복 패턴 누적)", "LiDAR 또는 카메라 건강, J>0"],
    ["REVISIT", "σ 큰 아는 셀 무리로 이동", "EXPLORE 와 같음"],
    ["RETURN", "기지로(LiDAR 없으면 지나온 길)", "항상"],
    ["AVOID", "0.4 m 후진 → 벌점 → 재계획 (기동 잠금)", "항상"],
    ["RELOCALIZE", "정지, LIO 수렴 대기", "LiDAR 또는 GNSS, σ>0.175 m"],
    ["SAFE_STOP", "제동 정지(모터 전원 유지)", "안전필터 전용"],
    ["EMERGENCY", "접촉기 차단", "안전필터 전용"],
], ["행동", "하드웨어 동작", "precondition"], "small"))

# 결정
add("<h3>3.10 결정 executive — 상태추정 → 증거 → guard → BT → 정책 → 중재 → 안전감독 (Step 10)</h3>")
add(T([
    ["1 EMERGENCY", "actuator_ok=0 또는 배터리 <5 %", "하드웨어 차단 확인 후 기록 계속"],
    ["2 SAFE_STOP", "위험 >0.92 · 기울기 ≥ 한계 · 항법 수단 전부 사망 · σ>1.2 m", "정지; 3 s 이어지면 벌점·재계획"],
    ["3 AVOID", "위험 >0.6 · 슬립 >0.45 · 기울기 >0.8", "후진 0.4 m, 슬립이면 반경 1.6 m 비용↑ + 5 s 불응기"],
    ["4 RETURN", "배터리 < 귀환필요+8 % · 저장 ≥98 % · 링크 ≥30 s · 커버리지 ≥92 % · LiDAR 사망", "기지로"],
    ["5 RELOCALIZE", "σ<sub>pose</sub> > 0.35 m", "정지"],
    ["6 (없음)", "-", "HOLD 제안 → 중재기가 효용 argmax(탐사·재방문·관측)"],
], ["BT 우선순위", "guard", "실행"], "small"))
add("<p>커널 순서(SE fw/agent.c 그대로): stale 검출 → 증거 → FDIR(건강 엣지 이벤트) → 계획(mode) → BT 제안 → 중재(precondition 을 만족하면 BT 존중, 아니면 효용 argmax) → 안전필터(이동 행동인데 위험 >0.6 이면 AVOID 로 강제). "
    "호스트 검사 21개 통과(결정 표 19 + 결정성 500 스텝 + 이벤트) [C]. 실행층 기동 잠금: 시작한 후진·정지관측은 끝까지 한다 — 첫 판은 0.1 s 마다 다시 골라 후진을 한 번도 못 했다(T04 AVOID↔EXPLORE 189회).</p>")
add(kit.drawing(DWG / "RCN-E-001_power.png", "RCN-E-001 전원 분배 회로도 — 모터 버스만 K1 로 끊고 로직 버스는 살린다. E-stop·433 MHz 킬·MOTOR_EN 이 코일에 직렬."))
add(kit.drawing(DWG / "RCN-M-001_mech.png", "RCN-M-001 기구도 — 측면·정면·평면 1:5, 뒤집은 Mid-360 시야 쐐기, 무게중심과 전복각."))
add(kit.fig(FIG / "rover3d_iso.png", "실물 치수 3D (1 칸 = 1 cm, spec.py 에서 생성). 라벨은 좌우 열 + 지시선으로 부품을 가리지 않는다.", "100%"))
add(kit.fig(FIG / "rover3d_explode.png", "분해도 — 전원 층(배터리·드라이버·퓨즈·접촉기·급전)을 옆으로 뺐다. 실제로는 아래 데크.", "100%"))
add(kit.fig(FIG / "rover3d_side.png", "측면: 뒤집은 LiDAR 시야와 사각 반경 0.47 m(주황), 무게중심(분홍).", "100%"))
add(kit.fig(FIG / "power_budget.png", "전력 예산(가정 부하). 시뮬 실측 평균과의 비교는 §6.1."))
add(kit.fig(FIG / "data_budget.png", "원시 데이터율. LiDAR 가 97 % 를 차지한다."))
add("</section>")

# ------------------------------------------------------------------ 제작
add("<section><h2>4. 제작 방법 — 기구 · 전기 · 계산 · 펌웨어 · 소프트웨어</h2>")
add(kit.drawing(DWG / "RCN-A-001_assembly.png", "RCN-A-001 조립 순서도 — 단계마다 측정하고 합격해야 다음 단계. 빨간 칸은 안전 기능 시험."))
add(kit.drawing(DWG / "RCN-H-001_harness.png", "RCN-H-001 하네스·커넥터 표 — 전선 굵기, 핀, 시작→끝."))
add("<h3>4.1 펌웨어 (STM32H753, 베어메탈)</h3>")
add(T([
    ["TIM1 PWM 20 kHz", "하드웨어", "4 채널 duty", "-"],
    ["엔코더 캡처", "TIM2/3/4/8 직교 모드", "틱 i32", "-"],
    ["IMU 1 kHz", "SPI1 DMA + EXTI", "링버퍼", "ISR"],
    ["제어 루프 50 Hz", "SysTick", "PID + 앞먹임 + 격리된 엔코더 대체", "~20 µs [A]"],
    ["결정 10 Hz", "SE fw 커널 + profile_recon.c", "행동 id", "측정 필요(G2)"],
    ["링크", "USB-CDC (예비 USART2) COBS+CRC16", "후보 J·건강 ← / 행동·틱·IMU →", "-"],
    ["안전", "IWDG 100 ms, MOTOR_EN 100k 풀다운, E-stop 감지 PE2", "하트비트 끊기면 정지", "하드웨어"],
], ["태스크", "자원", "출력", "시간"], "small"))
add("<h3>4.2 소프트웨어 (Jetson, Ubuntu 22.04 + ROS 2 Humble [A])</h3><p>livox_ros_driver2 → FAST-LIO2 → 자세 EKF(여기 시뮬의 estimation.py 와 같은 식) → 고도지도(mapping.py) → 증거·J(planning.py) → USB-CDC 로 MCU 에 후보 전송 → 행동 수신 → 유도(Dijkstra+순수추종) → v, ω 전송. "
    "기록: rosbag2(mcap) 원시 + 타일 델타. 이 보고서의 시뮬 코드는 그대로 호스트 노드의 참조 구현이다.</p>")
add("<h3>4.3 빌드 (저장소를 고치지 않고)</h3><pre>gcc -std=c99 -O2 -Wall -Wextra -Werror -fPIC -shared -I SE/fw -o libfw_recon.so \\\n    recon_bridge.c profile_recon.c SE/fw/{blackboard,estimator,evidence,bt,event,safety,arbiter,decision,planner,agent}.c ... -lm\n"
    "arm-none-eabi-gcc -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard -std=c99 -Os -ffreestanding ... (툴체인 없음 — 미실시)</pre></section>")

# ------------------------------------------------------------------ 안전
add("<section><h2>5. 취급과 안전</h2>")
add(T([
    ["팩 전압", "12.0–16.8 V", "BMS 차단, VBAT_SENSE 로 11.8 V 경보"],
    ["주 퓨즈", "30 A (설계 피크 12.4 A)", "배선 12 AWG"],
    ["모터 버스", "K1 뒤, 드라이버마다 15 A", "E-stop·킬·MOTOR_EN 중 하나로 차단"],
    ["경사", "정책 25°, 정적 전복 43.2°(앞뒤)", "tilt ≥ 1 → SAFE_STOP"],
    ["속도", "0.4 m/s 명목, 0.5 m/s 상한, DEGRADED 0.2", "제동거리 < 0.3 m [A]"],
    ["LiDAR 레이저", "Class 1 [조각]", "눈높이 운용은 확인"],
    ["배터리 취급", "18650 4S4P, 충전은 BMS 달린 CC/CV 16.8 V", "충전 중 무인 방치 금지"],
    ["원격 킬", "하트비트형 수신기만", "토글형 금지(링크 상실 시 안 끊김)"],
], ["항목", "한계", "근거·동작"], "small"))
add("</section>")

# ------------------------------------------------------------------ 결과
add("<section><h2>6. 결과 (가상 시험장 [C])</h2>")
add("<p>30 시나리오, 각 120–300 s 시뮬 → 영상 1 편(60 s, 배속 표시). 세계는 절차적으로 만든 30×30 m 시험장이다. 결정은 실제 C 커널(libfw_recon.so, SE fw 소스를 읽기만 해서 컴파일)이 한다.</p>")
rows = []
for i, sc in SCENARIOS.items():
    mt = MS.get(i)
    if not mt:
        rows.append([i, sc["title"], "미실행", "", "", "", "", "", ""]); continue
    k = mt["kpi"]
    rows.append([i, sc["title"].replace("TEST-0", "T-"), pct(k["coverage"]), pct(k.get("aoi_cov")) if k.get("aoi_cov") is not None else "-",
                 cm(k["rmse_m"]), cm(k.get("ate_m")), f"{k['dist_m']:.0f}", f"{k['energy_Wh']:.2f}", f"{k['collisions']}" + (" 실패" if k.get("crashed") else "")])
add(T(rows, ["ID", "시나리오", "커버리지", "관심구역", "고도 RMSE", "ATE", "거리 m", "Wh", "충돌"], "small"))
add("<p class='small'>커버리지 = 임무 구역(벽 제외) 중 σ<5 cm 셀 비율. 고도 RMSE 는 수직 구조 ±0.2 m 를 뺀 지면 셀(아는 셀 σ<10 cm). ATE = 추정-참 위치 RMSE(1 Hz). "
    "Wh 는 모터+기저 부하 22 W 전체.</p>")
if (FIG / "unc_maps.png").exists():
    add(kit.fig(FIG / "unc_maps.png", "최종 불확실도 지도(σ, cm)와 참 궤적. 빈칸은 미지."))
# 6.1 에너지
if b04:
    add("<h3>6.1 에너지 수지 검사</h3>")
    rows = []
    for i in ("T01", "T06", "B04", "P09"):
        mt = MS.get(i)
        if mt:
            k = mt["kpi"]; P_ = k["energy_Wh"] * 3600 / k["t"]
            rows.append([i, f"{k['t']:.0f} s", f"{k['energy_Wh']:.2f} Wh", f"{P_:.1f} W", f"{P_ - 22:.1f} W", f"{spec.E_WH / P_:.1f} h"])
    add(T(rows, ["런", "시간", "사용 에너지", "평균 전력", "구동 평균(−22 W 기저)", "이 전력으로 운용시간"], "small"))
    add(f"<p>가정 부하표의 평균 {spec.P_AVG:.1f} W 는 구동 24 W 를 잡았는데 시뮬 구동 평균은 이보다 작다(0.4 m/s·경사 작음). "
        "<b>이것은 같은 모터 모델을 적분한 값이라 구현 검사일 뿐</b>이고, 실제 구동 전력은 TEST-01 전류 측정으로 교체한다.</p>")
# 6.2 필터
add("<h3>6.2 바퀴 슬립에 의한 지도 왜곡 — 필터 비교</h3>")
if FIL:
    add(kit.fig(FIG / "filters_maps.png", "같은 원시 데이터·같은 주행(시드 0)으로 쌓은 네 지도의 |고도 오차|. 엔코더만 쓴 지도는 진흙(청록 윤곽) 통과 후 전체가 어긋난다."))
    add(kit.fig(FIG / "filters_bars.png", "3 시드 평균 ± 표준편차: 최종 위치 오차(로그), 요 오차, 유령 셀."))
    ks = [("odom", "F1 엔코더"), ("odom_gyro", "F2 +자이로"), ("ekf_lio", "F3 EKF+LIO"), ("proposed", "F4 제안")]
    add(T([[n, f"{fil_mean(k, 'final_err_m'):.3f} m", f"{fil_mean(k, 'yaw_err_deg'):.2f}°", f"{fil_mean(k, 'map_rmse_m') * 100:.1f} cm", f"{fil_mean(k, 'ghost_cells'):.0f}"] for k, n in ks],
          ["필터", "최종 위치 오차", "요 오차", "지도 RMSE", "유령 셀"], "small"))
    add("<p><b>해석.</b> 자이로는 요를 지켜 주지만(F1→F2) 종방향 슬립은 못 본다 — 위치 오차는 그대로 남는다. LIO 갱신(F3)이 위치를 붙잡는다. "
        f"F4 는 지도 RMSE 를 {fil_mean('ekf_lio', 'map_rmse_m') * 100:.1f} → {fil_mean('proposed', 'map_rmse_m') * 100:.1f} cm 로 더 줄인다: 진흙처럼 평평해 LIO 가 퇴화하는 곳에서 슬립을 못 재는 동안 주행거리를 의심하고(Q↑), "
        "그만큼 지도 셀의 σ 를 부풀려 틀린 높이가 확신으로 박히지 않게 한다. <b>깨지는 조건</b>: LIO 대용 모델은 퇴화 외의 실패(비·먼지·특징 없는 긴 복도)를 담지 않는다 — 실제 F3/F4 차이는 TEST-05 로 잰다.</p>")
# 6.3 기준선
add("<h3>6.3 기준선 비교 — 고정 웨이포인트 · 무작위 · 프런티어 · 제안 (같은 조건)</h3>")
if MC:
    add(kit.fig(FIG / "mc_bars.png", "240 s, 5 시드. 같은 세계·같은 안전층·같은 유도·제어. 관심구역(오른쪽 위 언덕, σ≤2 cm)은 제안 방법만 목적함수에 넣는다 — 기준선은 설계상 그것을 모른다."))
    add(kit.fig(FIG / "mc_curves.png", "커버리지 곡선(선 = 평균, 띠 = 시드 최소~최대)."))
    add(T([[{"fixed": "고정 웨이포인트", "random": "무작위", "frontier": "프런티어(Yamauchi)", "proposed": "제안"}[mm], mc_stat(mm, "coverage", 100), mc_stat(mm, "aoi_cov", 100),
            mc_stat(mm, "dist_m"), mc_stat(mm, "energy_Wh"), mc_stat(mm, "info_per_Wh"), mc_stat(mm, "collisions")] for mm in ("fixed", "random", "frontier", "proposed")],
          ["방법", "커버리지 %", "관심구역 %", "거리 m", "에너지 Wh", "정보 kbit/Wh", "충돌"], "small"))
    add("<p><b>공정성.</b> 네 방법은 후보 생성기만 다르고, fw 안전층·유도·제어·물리는 같다. 관심구역 지표는 제안 방법에 유리하게 정의된 것이므로 <b>전체 커버리지와 따로</b> 읽는다. "
        "5 시드는 통계적 결론에 부족하다 — 차이가 표준편차보다 작은 지표는 '차이 없음' 으로 읽는다.</p>")
    add(f"<p><b>읽는 법.</b> 전체 커버리지에서 제안({mc_stat('proposed', 'coverage', 100)} %)과 무작위({mc_stat('random', 'coverage', 100)} %)의 차이는 무작위의 표준편차 안팎이다 — "
        "30×30 m 에 장애물이 적은 이 세계에서는 무작위 목표도 멀리 흩어져 잘 덮는다. 제안이 분명히 앞서는 것은 <b>분산</b>(시드마다 고르게)과 <b>정보/에너지</b>, 그리고 목적함수에 넣은 관심구역이다. "
        f"프런티어는 가까운 경계만 쫓아 짧게 오가며 회전이 많아 에너지({mc_stat('frontier', 'energy_Wh')} Wh)가 가장 컸다. "
        "<b>이 결론이 깨지는 조건</b>: 더 넓거나 복잡한(막다른 길이 많은) 세계, 다른 λ. 세계 한 종류·시드 5개의 결과다.</p>")
# 6.4 재방문
revs = [(i, MS[i]["kpi"]["revisit_share"]) for i in MS if MS[i]]
nrev = sum(1 for _, r in revs if r > 0)
add("<h3>6.4 재방문이 왜 드문가 (부정 결과)</h3>")
add(f"<p>30 시나리오 중 REVISIT·OBSERVE 가 한 번이라도 선택된 것은 <b>{nrev}개</b>. 이유: LIO 가 성한 동안 한 번 지나간 셀은 σ 2–4 cm 로 목표 아래에 들어가, 재방문 IG 가 이동 비용(λ<sub>T</sub>·T)보다 작다. "
    "관심구역을 2 cm 로 조여도 한 번의 통과로 대부분 채워졌다(T07). 재방문 가치가 생기려면 σ 가 남아야 한다 — 먼지(P01), 자세 불확실(LIO 퇴화), 변화(동적 물체). "
    "이 결과는 지도 σ 과소평가(단점 표)와 겹쳐 있어, 실측 σ 보정 전에는 '재방문이 필요 없다' 는 결론으로 읽으면 안 된다.</p>")
# 6.5 고장
add("<h3>6.5 고장 대응 — 탐지 → 격리 → 성능저하 → 복구/정지</h3>")
rows = []
for i in ("F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F09", "T08", "P08"):
    mt = MS.get(i)
    if not mt:
        continue
    ev = mt["events"]
    def first(kind):
        e = [x for x in ev if x["kind"] == kind]
        return f"{e[0]['t']:.1f} s" if e else "-"
    tl = [a for _, a, _ in mt["timeline"]]
    rows.append([i, SCENARIOS[i]["title"].replace("고장: ", ""), first("detect"), first("isolate"), first("degrade"), first("recover"),
                 ", ".join(sorted(set(tl) - {"EXPLORE", "HOLD"}))[:40], pct(mt["kpi"]["coverage"])])
add(T(rows, ["ID", "고장", "탐지", "격리", "성능저하", "복구", "나온 안전 행동", "커버리지"], "small"))
add(T([
    ["LiDAR 끊김", "0.3 s 무프레임 → 건강 0", "지도 갱신 중지", "지나온 길로 0.2 m/s 귀환", "프레임 복귀 시 탐사 재개"],
    ["IMU 드리프트", "EKF 편향 |b̂| > 0.6°/s", "자이로 배제", "엔코더 요율 + LIO", "LIO 가 요를 계속 보정"],
    ["엔코더 고장", "짝 바퀴 대비 <20 %, 1 s", "짝 바퀴 값으로 대체(주행기록·PID)", "DEGRADED 속도 ½", "계속"],
    ["바퀴 슬립", "엔코더↔LIO 1 s 변위, ŝ>0.45", "Q 팽창", "후진 + 반경 1.6 m 비용↑ + 5 s 불응기", "다른 길"],
    ["카메라 고장", "프레임 시각 끊김", "영상 채널 배제", "지도·정책은 LiDAR 로", "-"],
    ["GNSS 상실", "고정 없음", "GNSS 갱신 중단", "LIO+IMU+엔코더", "재고정 후 게이트 통과 시 보정"],
    ["통신 지연/끊김", "링크 나이", "영상 중단", "정보밀도 높은 타일만", "30 s 두절 → 귀환"],
    ["저장 한계", "사용률", "-", "85 % DEGRADED", "98 % → 귀환"],
    ["배터리 부족", "귀환 필요+8 % 미만", "-", "귀환", "5 % → EMERGENCY"],
], ["고장", "탐지", "격리", "성능저하", "복구/정지"], "small"))
# 6.6 모델 검사표
add("<h3>6.6 모델 검사 표</h3>")
add(T([
    ["결정 커널 호스트 검사", "21/21 통과", "결정 표·결정성·이벤트. 정책의 '행동'만 잰다 — 타이밍 아님"],
    ["C 커널 freestanding", "-ffreestanding -Werror 통과, .text 9.3 KB", "호스트 x86 기준. ARM 크기는 다를 수 있다"],
    ["슬립 추정 대조", "첫 판 0.21 vs 참 0.04 → 1 s 창·LIO 품질 게이트로 수정", "독립 대조(참값)를 붙이자 오차가 드러났다"],
    ["지형 위험 대조", "첫 판 지도 42 % 치명 → σ 를 뺀 계단으로 수정", "먼 셀 잡음이 가짜 계단이 됐다"],
    ["EKF 일관성 (참값 대조)", "첫 판: 진흙에서 σ 0.9 cm 인데 실제 오차 3.3 m (T05 ATE 1.46 m) → 3회 연속 게이트 기각 = 발산으로 보고 공분산 팽창, 슬립 관측 불가 시 주행거리 20 % 의심 → ATE 8.3 cm", "참값을 대조로 붙였기에 잡혔다. 실기에는 참값이 없다 — NIS 연속 기각 감시가 그 대신이다"],
    ["지형 위험의 벽 팽창", "첫 판: 0.5 m 경사창이 벽 계단을 번지게 하고 계단을 양쪽 셀에 매겨 벽마다 ~0.4 m 치명 → 1.2 m 틈도 계획상 막힘 → 높은 셀에만·45° 넘는 기울기는 경사에서 제외", "통로 폭 쓸기(§6.7)로 통과 한계를 다시 쟀다"],
    ["교착", "벽에 붙은 탐사 목표로 가서 정지가 영원히 이어짐 → 목표는 팽창 치명대 밖, 정지 두 번 풀어도 그대로면 뒤쪽 위험을 보며 0.5 m 탈출", "P06 첫 판 커버리지 33 %"],
    ["에너지 압력 과대", "배터리 여유 30 % 부터 귀환 효용이 올라 14 % 출발 시 2.4 m 만 주행 → 12 % 부터로", "F09 재실행"],
    ["배터리 비율 정의", "첫 판 (SOC-0.05)/0.90 → 만충이 1.055 로 잘려 처음 7 Wh 동안 100 % 로 보임(영상에서 발견) → 가용 85 % 창 (SOC-0.15)/0.85", "spec.E_WH 와 같은 창으로 맞춤"],
    ["배터리 귀환 걸쇠", "귀환 guard 에 +5 % 이력(SAFE_RETURN 동안) — 집에 가까워질수록 필요 에너지가 줄어 guard 가 풀리던 설계 결함을 막음", "F09: 70.7 s 귀환 시작, 133.9 s 기지 도착, 잔량 7.2 %"],
    ["에너지 수지", "모터 모델 적분", "같은 식의 적분이라 구현 검사일 뿐"],
    ["LiDAR 사각 반경", "기하 계산 0.47 m ↔ 시뮬 첫 지면 고리", "정의상 일치(같은 기하)"],
], ["검사", "결과", "해석"], "small"))
GAP = json.loads((OUT / "gap.json").read_text()) if (OUT / "gap.json").exists() else []
if GAP:
    add("<h3>6.7 통로 폭 쓸기 — 어디서 뒤집히나</h3>")
    gs = sorted(set(g["gap"] for g in GAP))
    add(T([[f"{g:.1f} m", f"{sum(x['passed'] for x in GAP if x['gap'] == g)}/{sum(1 for x in GAP if x['gap'] == g)}",
             ", ".join(f"{x['t_pass']:.0f} s" for x in GAP if x['gap'] == g and x['passed']) or "-",
             f"{sum(x['collisions'] for x in GAP if x['gap'] == g)}"] for g in gs], ["틈 폭", "통과(시드)", "통과 시각", "충돌"], "small"))
    add("<p>로버 전폭 0.44 m. <b>계획기 여유가 원인이 아니다</b> — 깨끗한 합성 지도에서는 계획기가 0.8 m 틈도 연다(tests/test_recon.py). "
        "실제 시뮬에서 막은 것은 2.5D 지도의 벽 번짐(수직면 점이 이웃 셀을 높인다)과 그 셀을 읽는 전방 위험 판정이다. 첫 판 보고서는 이것을 '계획 여유' 라고 검사 없이 적었다. "
        "대책: 벽 셀을 복셀 층으로 분리하거나, 번짐 구역에서는 지면 추정기를 쓴다.</p>")
add("</section>")

# ------------------------------------------------------------------ 대책
add("<section><h2>7. 대책 — 약점마다</h2>")
add(T([
    ["σ 과소평가", "소프트웨어", "프레임 간 상관을 넣은 지도(자세 표류 공분산 유지) 또는 σ 하한 1 cm; TEST-07 반복 관측으로 보정"],
    ["벽 번짐", "소프트웨어", "수직 구조 셀은 복셀 층으로 분리, 번짐 구역은 '가장 높은 값' 대신 지면 추정기"],
    ["IG 가 가림 무시", "소프트웨어", "상위 후보 10개만 광선 추적 IG 로 재평가(Jetson GPU)"],
    ["Mid-360 단종", "부품", "Mid-360S 로 교체, 장착·전원 동일 [조각]"],
    ["모터 전압 불일치", "부품", "12 V 권선(#4753) — 정격 속도·토크 회복, 스톨 전류↑ → 드라이버 여유 확인"],
    ["무선 킬 신뢰", "회로", "하트비트형 수신기 + MCU 워치독 + 유선 E-stop 3중 직렬"],
    ["동적 장애물 늦은 반응", "소프트웨어", "점 군집 추적(칼만 등속)으로 1.5 s 앞 위치를 위험지도에 칠하고, 사람 크기 군집 1.5 m 안이면 SAFE_STOP. TEST-03 에 가로지르는 사람 모형 추가"],
    ["재방문 시연 약함", "운용", "임무 설정에 관심구역 σ 를 명시; 열화 뒤 재방문 시험(P01)을 TEST-07 에 포함"],
], ["약점", "구분", "대책"], "small"))
add("</section>")

# ------------------------------------------------------------------ 실험 청사진
add("<section><h2>8. 실험·검증 청사진 — TEST-01 ~ TEST-08 (Step 11)</h2>")
add("<p>모든 시험의 공통 준비: 참값 장비 — 토탈스테이션 또는 RTK 기준점(위치 ±2 cm), 지상 LiDAR 스캔 또는 사진측량(지형 참값 ±1 cm), 전류 기록(INA226 1 kHz). 각 시험 3회 이상, 원시 로그(mcap) 보관. "
    "<b>교체하는 모델 파라미터</b> 칸은 그 시험이 끝나면 시뮬의 가정값 [A] 을 실측 [M] 으로 바꾸는 자리다.</p>")
tests = [
    ["TEST-01 평지", "20×20 m 아스팔트/운동장, 기준점 4개", "고정 경로 50 m + 탐사 5 분", "ATE < 5 cm · 고도 RMSE < 3 cm · 구동 전력", "C<sub>rr</sub>, 구동 평균 W, 시계 오프셋"],
    ["TEST-02 요철", "±10 cm 요철 + 돌 10개", "탐사 10 분", "커버리지 ≥80 % · 전복·걸림 0", "계단 한계 5 cm, 기울기 위험 곡선"],
    ["TEST-03 장애물", "상자·기둥 7개, 폭 0.9 m 틈", "탐사, 속도 3단", "충돌 0 · AVOID 후 재계획 성공률 ≥95 %", "위험 임계 0.6/0.92"],
    ["TEST-04 무른 지반", "모래 5×10 m", "직진·회전 각 10회", "ŝ 오차 < 0.1 · 요 효율 χ 측정", "χ, s<sub>terr</sub>(모래)"],
    ["TEST-05 슬립 지도 왜곡", "진흙/젖은 잔디 + 기준점", "같은 로그로 F1–F4 재처리", "유령 셀 F4 ≤ F3 · 위치 오차 표", "Q 슬립 계수, NIS 게이트"],
    ["TEST-06 미지 환경", "처음 보는 30×30 m 현장", "4 방법 × 3 회 교대", "커버리지·정보/Wh 표, 안전 개입 수", "λ<sub>E</sub>, λ<sub>T</sub>, λ<sub>R</sub>, U<sub>0</sub>"],
    ["TEST-07 반복 관측", "같은 구역 5 회 통과 + 정지 스캔", "σ 예측 vs 실제 오차 분포", "실제 |오차| 의 68 % 가 σ 안 (보정)", "σ<sub>att</sub>, 셀 상관 계수"],
    ["TEST-08 센서 열화", "분무기 먼지/물, 커넥터 뽑기, 자이로 가열", "고장 9종 주입", "탐지 < 1 s · 잘못된 격리 0 · 안전 정지 보장", "건강 임계, 태그 비율"],
]
add(T(tests, ["시험", "설정", "절차", "합격 기준", "교체하는 모델 파라미터"], "small"))
add("<h3>측정 기록지 (시험마다 한 장)</h3>")
add(T([["날짜·장소·기상", "", "펌웨어/소프트웨어 해시", ""], ["배터리 시작/끝 V", "", "시계 오프셋 (ms)", ""], ["주행 거리·시간", "", "에너지 (Wh)", ""],
       ["ATE / 고도 RMSE", "", "커버리지 / 관심구역", ""], ["안전 개입 (종류·시각)", "", "고장 주입 (종류·시각)", ""], ["합격 여부", "", "교체한 파라미터", ""]], None, "small"))
add("<h3>KPI 정의 (Step 12)</h3>")
add(T([
    ["커버리지", "σ<5 cm 셀 / 임무 구역(벽 제외) 셀", "%"], ["관심구역 달성", "σ<σ<sub>t</sub> 셀 / 관심구역 셀", "%"],
    ["고도 RMSE", "지면 셀(수직 구조 ±0.2 m 제외) 추정-참", "cm"], ["edge RMSE", "수직 구조 ±0.2 m 셀", "cm"],
    ["ATE / RPE", "위치 RMSE / 1 m 당 상대오차", "cm / %"], ["정보", "Σ ½log₂(σ²<sub>전</sub>/σ²<sub>후</sub>)", "kbit"],
    ["정보/에너지 · 정보/바이트", "정보 ÷ Wh · 정보 ÷ 전송 kB", "kbit/Wh · kbit/kB"], ["데이터율", "원시 기록 · 하향 링크", "MB/s · kB/s"],
    ["재방문율", "REVISIT+OBSERVE 시간 비율", "%"], ["불확실도 감소", "평균 σ 시작→끝", "cm"], ["안전", "충돌 · 전복 · 안전 개입 수", "회"],
], ["KPI", "정의", "단위"], "small"))
add("<h3>데모 화면 (영상 30 편과 같은 화면)</h3><p>실시간 카메라(IMX219 시점) · 로버 자세(참: 흰 궤적, 추정: 주황 고리 = 2σ) · 3D 고도지도(색 = σ) + 현재 LiDAR 점 · 위에서 본 불확실도 지도 · "
    "정책 상태(BT 제안 → 중재 → 안전필터 → 행동, 안전 상태, J 막대 3) · 센서 건강 5 · 배터리(%, V, W, Wh, 귀환 필요) · 데이터율(원시·하향·압축비·링크·저장) · 대응 절차(탐지·격리·성능저하·복구/정지 점등)와 사건 기록.</p>")
if (paths.VIDEO / "stills").exists():
    for f in sorted((paths.VIDEO / "stills").glob("P09_*.png"))[:1]:
        add(kit.fig(f, "데모 화면 한 장 (P09 종합 임무).", "100%"))
add("</section>")

# ------------------------------------------------------------------ 비용 일정
add("<section><h2>9. 제작 방법 — 비용과 일정</h2>")
add(T([
    ["1주", "부품 발주(데이터시트 대조 후), 프레임 가공", "BOM 확정표"], ["2주", "기구 조립(A-001 1–2), 전원 버스(3–4), 안전 체인 시험", "E-stop 차단 실측"],
    ["3주", "MCU 펌웨어: PWM·엔코더·IMU·PID·워치독; fw 커널 크로스빌드", "바퀴 속도 계단응답, 커널 타이밍"],
    ["4주", "Jetson: 드라이버·PTP·LIO·고도지도 노드; 링크 프로토콜", "시계 오프셋 <1 ms"], ["5주", "TEST-01·02·03", "모델 파라미터 1차 교체"],
    ["6주", "TEST-04·05 (슬립), 필터 조정", "χ·s 실측"], ["7주", "TEST-06·07 (탐사·반복 관측), λ 조정", "기준선 비교 실측"], ["8주", "TEST-08 (고장 주입), 보고서 rev B", "실측판 청사진"],
], ["주", "작업", "산출물·합격"], "small"))
add(f"<p>예상 비용: 부품 약 <b>$2,540–2,830</b>(§3.2), 참값 장비 대여·현장 별도. 한 사람 기준 8 주 [A].</p></section>")

# ------------------------------------------------------------------ 응용
add("<section><h2>10. 응용 — 맞는 곳과 맞지 않는 곳</h2>")
add(T([["맞는 곳", "재난 현장 사전 지형 조사, 건설 현장 진척 측량, 농경지·과수원 지면 조사, 시설 순찰 기록, 교육·연구용 탐사 플랫폼"],
       ["맞지 않는 곳", "계단·다층 건물(2.5D·스키드), 30 cm 이상 장애물, 물웅덩이·깊은 진흙, 폭우(LiDAR·방수 미설계), 장거리 BVLOS(통신·규제)"]], ["구분", "분야"]))
add("<h3>루테늄 Ni–H<sub>2</sub> 배터리(RuH2-P1)를 여기에 쓸 수 있나</h3><p>SE 저장소의 RuH2 작업(ruh2/knowledge.md)을 참고했다. 그 프로토타입은 1 Ah·1.25 V 셀로 <b>에너지 밀도가 수 Wh/kg 수준</b>이고 316L 압력용기가 무게의 대부분이다. "
    f"이 로버는 {spec.E_WH:.0f} Wh 가 필요하므로 주 전원으로는 맞지 않는다(무게 수십 kg). 맞을 수 있는 자리는 <b>기지국 고정형 저장</b>(수만 사이클·안전성) 쪽이다. 이 판단은 RuH2 모델 출력에 기댄 것이고 실측이 아니다.</p></section>")

# ------------------------------------------------------------------ 증명
add("<section><h2>11. 증명한 것과 못 한 것 (가정과 실험 필요 구분)</h2><div class='two'><div><h3>이 작업에서 확인한 것 [C]</h3><ul>"
    "<li>SE fw 커널을 한 줄도 안 고치고 로버 정책 프로파일로 재사용 — 컴파일·호스트 검사 21개·결정성</li>"
    "<li>폐루프(센서→추정→지도→증거→C 결정→유도→PID→모터→물리) 30 시나리오가 끝까지 돈다</li>"
    "<li>모델 안에서: 뒤집은 LiDAR 의 사각 반경, 슬립 시 엔코더 지도의 붕괴와 LIO 의 복구, 고장 9종의 탐지→격리→저하→복구 경로</li>"
    "<li>버그 열한 개를 대조로 잡아 고쳤다(슬립 추정, 가짜 계단, 기동 잠금, 발밑 사각, 먼지, 완료 래치, EKF 과신·발산, 벽 팽창, 교착, 에너지 압력, 배터리 비율) — §6.6</li></ul></div>"
    "<div><h3>못 한 것 — 실험으로 확인해야 한다</h3><ul>"
    "<li>모든 부품 사양 (데이터시트 미열람) · 뒤집은 Mid-360 장착 허용 · Orin 하드웨어 PTP</li>"
    "<li>실제 LIO 성능, 슬립·요 효율 χ, 구동 전력, 지도 σ 보정 (TEST-01·04·05·07)</li>"
    "<li>ARM 크로스빌드·실시간 타이밍·스택 (SE fw/HW_BRINGUP.md G2·G6)</li>"
    "<li>λ 가중치의 현장 타당성 · 기준선 우열의 통계적 유의성(시드 5)</li>"
    "<li>카메라 기반 인지·정보량 — 모델에 없음</li></ul></div></div></section>")

# ------------------------------------------------------------------ 부록
add("<section><h2>부록 A. 요구 항목 ↔ 절 대응</h2>")
add(T([
    ["Step 1 시스템 구조(층별 I/O·주기·계산·메모리)", "§3.1"], ["Step 2 실구매 BOM·데이터시트 사양", "§3.2, 부록 B"], ["Step 3 최소/확장 센서 세트(11 항목)", "§3.3"],
    ["Step 4 원시 스키마·시각 동기", "§3.4, E-002"], ["Step 5 잡음 모델·필터 비교·슬립 지도 왜곡", "§2.4–2.5, §3.5, §6.2"], ["Step 6 3D 표현 비교·선정", "§3.6"],
    ["Step 7 셀 불확실도", "§2.3, §3.7"], ["Step 8 압축(정보/바이트, 오차 측정)", "§3.8"], ["Step 9 수집 정책 s·A·J(원시 데이터로 계산)", "§2.2, §3.9"],
    ["Step 10 비LLM executive 7단", "§3.10"], ["유도·제어·구동 분리", "그림 decision_arch, §4.1"], ["기구·전기·계산·펌웨어·SW 제작", "§4, 도면 6장"],
    ["TEST-01~08 · KPI", "§8"], ["기준선 4종 같은 조건", "§6.3"], ["데모 화면", "§8 끝, 영상 30편"], ["고장 9종 대응", "§6.5"], ["BOM 비용·일정", "§3.2, §9"],
    ["가정 vs 실험 필요 구분", "§11, 표지"], ["3D 렌더 · 주행 시뮬 영상 30 · 회로도", "§3, 부록 C"],
], ["요구", "절"], "small"))
add("<h2>부록 B. 영상 30 편</h2>")
add(T([[i, sc["title"], sc["what"][:40], sc["how"][:70]] for i, sc in SCENARIOS.items()], ["파일", "제목", "상황", "대응 방법"], "small"))
add("<h2>부록 C. 실행 방법 (SE 저장소 recon/, 산출물은 inbox/recon/)</h2><pre>python3 -m recon.make 커널            # SE fw 커널 + recon 프로파일 빌드 · 결정 검사 · 크기\n"
    "python3 -m recon.make 시뮬 T01         # 한 시나리오 (전부: 시뮬 전부)\n"
    "python3 -m recon.make 분석             # 몬테카를로 · 필터 · 통로 폭\n"
    "python3 -m recon.make 영상 T01         # 1분 MP4 (전부: 영상 전부)\n"
    "python3 -m recon.make 도면 | 3D | 그림 | 보고서 | 웹\n"
    "봇 도구: recon_rover(무엇=…) · recon_make(산출물=…)</pre>")
add("<h2>참고문헌</h2>")
add(kit.refs([
    "Yamauchi, B. A frontier-based approach for autonomous exploration. CIRA 1997, pp.146–151. DOI 10.1109/CIRA.1997.613851 [조각]",
    "Stachniss, C., Grisetti, G., Burgard, W. Information Gain-based Exploration Using Rao-Blackwellized Particle Filters. RSS 2005. DOI 10.15607/RSS.2005.I.009 [조각]",
    "Bircher, A. et al. Receding horizon next-best-view planner for 3D exploration. ICRA 2016, pp.1462–1468. DOI 10.1109/ICRA.2016.7487281 [조각] (공식 저장소 README 인용 블록 확인)",
    "Fankhauser, P. et al. Robot-Centric Elevation Mapping with Uncertainty Estimates. CLAWAR 2014. DOI 10.3929/ethz-a-010173654 [조각] (README 인용 확인)",
    "Fankhauser, P., Bloesch, M., Hutter, M. Probabilistic Terrain Mapping for Mobile Robots with Uncertain Localization. RA-L 3(4), 2018. DOI 10.1109/LRA.2018.2849506 [조각] (README 인용 확인)",
    "Miki, T. et al. Elevation Mapping for Locomotion and Navigation using GPU. IROS 2022. arXiv 2204.12876 [조각] (README 인용 확인)",
    "Xu, W. et al. FAST-LIO2: Fast Direct LiDAR-Inertial Odometry. IEEE T-RO 2022. arXiv 2107.06829 [조각]",
    "Shan, T. et al. LIO-SAM. IROS 2020, pp.5135–5142. arXiv 2007.00258 [조각]",
    "Hornung, A. et al. OctoMap. Autonomous Robots 34:189–206, 2013. DOI 10.1007/s10514-012-9321-0 [조각]",
    "Oleynikova, H. et al. Voxblox. IROS 2017. arXiv 1611.03631 [조각]",
    "Dang, T. et al. Graph-based subterranean exploration path planning using aerial and legged robots. JFR 37(8):1363–1388, 2020 [조각] (DOI 미확인)",
    "Cao, C., Zhu, H., Choset, H., Zhang, J. TARE. RSS 2021. DOI 10.15607/RSS.2021.XVII.018 [조각]",
    "Tranzatto, M. et al. CERBERUS in the DARPA Subterranean Challenge. Science Robotics 2022. DOI 10.1126/scirobotics.abp9742 [조각]",
    "Yi, J. et al. IMU-based localization and slip estimation for skid-steered mobile robots. IROS 2007 [조각] (DOI 미확인)",
    "Yi, J. et al. Kinematic Modeling and Analysis of Skid-Steered Mobile Robots With Applications to Low-Cost Inertial-Measurement-Unit-Based Motion Estimation. IEEE T-RO 2009. DOI 10.1109/TRO.2009.2026506 [조각]",
    "Mandow, A. et al. Experimental kinematics for wheeled skid-steer mobile robots. IROS 2007 [조각] (다른 논문의 참고문헌으로만 봄)",
    "Livox Mid-360 사양(점률·FOV·거리·전력·질량) — 검색 조각, 데이터시트 미열람 [조각]",
    "NVIDIA Jetson Orin Nano Super Developer Kit (전력 모드, DC 잭 9–20 V) — 검색 조각 [조각]",
    "Pololu 37D 50:1 24 V 기어모터 64 CPR (#4693) — 검색 조각 [조각]",
    "SE 저장소 fw/ (POLICY_TOOLKIT.md, HW_BRINGUP.md, profile_min.c) — 이 작업에서 직접 읽음 [전문]",
    "SE 저장소 ruh2/knowledge.md (RuH2-P1 Ni–H2 배터리 작업 기록) — 직접 읽음 [전문]",
]))
add("</section>")

if __name__ == "__main__":
    kit.reset()
    html = "".join(body)
    paths.ensure()
    r = kit.build_html(html, paths.REPORT / "RECON-R1_blueprint.pdf", "RECON-R1 설계·검증 청사진", strict=True, footer="RECON-R1 청사진 rev A — 설계 제안, 미검증")
    print(json.dumps({k: v for k, v in r.items() if k != "html"}, ensure_ascii=False, indent=1))
