"""고정 모델 호출 -- 정책 A.1 · A.2 · A.3 을 코드로.

  · **모델은 하나다.** `orchestrator/llm_pool.call` 은 모델 사이를 폴백하므로(FALLBACK_MODELS ·
    순위 · pin) 이 길에서는 안 쓴다. 키만 돌린다 -- 같은 모델이므로 A.2 에 어긋나지 않는다.
  · 키를 다 써도 안 되면 다른 모델로 가지 않고 `Blocked("model_unavailable")` 다.
  · **응답이 스스로 밝힌 모델**(`Reply.model_version`)을 설정과 맞춘다(A.3):
        같음 또는 `<설정>-<개정>`       -> verified
        응답에 없음                     -> unreported  (부른 이름으로 채우지 않는다 -- A.5)
        다름                            -> mismatch -> Blocked("model_mismatch"), 답은 버린다
    `<설정>-<개정>` 을 받아 주는 것은 선택이다: 같은 모델의 날짜·번호 개정이 붙어 올 수
    있어서다. 그 원래 값은 원장에 그대로 남는다.
  · 오류 본문은 진단 싱크로만. 원장에는 상태 코드와 이름만.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "orchestrator")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class Blocked(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class BudgetExhausted(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class ModelResult:
    text: str
    reported: "str | None"
    identity: str            # verified | unreported
    event_id: str


@dataclass
class TurnResult:
    parts: list              # [{"text"} | {"function_call": {"name", "args"}}]
    reported: "str | None"
    identity: str
    event_id: str


def _flatten(contents: list, system: str) -> str:
    out = [system] if system else []
    for c in contents:
        for p in c.get("parts", []):
            if "text" in p:
                out.append(p["text"])
            elif "functionResponse" in p:
                out.append("[tool result] " + json.dumps(p["functionResponse"], ensure_ascii=False))
    return "\n\n".join(out)


def identity_of(configured: str, reported: "str | None") -> str:
    if not reported:
        return "unreported"
    r = reported.strip()
    if r.startswith("models/"):
        r = r[len("models/"):]
    if r == configured or r.startswith(configured + "-"):
        return "verified"
    return "mismatch"


def _quota_of(e, status) -> "tuple[str, float] | None":
    """429 면 (minute|day, retryDelay 초), 아니면 None. 분류는 orchestrator/llm_pool 의 것을 그대로 쓴다."""
    t = str(e)
    if status != 429 and "RESOURCE_EXHAUSTED" not in t and " 429" not in t:
        return None
    import llm_pool
    return ("day" if "PerDay" in t else "minute"), llm_pool._retry_delay(e)


def _default_keys() -> list:
    import llm_pool
    return llm_pool.api_keys()


def _default_factory(model: str, key: str):
    import gemini_http
    return gemini_http.Client(model, key)


class FixedModel:
    def __init__(self, cfg, ledger, sink, keys=None, client_factory=None, clock=time.monotonic):
        self.cfg, self.ledger, self.sink = cfg, ledger, sink
        self._keys = keys
        self.factory = client_factory or _default_factory
        self.clock = clock
        self.t0 = clock()
        self.calls = 0

    def _check_budget(self):
        if self.calls >= self.cfg.budgets["model_calls"]:
            raise BudgetExhausted("budget_model_calls")
        if self.clock() - self.t0 > self.cfg.budgets["wall_seconds"]:
            raise BudgetExhausted("budget_wall_seconds")

    def call(self, prompt: str) -> ModelResult:
        r = self.turn([{"role": "user", "parts": [{"text": prompt}]}], [])
        return ModelResult("".join(p.get("text", "") for p in r.parts), r.reported, r.identity, r.event_id)

    def turn(self, contents: list, declarations: list, system: str = "") -> "TurnResult":
        """한 바퀴의 모델 호출. 함수 선언을 주면 Gemini 가 함수 호출 조각을 돌려줄 수 있다.
        클라이언트가 `invoke_tools` 를 못 하면(글만 받는 옛 꼴 · 시험 가짜) 대화를 글로 펴서 `invoke` 로 부른다 --
        그때는 함수 호출이 나올 수 없고, 원장에 `tools_offered: 0` 으로 남는다."""
        keys = self._keys if self._keys is not None else _default_keys()
        if not keys:
            raise Blocked("no_api_key")
        model = self.cfg.model
        last = ""
        quota = []                                       # 키마다 429 였나 -- 전부 429 면 '기다릴 일' 로 끝낸다
        for name, key in keys:
            self._check_budget()
            self.calls += 1
            client = self.factory(model, key)
            native = hasattr(client, "invoke_tools")
            self.ledger.emit("MODEL_CALL_START", "code", {"model": model, "key_name": name, "call_no": self.calls,
                                                          "tools_offered": len(declarations) if native else 0})
            try:
                if native:
                    reply = client.invoke_tools(contents, declarations, system)
                    parts = list(reply.parts)
                else:
                    reply = client.invoke(_flatten(contents, system))
                    parts = [{"text": reply.content or ""}]
            except Exception as e:                       # noqa: BLE001 -- 분류해서 원장에 남긴다
                status = getattr(e, "status", None)
                ename = getattr(e, "name", type(e).__name__)
                self.sink.write(f"model_error:{name}", str(e))
                self.ledger.emit("MODEL_CALL_END", "code", {
                    "result": "error", "status": status, "name": str(ename)[:80], "key_name": name})
                last = f"{status} {ename}"
                quota.append(_quota_of(e, status))
                continue                                 # 같은 모델, 다음 키. 다른 모델은 없다
            reported = getattr(reply, "model_version", None)
            ident = identity_of(model, reported)
            text_len = sum(len(p.get("text", "")) for p in parts)
            self.ledger.emit("MODEL_CALL_END", "code", {"result": "ok", "key_name": name, "chars": text_len,
                                                        "function_calls": sum("function_call" in p for p in parts)})
            eid = self.ledger.emit("MODEL_IDENTITY", "code", {
                "configured": model, "reported": reported, "status": ident})
            if ident == "mismatch":
                self.sink.write("model_text_discarded(mismatch)", json.dumps(parts, ensure_ascii=False))
                raise Blocked("model_mismatch")
            return TurnResult(parts, reported, ident, eid)
        self.sink.write("model_unavailable", f"keys tried: {len(keys)} · last: {last}")
        if quota and all(q is not None for q in quota):
            # CMD-WUG1 S7: 한도는 실패가 아니라 기다릴 일. 하루 한도가 하나라도 있으면 day, 아니면 가장 긴 retryDelay
            scope = "day" if any(q[0] == "day" for q in quota) else "minute"
            secs = max(q[1] for q in quota)
            raise Blocked(f"quota_wait:{scope}:{int(secs)}")
        raise Blocked("model_unavailable")
