"""WALP 앞단 -- 제어부의 맨 앞. 잡담은 WALP 가 끝내고(모델 호출 0), 나머지만 Gemini 로 넘긴다.

출처: github.com/cogito5170/walp `walp/llmfront.py` · `walp/data/front_model.json` (커밋 2c2ab72, 2026-10-01).
판정기 파일은 **설정에 박은 sha256 과 맞을 때만** 쓴다(정책 D.6). 다르면 앞단을 끄고 그 사실을 원장과 화면에
남긴 채 모델로 넘긴다 -- 다른 판정기가 조용히 사람의 말을 막는 길을 두지 않는다.

**알고 쓸 것(WALP 저장소가 잰 것, 여기서 다시 재지 않았다):** worldplan 봉인 모음에서 토큰을 38~44% 줄였지만,
일이 섞인 말("고마워~ 근데 latam 을 화요일로 옮겨줘")을 잡담으로 읽어 60 문장 중 9~10 개를 모델에 안 보냈다.
그래서:
  · `//` 로 시작하는 말은 앞단을 건너뛴다(WALP 의 규약 그대로)
  · 앞단이 답한 실행은 화면에 **그 사실과 건너뛰는 법**을 같이 그린다
  · 앞단이 터지면 막지 않고 모델로 넘긴다(사람의 말을 잃는 쪽으로 틀리지 않는다 -- WALP 훅과 같은 규율).
    다만 조용히 넘기지 않는다: WALP_FRONT 사건에 오류를 적는다
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "github.com/cogito5170/walp@2c2ab722fa00cfdf33427709174901398a3da71f"
BYPASS = "//"


@dataclass
class FrontResult:
    route: str              # small | model | bypass | disabled
    act: "str | None"
    reply: "str | None"
    data: dict


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def judge(text: str, cfg, small_talk=None) -> FrontResult:
    """앞단 판정. 사건은 부르는 쪽이 적는다(이 함수는 원장을 모른다)."""
    fc = cfg.front
    if not fc.get("walp"):
        return FrontResult("disabled", None, None, {"reason": "config_off"})
    if text.lstrip().startswith(BYPASS):
        return FrontResult("bypass", None, None, {"reason": "user_bypass"})
    t0 = time.monotonic()
    try:
        from walp import llmfront as LF
        model_path = Path(fc.get("model_path") or LF.MODEL)
        got = _sha(model_path)
        if got != fc["model_sha256"]:
            return FrontResult("disabled", None, None, {"reason": "model_sha256_mismatch",
                                                         "expected": fc["model_sha256"][:16], "got": got[:16]})
        st = small_talk or LF.SmallTalk(model_path)
        j = st.judge(text)
    except Exception as e:                               # noqa: BLE001 -- 막지 않되 적는다
        return FrontResult("disabled", None, None, {"reason": f"front_error:{type(e).__name__}"})
    data = {"act": j["act"], "unknown": j["unknown"], "winner": j["winner"],
            "ms": round((time.monotonic() - t0) * 1000, 1), "model_sha256": got[:16], "source": SOURCE}
    if j["small"]:
        return FrontResult("small", j["act"], LF.REPLY[j["act"]], data)
    return FrontResult("model", j["act"], None, data)


def strip_bypass(text: str) -> str:
    s = text.lstrip()
    return s[len(BYPASS):].lstrip() if s.startswith(BYPASS) else text
