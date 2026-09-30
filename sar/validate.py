#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""모델 검증(Level 2) — 자기채점을 벗어난다. 각 물리모델을 **독립 referent** 와 맞춰 오차를 잰다.

NASA 식(SE Handbook · NASA-STD-7009): validation 은 '실제 임무 전체를 해보는 것'이 아니다.
현실을 부품으로 나눠 **측정 가능한 부분을 독립 referent 로 검증**하고, 그 검증된 모델로
불가능한 조건을 시뮬한다. 그래서 증거를 세 층으로 나눈다:

  Level 1 VERIFICATION      코드가 설계(수식)대로 도는가            — 여기서 잰다
  Level 2 MODEL VALIDATION  모델이 현실(referent)을 대표하는가      — referent 있으면 재고, 없으면 GAP 로 명시
  Level 3 OPERATIONAL       시스템이 임무목적을 달성하는가          — 현장/HIL, 지금은 미확보

이 파일은 **있는 referent 로는 실제 오차를 재고, 없는 referent 는 '어떤 실험이 필요한지'를
정확히 적는다.** '없다'를 숨기지 않는 것이 핵심(가장 부족한 곳이 어디인지 드러낸다)."""
import math
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import radar


# ── Level 2 증거 1: SAR 해상도 ↔ 회절한계 식 (독립 해석 referent) ──────────────────
def _fit_law(x, y):
    """y = k·x 로 원점 통과 최소자승 + 결정계수 R²(법칙을 얼마나 따르나)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    k = float((x*y).sum() / (x*x).sum())
    ss_res = float(((y - k*x)**2).sum()); ss_tot = float(((y - y.mean())**2).sum())
    r2 = 1.0 - ss_res/ss_tot if ss_tot > 0 else 1.0
    return k, r2


