# sar/ — 지도+red spot → 능동탐색 → 실제 탐지 → Discord 수신기 (데모 (a))

추상 정책(`policy_core/`)을 **실제 임무**로 접지한 데모. 운용자가 지도에 red spot을 찍으면
UAV가 그 좌표를 능동탐색하고, **실제 탐지기**가 사람을 찾아 **Discord 수신기**로 탐지 카드를 보낸다.

**가짜 곡선이 없다.** 세 조각이 다 진짜다:
- **정책·belief** = 논문이 측정한 그 `policy_core.c` 그대로 (ctypes로 `sar_core.c` 껍데기를 통해 호출).
- **탐지기** = cv2 **YuNet** DNN 얼굴탐지기 (실제 ONNX 모델, 실제 이미지 크롭에 매 스텝 실행).
- **관측** = 명목 곡선이 아니라 YuNet이 실제 픽셀에서 낸 탐지/미탐이 `p_useful`을 채운다.

## 파이프라인

```
운용자 red spot ─▶ prior blob ─▶ [C pc_policy_step: 다음 관측 셀]
  ─▶ UAV footprint 크롭 ─▶ [cv2 YuNet: 실제 탐지] ─▶ 탐지/미탐
  ─▶ [C pc_belief_update: 베이즈] ─▶ 반복 ─▶ belief 수렴 ─▶ Discord 탐지 카드
```

다표적(생존자 여럿): 찾은 survivor는 belief에서 억제(found-suppression)해 다음 생존자로 탐색을
계속한다. 단일표적 belief는 첫 탐지에 붕괴(엔트로피→0)하므로, 순차 다표적 SAR엔 이 억제가 필요하다.

## 돌리기

```sh
pip install opencv-python-headless numpy matplotlib   # 데모 전용 의존(봇 런타임 아님)
make assets     # 제3자 이미지·YuNet 모델 내려받기(커밋 안 함; fetch_assets.sh)
make demo       # libsarcore.so 빌드 + map_demo.py 실행 -> out/*.png
```
출력: `out/sar_demo.png`(수색구역+궤적+belief), `out/discord_card.png`(수신기 탐지 카드).
최근 실행: 실제 YuNet이 3인 탐지 → 정책이 14스텝에 3/3 확정.

## 파일

| 파일 | 무엇 |
|---|---|
| `HW_DESIGN.md` | 하드웨어·통신 설계(센서·연산 분담·Discord 수신기 프로토콜·failsafe) |
| `sar_core.c` | `policy_core.c`의 얇은 C-ABI 껍데기(ctypes용). 정책·belief는 동일 코어 |
| `map_demo.py` | 데모: 실이미지+YuNet+C코어로 탐색 루프·그림·Discord 카드 |
| `fetch_assets.sh` | 이미지·모델 내려받기(제3자, 커밋 안 함) |
| `terrain.py` | **실제 지형(DEM) 받아오기** — AWS Terrain Tiles(Terrarium, 무키·전지구). `elev=R*256+G+B/256-32768`. 실측: 북한산 고도 30~813 m. `python3 terrain.py` -> `out/terrain_bukhansan.png` |
| `terrain_search.py` | **③ 실지형 위 3D 능동탐색**(NL 시나리오). 실 DEM + LOS 차폐 + 지형그림자 센서전환(EO↔열) + 고도 geofence RTA + 매스텝 판단로그. `python3 terrain_search.py` -> `out/terrain_search_{3d,map}.png` + `out/decision_log.txt`(Discord 게시용) |
| `sensors.py` | **센서 reliability 물리 모델**(RGB+IMU). Beer-Lambert 소광·Koschmieder 가시거리·광자한계 SNR·IMU 랜덤워크 드리프트. 로그의 모든 수치가 여기서 계산된다(지어내지 않음) |
| `scenario.py` | 자연어 시나리오 파싱 -> (가제티어 기반 **랜덤 실좌표** · 물리조건 · 조난자수). `python3 scenario.py "<NL>"` |
| `scenario_run.py` | **RGB+IMU baseline 탐색 + NHTSA fallback/MRC**. 8조건(정상/야간/안개/연기/화재/먼지/비/센서고장) 물리 모델링, 랜덤 실좌표·실 DEM, 거짓 없는 판단 로그. `python3 scenario_run.py --nl "<NL>"` -> `public_agent_memory/*.md` + `out/scenario_run.png` |
| `fault_mgmt.py` | **NASA Fault Management 루프** — 물리에서 Detect→Diagnose→Identify→Respond(회복가능성 포함). SE/FM Handbook |
| `assurance.py` | **NASA 3축 보증평가** — Reliability(규정)·Robustness(예상 off-nominal)·Resilience(예상못한 사건 후 복구). `python3 assurance.py` -> `out/assurance.png` + 보고서 |
| `NASA_ASSURANCE.md` | NASA 4계층(Architecture/Decision/R-R-R/Fault) 프레임 매핑 + 문서 인용 |
| `scn.py` | **NASA식 구조화 시나리오 + V&V 테스트 매트릭스**. 직교 축(Geometry×Visibility×Disturbance×Sensor×Fault+전이타이밍), 시나리오 ID(SCN-REL/ROB/RES), 상태전이 결함주입, V&V 판정. `python3 scn.py` -> `out/testmatrix.png` + 근거표 |
| `TEST_MATRIX.md` | NASA V&V(ConOps→Scenario→Outcome) 구조·축·ID·결함주입 설명 + 문서 인용 |
| `report.py` | **표준 SAR 무전 보고 형식**(WHO/WHAT/WHERE/STATUS/NEED/ACTION, MAYDAY>PAN-PAN). 드론 다운링크 = 고정 슬롯 레코드 → 온보드 LLM 불필요(지상국이 자연어 변환) |
| `playback.py` | **실시간 지휘 화면**(재생 GIF). ①top-down 커버리지 지도 ②RGB 카메라+검출 오버레이 ③3D 고도 ④미션 상태 ⑤SAR 무전. IMU/GPS 는 원시값이 아니라 상황표시(불확실↑·방위). `python3 playback.py --nl "<NL>"` → `out/playback.gif` |
| `postmission.py` | **사후 임무보고**(시간축 PNG). 정책 타임라인(SEARCH→VERIFY→REPORT→REPLAN→HOLD)·센서 타임라인(실패/회복 구간=robustness·resilience 증거)·3D 궤적·요약. `python3 postmission.py --nl "<NL>"` → `out/postmission.png` |
| `mission.py` | **`!시나리오` 배경 실행기** — 한 simulate() 로 실시간 GIF + 사후 PNG + 판단로그 .md 를 `public_agent_memory/` 에 낸다(봇이 첨부). 실시간·사후가 같은 임무 |

## 정직한 한계

- **지상 사진을 수색구역 스탠드인**으로, **얼굴탐지를 '사람 있음' 대리**로 쓴다(이 컨테이너서
  도달 가능한 실 모델·이미지의 한계). 실기 SAR은 **항공+열화상 프레임 + SAR-학습 탐지기**를 쓴다
  — 파이프라인(탐지→`p_useful`→belief→정책)은 그대로다.
- georeference 좌표(위경도)는 **데모 라벨**이다(중심 임의). 실기는 GNSS/정사영상 정합.
- `p_useful` 계획 모델은 명목이고 관측은 실측이라 model≠truth — `policy_core/CALIBRATION.md`가
  그 간극을 현장 캘리브로 좁힌다.
- 상용 지도 타일(네이버/카카오/구글)은 표시용일 뿐이며 재배포하지 않는다(ToS).
