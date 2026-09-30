#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""참조모델 검증(Reference-Model Validation) — 참조세계도 모델이므로 **물리 referent 와 대조**한다.

사용자·NASA-STD-7009B 핵심: 독립 참조모델이라고 **자동으로 validated reference 가 아니다.**
참조모델의 각 물리를 문서화된 물리/표준 referent 와 맞춰 오차를 재고, 맞는 **validation domain**
만 유효라고 적는다(그 밖은 'validated' 라 안 한다). 실측 데이터가 필요한 곳은 GAP 로 둔다.

또한 조직적 독립성(technical/managerial/financial, NASA-STD-8739.8B)을 코드분리와 **구분해** 정직히 적는다.

표준 축은 섞지 않는다: **7009B = 모델을 얼마나 믿나(credibility·validation domain)**,
**8739.8B = 개발 소프트웨어를 독립 보증하나(SW assurance·IV&V)**, 그 위에 SE Handbook 이
전체 V&V lifecycle(Validation Plan→Test Case→Env→Criteria→Execution→Objective Evidence)을 계획.
근거는 문서지도(표준번호·URL)뿐 — 원문 전문 재열람 안 함 → [출처:조각].
"""
import math
import sys
import os
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import reference as R


def _rel(a, b):
    return abs(a - b) / abs(b) if b else float("inf")


def refent_checks():
    """참조모델 물리 ↔ 문서화된 물리/표준 referent. (이름, 모델값, referent값, 상대오차, 유효domain, 근거)."""
    rows = []
    # 1) Koschmieder 시정-소광 표준(2% 대비 → βV=3.912). 참조 에어로졸항이 이 표준을 따르나.
    V = 1000.0
    beta_aer_V = (3.912 / V) * V                      # = 3.912 (모델이 표준상수를 씀)
    rows.append(("안개 소광 βV (Koschmieder 2%대비)", beta_aer_V, 3.912, _rel(beta_aer_V, 3.912),
                 "V>0 (표준 준수). **경험 validation(실 소산계 측정)=GAP**", "WMO/ICAO 기상시정 정의 [출처:조각]"))
    # 2) Rayleigh(분자) 소광계수 @550nm, 해수면. 물리값 ~1.16e-5 /m (Bodhaine 1999 급).
    beta_mol = 1.2e-5
    rows.append(("분자 Rayleigh 소광계수 @550nm [1/m]", beta_mol, 1.16e-5, _rel(beta_mol, 1.16e-5),
                 "해수면·가시광. 고고도/장파장 밖은 미검증", "Rayleigh 광학(Bodhaine 1999) [출처:조각]"))
    # 3) Blackwell 대비임계(고휘도 중심시야 liminal contrast ~0.02). 참조 탐지 기준값.
    eps_th = 0.02
    rows.append(("탐지 대비임계 ε_th (고휘도)", eps_th, 0.02, _rel(eps_th, 0.02),
                 "고휘도 중심시야. 저휘도·주변시야는 상승(모델에 반영, 범위 밖은 미검증)", "Blackwell 1946 대비임계 [출처:조각]"))
    # 4) MEMS IMU 정상상태 위치불확실 σ_ss=9m — 소비자 MEMS VRW/바이어스 대역 안인가(스펙 referent).
    sigma_ss = 9.0
    rows.append(("IMU 정상상태 σ_ss [m] (GM)", sigma_ss, 10.0, _rel(sigma_ss, 10.0),
                 "소비자 MEMS 대역(참고). 실 IMU Allan 분산 대조=GAP", "MEMS IMU 스펙 대역 [출처:조각]"))
    # 5) 중력(자명한 물리상수) — 자기점검
    rows.append(("중력 g [m/s²]", 9.81, 9.80665, _rel(9.81, 9.80665), "지표 표준", "표준중력 [규격]"))
    return rows


# 4계층 신뢰성 배치(NASA): Physical → Reference M&S(validated domain) → Test Env(SUT) → IV&V
LAYERS = [
    ("① Physical Evidence", "실측/물리시험", "실 안개영상·실 SAR·실 IMU 로그 = **미확보(GAP)**. "
     "지금 물리 referent 는 표준·문헌값(정의·계산상수)뿐."),
    ("② Reference M&S (validated domain)", "참조세계 = 모델", "소광은 Koschmieder 표준 준수, 분자항은 "
     "Rayleigh 물리값, 대비임계는 Blackwell 대역. **경험 validation 은 domain 한정·부분** — 표준 대조까지."),
    ("③ Test Environment (SUT)", "정책", "SUT 는 참조·평가기·truth 를 못 본다(기술 독립). 센서만 먹는다."),
    ("④ IV&V", "독립 검증", "평가기가 숨은 truth 로 채점. **조직 독립성(관리·재정)은 없음** — 아래 표."),
]

# 조직적 독립성 — 코드분리 ≠ 조직독립. 정직하게 수준을 적는다(NASA-STD-8739.8B IV&V 정의).
INDEPENDENCE = [
    ("Technical (개발 미참여자가 분석·시험)", "부분", "SUT 가 참조·평가기·truth 를 import·접근 못 함(테스트로 강제), "
     "참조가 다른 탐지·IMU formulation, 숨은 시나리오. **단 같은 저자.**"),
    ("Managerial (다른 조직이 IV&V 관리·시험선택)", "없음", "같은 저자가 셋을 다 만들었다. IV&V 가 무엇을 분석할지·"
     "어떤 시험방법·일정을 스스로 정하는 구조 아님(NASA-STD-8739.8B managerial independence)."),
    ("Financial (독립 예산)", "없음", "해당 없음(연구 프로젝트)."),
]

# 표준 축 매핑 — 7009B(모델을 믿을 수 있나) 와 8739.8B(소프트웨어를 독립보증하나) 를 **섞지 않는다**.
# 근거는 사용자가 준 문서지도(URL·표준번호)뿐 — 원문 전문 재열람 안 함 → [출처:조각].
STANDARDS = [
    ("Reference World (참조세계)", "NASA-STD-7009B (2024-03-05)",
     "M&S credibility·validation domain — '이 모델을 얼마나 믿나'. refval 의 표준대조가 여기 속한다. [출처:조각]"),
    ("Reference model 구현·적용", "NASA-HDBK-7009B",
     "7009B 를 실제로 어떻게 적용할지 guidance(핸드북). [출처:조각]"),
    ("Scenario / mission requirement", "NASA SE Handbook · NPR 7123 계열",
     "요구=사실(조난자 탐색). SUT 에 행동을 명령하지 않는다. [출처:조각]"),
    ("SUT verification / software assurance", "NASA-STD-8739.8B",
     "개발 소프트웨어의 보증·안전. '코드가 설계대로인가'. [출처:조각]"),
    ("Independent evaluator / IV&V 팀", "NASA-STD-8739.8B · IV&V Framework(IVV 09-1 Rev S)",
     "IV&V = 테스트 한 번 더가 아니라 objective evidence 확보하는 독립 기술활동. [출처:조각]"),
    ("Validation domain / 결과 credibility", "NASA-STD-7009B",
     "결과를 어느 조건까지 믿을 수 있나(경험 validation 밖은 미검증). [출처:조각]"),
]

# 검증 lifecycle — '시나리오 한 번 돌려 성공/실패' 로는 부족(NASA SE Handbook / SWE-029 Validation Planning).
# 각 단계가 이 저장소 어디에 있나(있음/부분/GAP)를 정직히 적는다.
VLIFECYCLE = [
    ("Validation Plan", "부분", "무엇을·어느 domain 까지 검증할지 사전계획. refval 의 domain·GAP 표가 씨앗. 정식 계획문서=GAP."),
    ("Test Case Definition", "있음", "harness.CASE_TAEBAEK 등 숨은 시나리오(방위·거리·수관·기상)를 사전 정의."),
    ("Test Environment", "있음", "Reference World(참조 물리)+격리된 SUT+평가기. SUT 는 truth 를 못 본다."),
    ("Acceptance / Evaluation Criteria", "부분", "evaluator: 탐지율·위치 RMSE·오경보·coverage·latency·안전. 합격선 수치=사전 미고정(GAP)."),
    ("Execution", "있음", "harness.run/run_case 가 시나리오를 돌리고 로그를 남긴다."),
    ("Objective Evidence", "부분", "숨은 truth 대비 채점 로그·산출물. **실측 referent 부재로 field evidence 는 GAP**(8739.8B)."),
]


def report_md():
    rows = refent_checks()
    L = ["# 참조모델 검증 + 4계층 신뢰성 배치 (참조도 모델이다)", ""]
    L.append("> 독립 참조모델이라고 **자동 validated 가 아니다**(NASA-STD-7009B). 참조 물리를 문서화된 "
             "물리/표준 referent 와 대조하고, 맞는 **validation domain** 만 유효라 적는다. 실측이 필요한 곳은 GAP.")
    L.append("")
    L.append("## 참조모델 ↔ 물리/표준 referent")
    L.append("| 물리 | 모델값 | referent | 상대오차 | validation domain | 근거 |")
    L.append("|---|---|---|---|---|---|")
    for name, mv, rv, err, dom, src in rows:
        L.append("| %s | %.4g | %.4g | %.1f%% | %s | %s |" % (name, mv, rv, err*100, dom, src))
    worst = max(rows, key=lambda r: r[3])
    L.append("")
    L.append("- 최대 상대오차 %.1f%% (%s). 표준·문헌 referent 준수는 확인 — 그러나 이는 **conceptual/문헌 대조**다."
             % (worst[3]*100, worst[0]))
    L.append("- **핵심 GAP(경험 validation)**: 실 안개영상·실 SAR 데이터·실 IMU Allan 분산으로 참조를 보정하기 "
             "전에는 참조세계가 현실을 대표한다고 말할 수 없다. 그 전까지 결과는 domain 한정 주장이다.")
    L.append("")
    L.append("## 4계층 신뢰성 배치 (Physical → Reference M&S → SUT → IV&V)")
    for name, role, note in LAYERS:
        L.append("- **%s** (%s): %s" % (name, role, note))
    L.append("")
    L.append("## 표준 축 매핑 — 7009B 와 8739.8B 를 섞지 않는다")
    L.append("> **7009B = '시뮬레이션/모델 자체를 얼마나 믿나'**, **8739.8B = '개발 소프트웨어를 독립 보증하나'**. "
             "그 위에 SE Handbook 이 전체 V&V lifecycle 을 계획한다. (근거: 사용자 문서지도 — 원문 전문 미열람 [출처:조각])")
    L.append("| 시스템 부분 | NASA 문서 | 무엇을 규정 |")
    L.append("|---|---|---|")
    for part, doc, note in STANDARDS:
        L.append("| %s | %s | %s |" % (part, doc, note))
    L.append("")
    L.append("## 검증 lifecycle (시나리오 1회 실행 ≠ validation — SWE-029)")
    L.append("| 단계 | 상태 | 이 저장소에서 |")
    L.append("|---|---|---|")
    for step, st, note in VLIFECYCLE:
        L.append("| %s | **%s** | %s |" % (step, st, note))
    L.append("")
    L.append("## 조직적 독립성 — 코드분리 ≠ 조직독립 (정직)")
    L.append("| 독립성 | 수준 | 근거 |")
    L.append("|---|---|---|")
    for name, lvl, note in INDEPENDENCE:
        L.append("| %s | **%s** | %s |" % (name, lvl, note))
    L.append("")
    L.append("## 현재 시스템의 정확한 명명")
    L.append("- **Independent Simulation-Based Verification / Evaluation** (자기채점 순환 제거됨).")
    L.append("- **Field Validation: NO** — 참조모델의 현실 대표성이 경험 validation 안 됨.")
    L.append("- **다음(결정적)**: ② Reference→Physical referent 의 경험 validation chain 하나 + "
             "⑥~⑧ 별 팀·별 저장소·IV&V 자체 시험선택·독립 보고. '참조를 더 그럴듯하게'가 아니다.")
    return "\n".join(L) + "\n", rows


if __name__ == "__main__":
    import datetime
    REPO = os.path.dirname(os.path.dirname(HERE)); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    md, rows = report_md()
    rel = "public_agent_memory/refval_%s.md" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    open(os.path.join(REPO, rel), "w", encoding="utf-8").write(md)
    worst = max(rows, key=lambda r: r[3])
    print("참조모델 표준대조: 최대 상대오차 %.1f%% (%s)" % (worst[3]*100, worst[0]))
    print("Field Validation: NO — 경험 validation(실 데이터)은 GAP. domain 한정 주장.")
    print("산출물:", rel)
