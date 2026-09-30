#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""모델 검증 하니스(Level 2) 검사 — 자기채점을 벗어났는지, GAP 을 숨기지 않는지.

핵심(과장방지): SAR 초점이 회절 척도법칙을 따르는지(R²)를 재고, **접힌 동작점을 뺐는지**,
그리고 referent 없는 모델을 GAP 으로 명시하는지 본다. R² 를 억지로 1 로 만들지 않는다.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sar"))
import validate                                                       # noqa: E402
import radar                                                         # noqa: E402

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


print("[Level 2 증거] SAR 초점이 회절 척도법칙(λR/2L, c/2B)을 따르나")
ev = validate.sar_resolution_evidence()
ok(ev["r2_az"] > 0.7, f"방위 초점이 λR/2L 척도를 따른다 (R²={ev['r2_az']:.3f} > 0.7)")
ok(ev["r2_rg"] > 0.6, f"거리 초점이 c/2B 척도를 따른다 (R²={ev['r2_rg']:.3f} > 0.6)")
ok(0.2 < ev["k_az"] < 3.0 and 0.2 < ev["k_rg"] < 3.0,
   f"구현 비례상수 k 가 유한·합리 (방위 {ev['k_az']:.2f}, 거리 {ev['k_rg']:.2f})")

print("\n[동작점 건전성] 접힌(비모호 밖) 동작점은 증거에서 뺀다 (과장방지)")
# 거리 스윕은 비모호 거리 안의 B 만 써야 한다. B=120MHz 는 비모호 160m < 209m 라 제외돼야.
import math
alt = 120.0; R = math.hypot(alt*math.tan(math.radians(55.0)), alt)
bad = radar.RadarCfg(B=120e6)
ok(bad.unambiguous_range <= R, f"B=120MHz 는 비모호({bad.unambiguous_range:.0f}m) < 표적경사({R:.0f}m) — 접힘")
ok(all("120MHz" not in name for name, _, _ in ev["rg_rows"]), "접히는 B=120MHz 는 거리증거에 안 들어간다")
ok(len(ev["rg_rows"]) >= 2, f"유효 거리 동작점이 남는다 ({len(ev['rg_rows'])}점)")

print("\n[GAP 을 숨기지 않는다] referent 없는 모델은 GAP 으로 명시")
models = {s["model"]: s for s in validate.SCORECARD}
ok(any("안개" in m for m in models), "안개 모델이 기록표에 있다")
_fog = [s for m, s in models.items() if "안개" in m][0]
ok("GAP" in _fog["gap"] or "미검증" in _fog["L2"] or "GAP" in _fog["L2"], "안개 탐지모델은 GAP(실 영상 대조 필요)로 적혀 있다")
_det = [s for m, s in models.items() if "탐지" in m][0]
ok("없음" in _det["referent"] or "대리" in _det["referent"], "사람탐지는 referent 없음(대리물)이라고 정직하게 적혀 있다")
ok(any("Level 3" in s["referent"] or "운용" in s["referent"] for s in validate.SCORECARD),
   "정책은 Level 3(운용) referent 없음으로 명시")

print("\n[정직 문장] 현장검증 주장 안 함")
ok("not" in validate.HONEST and "field-validated" in validate.HONEST, "‘현장검증 아님’을 영문 표준문장으로 명시")

print("\n[보고 생성] md 가 3계층과 GAP 을 담는다")
md, _ = validate.report_md()
ok("Level 1" in md and "Level 2" in md and "Level 3" in md, "3계층이 보고에 있다")
ok("GAP" in md and "Sandia" in md, "실 데이터 GAP(예: Sandia/UAVSAR)을 적는다")

print()
if fails:
    print("빨강 %d개:" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("초록 — 검증 하니스: 척도법칙 적합 + 동작점 건전 + GAP 명시")
