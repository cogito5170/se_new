"""루프 탐지기 -- 정책 F 를 코드로.

추적하는 것: 실행·작업 ID · 바퀴 번호 · 같은 (도구, 인자) · 같은 실패 코드 · 새 관측이 있었나.

    LOOP_DETECTED     탐지기가 평가했고 걸렸다
    NO_LOOP_DETECTED  탐지기가 **평가했고** 안 걸렸다
    UNKNOWN           평가를 못 했다(지문을 못 만듦 -- 인자가 JSON 으로 안 펴짐 등)

탐지 조건(문턱은 설정의 `loop`, 2 이상):
    same_action   같은 (도구, 인자 정규형)이 문턱 번째 나왔다
    same_failure  같은 실패 코드가 문턱 번 **이어서** 나왔다
    no_progress   새 관측이 없는 바퀴가 문턱 번 이어졌다(관측 = 도구 출력·오류의 해시. 처음 보는 해시가 새 관측)

바퀴마다 `evaluate` 를 부르면 LOOP_EVAL 사건을 **반드시** 하나 남긴다. 렌더러는 LOOP_EVAL 이 없으면 UNKNOWN 으로
그리므로, "로그가 없으니 루프가 없다" 의 길은 없다.

**한계:** 같은 도구를 인자만 조금씩 바꿔 맴도는 것(경로 a, a/, ./a ...)은 same_action 이 못 잡는다. 그 출력이
같으면 no_progress 가 늦게 잡는다.
"""
from __future__ import annotations

import hashlib
import json

LOOP_DETECTED, NO_LOOP_DETECTED, UNKNOWN = "LOOP_DETECTED", "NO_LOOP_DETECTED", "UNKNOWN"


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


class LoopDetector:
    def __init__(self, thresholds: dict):
        self.t = dict(thresholds)
        self.actions: dict = {}
        self.seen_obs: set = set()
        self.fail_streak = (None, 0)
        self.stale = 0
        self.evaluations = 0

    def would_repeat(self, action) -> bool:
        """Validate 단계에서 쓴다: 이 (도구, 인자)를 지금 돌리면 same_action 문턱에 닿는가.
        닿으면 **돌리기 전에** 거절한다 -- 같은 일을 또 하고 나서 고리라고 말하는 것은 늦다.
        지문을 못 만들면 False(막지 않는다) -- 그 바퀴의 evaluate 가 UNKNOWN 을 적는다."""
        try:
            k = _h([list(action)])
        except (TypeError, ValueError):
            return False
        return self.actions.get(k, 0) + 1 >= self.t["same_action"]

    def evaluate(self, L, turn: int, action, observation, failure: "str | None", task_id: str = "") -> str:
        """action = [(도구 이름, 인자), ...] 또는 None(도구 없이 끝난 바퀴). observation = 그 바퀴에 새로 본 것."""
        self.evaluations += 1
        try:
            a_keys = [_h([list(a)]) for a in action] if action is not None else []
            o_key = _h(observation) if observation is not None else None
        except (TypeError, ValueError) as e:
            L.emit("LOOP_EVAL", "code", {"turn": turn, "result": UNKNOWN, "note": f"fingerprint_failed:{type(e).__name__}"},
                   task_id=task_id)
            return UNKNOWN
        hits = []
        for a_key in a_keys:
            self.actions[a_key] = self.actions.get(a_key, 0) + 1
            if self.actions[a_key] >= self.t["same_action"] and "same_action" not in hits:
                hits.append("same_action")
        if failure:
            prev, n = self.fail_streak
            self.fail_streak = (failure, n + 1 if prev == failure else 1)
            if self.fail_streak[1] >= self.t["same_failure"]:
                hits.append("same_failure")
        else:
            self.fail_streak = (None, 0)
        if o_key is not None and o_key not in self.seen_obs:
            self.seen_obs.add(o_key)
            self.stale = 0
        else:
            self.stale += 1
            if self.stale >= self.t["no_progress"]:
                hits.append("no_progress")
        result = LOOP_DETECTED if hits else NO_LOOP_DETECTED
        L.emit("LOOP_EVAL", "code", {"turn": turn, "result": result, "kinds": hits,
                                     "actions": a_keys, "failure": failure, "stale": self.stale}, task_id=task_id)
        return result
