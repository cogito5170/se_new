"""SAR 고정 명령 — 지도 좌표·자연어 시나리오로 능동탐색·보증평가를 배경으로 돌린다.

규약(dispatch.py): PREFIX 와 run(text, runner=None, allow_write=True). **모르는 말엔 None**.
무거운 것(numpy/matplotlib/DEM 다운로드/GIF)은 이 모듈이 아니라 **배경 자식 프로세스** 안에서만
돈다 — 이 모듈은 가볍게 임포트돼야 한다(G012).

명령:
  !search <위도>,<경도> [반경m] [시나리오]   좌표(red spot)로 3D 능동탐색            (관리 채널)
  !시나리오 "<자연어 상황>"                    NL→실좌표·물리조건, 실시간+사후 보고     (공개 가능)
  !보증 [지명]                                 NASA 3축 보증(Reliability/Robust/Resil)  (공개 가능)
  !매트릭스 [지명]                             NASA V&V 테스트 매트릭스                 (공개 가능)
  !검증                                        모델 검증(Level 2): referent 대조·GAP    (공개 가능)
  !독립검증                                    IV&V: SUT·참조·평가기 분리 + 실시간 3D뷰 (공개 가능)
  !텔레메트리                                  3계층 실시간 통신(10Hz state/1Hz report/event)(공개 가능)
  !측정                                        파이프라인 4계층 실측(세계해상도/데이터율/지연/정확도)(공개 가능)
  !센서                                        센서 모델 스펙 + 환경 재점검 + sensor-agnostic 선택 정책(공개 가능)

(`!평가` 는 이미 eval 모듈이 쓰므로 SAR 보증은 `!보증` 이다 — 이름 충돌 회피)

안전: 모두 **시뮬/계획**이다. 실제 비행 명령은 사람이 승인한다(HW_DESIGN.md).
자연어→구조 변환·위치 없으면 되묻기는 여기(지상국 몫)에서 한다 — 드론에는 LLM 이 없다.
"""
from __future__ import annotations
import re
from pathlib import Path

PREFIX = "!search"
_ALT = "!탐색"
_SCEN = "!시나리오"
_EVAL = "!보증"                                                   # `!평가` 는 eval 모듈이 선점 → 충돌 회피
_MATRIX = "!매트릭스"
_VALID = "!검증"                                                  # 모델 검증(Level 2, referent 대조)
_IVV = "!독립검증"                                                # IV&V: SUT·참조·평가기 분리 + 3D 뷰
_TELE = "!텔레메트리"                                              # 3계층 rate-stratified 통신
_MEAS = "!측정"                                                    # 파이프라인 4계층 실측
_SENSOR = "!센서"                                                  # 센서 스펙+환경 재점검+선택 정책
_SIMVID = "!시뮬영상"                                              # 자연어 시나리오 → 폐루프 미션 두 mp4
# 로그는 **Path** 여야 한다 — _배경으로 가 .parent.mkdir·.is_file 을 부른다(str 이면 AttributeError).
_LOG = Path(__file__).resolve().parent / "logs" / "search.log"
HELP = (f"`{PREFIX} <위도>,<경도> [반경m] [시나리오]` — 그 좌표를 실지형 위에서 능동탐색(배경).\n"
        f"예: `{PREFIX} 38.1194,128.4656 3000 설악산 산불 조난자 탐색`\n"
        "결과: 조난자 georef · 센서(EO/열) · 매스텝 판단 로그 보고서를 첨부한다. (관리 채널)\n"
        "시뮬/계획이다. 실제 비행 명령은 사람이 승인한다.")
_SCEN_HELP = (f"`{_SCEN} \"<자연어 상황>\"` — 예: `{_SCEN} \"설악산 일대 산불, 비, 조난자 2명 탐색\"`\n"
              "장소→랜덤 실좌표·실 DEM, 날씨→물리 조건(비/안개/야간/연기/화재/먼지/센서고장). "
              "실시간 화면(RGB 장면+IMU/GPS 상황표시+SAR 무전)과 사후 보고(시간축)를 낸다. 위치가 없으면 되묻는다.")

