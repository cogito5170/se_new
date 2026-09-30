#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""표준 SAR 무전 보고 형식 — 드론의 보고 = 정책 I/O 인터페이스.

USCG/IAMSAR·USFA·MRA·NASA 자료 공통 구조:
  [호출대상] → [내 식별] → [상황 WHAT] → [위치 WHERE] → [상태 STATUS] → [필요 NEED] → [행동 ACTION]
우선순위 신호(IAMSAR): MAYDAY(임박 위험) > PAN-PAN(긴급) > 보통. 세 번 반복이 규정.

**이 형식이 온보드 LLM 을 없애는 열쇠다.** 고정 슬롯(WHO/WHAT/WHERE/STATUS/NEED/ACTION)이므로
드론은 이 구조화 레코드만 채워 보내면 된다(무거운 모델 불필요). 지상국(GCS)이 자연어↔구조 변환을
맡고, 드론은 결정적 정책 + 이 고정 문법 메시지만 주고받는다.  MRA 평가기준: clear·concise·understood.
"""
PRIORITY = {"mayday": "메이데이, 메이데이, 메이데이. ", "panpan": "팬팬, 팬팬, 팬팬. ", "normal": ""}


def record(what="", where="", status="", need="", action="", frm="UAV-1", to="지휘본부", pri="normal"):
    """구조화 보고 레코드(정책 입출력). 고정 슬롯이라 하드웨어/온보드 친화."""
    return dict(who=frm, to=to, what=what, where=where, status=status, need=need, action=action, pri=pri)


def radio(rec):
    """구조화 레코드 → 무전 음성 문장(WHO→WHAT→WHERE→STATUS→NEED→ACTION)."""
    s = PRIORITY.get(rec.get("pri", "normal"), "") + "%s, 여기는 %s." % (rec.get("to", "지휘본부"), rec["who"])
    if rec.get("what"):   s += " " + rec["what"] + "."
    if rec.get("where"):  s += " 위치 " + rec["where"] + "."
    if rec.get("status"): s += " 상태 " + rec["status"] + "."
    if rec.get("need"):   s += " " + rec["need"] + "."
    if rec.get("action"): s += " " + rec["action"] + "."
    return s + " 이상."


# 사건 → 표준 보고 (정책이 상태에서 뽑는다)
def on_start(area, mission):
    return record(what="탐색 개시", where=area, action=mission, pri="normal")

def on_detect(where_latlon, sector, status="확인되지 않음"):
    return record(what="사람으로 추정되는 대상 발견", where="%s (%s)" % (sector, where_latlon),
                  status=status, action="현 위치 유지하며 관찰·추적하겠음", pri="normal")

def on_degraded(cause):
    return record(what="센서 정보 저하(%s)" % cause, status="탐지 신뢰도 낮음",
                  action="감속·재접근으로 계속 탐색하겠음", pri="normal")

def on_fault(cause, safe_action):
    return record(what="결함 감지: %s" % cause, need="자율 대응 중",
                  action=safe_action, pri="panpan")

def on_mrc(cause):
    return record(what="최소위험 상태 진입: %s" % cause, need="즉각적인 지원이 필요",
                  action="안전지대로 복귀/체공하겠음", pri="mayday")

def on_waypoint(sector, elev, cov):
    return record(what="정상 초계 중", where="%s 격자, 고도 %.0fm" % (sector, elev),
                  status="수색 진척 %.0f%%" % cov, action="다음 격자로 이동하겠음", pri="normal")

def on_coverage(cov, found, total):
    return record(what="구역 수색 경과 보고", status="커버리지 %.0f%%, 조난자 %d/%d 확보" % (cov, found, total),
                  action="미탐색 구역 계속 훑겠음", pri="normal")

def on_sensor(vis, sig, sar_hits):
    return record(what="센서 상태 보고",
                  status="EO 가시도 %s, 관성드리프트 %.0fm, SAR 표적반사 %d" % (vis, sig, sar_hits),
                  action="전천후 SAR 병행 유지", pri="normal")

def on_verify(sector, conf):
    return record(what="접촉 재확인 중", where=sector, status="탐지 신뢰도 %.0f%%" % (conf * 100),
                  action="감속·재접근으로 식별 확정하겠음", pri="normal")

def on_replan(cause):
    return record(what="항로 재계획: %s" % cause, action="고지대 상승·경로 갱신 후 수색 재개하겠음", pri="panpan")
