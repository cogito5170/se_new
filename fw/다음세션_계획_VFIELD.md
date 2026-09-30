# 다음 세션 계획 — V-FIELD(현장/운용 validation) 남은 것

이 세션에서 fw 결정 executive(#440~#452)는 **Verification(L0–L2, 시뮬)** 을 CMPC·FDIR 양축에서
확보했다. traceability 표의 남은 ○ 는 전부 **V-FIELD(validation)** — target platform·high-fidelity·
현장. NASA 기준으로 L3+ operational validation 이라 시뮬(이 세션 범위)로는 못 채운다. 다음 세션이
무엇을, 어떤 순서로, 무엇을 준비해야 하는지 정리한다.

## 1. 남은 V-FIELD 항목 (traceability 의 ○)

| ID | 요구 | 지금(확보) | 남은 것(V-FIELD) |
|---|---|---|---|
| V-FIELD-CMPC-001 | CMPC/liveness 규칙이 **실 센서·실 환경**에서 관측가능성 경계를 재현 | 규칙 등가(host_test[14])·시뮬 방향 재현(cmpc_vv C) | 실 센서 로그·실 decoy/clutter |
| V-FIELD-FDIR-001 | 센서고장·공분산폭발·actuator·stale 를 **실 하드웨어**에서 주입·검증 | 시뮬 fault_test 6군데 | target 보드 fault 주입 |
| GAP-CMPC/FDIR | 정지·고착·전-서명 가짜(공통 gap) | 시뮬서 liveness 필요 실증 | 실 liveness 센서(생체징후 레이더 등)로 실증 |

## 2. Fidelity ladder 로 본 다음 계단 (L2 → L5)

지금 **L2**(실측 DEM + landcover + 물리 센서모델). validation 은 L3부터.

- **L3 — high-fidelity simulation (하드웨어 없이, 다음 세션 가능):**
  - 실 위성 imagery 텍스처 + 검증된 조명/기상 → 센서 관측을 실 데이터에 대조.
  - NASA 선례(Blender-TRN NTRS): 고도+imagery 로 3D scene 짓고 **실 비행 영상과 대조해 scene 검증**.
  - 준비물: 대상 지역 위성 imagery(공개), 조명/BRDF 모델. **모델 V&V 를 먼저**(NPR 7150.2: sim 도 V&V 대상) — 센서 모델을 실 센서 스펙시트/한 컷 실측에 캘리브레이션.
  - 산출: L3 재측정으로 CMPC/FDIR 수치가 L2 와 얼마나 벌어지는지(모델 민감도).
- **L4 — field validation (하드웨어 필요):**
  - 실 terrain·실 센서(RGB/열/LiDAR/레이더/마이크)로 clutter·decoy·부분관측·고장을 재현.
  - liveness: 생체징후/마이크로도플러 레이더 실물(FINDER 개념)로 전-서명 decoy 를 실제로 거르는지.
  - 준비물: 센서 페이로드, 시험장(수관·안개 가능 지형), 안전 승인.
- **L5 — system validation (실 platform+SW):**
  - fw/evidence.c 를 실 MCU(STM32/ESP32)에 cross-gcc + HAL 로 올려 HITL → 비행.
  - 준비물: 실 비행체·인증 절차·타이밍/전원 마진(NPR 7150.2 high-fidelity sim = 동일 processor/timing/memory).

## 3. 다음 세션에 **시뮬 범위 안에서** 당길 수 있는 것 (L3 접근)

하드웨어 없이도 validation 에 한 걸음:
1. **모델 V&V 먼저.** `sar/sensors_ref.py` 의 물리 모델(Planck·Koschmieder·LiDAR·GNSS·Audio)을 센서
   스펙시트/문헌값에 대조하는 원장(`paper/측정.jsonl` 식) — 모델이 대표성이 있는지부터.
2. **L3 imagery 주입.** reference 에 실 위성 imagery 타일(공개 ESA/USGS)로 RGB 관측을 실 텍스처
   기반으로. 조명/그림자 모델 추가. CMPC 표를 L3 로 재측정 → L2 대비 민감도.
3. **HITL 준비(코드만):** `fw/evidence.c` 를 cross-gcc 타깃 빌드가 되게(현재 host gcc). 타이밍/스택
   상한 정적 분석. bare-metal 링크 스텁.
4. **CMPC C 이식의 strict 변형** 추가(현재 C 는 조건부만) — 프로토타입 strict 열까지 C 재현.

## 4. 순서 (권장)

```
[이번 세션까지] L0–L2 Verification (CMPC·FDIR 시뮬) ✓
        ↓
[다음] 모델 V&V (센서모델을 스펙/문헌에 대조) — 시뮬 신뢰성의 전제
        ↓
[다음] L3 high-fidelity (실 imagery·조명) — CMPC/FDIR 재측정, 모델 민감도
        ↓
[하드웨어 확보 후] L4 field (실 센서·실 decoy·liveness 실물)
        ↓
L5 system (실 MCU HITL → 비행)
```

## 5. 정직 — 이 계획의 전제

- 이 세션의 모든 수치는 **Verification evidence(L2)** 이지 validation 아님(`fw/V&V.md`).
- L4·L5 는 **하드웨어·시험장·승인**이 있어야 하며 이 세션의 시뮬로는 대체 불가.
- "시뮬에서 됐으니 현장도 된다"는 점프는 하지 않는다 — L3 모델 민감도부터 재서 간극을 좁힌다.
- 남은 ○ 를 못 채운 것은 실패가 아니라 **validation boundary 를 정직히 그은 것**이다.
