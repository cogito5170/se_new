#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IV&V 분리 검사 — 자기채점이 **구조적으로** 불가능한지 붙든다.

핵심(NASA IV&V): (1) SUT 는 reference·evaluator·truth 를 import 안 한다(기술적 독립),
(2) 버스가 SUT 에 truth 를 안 준다, (3) 참조세계는 SUT 와 **다른 물리 formulation**,
(4) 평가기가 truth 로 채점(정답을 바꾸면 점수가 바뀐다). 하나라도 깨지면 자기채점이다.
"""
from __future__ import annotations
import ast
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IVV = REPO / "sar" / "ivv"
sys.path.insert(0, str(IVV))
sys.path.insert(0, str(REPO / "sar"))

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def _imports(path):
    names = set()
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            names.add(n.module.split(".")[0])
    return names

print("[기술적 독립] SUT 는 reference·evaluator·truth 를 import 하지 않는다")
_sut_imp = _imports(IVV / "sut.py")
ok("reference" not in _sut_imp, f"sut.py 가 reference 를 import 안 한다 ({_sut_imp & {'reference','evaluator'}})")
ok("evaluator" not in _sut_imp, "sut.py 가 evaluator 를 import 안 한다")
# 주석의 'truth' 언급은 허용. 실제 **접근**(.truth( 호출·["truth"] 첨자)만 금지.
_sut_src = Path(IVV / "sut.py").read_text(encoding="utf-8")
_bad = [".truth(", '["truth"]', "['truth']", "truth=", ".targets"]
ok(not any(b in _sut_src for b in _bad), f"sut.py 가 truth 를 **접근**하지 않는다(호출·첨자): {[b for b in _bad if b in _sut_src]}")

print("\n[버스 필터] 참조가 SUT 에 주는 관측에 truth 가 없다")
import reference as R                                                  # noqa: E402
scn = dict(seed=1, lat=38.12, lon=128.47, V=300.0, illum=2000.0, n_target=2)
ref = R.Reference(scn)
obs = ref.observe((5.0, 5.0))
ok("truth" not in obs, f"observe() 반환에 truth 키 없음: {list(obs.keys())}")
ok("targets" not in str(obs), "관측 어디에도 표적 실위치가 안 들어간다")
ok("targets" in ref.truth(), "truth() 는 표적 실위치를 준다(evaluator·viewer 전용)")

print("\n[검증된 표준은 일치, formulation 은 다르다] — 독립성은 '틀린 상수'가 아니라 다른 물리에서")
import sensors as S                                                    # noqa: E402
# 소광은 둘 다 검증된 Koschmieder 표준을 써야 옳다 → 거의 일치(공통 '가정'이 아니라 공통 '표준')
V, Rm = 300.0, 200.0
t_ref = R.ref_transmittance(V, Rm); t_sut = math.exp(-S.beta_from_visibility(V) * Rm)
ok(abs(t_ref - t_sut) < 0.02, f"소광은 검증된 표준이라 거의 일치(옳음): 참조 {t_ref:.3f} vs SUT {t_sut:.3f}")
# 독립성 ①: 탐지 formulation 이 다르다 — 참조 Blackwell 대비 vs SUT SNR(rgb_reliability)
p_ref = R.ref_detect_prob(V, Rm, 2000.0)
_rho, _det = S.rgb_reliability(S.beta_from_visibility(V), Rm, 2000.0, 0.0)
ok(abs(p_ref - _rho) > 0.1, f"탐지 formulation 이 다르다: 참조 Blackwell {p_ref:.2f} vs SUT SNR {_rho:.2f}")
# 독립성 ②: IMU — 참조 GM(수렴) vs SUT 랜덤워크(발산)
ok(R.ref_imu_sigma(120) < S.imu_sigma(120), f"IMU: 참조 GM({R.ref_imu_sigma(120):.0f}) < SUT 랜덤워크({S.imu_sigma(120):.0f})")

print("\n[평가기가 truth 로 채점] 정답을 바꾸면 점수가 바뀐다")
import evaluator as E                                                  # noqa: E402
log = [{"detections": [(10.0, 10.0, 0.9)], "state": "SEARCHING", "telemetry": {"coverage": 20.0}}]
m_hit = E.evaluate({"targets": [(10.0, 10.0)]}, log)     # 주장이 truth 와 일치
m_miss = E.evaluate({"targets": [(2.0, 2.0)]}, log)      # truth 가 멀리 → 오경보
ok(m_hit["detection_rate"] == 100.0 and m_hit["false_alarms"] == 0, "주장이 truth 와 맞으면 탐지 100%")
ok(m_miss["detection_rate"] == 0.0 and m_miss["false_alarms"] == 1, "truth 가 다르면 미탐+오경보 (평가기가 truth 를 쓴다)")

print("\n[하니스] 숨은 시나리오를 돌려 독립 지표가 나온다")
import harness as H                                                    # noqa: E402
rows, summ = H.run(n=2, budget=20)
ok(len(rows) == 2 and "detection_rate" in rows[0], "지표가 시나리오마다 나온다")
ok(0.0 <= summ["safe_frac"] <= 100.0, "안전 비율이 범위 안")
ok("truth" not in str(H._sut_view({"rgb": 1, "truth": 2})), "버스 필터 _sut_view 가 truth 를 뺀다")

print("\n[참조모델 검증층] 참조도 모델 → 물리 referent 대조 + domain + 조직독립 정직")
import refval as RV                                                    # noqa: E402
_rows = RV.refent_checks()
ok(len(_rows) >= 4 and max(r[3] for r in _rows) < 0.5, "참조 물리가 표준/물리 referent 와 대조된다(오차 유한)")
_md, _ = RV.report_md()
ok("Field Validation: NO" in _md, "현장 validation 을 주장하지 않는다(경험 validation GAP)")
ok("Managerial" in _md and "없음" in _md, "조직 독립성(관리·재정)은 없음이라고 정직히 적는다(코드분리≠조직독립)")
ok("경험 validation" in _md and "GAP" in _md, "실 데이터 경험 validation 을 GAP 으로 명시")

print()
if fails:
    print("빨강 %d개:" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("초록 — IV&V 분리: 기술독립·버스필터·다른formulation·truth채점 전부 확인")
