# ssm/fw — 최소 선택적 SSM (Mamba 원자) 스트리밍 추론 커널 (소프트웨어/MCU 경로)

이 폴더는 `ssm/` SSM selective-scan 가속기 프로젝트의 **소프트웨어(MCU) 경로**다. 형제 폴더:
- `ssm/rtl/` : 하드웨어(Verilog) scan-코어 — `scan_seq.v`·`scan_mac.v`·`exp_unit.v`
- `ssm/model/` : 고정소수 골든(`scan_golden.py`) — 이 fw 의 **step-3 재귀와 동일 수식**
- `ssm/설계.md` : 시스템 설계·고정소수 Q포맷 계획

Mamba 블록을 **최소 단위로 쪼갠** C 커널. 병렬 스캔(GPU 학습용)이 아니라 **스텝당 순차 재귀**
(엣지 추론용). 채널 하나는 **입력에 따라 계수가 바뀌는 1차 IIR** — **학습된 게인-스케줄
필터뱅크**. 학습은 오프디바이스(GPU), 추론(이 커널)만 MCU. `policy_core` 와 같은 규율:
힙·재귀 없음, 결정적, host_test 로 잠금.

**rtl 과의 관계**: 이 fw 의 **step-3 (선택적 상태 갱신·읽기)** = `rtl/scan_seq.v` = `model/
scan_golden.py` 의 `h=Abar·h+Bbar·x, y=ΣC·h`. fw 는 그 scan-코어를 감싸는 **풀 블록**(conv +
투영 + Δ→exp(Δ·A)=Abar 이산화)까지 SW 로 한다. → HW-SW 분할: **투영·conv 는 SW, scan-코어는
FPGA(rtl) 또는 전부 MCU(fw)**. 같은 원자의 두 기판.

> ⚠ 이건 **float 참조 구현**이다. 고정소수(Q15 등)는 명시된 다음 단계이며 아직 아님(주석 `[FX]`).
> 학습 가중치도 아직 없다(host_test 는 결정적 시험 가중치로 *원자의 거동*만 붙든다).

## 한 스텝 (u = conv+SiLU 후 입력; 채널 i, 상태 n)
```
conv1d(depthwise FIR) → SiLU → u
Δ_i = softplus(W_dt·u + b)        입력의존 시간상수(>0)
B_n = W_B·u,  C_n = W_C·u          입력의존(선택성의 핵심)
Ā_in = exp(Δ_i·A_in) ∈(0,1)       A<0 → 안정 감쇠
h_in = Ā_in·h_in + (Δ_i·B_n)·u_i   상태 갱신 = IIR
y_i  = Σ_n C_n·h_in + D_i·u_i       읽기 + skip
```
= **FIR + matvec + 입력변조 IIR뱅크 + LUT.** 전부 DSP 원자.

## 계층
| 조각 | = DSP | 코드 |
|---|---|---|
| conv1d depthwise | FIR(링버퍼) | `ssm_step` 1) |
| Δ/B/C 투영 | matvec | 2) |
| 선택적 상태 갱신·읽기 | 입력변조 IIR | 3) |
| softplus·SiLU·exp | 비선형/이산화 | `[FX]`→LUT |

## 돌리기
```sh
make test   # 결정성 · NaN 없음 · IIR 감쇠(0입력서 상태 단조↓) · 안정성(A<0 유계)
```
host_test 가 붙드는 것: reset=상태0, 같은 입력→같은 출력, 거친 입력서 NaN/Inf 없음,
0 입력 흘리면 상태 ||h||² 단조 감쇠(IIR), 상수 입력 300스텝서 상태 유계(폭주 없음).

## MCU 이식
```sh
arm-none-eabi-gcc -std=c99 -Os -mcpu=cortex-m4 -c ssm.c
```
힙·재귀 없음, 상태는 호출자 제공 `SSM_State`(고정크기). 스텝당 비용 = O(d_inner·d_state) +
투영 matvec. **투영 matvec 이 주 비용** — d 작게(현재 4×4) 두거나 DSP 확장(CMSIS-NN·Helium/
Ethos-U). 초월함수(expf/logf)는 libm 또는 LUT.

## 고정소수 이식 (다음 단계, `[FX]`)
**scan-코어의 Q포맷은 이미 정해져 있다 — `../설계.md §3` 을 따른다**(새로 만들지 않는다):
- `Δ·A` = Q4.12, `Abar` = Q0.16 무부호(0,1), `x,B,C,h,y` = Q1.15/Q4.12, 곱누산 32b.
- 그 scan-코어(Abar,Bbar,C→h,y)는 `../model/scan_golden.py` 로 이미 골든 대조된다.
- 이 fw 가 추가로 고정소수화할 것 = **conv·투영·softplus·SiLU·exp** — 초월함수는 LUT.
- IIR 재귀 안정성: A<0(감쇠) → Abar∈(0,1) → 발산 없음(host_test 안정성 시험이 이 성질 확인).

## 우리 프로젝트와의 연결
이 커널은 두 자리의 **공통 빌딩블록**(둘 다 학습 가중치를 이 원자로 실행):
1. **시간적 지각 어댑터** (`PC_ObsModel` 뒤): 센서 시계열 → 보정된 탐지확률 `p_useful`.
2. **학습 가치 head** (정책의 판단 보강): belief/관측 이력 → value-to-go
   (측정된 freeze·myopia 를 원리적으로 흡수). **belief 수학·RTA 안전은 결정적으로 남김.**

즉 학습(GPU)→가중치 export→이 커널로 MCU 추론. **`policy_core` 결정적 뼈대 안에서
'보는 것/판단 보강'만 학습**이 이 모듈의 자리.

**2번(학습 가치 head)은 배선까지 구현됨** — `ssm_value.c` 가 이 커널을 `policy_core` 의
`PC_ValueHead`(순수 `value()` + `advance()`)로 감싼다. 정책 합성·불변식·안전 경계는
`../../policy_core/VALUE_HEAD.md`. 학습 가중치는 아직 없어 `λ=0`(la2 와 비트동일)로 둔다.
