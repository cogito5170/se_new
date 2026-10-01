"""얼린 설정 -- 정책 A(Immutable Configuration)를 코드로.

설정은 `agentic/config.json` 한 파일이고, **실행마다 그 바이트의 sha256 을 원장 첫 줄에 적는다.**
설정이 바뀐 실행은 다른 실행이다.

거절하는 것(정책 A.1 · A.2):
  · 모델 이름이 비었거나 문자열이 아님
  · `model_fallback` 이 false 가 아님 -- 폴백을 켜는 길을 설정에 두지 않는다
  · 모델 목록처럼 보이는 칸(`models` · `fallback_models` · `fallback`) -- 모델은 하나다
  · 예산이 양의 정수가 아님
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PATH = HERE / "config.json"

BUDGET_KEYS = ("model_calls", "forgery_retries", "wall_seconds")
_FORBIDDEN_KEYS = ("models", "fallback_models", "fallback")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    model: str
    budgets: dict
    sandbox: str
    sha256: str
    path: str


def load(path: "str | Path | None" = None) -> Config:
    p = Path(path or DEFAULT_PATH)
    raw = p.read_bytes()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(f"config_not_json: {e}") from None
    if not isinstance(d, dict):
        raise ConfigError("config_not_object")
    model = d.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ConfigError("model_missing")
    if d.get("model_fallback") is not False:
        raise ConfigError("model_fallback_must_be_false")
    for k in _FORBIDDEN_KEYS:
        if k in d:
            raise ConfigError(f"forbidden_key:{k}")
    b = d.get("budgets")
    if not isinstance(b, dict):
        raise ConfigError("budgets_missing")
    for k in BUDGET_KEYS:
        v = b.get(k)
        # bool 은 int 의 하위형이라 따로 막는다 -- true 가 1 로 통과하면 안 된다
        if not isinstance(v, int) or isinstance(v, bool) or v < (0 if k == "forgery_retries" else 1):
            raise ConfigError(f"budget_invalid:{k}")
    return Config(model=model.strip(), budgets=dict(b), sandbox=str(d.get("sandbox", "")),
                  sha256=hashlib.sha256(raw).hexdigest(), path=str(p))