def sar_resolution_evidence(cfg=None):
    """SAR 백프로젝션 초점폭(측정)이 **회절 척도법칙**(내 코드와 독립한 해석 referent)을 따르나.

    referent: 방위 δa ∝ λR/2L_sa, 거리 δr ∝ c/2B (1차원리). **절대상수를 억지로 맞추지 않고**,
    측정이 그 척도(1/L, 1/B)를 따르는지를 본다 — 원점통과 최소자승의 R²(법칙 적합)와 비례상수 k.
    R²≈1 이면 imaging 모델이 회절법칙을 재현하는 것(부분 validation). k 는 창·정의 차이의 구현상수다.

    **유효 동작점만**: 표적 경사거리가 비모호 거리 안이어야 함(넘으면 접혀 무효 — 과장방지).
    """
    alt = 120.0; inc = math.radians(55.0); Rg = alt*math.tan(inc); R = math.hypot(Rg, alt)
    az_x = []; az_y = []; az_rows = []
    for Ti in (0.35, 0.45, 0.55, 0.7):
        c = radar.RadarCfg(Ti=Ti); np.random.seed(0)
        img, ext, _ = radar.sar_image(c, np.array([[0.0, Rg]]), np.array([1.0]), np.array([0.0, 0.0]), np.array([0.0, Rg]), 0.0, alt, half=6.0, npx=161)
        wx, _ = radar._measure_spot(img, ext, 161)
        law = c.lam * R / (2 * c.L_sa)                       # 척도량 λR/2L
        az_x.append(law); az_y.append(wx); az_rows.append(("방위 (L_sa=%.1fm)" % c.L_sa, law, wx))
    rg_x = []; rg_y = []; rg_rows = []
    for B in (45e6, 60e6, 75e6, 90e6):
        c = radar.RadarCfg(B=B)
        if c.unambiguous_range <= R + 5:                     # 비모호 거리 밖이면 접힘 → 제외
            continue
        np.random.seed(0)
        trk = radar.track(c, np.array([0.0, 0.0]), 0.0)
        s = radar.synth_raw(c, np.array([[0.0, Rg]]), np.array([1.0]), trk, alt)
        # 거리 -3dB 를 정확히 재려고 fast-time FFT 를 4× 제로패딩(해상도는 그대로, 격자만 촘촘)
        pad = 4; row = s[trk.shape[0]//2, :] * np.hanning(c.n_fast)
        RC = np.abs(np.fft.fft(row, n=c.n_fast*pad))
        freqs = np.fft.fftfreq(c.n_fast*pad, d=c.Tp/c.n_fast); kf = 2*c.B/(radar.C*c.Tp)
        rng = freqs/kf; keep = rng >= 0; RC = RC[keep]; rng = rng[keep]
        pdb = 20*np.log10(RC/RC.max() + 1e-9)
        w = float((pdb >= -3.0).sum() * (rng[1]-rng[0]))     # 1D 경사거리 -3dB 폭(촘촘한 격자)
        law = c.range_res                                    # 척도량 c/2B (경사)
        rg_x.append(law); rg_y.append(w); rg_rows.append(("거리 (B=%.0fMHz)" % (B/1e6), law, w))
    k_az, r2_az = _fit_law(az_x, az_y)
    k_rg, r2_rg = _fit_law(rg_x, rg_y)
    return dict(az_rows=az_rows, rg_rows=rg_rows, k_az=k_az, r2_az=r2_az, k_rg=k_rg, r2_rg=r2_rg,
                az_x=az_x, az_y=az_y, rg_x=rg_x, rg_y=rg_y)


# ── 모델별 신뢰성 기록(NASA-STD-7009 관점) — 정직하게 채운다 ──────────────────────
# 각 항목: 모델, referent(있음/종류), Level1 검증, Level2 검증상태, 입력혈통, 불확실도, GAP·필요실험
SCORECARD = [
    dict(model="지형 기하 (DEM)",
         referent="실측 표고 (AWS Terrarium ← SRTM/ASTER 측량)",
         L1="좌표변환·경사 검사됨", L2="입력이 실측 데이터 자체(재측정은 안 함)",
         pedigree="높음 — 공개 측량 산출물", uncertainty="타일 수직오차 ~10m(문헌)",
         gap="이 좌표의 실측 대조는 안 함. 표고 정확도는 데이터 제공자 문서에 의존."),
    dict(model="안개 소광 (Koschmieder β=3.912/V)",
         referent="WMO/ICAO 기상시정 정의 (표준)",
         L1="식 그대로 구현·검사", L2="β↔V 관계는 표준정의(강). **탐지확률↔β 는 미검증**",
         pedigree="높음 — 국제표준 관계식", uncertainty="탐지 임계는 미측정",
         gap="**최대 GAP**: 실제 안개챔버 카메라 영상 ↔ 렌더 투과율 대조 필요(RMSE 측정)."),
    dict(model="대기 투과 (Beer-Lambert)",
         referent="물리법칙 (지수감쇠)",
         L1="식 구현 검사", L2="법칙 자체는 확립. 계수→실영상 대응은 미검증",
         pedigree="높음 — 물리법칙", uncertainty="산란상(mie) 근사 미포함",
         gap="실 안개/연기 영상으로 계수 보정 필요."),
    dict(model="FMCW-SAR 영상 (백프로젝션)",
         referent="회절한계 해석식 δa=λR/2L, δr=c/2B (구현과 독립)",
         L1="**측정 초점 ↔ 식 대조(이 파일이 계산)** — 강한 verification",
         L2="**실 SAR 데이터셋(예 Sandia/UAVSAR)과는 미대조**",
         pedigree="중 — 파라미터는 문헌 대역", uncertainty="클러터·모션보상 단순화",
         gap="실 SAR raw/영상과 대조해야 imaging 모델 validation. 지금은 이론 대조까지."),
    dict(model="관성 드리프트 (랜덤워크 σ=½b t²)",
         referent="공개 MEMS IMU 스펙(바이어스 안정도)",
         L1="적분식 검사", L2="A_BIAS=0.02 m/s² 를 문헌 스펙대와 비교(혈통), 실 로그 미대조",
         pedigree="중 — 소비자/전술 MEMS 대역", uncertainty="온도·진동 의존 미모델",
         gap="실 IMU 로그의 Allan 분산으로 검증 필요."),
    dict(model="사람 탐지 (YuNet 대역)",
         referent="없음 — 지상사진·얼굴탐지를 대리로 씀",
         L1="파이프라인(탐지→belief) 검사", L2="**미검증** — SAR용 항공·열화상 탐지기 아님",
         pedigree="낮음 — 대리물", uncertainty="현장 도메인 갭 큼",
         gap="항공+열화상 프레임 + SAR-학습 탐지기의 실 성능 필요."),
    dict(model="능동탐색 정책 (policy_core)",
         referent="Level 3 (운용) — 없음",
         L1="상태전이·커버리지·수렴 검사됨(host_test)", L2="모델 내부 행동만 확인",
         pedigree="해당 없음", uncertainty="모델 조건부 성능",
         gap="검증된 모델 + HIL + 대표 운용 시나리오에서 임무목적 달성 확인 필요."),
]

HONEST = ("We do not claim the simulated mission is field-validated. The current system provides "
          "verified software behavior (Level 1) and model-internal performance analysis. Operational "
          "validation is established incrementally by comparing each critical model component against "
          "independent physical referents (Level 2), followed by integrated/HIL testing under "
          "representative operational conditions (Level 3).")


def report_md():
    ev = sar_resolution_evidence()
    L = []
    L.append("# 모델 검증 보고 (V&V 3계층) — 자기채점을 벗어난다")
    L.append("")
    L.append("> " + HONEST)
    L.append("")
    L.append("## Level 1 — VERIFICATION (코드가 설계대로)")
    L.append("- SAR 해상도식·gradient·좌표변환·정책 상태전이·커버리지 계산이 검사로 붙들려 있다"
             "(tests/test_radar·test_sar_bot 등).")
    L.append("")
    L.append("## Level 2 — MODEL VALIDATION (모델 ↔ 독립 referent)")
    L.append("### 잰 것: SAR 초점폭이 회절 **척도법칙**을 따르나 (해석식 = 구현과 독립한 referent)")
    L.append("절대상수를 억지로 맞추지 않는다. 측정 초점이 λR/2L·(1/L)·(c/2B·1/B) 척도를 따르는지를 본다:")
    L.append("| 축 | 척도법칙(referent) | 적합 R² | 구현 비례상수 k | 유효 동작점 |")
    L.append("|---|---|---|---|---|")
    L.append("| 방위 | δa ∝ λR/2L_sa | **%.3f** | %.2f | %d점(비모호 내) |" % (ev["r2_az"], ev["k_az"], len(ev["az_rows"])))
    L.append("| 거리 | δr ∝ c/2B (경사) | **%.3f** | %.2f | %d점(비모호 내) |" % (ev["r2_rg"], ev["k_rg"], len(ev["rg_rows"])))
    L.append("")
    L.append("- R²≈1 이면 imaging 모델이 **회절 척도법칙을 재현**한다 → 해석 referent 에 대한 **부분 validation(verification)**.")
    L.append("- 비례상수 k 는 창(해닝)·해상도 정의(−3dB vs Rayleigh) 차이의 구현상수다. **k≠1 을 '오차 없음'으로 포장하지 않는다** — "
             "절대 척도 보정은 문서화된 하위 GAP.")
    L.append("- **접힌 동작점은 뺐다**: B=120MHz 는 비모호 거리(160m) < 표적 경사거리(209m) 라 접힘 → 무효(과장방지).")
    L.append("- **여전히 GAP**: 실 SAR 데이터셋(Sandia/UAVSAR)과의 대조는 안 함. 지금은 이론 척도까지.")
    L.append("")
    L.append("### 신뢰성 기록표 (NASA-STD-7009 관점) — GAP 을 숨기지 않는다")
    L.append("| 모델 | 독립 referent | Level1 | Level2 상태 | 입력혈통 | 필요 실험(GAP) |")
    L.append("|---|---|---|---|---|---|")
    for s in SCORECARD:
        L.append("| %s | %s | %s | %s | %s | %s |" %
                 (s["model"], s["referent"], s["L1"], s["L2"], s["pedigree"], s["gap"]))
    L.append("")
    L.append("## Level 3 — OPERATIONAL VALIDATION")
    L.append("- 검증된 모델을 합쳐 HIL/대표 운용환경에서 대표 운용자와 임무목적 달성 확인 — **미확보**.")
    L.append("")
    L.append("## 다음 단계(가치 순) — 현장비행보다 먼저")
    L.append("1. 실 안개 영상 → 안개/투과 모델 validation(RMSE)  2. 실 SAR 데이터 → imaging 모델 validation")
    L.append("3. 실 IMU/GNSS 로그 → 항법 모델 validation(Allan)  4. 셋을 합친 HIL/대표환경 시험")
    L.append("→ 그러면 '모델이 맞다고 가정하면 성공' 이 '모델 오차를 재고 그 위에서 정책을 평가' 로 바뀐다.")
    return "\n".join(L) + "\n", ev


def render(path, ev=None):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.font_manager as fm
    for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",):
        if os.path.exists(_c): fm.fontManager.addfont(_c); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name()
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt
    ev = ev or sar_resolution_evidence()
    fig, (axb, axl) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1.1, 1]})
    axb.scatter(ev["az_x"], ev["az_y"], c="steelblue", label="방위 측정", zorder=3)
    axb.scatter(ev["rg_x"], ev["rg_y"], c="indianred", marker="s", label="거리 측정", zorder=3)
    xmax = max(ev["az_x"] + ev["rg_x"] + [1e-6])
    xx = np.linspace(0, xmax, 20)
    axb.plot(xx, ev["k_az"]*xx, "-", color="steelblue", alpha=0.6, label="방위 적합 k=%.2f R²=%.3f" % (ev["k_az"], ev["r2_az"]))
    axb.plot(xx, ev["k_rg"]*xx, "-", color="indianred", alpha=0.6, label="거리 적합 k=%.2f R²=%.3f" % (ev["k_rg"], ev["r2_rg"]))
    axb.set_xlabel("척도법칙 λR/2L · c/2B  [m]"); axb.set_ylabel("측정 초점폭 [m]"); axb.legend(fontsize=7.5)
    axb.set_title("Level 2 증거: SAR 초점이 회절 척도법칙을 따르나\n(원점통과 적합 R²≈1 = 법칙 재현, k=구현상수)", fontsize=9.5)
    axl.axis("off")
    ladder = ["Level 3  OPERATIONAL\n  시스템↔임무목적 (현장/HIL) — 미확보",
              "Level 2  MODEL VALIDATION\n  모델↔독립 referent — SAR 이론대조 O,\n  안개·SAR실데이터·IMU 대조 = GAP",
              "Level 1  VERIFICATION\n  코드↔설계식 — 검사로 붙듦"]
    cols = ["#c62828", "#f9a825", "#2e7d32"]
    for i, (t, c) in enumerate(zip(ladder, cols)):
        axl.add_patch(plt.Rectangle((0.02, 0.7-i*0.30), 0.96, 0.24, color=c, alpha=0.18, transform=axl.transAxes))
        axl.text(0.05, 0.82-i*0.30, t, fontsize=9, va="top", transform=axl.transAxes)
    axl.text(0.02, 0.02, "자기채점 ≠ validation. referent 로 각 부품을 재고, 없는 곳은 GAP 로 명시.",
             fontsize=8, color="0.3", transform=axl.transAxes)
    axl.set_title("V&V 3계층 — 증거의 층위", fontsize=10)
    fig.tight_layout(); fig.savefig(path, dpi=110, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    import datetime
    REPO = os.path.dirname(HERE); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    md, ev = report_md()
    md_rel = "public_agent_memory/sar_validation_%s.md" % ts
    png_rel = "public_agent_memory/sar_validation_%s.png" % ts
    open(os.path.join(REPO, md_rel), "w", encoding="utf-8").write(md)
    render(os.path.join(REPO, png_rel), ev)
    print("SAR 척도법칙 적합: 방위 R²=%.3f(k=%.2f), 거리 R²=%.3f(k=%.2f)"
          % (ev["r2_az"], ev["k_az"], ev["r2_rg"], ev["k_rg"]))
    print("산출물:", md_rel)
    print("산출물:", png_rel)