# 위도,경도 (쉼표/슬래시/공백 구분). 위도 -90..90, 경도 -180..180 은 아래서 검증.
_LL = re.compile(r"(-?\d{1,3}\.\d+)\s*[,/ ]\s*(-?\d{1,3}\.\d+)")


def _launch(runner, argv, findword):
    launch = runner
    if launch is None:
        try:
            from eval.discord_cmd import _배경으로 as launch     # 배경 실행기(setsid+등록)
        except Exception as e:                                   # noqa: BLE001
            return None, "배경 실행기를 못 불렀다: %s" % type(e).__name__
    try:
        return launch(argv, _LOG, findword), None               # _배경으로 가 _LOG.parent.mkdir 을 한다
    except Exception as e:                                       # noqa: BLE001
        return None, "못 띄웠다: %s: %s" % (type(e).__name__, e)


def _scenario(nl, runner):
    """NL→구조 변환 + 위치 없으면 되묻기(지상국 몫). 위치 있으면 mission.py 배경 실행."""
    try:
        import random as _rnd
        from sar import scenario as _scn
        s = _scn.parse(nl, _rnd.Random())
    except Exception as e:                                       # noqa: BLE001
        return "시나리오를 못 읽었다: %s" % type(e).__name__
    if s.get("place_source") == "random":                       # 필수(위치)가 없으면 되묻는다
        return ("위치를 못 알아들었다 — 어디를 탐색할지 정해 달라.\n"
                "지명(예: 설악산, 포지타노, 로마) 또는 좌표(위도,경도)를 넣어라.\n"
                f"예: `{_SCEN} \"설악산 일대 산불, 안개, 조난자 2명 탐색\"`")
    ack, err = _launch(runner, ["python3", "sar/mission.py", "--nl", nl[:400]], "mission.py")
    if err:
        return "시나리오를 " + err
    pre = "해석: 장소=%s · 조건=%s · 조난자 %d명 (좌표는 그 일대서 랜덤)\n" % (s["place"], s["condition"], s["n_surv"])
    return ("시나리오 실행: %s\n%s실시간(RGB 장면+IMU/GPS 상황표시)·사후 보고를 낸다. 끝나면 첨부한다.\n%s"
            % (nl, pre, ack))


def _cmd(t, pfx):
    """접두사 뒤가 공백·따옴표·끝일 때만 그 명령으로 본다(‘붙여 쓴 말’은 명령이 아니다 —
    eval 모듈과 같은 규약). 맞으면 나머지(strip)를, 아니면 None."""
    if not t.startswith(pfx):
        return None
    tail = t[len(pfx):]
    if tail and tail[0] not in " \t\"'":
        return None
    return tail.strip()


