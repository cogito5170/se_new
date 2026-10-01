"""agentic 앞단 -- WALP(walp/llmfront.py, 진짜 판정기 파일)가 잡담을 끝내고 나머지를 Gemini 로 넘기는가.

모델은 가짜(배선 확인). 판정기는 **진짜**다 -- 묶여 온 `walp/data/front_model.json` 을 그대로 읽는다.

    python3 tests/test_agentic_front.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestrator"))

from agentic import config as C                        # noqa: E402
from agentic.ledger import read_events                 # noqa: E402
from agentic.run import run                            # noqa: E402

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


MODEL = "gemini-3.1-flash-lite"
SHA = hashlib.sha256((ROOT / "walp/data/front_model.json").read_bytes()).hexdigest()


class _Reply:
    def __init__(self, t):
        self.content, self.model_version = t, MODEL


class Fac:
    def __init__(self):
        self.seen, self.prompts = [], []

    def __call__(self, model, key):
        self.seen.append(model)
        fac = self

        class _C:
            def invoke(self, prompt):
                fac.prompts.append(prompt)
                return _Reply("모델의 답")
        return _C()


def cfg_at(d, **over):
    base = {"model": MODEL, "model_fallback": False,
            "budgets": {"model_calls": 4, "forgery_retries": 1, "wall_seconds": 180, "tasks": 20,
                        "sandbox_seconds": 60, "react_turns": 6, "tool_output_chars": 4000},
            "sandbox": "sandbox/", "mandatory_checks": ["sandbox"], "allowed_kinds": ["read", "compute"],
            "loop": {"same_action": 2, "same_failure": 2, "no_progress": 3},
            "rag": {"k": 3, "repo_graph": False, "record": False}, "repair": {"trip_after": 2},
            "front": {"walp": True, "model_sha256": SHA}}
    base.update(over)
    p = Path(d) / f"cfg{len(list(Path(d).glob('cfg*')))}.json"
    p.write_text(json.dumps(base))
    return C.load(p)


KEYS = [("GEMINI_API_KEY", "k")]

with tempfile.TemporaryDirectory() as tmp:
    T = Path(tmp)
    cfg = cfg_at(T)
    n = [0]

    def go(text, c=None, small_talk=None):
        n[0] += 1
        f = Fac()
        st, rd, txt = run(text, c or cfg, root=T, keys=KEYS, client_factory=f, run_id=f"f{n[0]}",
                          small_talk=small_talk)
        return st, rd, txt, f

    print("[설정] 저장소 설정이 묶여 온 판정기 파일의 해시와 맞는다")
    real = C.load()
    ok(real.front.get("walp") is True and real.front.get("model_sha256") == SHA,
       "agentic/config.json 의 front.model_sha256 == walp/data/front_model.json 의 sha256")
    for bad, why in [({"front": {"walp": True}}, "front_model_sha256_required"),
                     ({"front": {"walp": "yes", "model_sha256": SHA}}, "front_invalid")]:
        try:
            cfg_at(T, **bad)
            ok(False, f"{why} 를 거절한다")
        except C.ConfigError as e:
            ok(str(e) == why, f"{why} 를 거절한다")

    print("[앞단] 잡담은 WALP 가 끝낸다 -- 모델 호출 0")
    for text, act in [("고마워", "thanks"), ("안녕", "greet"), ("너 누구야", "about_self")]:
        st, rd, txt, f = go(text)
        ok(st == "DONE" and f.seen == [] and f"잡담({act})" in txt and "모델 호출 0" in txt,
           f"{text!r} -> {act}, 모델 안 부름")
    ok("'//'" in txt, "화면이 건너뛰는 법('//')을 같이 보인다")
    ok("이 실행은 모델을 부르지 않았다" in txt, "모델 칸: 부르지 않았다")
    ev = [e for e in read_events(rd) if e["type"] == "TERMINAL"][0]["data"]
    ok(ev["reason"] == "walp_front_smalltalk", "종료 사유 walp_front_smalltalk")

    print("[앞단] 일이 담긴 말은 모델로 -- 이 대화에서 실제로 보낸 말들")
    for text in ["지어", "바로 1단계 시작해", "설계 시작해라",
                 "4. gemini-3.1-flash-lite. VM 안쓸거야 sandbox/로 정책 인정할게. 바로 1단계 시작해",
                 "Walp래포애서 Walp-front를 너의 앞단에 적용해줘", "다음 주 회의 잡아줘"]:
        st, rd, txt, f = go(text)
        ok(st == "DONE" and f.seen == [MODEL] and "WALP 가 넘겼다" in txt, f"{text[:30]!r} -> 모델")

    print("[앞단] '//' 는 건너뛴다")
    st, rd, txt, f = go("//고마워")
    ok(f.seen == [MODEL] and "'//' 로 건너뛰었다" in txt, "'//고마워' -> 모델")
    ok(f.prompts and f.prompts[0].endswith("고마워") and "//고마워" not in f.prompts[0], "모델에는 '//' 를 떼고 보낸다")

    print("[D.6] 판정기 해시가 다르면 앞단을 끄고 넘긴다 -- 조용히가 아니라")
    st, rd, txt, f = go("고마워", c=cfg_at(T, front={"walp": True, "model_sha256": "0" * 64}))
    ok(f.seen == [MODEL] and "앞단: 꺼짐 (model_sha256_mismatch)" in txt, "해시 불일치 -> 꺼짐(사유 보임) -> 모델")

    print("[막지 않는다] 앞단이 터지면 모델로, 사유는 적는다")

    class Broken:
        def judge(self, t):
            raise RuntimeError("x")
    st, rd, txt, f = go("고마워", small_talk=Broken())
    ok(st == "DONE" and f.seen == [MODEL] and "front_error:RuntimeError" in txt, "앞단 예외 -> 모델, 화면에 사유")
    st, rd, txt, f = go("고마워", c=cfg_at(T, front={"walp": False}))
    ok(f.seen == [MODEL] and "config_off" in txt, "설정으로 끄면 꺼짐(config_off)")

    print("[알려진 약점] 섞인 말은 잡담으로 삼킨다 -- WALP 저장소가 잰 9~10/60 과 같은 부류")
    st, rd, txt, f = go("고마워요 이제 머지해줘")
    ok(f.seen == [] and "잡담(thanks)" in txt,
       "'고마워요 이제 머지해줘' 는 지금 삼켜진다. 이 줄이 빨개지면 판정기가 바뀐 것이다 -- 설계 문서의 약점 칸도 고쳐라")

print()
if fails:
    print(f"agentic 앞단: {len(fails)}개 실패 -- {fails}")
    sys.exit(1)
print("agentic 앞단: 잡담 끝냄 · 일은 넘김 · '//' · 해시 불일치 · 고장 · 알려진 약점 -- 통과")
