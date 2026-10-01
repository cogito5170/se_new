"""사건 원장과 진단 싱크 -- 정책 E(Raw Log)와 J(Terminal States)를 코드로.

    events.jsonl   구조화 사건. 언제나 쓴다(E.3). 사용자에게 가는 글은 여기서만 그린다
    diag.log       원시 stdout/stderr · 오류 본문. 마스킹해서(E.5) 여기에만 둔다(E.1·E.2)

**쓰기에 실패하면 `LoggingFailure` 를 던진다(E.4).** 삼키지 않는다 -- 원장이 없는 진행은
검사할 수 없는 진행이다. 부르는 쪽(run.py)이 그것을 `LOGGING_FAILURE` 종료로 바꾼다.

사건 종류와 종료 상태는 **닫힌 목록**이다. 모르는 종류를 적으려 하면 거절한다 -- 열린 목록이면
모델이든 사람이든 아무 이름이나 만들어 넣고, 렌더러는 그것을 못 읽는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from secret_filter import redact_secrets

EVENT_TYPES = frozenset({
    "RUN_START",            # 설정 해시 · 모델 · HEAD SHA
    "WALP_FRONT",           # 앞단 판정: small | model | bypass | disabled (+ 까닭)
    "MODEL_CALL_START",
    "MODEL_CALL_END",       # ok | error(상태·이름만. 본문은 diag 로)
    "MODEL_IDENTITY",       # 설정한 모델 · 응답이 밝힌 모델 · verified|unreported|mismatch
    "MODEL_FLAG_FORGERY",   # 모델 글에 깃발 어휘가 있었다
    "NEXT_PROPOSED",        # 모델이 다음 작업을 제안했다(디스패치 아님)
    "LOOP_EVAL",            # 루프 탐지기가 실제로 평가했다 (2단계부터)
    "GATE_EVAL",            # Gate01 이 실제로 평가했다 (2단계부터)
    "MCP_VERSION",          # protocol · sdk · server 를 따로 (5단계부터)
    "DIAG_WRITTEN",         # 진단 싱크에 몇 바이트 썼나(내용은 안 적는다)
    "ANSWER_ADOPTED",
    # 2단계 -- Sequencer · Gate01 (정책 G · H)
    "CHAIN_START",          # 작업 수 · 레지스트리 해시
    "NEXT_RAISED",          # 작업 ID · 멱등키
    "TASK_VALIDATED",
    "TASK_REJECTED",        # 명세·권한 위반(사유 목록)
    "DUPLICATE_SKIPPED",    # 같은 멱등키가 이미 승인됨 -- 다시 안 돈다
    "NEXT_DISPATCHED",      # 앞 작업의 승인 ID 를 **원장에서 읽어** 싣는다
    "NEXT_NOT_DISPATCHED",  # 막힌 작업도 조용히 건너뛰지 않는다
    "TOOL_START",           # 실행기가 실제로 시작
    "TOOL_END",             # 실행기 확인(끝남 · 결과 요약)
    "CHECK_EVAL",           # 필수 검사(sandbox 등) 하나의 판정
    "GATE_DECISION",        # Gate01 최종 판정 + 승인 ID
    "TASK_COMPLETED",       # TOOL_END 와 승인 뒤에만
    "TERMINAL",
})
ACTORS = frozenset({"code", "model", "executor"})
TERMINAL_STATES = frozenset({
    "DONE", "BLOCKED", "FAILED", "NEEDS_REVIEW",
    "RED_RED_STOP", "LOOP_LIMIT_REACHED", "LOGGING_FAILURE",
})


class LoggingFailure(RuntimeError):
    pass


def _append(path: Path, line: str) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        raise LoggingFailure(f"{type(e).__name__}: {path.name}") from None


class Ledger:
    def __init__(self, run_dir: "str | Path", run_id: str):
        self.dir = Path(run_dir)
        self.run_id = run_id
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise LoggingFailure(f"{type(e).__name__}: run_dir") from None
        self.path = self.dir / "events.jsonl"
        self.seq = 0
        self.terminated = False

    def emit(self, type_: str, actor: str, data: "dict | None" = None,
             evidence: "tuple | list" = (), task_id: str = "") -> str:
        if type_ not in EVENT_TYPES:
            raise ValueError(f"unknown_event_type:{type_}")
        if actor not in ACTORS:
            raise ValueError(f"unknown_actor:{actor}")
        if self.terminated:
            raise ValueError("event_after_terminal")
        self.seq += 1
        eid = f"{self.run_id}:{self.seq}"
        ev = {"id": eid, "run_id": self.run_id, "task_id": task_id, "seq": self.seq,
              "ts": round(time.time(), 3), "type": type_, "actor": actor,
              "data": data or {}, "evidence": list(evidence)}
        # 사건에도 비밀이 섞일 수 있다(모델 답에 키를 되뇌는 등) -- 줄 전체를 마스킹한다
        _append(self.path, redact_secrets(json.dumps(ev, ensure_ascii=False)) + "\n")
        return eid

    def terminal(self, state: str, reason: str, summary: str, evidence=()) -> str:
        if state not in TERMINAL_STATES:
            raise ValueError(f"unknown_terminal_state:{state}")
        if not reason:
            raise ValueError("terminal_reason_required")
        eid = self.emit("TERMINAL", "code", {"state": state, "reason": reason, "summary": summary},
                        evidence)
        self.terminated = True
        return eid


class DiagnosticSink:
    """원시 출력의 보호된 자리. 내용은 사건 원장에 안 싣고 크기·해시만 싣는다."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.path = ledger.dir / "diag.log"

    def write(self, source: str, text: str) -> None:
        masked = redact_secrets(text or "")
        _append(self.path, f"--- {source} @ {time.time():.3f}\n{masked}\n")
        try:
            os.chmod(self.path, 0o600)
        except OSError as e:
            raise LoggingFailure(f"{type(e).__name__}: chmod diag") from None
        self.ledger.emit("DIAG_WRITTEN", "code", {
            "source": source, "bytes": len(masked.encode("utf-8")),
            "sha256": hashlib.sha256(masked.encode("utf-8")).hexdigest()})


def read_events(run_dir: "str | Path") -> list:
    p = Path(run_dir) / "events.jsonl"
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out
