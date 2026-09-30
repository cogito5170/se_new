# 실사 2D/3D 렌더 파이프라인 (render3d) — 선행조사

작성 2026-09-28. **코드보다 먼저 커밋한다**(CLAUDE.md '짓기 전에 조사한다').

## 무엇을 짓나

공간 배치 하나(JSON)로 **2D 평면도 · 3D 실사 렌더(three.js PBR) · 인터랙티브 HTML**을 함께 뽑는 도구다.
같은 장면 형식에 두 가지 입력을 받는다.
- 실내 공간: 매장 배치(`render3d/examples/`)
- SAR 세계: DEM 하이트필드, SceneDB 피처, IV&V 프레임(UAV 궤적, truth, SUT 탐지)

## 가장 가까운 선행 사례와 우리가 다른 점

| 선행 | 무엇 | 우리와 다른 점 | 확인수준 |
|---|---|---|---|
| AirSim (Shah et al., 2017, arXiv:1705.05065) | Unreal 기반 드론·차량 실사 시뮬레이터 | 게임엔진으로 센서를 **생성**한다. 우리는 이미 있는 SAR 물리 모델(`sar/camera.py`)과 **같은 수식으로 그리는지**를 V&V 한다 | 기억 · 전문 미확인 |
| CARLA (Dosovitskiy et al., 2017, arXiv:1711.03938) | 자율주행 검증용 실사 시뮬레이터 | 같음. 렌더 품질이 검증 강도를 주지 않는다는 점(`sar/ivv/viewer.py` 문구 "photorealism ≠ validation")을 그대로 따른다 | 기억 · 전문 미확인 |
| three.js `FogExp2` | 웹 실사 렌더의 지수 안개 | 식이 `1 − exp(−(ρ·d)²)`, 즉 **제곱 지수**다. 거리 d 는 시선축 깊이(view-space z)다. SAR 카메라는 Beer-Lambert `exp(−β·r)`(선형 지수, 광선 거리 r)다. **그대로 쓰면 두 파이프라인의 안개가 다르다** → 셰이더를 덮어써 맞춘다 | three.js r170 소스 `fog_fragment.glsl.js:6`·`fog_vertex.glsl.js:4` 에서 확인 |
| Koschmieder (1924) | 기상 가시거리 V = 3.912/β (대비 2%) | 이미 `sar/sensors.py`, `sar/ivv/refval.py`가 referent 로 쓴다. 렌더러도 **같은 referent 로 대조**한다 | 저장소 코드에서 확인 |
| NASA-STD-7009 (M&S 신뢰성) | referent 대조 · 유효 영역 · GAP 명시 | `sar/ivv/refval.py`의 형식(측정 · 기준 · 상대오차 · 유효영역 · GAP)을 렌더러 V&V 에 그대로 쓴다 | 저장소 코드에서 확인 |
| Benedikt (1979) isovist | 한 지점에서 보이는 영역(시야 분석) | 매장 배치의 "입구에서 안쪽이 보이나"를 재는 데 쓸 수 있다. **이번 판에는 없다**(다음 후보) | 기억 · 전문 미확인 |

## 우리 쪽 기여라고 부를 수 있는 것 (과장 금지)

1. **두 렌더러(SAR 카메라, three.js)가 같은 세계를 같은 수식으로 그리는지 재는 V&V 검사.**
   - 투영: SAR 카메라는 열 방위각이 **각도에 선형**(`linspace`)이다. three.js 는 **핀홀**(tan 에 선형)이다. 같은 FOV 에서 둘은 가장자리가 아닌 곳에서 어긋난다. 그 크기를 잰다.
   - 안개: Beer-Lambert 덮어쓰기 뒤 픽셀 투과율을 `exp(−βr)`와 대조한다.
2. **2D·3D가 한 데이터에서 나온다.** 평면 점유와 3D 정사영 점유를 대조할 수 있다.

새 렌더링 기법이 아니다. 기존 도구(three.js, matplotlib, SAR 물리)를 **검사 가능하게 이은 것**이다.

## 찾아본 질의

- "three.js FogExp2 formula fogDensity vFogDepth"
- "Beer-Lambert fog shader WebGL radial distance"
- "photorealistic simulator validation UAV AirSim CARLA rendering fidelity"
- "isovist retail store visibility analysis"

## 아직 못 지운 가능성

- 브라우저 없는 서버(VM)에서는 실사 PNG 대신 matplotlib 대체 렌더만 나올 수 있다. 크로미움 설치가 배포에서 실패하면 그렇다 → 출력에 백엔드를 반드시 적는다.
- three.js 셰이더 청크 이름(`fog_fragment`, `fog_vertex`)은 판마다 바뀔 수 있다 → 판을 고정한다(0.170.0).
- 논문 원문(AirSim, CARLA, Benedikt)을 이 세션에서 읽지 못했다(네트워크 정책). 인용할 때는 원문을 확인한 뒤에 한다.
