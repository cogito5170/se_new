"""H0 -- 깃발 위조 게이트.

실측(2026-10-01, 사용자가 붙여 준 답): 정책을 프롬프트로 받은 Gemini 가

    Log: NO_LOOP_DETECTED. Status: Gate01 evaluation (A_TO_B: TRUE). MCP version: 0.46.0.

을 찍었다. 탐지기도, A·B 의 정의도, 그 버전 값도 어디에도 없었다. 깃발이 **모델이 낼 수
있는 토큰**이었기 때문이다. 여기서는 그 토큰이 모델 글에 나오면 보고가 아니라 위조로 본다.

**한계(글자를 보는 검사다):** 바꿔 말한 위조("루프는 없었습니다", "모든 검사를 통과")는
못 잡는다. 그래서 이것은 첫 번째 벽이고, 두 번째 벽은 렌더러다 -- 상태 칸은 원장에서만
채우고 모델 글을 거기 넣지 않는다. 이 게이트가 놓쳐도 상태 칸은 거짓이 되지 않는다.

**대문자 낱말만 본다.** 'failed' · 'done' 같은 산문 낱말까지 잡으면 늘 우는 경보가 되고
(toolgate.py 가 이미 배운 것), 늘 우는 경보는 아무도 안 듣는다.
"""
from __future__ import annotations

import re

# 정책 F·G·H·J 의 깃발 어휘. 대소문자를 가린다.
_FLAG_WORDS = (
    "NO_LOOP_DETECTED", "LOOP_DETECTED", "LOOP_LIMIT_REACHED",
    "NOT_A_TO_B_PRIME", "A_TO_B", "NOT_B_PRIME", "RED_RED_STOP",
    "NEXT_RAISED", "NEXT_DISPATCHED", "LOGGING_FAILURE", "NEEDS_REVIEW",
    "DONE", "BLOCKED", "FAILED",
)
_FLAG_RE = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(_FLAG_WORDS) + r")(?![A-Za-z0-9_])")
# 게이트 이름을 상태처럼 말하는 것: "Gate01 evaluation", "Gate01: PASS"
_GATE_RE = re.compile(r"\bGate\s?0?1\b", re.I)
# 상태 머리줄: 줄 머리의 "Status:" "Log:" "Loop:" (대소문자 무시)
_STATUS_LINE_RE = re.compile(r"(?m)^\s*(?:[*_#>-]\s*)*(status|log|loop(?:\s+status)?)\s*:", re.I)
# 버전 주장: "MCP version: 0.46.0", "SDK v1.2", "protocol version 2025-06-18"
_VERSION_RE = re.compile(
    r"\b(mcp|sdk|protocol|server|runtime)\b[^\n]{0,20}?\bv(?:ersion)?\b\s*[:=]?\s*v?\d", re.I)
_MODEL_CLAIM_RE = re.compile(r"\b(i am|i'm|running on|this is)\s+(gemini|claude|gpt)\b", re.I)


def scan(text: str) -> list:
    """[(종류, 걸린 글)] -- 비었으면 위조 없음(이 검사가 볼 수 있는 범위에서)."""
    if not text:
        return []
    hits = []
    for m in _FLAG_RE.finditer(text):
        hits.append(("flag", m.group(1)))
    for m in _GATE_RE.finditer(text):
        hits.append(("gate", m.group(0)))
    for m in _STATUS_LINE_RE.finditer(text):
        hits.append(("status_line", m.group(0).strip()))
    for m in _VERSION_RE.finditer(text):
        hits.append(("version_claim", m.group(0)))
    for m in _MODEL_CLAIM_RE.finditer(text):
        hits.append(("model_claim", m.group(0)))
    return hits


# [Next] 는 정책 H 의 표지다. 모델이 쓰면 **제안**이지 사건이 아니다 -- 위조로 치지 않고 따로 뽑는다.
_NEXT_RE = re.compile(r"\[\s*Next\s*\]\s*:?\s*(.+)", re.I)


def next_proposals(text: str) -> list:
    return [m.group(1).strip() for m in _NEXT_RE.finditer(text or "") if m.group(1).strip()]


def strip_next(text: str) -> str:
    """답 본문에서 [Next] 줄을 뺀다 -- 그것은 렌더러가 '제안(디스패치 안 됨)' 칸에 따로 그린다."""
    return "\n".join(l for l in (text or "").splitlines() if not _NEXT_RE.search(l)).strip()
