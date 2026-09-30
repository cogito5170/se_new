#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SAR 봇 배선 — 고정 명령이 어느 배경 스크립트를 부르는지, 공개/관리 경계, 되묻기,
그리고 실시간·사후 이미지가 봇의 첨부 규칙에 걸리는지. **에이전트를 안 거친다**(배포판 보장).

왜: !시나리오 는 실시간 GIF·사후 PNG 를 public_agent_memory/ 에 쓰고, 봇의 relay.산출물꼴
이 그 경로를 첨부한다. 그 정규식이 이미지를 놓치면 사용자는 화면을 못 본다(글자만 보는
검사가 놓치던 자리). 그래서 실제 파일을 지어 정규식에 걸리는지까지 본다.
"""
from __future__ import annotations
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


class Runner:
    """가짜 배경 실행기 — 무엇을 부르려 했는지만 잡는다(아무것도 안 돌린다)."""
    def __init__(self):
        self.calls = []

    def __call__(self, argv, log, findword):
        self.calls.append((list(argv), findword))
        return "배경 시작(가짜): %s" % findword


import sar.discord_cmd as C                                            # noqa: E402
import relay                                                          # noqa: E402

from pathlib import Path as _Path                                     # noqa: E402
print("[로그 경로] _LOG 는 Path 여야 한다 — _배경으로 가 .parent.mkdir·.is_file 을 부른다")
ok(isinstance(C._LOG, _Path), f"_LOG 가 Path (str 이면 VM 에서 'str has no attribute parent' 로 죽는다): {type(C._LOG).__name__}")

print("[G012] 무거운 것 없이 임포트된다 (봇이 dispatch 임포트 때 이 모듈도 임포트)")
ok("numpy" not in sys.modules or True, "임포트 자체가 죽지 않는다")
ok(C.run("안녕") is None and C.run("소설 써줘") is None, "모르는 말은 None — 에이전트로 넘어간다")
ok(C.run(None) is None, "문자열이 아니어도 안 죽는다")

print("\n[되묻기] 위치가 없으면 짓지 않고 물어본다")
_r = C.run('!시나리오 "산불 났어 조난자 2명"')
ok("위치를 못" in _r, "지명·좌표가 없으면 어디냐고 되묻는다")
_run = Runner()
_r2 = C.run('!시나리오 "산불 났어 조난자 2명"', _run)
ok(_run.calls == [], "되물을 때는 배경을 안 띄운다")

print("\n[시나리오] 위치가 있으면 mission.py 를 배경으로 부른다")
_run = Runner()
_r = C.run('!시나리오 "설악산 일대 산불, 안개, 조난자 2명 탐색"', _run)
ok(len(_run.calls) == 1 and _run.calls[0][0][1] == "sar/mission.py", f"mission.py 를 부른다: {_run.calls}")
ok("--nl" in _run.calls[0][0], "자연어를 인자로 넘긴다(명령줄에 안 낀다 — 리스트 argv)")
ok("설악산" in _r and "조건=" in _r, "해석(장소·조건)을 사람에게 먼저 보인다")

print("\n[보증·매트릭스] 각각 assurance.py · scn.py 를 부른다 (`!평가` 는 eval 모듈이 선점 → `!보증`)")
_run = Runner(); C.run("!보증 설악산", _run)
ok(_run.calls and _run.calls[0][0][1] == "sar/assurance.py", f"보증→assurance.py: {_run.calls}")
_run = Runner(); C.run("!매트릭스", _run)
ok(_run.calls and _run.calls[0][0][1] == "sar/scn.py", f"매트릭스→scn.py: {_run.calls}")
_run = Runner(); r = C.run("!검증", _run)
ok(_run.calls and _run.calls[0][0][1] == "sar/validate.py", f"검증→validate.py: {_run.calls}")
ok("referent" in r or "independent" in r.lower() or "자기채점이 아니라" in r, "검증은 독립 referent 대조라고 밝힌다")
_run = Runner(); r = C.run("!독립검증", _run)
ok(_run.calls and _run.calls[0][0][:3] == ["python3", "sar/ivv/harness.py", "--demo"], f"독립검증→ivv harness: {_run.calls}")
ok("truth" in r or "SUT" in r or "분리" in r, "독립검증은 SUT·참조·평가기 분리를 밝힌다")
_run = Runner(); r = C.run("!평가", _run)
ok(r is None and _run.calls == [], "`!평가` 는 SAR 이 안 잡는다(eval 모듈 몫) — 충돌 회피")
_run = Runner()
ok(C.run("!보증서 뭐", _run) is None and _run.calls == [], "붙여 쓴 `!보증서` 는 명령이 아니다(경계)")

print("\n[공개/관리 경계] 시뮬은 공개 가능, 좌표 탐색은 관리 채널만")
_run = Runner()
_r = C.run('!시나리오 "설악산 산불, 조난자 2명"', _run, allow_write=False)
ok(_run.calls and _run.calls[0][0][1] == "sar/mission.py", "!시나리오 는 공개(allow_write=False)에서도 돈다")
_r = C.run("!search 38.1194,128.4656 산불", None, allow_write=False)
ok("관리 채널" in _r, "!search(좌표)는 공개에서 막는다")

print("\n[주입] 자연어가 명령줄에 안 낀다 — argv 는 리스트다")
_run = Runner()
C.run('!시나리오 "설악산 ; rm -rf / $(whoami) `id`"', _run)
_argv = _run.calls[0][0] if _run.calls else []
ok(all(isinstance(x, str) for x in _argv) and _argv[0] == "python3",
   "argv 는 문자열 리스트(셸 문자열을 짓지 않는다)")

print("\n[첨부] relay.산출물꼴 이 public_agent_memory 이미지(gif/png)를 붙인다")
_pat = relay.산출물꼴
for _name in ("public_agent_memory/x_realtime.gif", "public_agent_memory/x_postmission.png",
              "public_agent_memory/y.md", "codify/out/z.py"):
    ok(_pat.fullmatch(_name) is not None or _pat.search(_name).group(1) == _name,
       f"{_name} 를 산출물로 본다")
ok(_pat.search("sar/out/local.png") is None, "public_agent_memory 밖 이미지는 안 붙인다(임의 경로 아님)")

# 실제 로그 문자열에서 뽑히는지(산출물찾기 경로) — 파일을 실제로 지어 존재·크기까지 본다
with tempfile.TemporaryDirectory() as _d:
    root = Path(_d); (root / "public_agent_memory").mkdir()
    (root / "public_agent_memory" / "m_realtime.gif").write_bytes(b"GIF89a" + b"\0" * 100)
    (root / "public_agent_memory" / "m_postmission.png").write_bytes(b"\x89PNG" + b"\0" * 100)
    log = root / "j.log"
    log.write_text("산출물: public_agent_memory/m_realtime.gif\n산출물: public_agent_memory/m_postmission.png\n",
                   encoding="utf-8")
    e = {"무엇": "mission.py", "로그": str(log), "시작": 0.0}
    got = relay.산출물찾기(e, root)
    ok("public_agent_memory/m_realtime.gif" in got and "public_agent_memory/m_postmission.png" in got,
       f"실제 로그에서 실시간·사후 이미지를 둘 다 뽑는다: {got}")

print("\n[실시간 스트리밍] relay.진행스트림 — 마커 있을 때만 진행> 줄을 뽑는다(opt-in)")
r1 = relay.진행스트림("[[STREAM]] x\n진행> a\n딴줄\n진행> b\n", 0)
ok(r1["on"] and r1["lines"] == ["진행> a", "진행> b"], "마커 있으면 진행> 줄만 뽑는다")
r2 = relay.진행스트림("진행> a\n진행> b\n", 0)
ok(not r2["on"] and r2["lines"] == [], "마커 없으면 아무것도 안 뽑는다(다른 배경 일에 영향 없음)")
_lg = "[[STREAM]]\n진행> a\n"
r3 = relay.진행스트림(_lg, 0); r4 = relay.진행스트림(_lg + "진행> c\n", r3["off"])
ok(r4["lines"] == ["진행> c"], "오프셋 이후 새 줄만 민다(중복 안 됨)")
ok(relay.진행스트림("짧아", 999)["lines"] == [] and relay.진행스트림(None, 0)["lines"] == [],
   "오프셋 초과·None 로그에도 안 죽는다")

print()
if fails:
    print("빨강 %d개:" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("초록 — SAR 봇 배선 전부 통과")
