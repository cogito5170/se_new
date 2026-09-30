#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""독립 평가기(Independent Evaluator) — truth ↔ SUT 출력. 정책을 안 돌린다.

SUT 는 자기 성공을 못 정한다. 여기서 **참조 truth** 와 SUT 의 주장(claims)을 비교해 채점한다:
탐지율·위치오차(RMSE)·오경보·커버리지·지연·안전. truth 는 evaluator 만 쥔다.
"""
import math


def evaluate(truth, sut_log, eps_cells=2.5):
    """truth={'targets':[(gx,gy)...]}, sut_log=[step_output ...] → 지표 dict.

    eps_cells: 위치일치 허용반경(격자). 매칭은 truth 표적마다 가장 가까운 주장 하나."""
    targets = truth["targets"]
    # 시간순 주장 모으기(첫 등장 스텝 기록 → 지연)
    claims = []
    for i, out in enumerate(sut_log):
        for (cx, cy, *_rest) in out.get("detections", []):
            claims.append((i, cx, cy))
    matched_t = set(); matched_c = set(); errs = []; first_hit = None
    for ti, (tx, ty) in enumerate(targets):
        best = None; bd = 1e9
        for ci, (si, cx, cy) in enumerate(claims):
            if ci in matched_c:
                continue
            d = math.hypot(cx - tx, cy - ty)
            if d < bd:
                bd = d; best = (ci, si, d)
        if best is not None and bd <= eps_cells:
            matched_t.add(ti); matched_c.add(best[0]); errs.append(bd)
            if first_hit is None or best[1] < first_hit:
                first_hit = best[1]
    n_t = max(1, len(targets))
    false_alarms = len(claims) - len(matched_c)
    rmse = math.sqrt(sum(e*e for e in errs)/len(errs)) if errs else float("nan")
    cov = max((o["telemetry"]["coverage"] for o in sut_log), default=0.0)
    states = [o["state"] for o in sut_log]
    safe = all(s in ("SEARCHING", "DEGRADED", "LOW-INFO", "MRC", "RECOVER↑", "RTL") for s in states)
    unsafe = any(o["telemetry"].get("geofence_violation") for o in sut_log)   # 설계상 없음
    return {
        "n_targets": len(targets),
        "detected": len(matched_t),
        "detection_rate": 100.0 * len(matched_t) / n_t,
        "loc_rmse_cells": rmse,
        "false_alarms": false_alarms,
        "coverage_pct": cov,
        "latency_steps": first_hit if first_hit is not None else None,
        "safe": safe and not unsafe,
        "steps": len(sut_log),
    }


def summarize(rows):
    """여러 시나리오 지표 → 평균·표준편차(간이). rows: evaluate() 반환들."""
    import statistics as st
    def col(k):
        vals = [r[k] for r in rows if isinstance(r.get(k), (int, float)) and not (isinstance(r[k], float) and math.isnan(r[k]))]
        return (st.mean(vals) if vals else float("nan"), st.pstdev(vals) if len(vals) > 1 else 0.0, len(vals))
    return {
        "n_scenarios": len(rows),
        "detection_rate": col("detection_rate"),
        "loc_rmse_cells": col("loc_rmse_cells"),
        "false_alarms": col("false_alarms"),
        "coverage_pct": col("coverage_pct"),
        "safe_frac": 100.0 * sum(1 for r in rows if r["safe"]) / max(1, len(rows)),
    }
