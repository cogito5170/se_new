# -*- coding: utf-8 -*-
"""render3d fixed command -- 2D plans, photoreal 3D, and the V&V that checks them against the SAR camera physics.

Contract (dispatch.py): PREFIX and run(text, runner=None, allow_write=True). **Unknown text returns None.**
Heavy work (numpy, matplotlib, a headless browser) runs only in a background child process -- this module must import light (G012).

Commands:
  !렌더                     help
  !렌더 검증                V&V: SAR camera reimplementation, projection model difference, fog (Koschmieder), heightfield, area
  !렌더 예제 [이름]          bundled layouts (hongdae/F1 ... F3, B1, store_module/asis|tobe). No name = list
  !렌더 홍대 [B1|1F|2F|3F]   Hongdae flagship proposal (estimated footprint)
  !렌더 sar [케이스]         SAR world photoreal: default is synthetic DEM + SceneDB (no network), 케이스 = IV&V Taebaek (real DEM)

Outputs go to public_agent_memory/render3d/ (not tracked) -- they never change the repository, so every command works in public channels too.
"""
from __future__ import annotations

from pathlib import Path

PREFIX = "!렌더"
# The log must be a **Path** -- _배경으로 calls .parent.mkdir and .is_file.
_LOG = Path(__file__).resolve().parent / "logs" / "render3d.log"
HELP = (f"`{PREFIX}` — 공간 하나(JSON)를 **2D 평면 · 실사 3D(three.js PBR) · 인터랙티브 HTML** 로 그린다.\n"
        f"`{PREFIX} 검증` — 실사 렌더가 RGB 카메라(sar/camera.py)와 **같은 수식**으로 그리는지 V&V(투영·Beer-Lambert 안개·Koschmieder·지형).\n"
        f"`{PREFIX} 홍대 [B1|1F|2F|3F]` — 홍대 플래그십 제안 도면(추정 외곽, 실측 아님).\n"
        f"`{PREFIX} 예제 [이름]` — 들어 있는 배치(이름 없이 치면 목록).\n"
        f"`{PREFIX} sar [케이스]` — SAR 세계 실사 렌더(기본: 합성 DEM, 케이스: IV&V 태백 실 DEM).\n"
        f"`{PREFIX} 3d비교 [단위|협곡|나무|전부]` — 참조세계 3D 가시성 켬/끔 A/B(요인별 탐지율·신뢰구간). 단위=사거리 단위 수정 영향 · 협곡=저고도 지형가림·레이더그림자 · 나무=나무 배치 쓸기.\n"
        f"`{PREFIX} 영상 [협곡] [V=6000]` — UAV 가 참조세계를 나는 3D 영상(webm) + HTML. 10 Hz 기계상태·1 Hz 운용보고·이벤트·SUT 결정 근거가 실시간 로그로 흐른다.\n"
        "브라우저가 없는 서버에서는 matplotlib 대체로 그리고 **'실사 아님'** 이라고 적는다.")
_FLOORS = {"b1": "B1", "지하": "B1", "1f": "F1", "1층": "F1", "2f": "F2", "2층": "F2", "3f": "F3", "3층": "F3"}


def _cmd(t: str, pfx: str):
    """Only a command if the prefix is followed by whitespace or the end (same rule as eval/sar). Match -> rest; otherwise None."""
    if not t.startswith(pfx):
        return None
    tail = t[len(pfx):]
    if tail and tail[0] not in " \t":
        return None
    return tail.strip()


def _launch(runner, argv, findword):
    launch = runner
    if launch is None:
        try:
            from eval.discord_cmd import _배경으로 as launch
        except Exception as e:                                   # noqa: BLE001
            return None, "배경 실행기를 못 불렀다: %s" % type(e).__name__
    try:
        return launch(argv, _LOG, findword), None
    except Exception as e:                                       # noqa: BLE001
        return None, "못 띄웠다: %s: %s" % (type(e).__name__, e)


def run(text, runner=None, allow_write: bool = True):
    rest = _cmd((text or "").strip(), PREFIX)
    if rest is None:
        return None
    if not rest or rest in ("도움", "help", "?"):
        return HELP
    head, _, tail = rest.partition(" ")
    head_l, tail = head.lower(), tail.strip()
    if head_l in ("검증", "vv"):
        argv, what = ["python3", "-m", "render3d", "vv"], "V&V(RGB 카메라(sar/camera.py)·안개·지형·면적)"
    elif head_l in ("홍대", "hongdae"):
        fl = _FLOORS.get(tail.lower().replace(" ", ""), "F1") if tail else "F1"
        argv, what = ["python3", "-m", "render3d", "example", "hongdae/" + fl, "--views", "aerial,eye"], "홍대 %s 도면·3D" % fl
    elif head_l in ("예제", "example"):
        if not tail:
            argv, what = ["python3", "-m", "render3d", "example", "--list"], "예제 목록"
        else:
            argv, what = ["python3", "-m", "render3d", "example", tail.split()[0][:60]], "예제 %s" % tail.split()[0][:60]
    elif head_l in ("3d비교", "ab"):
        sets = {"단위": "units", "units": "units", "협곡": "canyon", "canyon": "canyon", "나무": "trees", "trees": "trees", "전부": "all", "all": "all"}
        st = sets.get(tail.split()[0].lower(), "main") if tail else "main"
        argv = ["python3", "-m", "render3d", "ab"] + ([] if st == "main" else ["--set", st])
        what = "scene3d A/B(%s, 200 시나리오)" % {"main": "3D 가시성 요인별 효과", "units": "사거리 단위 수정 영향", "canyon": "저고도 협곡 지형가림·레이더그림자",
                                                 "trees": "나무 배치 쓸기", "all": "단위·협곡·나무"}[st]
    elif head_l in ("영상", "anim", "video"):
        import re as _re
        canyon = "협곡" in tail or "canyon" in tail.lower()
        mv = _re.search(r"V\s*=\s*(\d{2,6})", tail)
        argv = ["python3", "-m", "render3d", "anim", "--video"] + (["--canyon"] if canyon else []) + (["--V", mv.group(1)] if mv else [])
        what = "UAV 임무 3D 영상(%s) + 실시간 정책 로그" % ("협곡 AGL 60" if canyon else "언덕 AGL 90")
    elif head_l == "sar":
        case = tail.startswith("케이스") or tail.lower().startswith("case")
        argv = ["python3", "-m", "render3d", "sar"] + (["--case"] if case else [])
        what = "SAR 세계 실사 렌더(%s)" % ("IV&V 태백 실 DEM" if case else "합성 DEM·무네트워크")
    else:
        return "모르는 하위 명령: `%s`\n%s" % (head[:30], HELP)
    ack, err = _launch(runner, argv, "render3d")
    if err:
        return "렌더를 " + err
    return "%s 실행 — 평면·3D·HTML 을 만들고 백엔드(실사/대체)를 적는다. 끝나면 그림을 붙인다.\n%s" % (what, ack)
