/* ssm.h -- 최소 선택적 상태공간(Selective SSM = Mamba 원자) 스트리밍 추론 커널.
 *
 * 무엇: Mamba 블록을 "최소 단위"로 쪼갠 것 -- 병렬 스캔(GPU 학습용)이 아니라 스텝당
 *   순차 재귀(엣지 추론용). 채널 하나는 '입력에 따라 계수가 바뀌는 1차 IIR'이다.
 *   = 학습된 게인-스케줄 필터뱅크. 학습은 오프디바이스(GPU), 추론(이 커널)만 MCU.
 *
 * MCU 안전: 힙 없음(상태는 호출자 제공 정적 구조), 재귀 없음, 경계 있는 루프, 결정적.
 *   초월함수(expf/logf)는 이 float 참조 구현서만 -- 고정소수 이식 시 LUT 로 교체(README).
 *
 * ⚠ 이 파일은 **float 참조 구현**이다. 고정소수(Q15 등)는 명시된 다음 단계이며 아직 아님.
 *
 * 한 스텝 수식 (u = conv+SiLU 후 입력, 채널 i∈d_inner, 상태 n∈d_state):
 *   Δ_i   = softplus( W_dt[i]·u + b_dt[i] )            (채널별 시간상수, >0)
 *   B_n   = W_B[n]·u,   C_n = W_C[n]·u                 (입력의존, 공유)
 *   Ā_in  = exp(Δ_i · A_in),   A_in < 0                (감쇠계수 ∈(0,1))
 *   h_in  = Ā_in·h_in + (Δ_i·B_n)·u_i                  (상태 갱신 = IIR)
 *   y_i   = Σ_n C_n·h_in + D_i·u_i                     (읽기 + skip)
 */
#ifndef SSM_H
#define SSM_H

/* 컴파일타임 차원 (최소값 -- 표적탐지용 작은 필터뱅크). 필요시 늘린다. */
#ifndef SSM_D_INNER
#define SSM_D_INNER 4     /* SSM 채널 수 (= 여기선 입력차원, in-proj 생략) */
#endif
#ifndef SSM_D_STATE
#define SSM_D_STATE 4     /* 채널당 상태 차원 N */
#endif
#ifndef SSM_CONV_K
#define SSM_CONV_K  3     /* depthwise causal conv 커널 길이(FIR) */
#endif

/* 학습된 파라미터 (오프디바이스 학습 → const 배열로 export). */
typedef struct {
    float A[SSM_D_INNER][SSM_D_STATE];        /* 음수(감쇠). Ā=exp(Δ·A) */
    float W_dt[SSM_D_INNER][SSM_D_INNER];     /* Δ 투영 (u→Δ) */
    float b_dt[SSM_D_INNER];                  /* Δ 바이어스 */
    float W_B[SSM_D_STATE][SSM_D_INNER];      /* B 투영 (u→B, 공유) */
    float W_C[SSM_D_STATE][SSM_D_INNER];      /* C 투영 (u→C, 공유) */
    float D[SSM_D_INNER];                     /* skip 게인 */
    float conv_w[SSM_D_INNER][SSM_CONV_K];    /* depthwise FIR */
} SSM_Weights;

/* 스트리밍 상태 (고정크기, 힙 없음). 채널×상태 = 작다. */
typedef struct {
    float h[SSM_D_INNER][SSM_D_STATE];        /* SSM 상태(IIR 메모리) */
    float conv_buf[SSM_D_INNER][SSM_CONV_K];  /* conv 링버퍼(최근 K 입력) */
    unsigned char conv_head;                  /* 링버퍼 헤드 */
} SSM_State;

/* 상태 0으로. 임무 시작마다 호출. */
void ssm_reset(SSM_State *s);

/* 한 스텝: 입력 x[SSM_D_INNER] → 출력 y[SSM_D_INNER]. 상태 갱신. 힙/재귀 없음, 결정적. */
void ssm_step(const SSM_Weights *w, SSM_State *s,
              const float x[SSM_D_INNER], float y[SSM_D_INNER]);

#endif /* SSM_H */
