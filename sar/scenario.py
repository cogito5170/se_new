#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자연어 시나리오 파싱 -> (랜덤 실좌표 · 물리 조건 · 조난자 수).

예: !시나리오 "설악산 일대에서 산불 발생. 비가 오고 있는 상황이며 조난자 2명으로 추정된다. 주변 일대를 탐색하여라."
  -> 장소=설악산(일대) -> 그 산 영역서 **랜덤 실좌표** 하나 뽑음(매 실행 다른 지점),
     조건=비(rain, 물리 모델), 조난자=2명, 사건=산불(화점 근처 연기·글레어).

'랜덤 좌표 + 실제 지리정보'를 위해: 장소명을 가제티어로 대략 좌표화한 뒤 ±수 km 흔들어
매번 다른 실지점을 만들고, 그 좌표의 실제 DEM 을 terrain.fetch_dem 이 받아온다.
장소를 못 알아보면 가제티어에서 무작위 산악지를 고른다(바다·평지 회피 -> 실지형 보장).
"""
import re
import math

# 가제티어(대략 좌표). '일대'는 여기에 무작위 jitter 로 실좌표를 만든다.
# ※ DEM(AWS Terrarium)은 전 세계 무키 -> 아래에 없는 곳은 **좌표를 직접** 주면 된다(어디든).
GAZETTEER = {
    # 한국 산악
    "설악산": (38.1194, 128.4656), "지리산": (35.3372, 127.7305), "북한산": (37.6586, 126.9880),
    "한라산": (33.3617, 126.5292), "태백산": (37.0966, 128.9156), "오대산": (37.7936, 128.5430),
    "소백산": (36.9576, 128.4856), "덕유산": (35.8603, 127.7472), "속리산": (36.5339, 127.8700),
    "가야산": (35.8219, 128.1206), "치악산": (37.3717, 128.0503), "월악산": (36.8869, 128.1147),
    # 한국 도심/평지 (강원·경기)
    "춘천": (37.8813, 127.7300), "원주": (37.3422, 127.9202), "판교": (37.3947, 127.1112),
    "수원": (37.2636, 127.0286), "가평": (37.8315, 127.5105), "포천": (37.8949, 127.2003),
    # 세계
    "포지타노": (40.6280, 14.4850), "positano": (40.6280, 14.4850),
    "로마": (41.9028, 12.4964), "rome": (41.9028, 12.4964),
    "알프스": (46.0207, 7.7491), "체르마트": (46.0207, 7.7491), "zermatt": (46.0207, 7.7491), "alps": (46.0207, 7.7491),
    "라플란드": (68.4200, 27.4000), "핀란드": (68.4200, 27.4000), "lapland": (68.4200, 27.4000), "finland": (68.4200, 27.4000),
    "그랜드캐니언": (36.1069, -112.1129), "grandcanyon": (36.1069, -112.1129),
    "히말라야": (27.9881, 86.9250), "쿰부": (27.9881, 86.9250), "에베레스트": (27.9881, 86.9250),
    "himalaya": (27.9881, 86.9250), "everest": (27.9881, 86.9250),
    "돌로미티": (46.4102, 11.8440), "dolomites": (46.4102, 11.8440),
    "요세미티": (37.7456, -119.5936), "yosemite": (37.7456, -119.5936),
}
# 좌표 직접 지정: "위도,경도" (소수점). 있으면 가제티어보다 우선.
_COORD = re.compile(r"(-?\d{1,3}\.\d{2,})\s*[,/ ]\s*(-?\d{1,3}\.\d{2,})")

# 날씨/조건 키워드 -> sensors.COND_PHYS 의 조건. 위에서부터 먼저 걸리는 것이 이긴다.
_COND_KW = [
    ("센서고장", r"센서\s*고장|센서\s*먹통|장비\s*고장|카메라\s*고장|imu\s*고장|failure"),
    ("안개", r"안개|박무|짙은\s*안개|시계\s*불량"),
    ("비",   r"비\b|우천|강우|비가|빗"),
    ("야간", r"야간|밤|심야|어둠|저녁|일몰\s*후"),
    ("연기", r"연기|매연|스모그"),
    ("먼지", r"먼지|황사|미세먼지|분진"),
    ("화재", r"화재\s*현장|불길\s*속|화염"),
]


def parse(nl: str, rng=None):
    """자연어 -> 시나리오 dict. rng 없으면 결정적(테스트용) 기본 시드."""
    import random
    rng = rng or random.Random(0)
    t = (nl or "").strip().strip('"').strip("'")
    tl = t.lower()
    # 장소: (1) 좌표 직접(전세계 아무데나) 우선, (2) 지명(한/영), (3) 무작위
    place = None; base = None; jit_m = 3000.0; place_source = None
    mco = _COORD.search(t)
    if mco:
        la, lo = float(mco.group(1)), float(mco.group(2))
        if -90 <= la <= 90 and -180 <= lo <= 180:
            place = "직접좌표"; base = (la, lo); jit_m = 800.0; place_source = "coord"
    if base is None:
        for name in GAZETTEER:                                    # 지명(영문 소문자 키 포함)
            if name in t or name in tl:
                place = name; base = GAZETTEER[name]; place_source = "gazetteer"; break
    if base is None:
        place = rng.choice([k for k in GAZETTEER if not k.isascii()])  # 못 알아보면 무작위(한글 지명)
        base = GAZETTEER[place]; place_source = "random"
    # '일대' -> 그 영역서 랜덤 실좌표(jitter)
    dlat = rng.uniform(-1, 1) * jit_m / 111320.0
    dlon = rng.uniform(-1, 1) * jit_m / (111320.0 * math.cos(math.radians(base[0])))
    lat, lon = base[0] + dlat, base[1] + dlon
    # 사건(산불)
    fire = bool(re.search(r"산불|화재|불이|들불|산림\s*화재", t))
    # 대기 조건: 명시된 날씨 우선, 없고 산불이면 화재(연기·글레어), 그래도 없으면 무작위
    condition = None
    for name, pat in _COND_KW:
        if re.search(pat, t):
            condition = name; break
    if condition is None:
        condition = "화재" if fire else rng.choice(["정상", "야간", "안개", "먼지", "비"])
    # 조난자 수
    m = re.search(r"(?:조난자|실종자|요구조자|생존자|조난객)\s*(?:약\s*)?(\d+)\s*명", t)
    n_surv = int(m.group(1)) if m else rng.randint(1, 3)
    n_surv = max(1, min(5, n_surv))
    return dict(nl=t, place=place, lat=lat, lon=lon, fire=fire, condition=condition,
                n_surv=n_surv, base=base, place_source=place_source)


if __name__ == "__main__":
    import sys, random
    nl = sys.argv[1] if len(sys.argv) > 1 else \
        "설악산 일대에서 산불 발생. 비가 오고 있는 상황이며 조난자 2명으로 추정된다. 주변 일대를 탐색하여라."
    s = parse(nl, random.Random())
    print("장소:", s["place"], "-> 랜덤 실좌표 (%.5f, %.5f)" % (s["lat"], s["lon"]))
    print("조건:", s["condition"], "| 산불:", s["fire"], "| 조난자:", s["n_surv"], "명")
