#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rate-stratified 텔레메트리 검사 — '하나의 주기로 다 보내지 않는다'가 **실제로** 그런지 붙든다.

핵심: (1) state 는 10 Hz, report 는 1 Hz 로 데시메이트, event 는 즉시(타임스탬프 있음),
(2) 버스의 SUT view 는 관측만 남기고 나머지(내부·평가 필드)를 지운다,
(3) 하니스 실행이 세 스트림을 실제 그 주기로 낸다 + state 로그에 truth 가 안 샌다.
글자만 보는 검사가 아니라 **버스를 돌려 실측 주기를 잰다**.
"""
from __future__ import annotations
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


def test_bus_decimates():
    import telemetry as tel
    b = tel.TelemetryBus()
    # 5초치 10Hz state 를 넣는다 → report 는 매초 한 번이어야
    for i in range(50):
        b.publish_state({"t": i * 0.1, "alt": 150, "vel": 20, "heading": 45,
                         "coverage": i, "policy": "SEARCHING",
                         "sensors": {"rgb": "OK", "sar": "OK", "imu": "OK"}})
    r = b.rates()
    ok(abs(r["state_hz"] - 10.0) < 1e-6, "state 실측 = 10 Hz (%.3f)" % r["state_hz"])
    ok(abs(r["report_hz"] - 1.0) < 1e-6, "report 실측 = 1 Hz (%.3f)" % r["report_hz"])
    ok(len(b.state_log) == 50, "state 로그 50개 (%d)" % len(b.state_log))
    ok(len(b.reports) == 5, "report 로그 5개 = 5초 (%d)" % len(b.reports))


def test_events_immediate():
    import telemetry as tel
    b = tel.TelemetryBus()
    b.publish_state({"t": 0.0, "sensors": {}})
    b.emit_event(1.37, "DETECT", "x")   # 1 Hz 격자에 안 맞는 순간
    ok(len(b.events) == 1, "이벤트 1개")
    ok(abs(b.events[0]["t"] - 1.37) < 1e-9, "이벤트가 격자 아닌 발생순간 t=1.37 기록 (%.3f)" % b.events[0]["t"])
    ok(b.events[0]["kind"] == "DETECT", "이벤트 kind 보존")


def test_sut_view_filters():
    import telemetry as tel
    b = tel.TelemetryBus()
    s = {"t": 1.0, "rgb": {"vis": 0.1}, "sar": {"hits": 2}, "imu": {"sigma": 3.0},
         "gps": {"uncertain": True}, "pos": (1, 2), "policy": "SEARCHING", "coverage": 10.0}
    v = b.sut_view(s)
    ok(set(v.keys()) <= {"t", "rgb", "sar", "imu", "gps"}, "SUT view = 관측 필드만 (%s)" % sorted(v.keys()))
    ok("pos" not in v and "policy" not in v and "coverage" not in v, "내부/보고 필드는 SUT 에 안 감")


def test_harness_three_streams():
    import harness as H
    bus, metrics, ref = H.run_case_telemetry(H.CASE_TAEBAEK)
    r = bus.rates()
    ok(abs(r["state_hz"] - 10.0) < 1e-6, "하니스 state = 10 Hz (%.3f)" % r["state_hz"])
    ok(abs(r["report_hz"] - 1.0) < 1e-6, "하니스 report = 1 Hz (%.3f)" % r["report_hz"])
    ok(r["events"] >= 1, "이벤트 ≥1 (%d)" % r["events"])
    # state 는 report 보다 훨씬 촘촘 (10:1 근처)
    ok(len(bus.state_log) >= 9 * len(bus.reports), "state 로그가 report 의 ~10배 (%d vs %d)"
       % (len(bus.state_log), len(bus.reports)))
    # 모든 이벤트에 타임스탬프
    ok(all("t" in e and isinstance(e["t"], float) for e in bus.events), "모든 이벤트에 float 타임스탬프")


def test_no_truth_leak_in_state():
    """10 Hz state 를 SUT view 로 거른 것에 truth 계열 키가 없어야(자기채점 방지)."""
    import harness as H
    bus, _m, _r = H.run_case_telemetry(H.CASE_TAEBAEK)
    banned = {"truth", "targets", "canopy", "target_xy"}
    leaked = [k for s in bus.state_log for k in bus.sut_view(s) if k in banned]
    ok(not leaked, "SUT view state 에 truth 계열 키 없음 (%s)" % (set(leaked) or "clean"))


if __name__ == "__main__":
    for fn in (test_bus_decimates, test_events_immediate, test_sut_view_filters,
               test_harness_three_streams, test_no_truth_leak_in_state):
        print("[%s]" % fn.__name__)
        fn()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\n텔레메트리 검사 통과: state=10Hz · report=1Hz · event=즉시 · truth 격리")
