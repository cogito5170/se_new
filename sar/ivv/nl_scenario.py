# -*- coding: utf-8 -*-
"""자연어 상황 → IV&V 5센서 폐루프 시뮬레이션 시나리오(reference.Reference 가 먹는 dict).

지상국(봇)이 자연어를 구조로 바꾸고 드론은 결정적 정책만 돈다(온보드 LLM 없음) — 기존 !시나리오 계약.
여기서는 5센서 IV&V 미션용 spec 을 낸다: 표적 수·센서·수관(false-)·decoy/clutter(false+)·환경.

정직: 파서는 '무엇을 시뮬레이션할지'만 정한다. false+/false- 개수는 물리·평가기가 낸다(여기서 안 정함).
정지(static) 자체는 놓침 사유가 아니다 — liveness 는 미세도플러라 정지한 사람도 호흡으로 잡힌다.
놓침(FN)은 **수관 은폐**로 생긴다(RGB/열이 가려 CMPC≥2 미달). 그래서 FN 후보를 수관 아래로 놓는다.
"""
from __future__ import annotations
import math
import random
import re

_KNUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}

_COORD = re.compile(r"(-?\d{1,3}\.\d{2,})\s*[,/ ]\s*(-?\d{1,3}\.\d{2,})")


# DMZ 인근 실좌표(비무장지대 접경 — 실 지형 DEM 조회용). 고성=강원 동부, 파주=경기 서부.
_DMZ = {
    "고성 DMZ": (38.3000, 128.4400), "고성 통일전망대": (38.2970, 128.4430), "고성": (38.3000, 128.4400),
    "파주 DMZ": (37.9000, 126.7100), "파주 도라전망대": (37.9000, 126.7100), "파주": (37.9000, 126.7100),
    "임진각": (37.8880, 126.7340), "판문점": (37.9550, 126.6770), "철원 DMZ": (38.2060, 127.2100), "철원": (38.2060, 127.2100),
}


def _place(text, default_lat, default_lon):
    """자연어에서 지명·좌표 → (place, lat, lon). 실 DEM 조회에 쓴다. 좌표가 지명보다 우선.
    좌표 인용은 실좌표(DMZ 접경·sar.scenario 가제티어)를 그대로 쓴다 — 좌표를 지어내지 않는다."""
    m = _COORD.search(text)
    if m:
        la, lo = float(m.group(1)), float(m.group(2))
        if -90 <= la <= 90 and -180 <= lo <= 180:
            return ("좌표(%.4f,%.4f)" % (la, lo), la, lo)
    for name in sorted(_DMZ, key=len, reverse=True):    # DMZ 지명 우선(긴 이름 먼저)
        if name in text:
            return (name, *_DMZ[name])
    try:
        from sar.scenario import GAZETTEER as _G
    except Exception:                               # noqa: BLE001
        _G = {}
    low = text.lower()
    for name, (la, lo) in _G.items():
        if name in text or (name.isascii() and name in low):
            return (name, la, lo)
    if re.search(r"강원", text) and "설악산" in _G:     # '강원도 산맥' → 대표 실산(설악산)
        return ("설악산", *_G["설악산"])
    if "DMZ" in text or "비무장" in text:               # 지명 없이 DMZ 만 → 고성 DMZ
        return ("고성 DMZ", *_DMZ["고성 DMZ"])
    return (None, default_lat, default_lon)


def _count_people(text):
    m = re.search(r"(\d+)\s*명", text)
    if m:
        return int(m.group(1))
    for w, n in _KNUM.items():
        if re.search(w + r"\s*명", text):
            return n
    m = re.search(r"(?:실종|조난|생존자|대상|요구조)\D{0,4}(\d+)", text)
    return int(m.group(1)) if m else None


def _env(text):
    """환경어 → (V 가시거리 m, illum lux). 기본 맑은 주간."""
    V, illum = 8000.0, 20000.0
    if re.search(r"야간|밤|새벽|어둠|심야|일몰", text):
        illum = 0.5
    if re.search(r"안개|연무|박무|시계\s*불량", text):
        V = 400.0
    if re.search(r"연기|매연|스모그|산불|화재|화염", text):
        V = 300.0
    if re.search(r"비|우천|강우|빗", text):
        V = 2000.0
    if re.search(r"먼지|황사|분진", text):
        V = 1500.0
    return V, illum


def _sensors(text):
    """언급된 센서. RGB·IMU 는 기본. 열화상/SAR/LiDAR/음향은 언급 시 추가."""
    s = ["RGB", "IMU"]
    if re.search(r"열화상|열영상|적외|IR|thermal", text, re.I):
        s.append("Thermal")
    if re.search(r"\bSAR\b|합성개구|레이더|radar", text, re.I):
        s.append("SAR")
    if re.search(r"라이다|LiDAR|lidar", text, re.I):
        s.append("LiDAR")
    if re.search(r"음향|소리|audio|마이크|청음", text, re.I):
        s.append("Audio")
    out = []
    for x in s:
        if x not in out:
            out.append(x)
    return out


