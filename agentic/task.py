"""작업 명세(TaskSpec)와 실행 레지스트리 -- 정책 G 의 A·B 를 **이름이 아니라 함수로** 들고 온다.

정책 G 는 A_TO_B 를 평가하라고 하지만 A·B 가 무엇인지는 말하지 않는다. 그래서 모델이 채웠다
(1단계 진단). 여기서는 작업마다

    primary        -> 실행할 행동 이름 (레지스트리에 있어야 한다)
    post           -> 그 뒤에 참이어야 하는 술어 이름  (= B)
    alt / post_alt -> 대체 행동과 그 술어            (= NOT_A_TO_B_PRIME 의 B')
    followup / post_followup -> NOT_B_PRIME 후속과 그 술어
    verify_argv    -> sandbox 에서 돌릴 검증 명령(정책 C). 없으면 '필수 시험 없음' 으로 막힌다

를 들고 온다. **대체를 두려면 넷(alt · post_alt · followup · post_followup)을 다 둬야 한다.**
반만 있으면 명세 검증에서 거절한다 -- 반쪽 대체는 실행 시점에 '정의 안 됨 = FALSE' 로 빠지는데,
그것을 실행 시점까지 미뤄 둘 이유가 없다.

행동은 `fn(inputs: dict, state: dict) -> dict`, 술어는 `fn(state: dict, task: TaskSpec) -> bool`.
술어가 **정확히 `True`** 를 돌려줄 때만 TRUE 다. `1` · `"yes"` · `None` · 예외는 전부 UNKNOWN 이고
UNKNOWN 은 FALSE 로 다룬다(정책 G: 없는 결과를 TRUE 로 읽지 마라).
"""
from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TaskSpec:
    name: str
    goal: str
    primary: str
    post: str
    inputs: dict = field(default_factory=dict)
    permissions: tuple = ("read", "compute")
    alt: "str | None" = None
    post_alt: "str | None" = None
    followup: "str | None" = None
    post_followup: "str | None" = None
    verify_argv: "tuple | None" = None
    # 이 작업을 낳은 사건(사용자 메시지 하나 = 사건 하나). 멱등키에 섞인다 -- 같은 사건이 두 번 오면
    # 한 번만 돌고, **다른 사건이 같은 일을 시키면** 다시 돈다(읽기 도구의 답은 그때마다 새로 읽어야 한다)
    event: str = ""

    def canonical(self) -> str:
        d = asdict(self)
        d["permissions"] = sorted(d["permissions"])
        d["verify_argv"] = list(d["verify_argv"]) if d["verify_argv"] is not None else None
        return json.dumps(d, ensure_ascii=False, sort_keys=True, default=str)


@dataclass(frozen=True)
class Action:
    kind: str           # read | compute | write | shell | net
    fn: object


class Registry:
    def __init__(self, actions: "dict[str, Action]", predicates: "dict[str, object]"):
        self.actions, self.predicates = dict(actions), dict(predicates)

    def hash(self) -> str:
        """이름 · 종류 · **함수 원문** 의 해시(정책 D.6: 검증된 판과 내용 해시에 묶는다).
        원문을 못 읽는 함수(내장 · 람다 일부)는 qualname 으로 -- 그 한계는 해시에 그대로 섞인다."""
        h = hashlib.sha256()
        for kind_tag, table in (("A", self.actions), ("P", self.predicates)):
            for name in sorted(table):
                obj = table[name]
                fn = obj.fn if isinstance(obj, Action) else obj
                try:
                    src = inspect.getsource(fn)
                except (OSError, TypeError):
                    src = getattr(fn, "__qualname__", repr(fn))
                h.update(f"{kind_tag}|{name}|{getattr(obj, 'kind', '')}|".encode())
                h.update(hashlib.sha256(src.encode()).digest())
        return h.hexdigest()


def idempotency_key(spec: TaskSpec, registry_hash: str) -> str:
    return hashlib.sha256((spec.canonical() + "|" + registry_hash).encode()).hexdigest()


def validate(spec: TaskSpec, reg: Registry, allowed_kinds) -> list:
    """사유 목록. 비었으면 통과."""
    why = []
    if not spec.name or not spec.goal:
        why.append("name_or_goal_missing")
    if not isinstance(spec.inputs, dict):
        why.append("inputs_not_dict")
    perms = set(spec.permissions)
    bad_perm = perms - set(allowed_kinds)
    if bad_perm:
        why.append(f"permission_not_allowed:{','.join(sorted(bad_perm))}")
    for slot in ("primary", "alt", "followup"):
        nm = getattr(spec, slot)
        if nm is None:
            continue
        a = reg.actions.get(nm)
        if a is None:
            why.append(f"unknown_action:{slot}:{nm}")
        elif a.kind not in perms:
            why.append(f"action_kind_not_permitted:{slot}:{nm}:{a.kind}")
    for slot in ("post", "post_alt", "post_followup"):
        nm = getattr(spec, slot)
        if nm is not None and nm not in reg.predicates:
            why.append(f"unknown_predicate:{slot}:{nm}")
    if not spec.primary:
        why.append("primary_missing")
    if not spec.post:
        why.append("post_missing")
    alt_parts = (spec.alt, spec.post_alt, spec.followup, spec.post_followup)
    if any(x is not None for x in alt_parts) and not all(x is not None for x in alt_parts):
        why.append("alternative_incomplete")
    if spec.verify_argv is not None and (not isinstance(spec.verify_argv, (list, tuple))
                                         or not spec.verify_argv
                                         or not all(isinstance(x, str) for x in spec.verify_argv)):
        why.append("verify_argv_invalid")
    return why
