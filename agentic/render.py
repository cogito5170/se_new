"""사용자에게 가는 글은 **원장에서만** 그린다.

모델의 답은 '답' 칸 하나에만 들어간다. 상태 · 모델 정체 · 루프 · Gate01 · MCP 버전 칸은
원장 사건으로만 채우고, 그 사건이 없으면 **없다고** 쓴다:

    루프     LOOP_EVAL 없음    -> UNKNOWN            (정책 F: 로그가 없다고 루프가 없는 게 아니다)
    Gate01   GATE_EVAL 없음    -> 평가 안 함          (정책 G: 없는 결과를 TRUE 로 읽지 않는다)
    MCP      MCP_VERSION 없음  -> 기록 없음 ×3        (정책 A.4 · A.5)
    상태     TERMINAL 없음     -> FAILED(no_terminal_event)

원시 로그는 그리지 않는다(정책 E.1). 진단 싱크는 경로와 바이트 수만.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _last(events, type_):
    for e in reversed(events):
        if e.get("type") == type_:
            return e
    return None


def render(events: list, run_dir: "str | Path | None" = None) -> str:
    out = []
    start = _last(events, "RUN_START")
    term = _last(events, "TERMINAL")
    if term:
        d = term["data"]
        out.append(f"상태: {d['state']} ({d['reason']}) -- {d.get('summary', '')}")
    else:
        out.append("상태: FAILED (no_terminal_event) -- 원장에 종료 사건이 없다")
    if start:
        s = start["data"]
        out.append(f"실행: {start['run_id']} · 설정 sha256 {s.get('config_sha256', '?')[:12]} · "
                   f"HEAD {s.get('head_sha') or '기록 없음'}")

    ident = _last(events, "MODEL_IDENTITY")
    if ident:
        d = ident["data"]
        shown = {"verified": "확인됨", "unreported": "미확인(응답이 모델을 밝히지 않음)",
                 "mismatch": "불일치"}.get(d["status"], d["status"])
        out.append(f"모델: 설정 {d['configured']} · 응답 {d.get('reported') or '없음'} · {shown}")
    else:
        conf = start["data"].get("model") if start else None
        out.append(f"모델: 설정 {conf or '기록 없음'} · 응답 없음 · 미확인(호출이 성공하지 않았다)")

    loop = _last(events, "LOOP_EVAL")
    out.append(f"루프: {loop['data']['result']}" if loop else
               "루프: UNKNOWN (탐지기가 평가하지 않았다)")
    gate = _last(events, "GATE_EVAL")
    out.append(f"Gate01: {gate['data'].get('decision')}" if gate else "Gate01: 평가 안 함")
    mcp = _last(events, "MCP_VERSION")
    if mcp:
        d = mcp["data"]
        out.append(f"MCP: protocol {d.get('protocol', 'unreported')} · sdk {d.get('sdk', 'unreported')} · "
                   f"server {d.get('server', 'unreported')}")
    else:
        out.append("MCP: protocol 기록 없음 · sdk 기록 없음 · server 기록 없음")

    forg = [e for e in events if e["type"] == "MODEL_FLAG_FORGERY"]
    if forg:
        kinds = sorted({h[0] for e in forg for h in e["data"].get("hits", [])})
        out.append(f"깃발 위조: {len(forg)}회 거절 (종류: {', '.join(kinds)})")
    for e in events:
        if e["type"] == "NEXT_PROPOSED":
            out.append(f"다음 작업 제안(디스패치 안 됨): {e['data']['text']}")

    diag = [e for e in events if e["type"] == "DIAG_WRITTEN"]
    if diag:
        where = (Path(run_dir) / "diag.log") if run_dir else "diag.log"
        out.append(f"진단 로그: {where} ({sum(e['data']['bytes'] for e in diag)} 바이트, 화면에 안 싣는다)")

    ans = _last(events, "ANSWER_ADOPTED")
    out.append("")
    out.append("답:" if ans else "답: (채택된 답 없음)")
    if ans:
        out.append(ans["data"]["text"])
    return "\n".join(out)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from agentic.ledger import read_events
    d = sys.argv[1]
    print(render(read_events(d), d))
