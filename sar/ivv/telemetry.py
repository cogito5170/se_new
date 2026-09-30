#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rate-stratified 텔레메트리 버스 — 하나의 주기로 다 보내지 않는다(NASA UAS/JPL 사례).

세 계층으로 나눈다:
  · **10 Hz  기계 상태(state)**: POS·ALT·VEL·자세·IMU 드리프트·센서상태 — 3D 애니메이션·기록용.
  · **1 Hz   운용 보고(report)**: 사람이 읽는 대시보드(상태·센서·임무) — 화면에 매초 한 번.
  · **event  결정/경보(즉시)**: 탐지·REPLAN·waypoint 변경·MRC — 일어나는 순간.

'보고'와 '데이터 전송'을 분리한다: 버스엔 10 Hz state 가 흐르고, 사람 화면엔 3D + 1 Hz
대시보드 + 즉시 경보만 보인다. SUT 는 이 버스에서 **관측만** 뽑아 자기 주기로 판단한다.

**10 Hz 는 NASA 표준이 아니다** — 연구용 중간 설계점(1 Hz 보다 빠르고 15–20 Hz 항공보다 가볍다).
근거(NASA NTRS): UAS CNPC 15–20 Hz [출처:조각], AirSTAR 200 Hz+ [출처:조각], 어떤 UAS 는 5 s(0.2 Hz)가
느려 ≥1 Hz 로 변경 [출처:조각], JPL 텔레메트리 1–100 Hz 이질 채널 [출처:조각].
"""

STATE_HZ = 10.0     # 기계 상태 스트림
REPORT_HZ = 1.0     # 운용 보고(대시보드)


class TelemetryBus:
    """10 Hz state 를 받아 1 Hz report 로 데시메이트하고, event 는 즉시 기록한다."""

    def __init__(self, state_hz=STATE_HZ, report_hz=REPORT_HZ):
        self.state_hz = state_hz; self.report_hz = report_hz
        self.state_log = []      # 10 Hz
        self.reports = []        # 1 Hz (사람용)
        self.events = []         # 즉시
        self._last_report_t = -1e9

    def publish_state(self, s):
        """10 Hz 기계 상태 한 프레임. s 는 dict(t, pos, alt, vel, heading, imu_sigma, sensors, coverage, policy...)."""
        self.state_log.append(s)
        if s["t"] - self._last_report_t >= (1.0 / self.report_hz) - 1e-9:
            self._last_report_t = s["t"]
            self.reports.append(make_report(s))

    def emit_event(self, t, kind, detail):
        """결정/경보를 **즉시** 기록(일어난 순간). kind: DETECT·REPLAN·WAYPOINT·MRC·NAV_DEGRADED."""
        self.events.append({"t": float(t), "kind": kind, "detail": detail})

    def sut_view(self, s):
        """SUT 는 이 버스에서 **관측만** 뽑는다(truth·평가용 필드 제거)."""
        return {k: v for k, v in s.items() if k in ("t", "rgb", "sar", "imu", "gps")}

    def rates(self):
        """실측 주기(로그 간격의 중앙값 역수) — '정말 10 Hz/1 Hz 인가'를 잰다."""
        def hz(ts):
            d = sorted(round(ts[i+1]-ts[i], 6) for i in range(len(ts)-1))
            return (1.0/d[len(d)//2]) if d and d[len(d)//2] > 0 else 0.0
        return {"state_hz": hz([s["t"] for s in self.state_log]),
                "report_hz": hz([r["t"] for r in self.reports]),
                "events": len(self.events)}


def make_report(s):
    """1 Hz 운용 보고(사람용 대시보드) — 상황화된 값(원시 아님)."""
    se = s.get("sensors", {})
    return {
        "t": round(s["t"], 1),
        "ALT": "%.0f m" % s.get("alt", 0.0),
        "SPEED": "%.1f m/s" % s.get("vel", 0.0),
        "HEADING": "%03d°" % (int(s.get("heading", 0)) % 360),
        "RGB": se.get("rgb", "?"),
        "SAR": se.get("sar", "?"),
        "IMU": se.get("imu", "?"),
        "COVERAGE": "%.1f%%" % s.get("coverage", 0.0),
        "POLICY": s.get("policy", "?"),
        "TARGET": s.get("target", "UNKNOWN"),
    }


def format_report(r):
    """대시보드 문자열(1 Hz)."""
    return ("T+%05.1f  UAV %s %s %s | RGB %s · SAR %s · IMU %s | COV %s · %s · TGT %s"
            % (r["t"], r["ALT"], r["SPEED"], r["HEADING"], r["RGB"], r["SAR"], r["IMU"],
               r["COVERAGE"], r["POLICY"], r["TARGET"]))


def format_event(e):
    """즉시 경보 문자열."""
    return "T+%05.1f  [%s] %s" % (e["t"], e["kind"], e["detail"])