def _fp_sources(text):
    """오인(false+) 원인어. 바위·동물=전-서명 decoy(생체 없음), 흔들리는 식생·나무=순간 clutter."""
    want = bool(re.search(r"오인|false\s*positive|헛|거짓\s*양성|착각|사람으로", text, re.I))
    rock_animal = bool(re.search(r"바위|암석|동물|짐승|노루|멧돼지|고라니|가축", text))
    veg = bool(re.search(r"식생|수풀|덤불|흔들|바람|풀", text))
    return want, rock_animal, veg


def _fn_hint(text):
    return bool(re.search(r"놓치|은폐|숨|가려|미탐|false\s*negative|거짓\s*음성", text, re.I))


def parse(text, lat=38.25, lon=128.30, seed=4242):
    """자연어 → IV&V spec. 위경도 기본은 DMZ 부근(사용자가 좌표를 주면 대체). scene3d 켠다(지형·수관)."""
    n = _count_people(text) or 3
    V, illum = _env(text)
    sensors = _sensors(text)
    want_fp, rock_animal, veg = _fp_sources(text)
    want_fn = _fn_hint(text)
    forest = bool(re.search(r"산림|숲|수관|삼림|나무|DMZ|비무장|임야", text))
    place, lat, lon = _place(text, lat, lon)         # 실 지명·좌표 → 실 DEM 조회용

    rng = random.Random(seed)
    cellm = 250.0                                            # reference: PATCH_M/GW = 6000/24

    def _spread(count, rmin, rmax, existing, min_sep_cells, canopy_fn):
        """탐색 구역 전체로 퍼뜨린다(격자 분리 강제). 중심 군집이면 실제 area search 가 안 된다.
        bearing/range 로 후보를 만들되 격자 좌표로 분리·경계를 확인한다."""
        out = []; pts = list(existing)
        for i in range(count):
            for _try in range(200):
                br = rng.uniform(0, 360); rm = rng.uniform(rmin, rmax)
                gx = 12.0 + (rm / cellm) * math.sin(math.radians(br))
                gy = 12.0 - (rm / cellm) * math.cos(math.radians(br))
                if not (2.5 <= gx <= 21.5 and 2.5 <= gy <= 21.5):
                    continue
                if all((gx - px) ** 2 + (gy - py) ** 2 >= min_sep_cells ** 2 for px, py in pts):
                    pts.append((gx, gy))
                    out.append({"bearing_deg": round(br, 1), "range_m": round(rm, 0), "canopy": canopy_fn(i)})
                    break
            else:                                            # 자리를 못 찾으면 분리 요구만 완화(정직: 억지로 안 우김)
                br = rng.uniform(0, 360); rm = rng.uniform(rmin, rmax)
                out.append({"bearing_deg": round(br, 1), "range_m": round(rm, 0), "canopy": canopy_fn(i)})
        return out, pts

    # 표적: 탐색 구역 전체(900~2400m)로 퍼뜨림, 최소 분리 5칸(1250m). 절반쯤 수관 은폐(FN 후보).
    def _canopy(i):
        return (want_fn or forest) and (i % 2 == 1)
    targets, pts = _spread(n, 900.0, 2400.0, [], 5.0, _canopy)

    decoys = []
    if want_fp or rock_animal or veg:                        # 바위·동물 decoy(전-서명, liveness 없음)
        decoys, _ = _spread(max(2, round(n * 0.6)), 700.0, 2200.0, pts, 3.5, lambda i: False)

    clutter = 0.15 if (want_fp or veg) else 0.05             # 흔들리는 식생 = 순간 헛탐지율(persist=1, transient)
    fidelity = ("L2 실 DEM(%s) + SceneDB" % place) if place else "L1 합성 DMZ-유사 산림·초지 DEM + SceneDB"
    return dict(seed=seed, lat=lat, lon=lon, V=V, illum=illum, agl=90.0,
                sensors=sensors, clutter=clutter, clutter_persist=1, scene3d=True,
                target_motion="static", n_target=n, place=place,
                fidelity=fidelity,
                targets_spec=targets, decoys_spec=decoys,
                _nl={"text": text, "want_fp": want_fp, "want_fn": want_fn, "forest": forest, "place": place,
                     "n_canopy": sum(1 for t in targets if t["canopy"]), "n_decoy": len(decoys)})


if __name__ == "__main__":
    import json
    demo = ("DMZ와 유사한 산림·초지 환경에서 드론이 RGB·열화상·IMU 센서를 이용해 실종 다섯명을 "
            "탐색하며, 나무·바위·동물·흔들리는 식생을 사람으로 오인하는 false positive와 "
            "정지·은폐된 사람을 놓치는 false negative를 포함하라.")
    print(json.dumps(parse(demo), ensure_ascii=False, indent=1))