def run(text, runner=None, allow_write: bool = True):
    t = (text or "").strip()

    rest = _cmd(t, _EVAL)                                        # NASA 3축 보증평가 (공개 가능)
    if rest is not None:
        argv = ["python3", "sar/assurance.py"] + (["--place", rest[:40]] if rest else [])
        ack, err = _launch(runner, argv, "assurance.py")
        return ("보증을 " + err) if err else \
            ("NASA 3축 보증평가 실행(Reliability·Robustness·Resilience). 끝나면 보고서·그림을 붙인다.\n" + ack)

    rest = _cmd(t, _MATRIX)                                      # NASA V&V 테스트 매트릭스 (공개 가능)
    if rest is not None:
        argv = ["python3", "sar/scn.py"] + (["--place", rest[:40]] if rest else [])
        ack, err = _launch(runner, argv, "scn.py")
        return ("매트릭스를 " + err) if err else \
            ("NASA V&V 테스트 매트릭스 실행. 끝나면 근거표·그림을 붙인다.\n" + ack)

    rest = _cmd(t, _VALID)                                       # 모델 검증(Level 2) (공개 가능)
    if rest is not None:
        ack, err = _launch(runner, ["python3", "sar/validate.py"], "validate.py")
        return ("검증을 " + err) if err else \
            ("모델 검증(V&V 3계층) 실행 — SAR 초점↔회절 척도법칙 대조(R²)+신뢰성 기록표+GAP. "
             "자기채점이 아니라 독립 referent 대조다. 끝나면 보고서·그림을 붙인다.\n" + ack)

    rest = _cmd(t, _IVV)                                         # IV&V 독립검증 (공개 가능)
    if rest is not None:
        ack, err = _launch(runner, ["python3", "sar/ivv/harness.py", "--demo"], "sar.ivv.harness")
        return ("독립검증을 " + err) if err else \
            ("IV&V 독립검증 실행 — SUT(센서만)·독립 참조세계(다른 물리)·독립 평가기(숨은 truth 채점)를 "
             "분리한다. 자기채점이 구조적으로 불가능. 실시간 3D 뷰(관찰자는 truth, SUT 는 못 봄)+독립 "
             "지표(탐지율·위치RMSE·오경보). 같은 임무를 render3d 로 실사 3D(탑재카메라 Beer-Lambert 안개)로도 그린다. "
             "끝나면 보고서·그림을 붙인다.\n" + ack)

    rest = _cmd(t, _TELE)                                        # 3계층 텔레메트리 (공개 가능)
    if rest is not None:
        ack, err = _launch(runner, ["python3", "sar/ivv/harness.py", "--telemetry"], "sar.ivv.harness")
        return ("텔레메트리를 " + err) if err else \
            ("Rate-stratified 텔레메트리 실행 — 하나의 주기로 다 보내지 않는다. 10Hz 기계상태 · 1Hz 운용보고 · "
             "즉시 이벤트(탐지/재탐색/MRC)로 나눠 실측 주기를 잰다('보고'와 '데이터 전송' 분리). "
             "10Hz 는 NASA 표준이 아니라 연구용 설계점이다(1Hz~20Hz 사이). 끝나면 보고서를 붙인다.\n" + ack)

    rest = _cmd(t, _MEAS)                                        # 파이프라인 4계층 실측 (공개 가능)
    if rest is not None:
        argv = ["python3", "sar/measure.py", "--demo"] + (["--accuracy"] if "정확도" in (rest or "") else [])
        ack, err = _launch(runner, argv, "measure.py")
        return ("측정을 " + err) if err else \
            ("파이프라인 4계층 실측 실행 — 세계해상도(mpp·피처수)·센서 데이터율(RGB·SAR raw 실 바이트)·"
             "처리지연(벽시계, 추정 아님)을 다섯 환경(숲·사막·도시·해안·고산)에서 잰다. 과장방지 4검사"
             "(재려던걸 쟀나·동작점·독립대조·사소한설명)를 건다. **임베디드 HW 아님**(상대 비교). "
             "'정확도' 를 붙이면 IV&V 평가기로 탐지정확도까지(실 DEM 필요). 끝나면 보고서 첨부.\n" + ack)

    rest = _cmd(t, _SENSOR)                                      # 센서 스펙+환경 재점검+선택 정책 (공개 가능)
    if rest is not None:
        ack, err = _launch(runner, ["python3", "sar/sensor_select.py", "--demo"], "sensor_select.py")
        return ("센서 스펙을 " + err) if err else \
            ("센서 모델 스펙 + 환경변수 재점검(NASA-STD-7009B) + sensor-agnostic 선택 정책 실행. "
             "RGB(ISETCam)·Thermal(Planck+MODTRAN)·LiDAR(waveform)·IMU(Allan)·GNSS(ESA)·Audio(Image Source) "
             "reference model(radar 제외 — 이미 있음)을 우리 환경변수에 fit 시키고, 상황(안개·야간·수관·협곡·화재)"
             "마다 물리로 센서를 고른다. 대표/유도 변수는 domain 한정(GAP 명시). 끝나면 보고서 첨부.\n" + ack)

    rest = _cmd(t, _SIMVID)                                      # 자연어 → 폐루프 미션 두 mp4 (공개 가능)
    if rest is not None:
        nl = rest.strip('"').strip("'").strip()
        if not nl:
            return (f"`{_SIMVID} \"<자연어 상황>\"` — 예: `{_SIMVID} \"강원도 고성 DMZ 산림에서 RGB·열화상·IMU 로 "
                    "실종 5명 탐색, 바위·동물·흔들리는 식생 오인(FP)과 은폐된 사람 놓침(FN) 포함\"`\n"
                    "자연어→시나리오(장소·표적수·센서·수관·decoy·clutter)로 fw C 결정 executive가 참조세계 안에서 "
                    "UAV 를 몰아 배터리 소진(운용 불능)까지 탐색. **실 지명(고성·파주 DMZ·설악산·오대산 등)이면 실 고도 "
                    "DEM(AWS Terrarium)로 3D 렌더(three.js webm→mp4)** + 2D 도식(상공/온보드, FP/FN 주석). "
                    "실 고도 geometry(위성 사진 텍스처 아님). false+/false- 개수는 물리·평가기가 낸 것을 그대로 보고한다.")
        argv = ["python3", "sar/ivv/mission_make.py", "--nl", nl[:400]]
        ack, err = _launch(runner, argv, "mission_make")
        return ("시뮬영상을 " + err) if err else \
            ("미션 시뮬 영상 실행: %s\n자연어→시나리오→fw C 폐루프(배터리 소진까지). 온보드·상공 두 mp4 를 "
             "낸다. false+(decoy·식생 오인)는 liveness 로 거르고, false-(수관 은폐)는 그대로 놓침으로 보고. "
             "끝나면 첨부한다.\n%s" % (nl, ack))

    rest = _cmd(t, _SCEN)                                        # 자연어 시나리오 (공개 가능)
    if rest is not None:
        nl = rest.strip('"').strip("'").strip()
        return _SCEN_HELP if not nl else _scenario(nl, runner)

    if t.startswith(_ALT):
        t = PREFIX + t[len(_ALT):]
    if not t.startswith(PREFIX):
        return None                                             # 모르는 말 -> 다음 모듈/에이전트로
    tail = t[len(PREFIX):].strip()
    if not tail or tail in ("도움", "help", "?"):
        return HELP
    m = _LL.search(tail)
    if not m:
        return "좌표를 못 읽었다 — `%s <위도>,<경도> [반경m] [시나리오]` 꼴이어야 한다.\n%s" % (PREFIX, HELP)
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return "위경도 범위 밖이다 (위도 ±90, 경도 ±180)."
    rest = (tail[:m.start()] + " " + tail[m.end():]).strip()
    rm = re.search(r"\b(\d{3,5})\b", rest)                       # 반경[m] (선택)
    radius = float(rm.group(1)) if rm else 3000.0
    if rm:
        rest = (rest[:rm.start()] + " " + rest[rm.end():]).strip()
    scenario = rest or "지정 좌표 주변 조난자 탐색"
    if not allow_write:                                          # 좌표 명령은 관리 채널만
        return "탐색 시작은 관리 채널에서만 — 이 채널은 읽기 전용이다."
    ack, err = _launch(runner, ["python3", "sar/terrain_search.py", "--lat", "%.6f" % lat, "--lon", "%.6f" % lon,
                                "--radius", "%.0f" % radius, "--scenario", scenario[:200]], "terrain_search.py")
    if err:
        return "탐색을 " + err
    return ("탐색 시작: (%.4f, %.4f) 반경 %.0fm\n시나리오: %s\n"
            "끝나면 보고서(조난자 georef · 센서 · 판단 로그)를 붙인다.\n%s"
            % (lat, lon, radius, scenario, ack))
