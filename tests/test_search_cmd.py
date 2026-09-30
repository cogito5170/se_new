#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""!search (SAR 탐색) 명령 배선 검사.

이 명령은 실 배경 실행(DEM 다운로드·matplotlib)을 하므로, 검사는 **runner 를 mock** 으로
주입해 배선 로직만 본다(좌표 파싱·범위·읽기전용·별칭·모르는말 통과). 실제 탐색은 자식
프로세스라 이 검사와 무관하다. dispatch 에 실제로 실려 임포트되는지도 함께 본다(G012).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sar import discord_cmd as sc

fails = 0


def ok(cond, msg):
    global fails
    if not cond:
        print("실패:", msg); fails += 1


_calls = []
def mock(argv, log, name):
    _calls.append((argv, log, name)); return "ack(bg %s)" % name

# 1) 모르는 말에는 None (다른 명령·자연어를 안 뺏는다) -- dispatch 규약
ok(sc.run("!소설 상태") is None, "다른 고정명령을 안 뺏어야 한다")
ok(sc.run("그냥 대화") is None, "자연어에 None 을 줘야 한다(에이전트로 간다)")
ok(sc.run("") is None, "빈 말에 None")

# 2) 도움말
ok("위도" in (sc.run("!search") or ""), "인자 없으면 사용법")
ok("위도" in (sc.run("!search 도움") or ""), "도움 키워드")

# 3) 좌표 파싱 + 배경 launch (mock)
_calls.clear()
r = sc.run("!search 38.1194,128.4656 3000 설악산 산불 조난자 탐색", runner=mock, allow_write=True)
ok(r is not None and "탐색 시작" in r, "유효 좌표면 탐색 시작 ack")
ok(len(_calls) == 1, "배경 실행기를 정확히 한 번 부른다")
if _calls:
    argv, log, name = _calls[0]
    ok(argv[:2] == ["python3", "sar/terrain_search.py"], "자식은 terrain_search.py")
    ok("--lat" in argv and "--lon" in argv and "--radius" in argv, "좌표·반경 인자 전달")
    ok(name == "terrain_search.py", "찾을말(pgrep)은 아스키 -- 한글 패턴 금지(CLAUDE.md)")
    ok(all(ord(c) < 128 for c in name), "찾을말 아스키 확인")

# 4) 잘못된 입력
ok("범위 밖" in (sc.run("!search 999.0,999.0", runner=mock) or ""), "위경도 범위 밖 거절")
ok("좌표를 못" in (sc.run("!search 어디산 근처", runner=mock) or ""), "좌표 없으면 거절")

# 5) 읽기전용 채널(공개 채널)에서는 탐색을 못 띄운다 -- 쓰기 경계
_calls.clear()
ro = sc.run("!search 38.1,128.4", runner=mock, allow_write=False)
ok("관리 채널" in (ro or ""), "읽기전용 채널 거절")
ok(len(_calls) == 0, "읽기전용이면 배경을 안 띄운다")

# 6) !탐색 별칭
ok("탐색 시작" in (sc.run("!탐색 37.5,127.0", runner=mock, allow_write=True) or ""), "!탐색 별칭")

# 7) dispatch 에 실제로 실려 임포트되는가(G012 정신) + run 규약
import dispatch
ok(sc in dispatch.명령들, "dispatch.명령들 에 등록됨")
ok(callable(getattr(sc, "run", None)) and hasattr(sc, "PREFIX"), "PREFIX·run 규약")
ok(dispatch.run("!search", None, True) is not None, "dispatch.run 이 !search 를 잡는다")

# 8) !시나리오 "<NL>" -- 자연어 상황 -> mission.py 배경(실시간 GIF + 사후 PNG). 공개 채널 가능.
_calls.clear()
ok("자연어 상황" in (sc.run("!시나리오") or ""), "인자 없으면 사용법")
r = sc.run('!시나리오 "설악산 일대 산불, 비, 조난자 2명 탐색"', runner=mock, allow_write=True)
ok(r is not None and "시나리오 실행" in r, "위치 있으면 실행 ack")
ok(len(_calls) == 1, "시나리오 배경 실행기 한 번")
if _calls:
    a2 = _calls[0]
    ok(a2[0][:2] == ["python3", "sar/mission.py"], "자식은 mission.py(실시간+사후 한 번에)")
    ok("--nl" in a2[0], "자연어를 --nl 로 전달")
    ok(a2[2] == "mission.py" and all(ord(c) < 128 for c in a2[2]), "찾을말 아스키")

# 공개 채널(allow_write=False)에서도 시나리오는 돈다 -- 사용자 요구("공개채널에서도 가능하게")
_calls.clear()
rp = sc.run('!시나리오 "포지타노 산불, 조난자 2명"', runner=mock, allow_write=False)
ok(rp is not None and "시나리오 실행" in rp, "시나리오는 공개 채널에서도 실행된다")
ok(len(_calls) == 1, "공개에서도 배경을 띄운다")

# 위치를 못 알아들으면 짓지 않고 되묻는다 (필수 조건 없으면 물어본다)
_calls.clear()
ask = sc.run('!시나리오 "산불 났어 조난자 2명"', runner=mock, allow_write=True)
ok("위치를 못" in (ask or ""), "위치 없으면 되묻는다")
ok(len(_calls) == 0, "되물을 때는 배경 안 띄운다")

# 9) !보증 · !매트릭스 -- 각각 assurance.py · scn.py (공개 채널 가능)
#    `!평가` 는 eval 모듈이 선점 → SAR 보증은 `!보증`(충돌 회피, test_eval.py 가 붙든다)
_calls.clear()
ok("보증평가" in (sc.run("!보증", runner=mock, allow_write=False) or ""), "!보증 은 공개에서도 돈다")
ok(_calls and _calls[0][2] == "assurance.py", "!보증 -> assurance.py")
_calls.clear()
ok(sc.run("!평가", runner=mock) is None and len(_calls) == 0, "!평가 는 SAR 이 안 잡는다(eval 몫)")
_calls.clear()
ok("매트릭스" in (sc.run("!매트릭스", runner=mock, allow_write=False) or ""), "!매트릭스 는 공개에서도 돈다")
ok(_calls and _calls[0][2] == "scn.py", "!매트릭스 -> scn.py")

ok(sc.run("!시나리오abc") is None or "시나리오" in (sc.run("!시나리오abc") or ""), "접두사 경계")

print("search_cmd: %d FAIL" % fails if fails else "search_cmd: ALL PASS")
sys.exit(1 if fails else 0)
