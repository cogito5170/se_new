/* ssm.c -- 최소 선택적 SSM(Mamba 원자) 스트리밍 추론. float 참조 구현.
 * 힙/재귀 없음, 경계 루프, 결정적. 고정소수 이식 지점은 주석 [FX] 로 표시. */
#include "ssm.h"
#include <math.h>   /* expf, logf -- [FX] 고정소수선 LUT/근사로 교체 */

/* softplus(x)=log(1+e^x). Δ>0 보장(시간상수 양수). [FX] LUT. */
static float softplus(float x) {
    if (x > 20.0f) return x;                 /* overflow 방지 */
    return logf(1.0f + expf(x));
}
/* SiLU(x)=x·sigmoid(x)=x/(1+e^-x). [FX] LUT. */
static float silu(float x) {
    return x / (1.0f + expf(-x));
}

void ssm_reset(SSM_State *s) {
    int i, n, k;
    for (i = 0; i < SSM_D_INNER; ++i) {
        for (n = 0; n < SSM_D_STATE; ++n) s->h[i][n] = 0.0f;
        for (k = 0; k < SSM_CONV_K; ++k) s->conv_buf[i][k] = 0.0f;
    }
    s->conv_head = 0;
}

void ssm_step(const SSM_Weights *w, SSM_State *s,
              const float x[SSM_D_INNER], float y[SSM_D_INNER]) {
    float u[SSM_D_INNER];        /* conv+SiLU 후 채널 입력 */
    float dt[SSM_D_INNER];       /* Δ_i */
    float Bv[SSM_D_STATE];       /* B_n */
    float Cv[SSM_D_STATE];       /* C_n */
    int i, n, k;

    /* 1) depthwise causal conv1d(FIR) + SiLU. 링버퍼에 x 밀어넣고 커널 곱-누적. */
    unsigned char head = s->conv_head;
    for (i = 0; i < SSM_D_INNER; ++i) s->conv_buf[i][head] = x[i];
    for (i = 0; i < SSM_D_INNER; ++i) {
        float acc = 0.0f;
        /* buf[head] 가 가장 최신. k=0 최신 탭에 conv_w[i][K-1] 매칭(causal). */
        for (k = 0; k < SSM_CONV_K; ++k) {
            int idx = (int)head - k;
            if (idx < 0) idx += SSM_CONV_K;
            acc += w->conv_w[i][SSM_CONV_K - 1 - k] * s->conv_buf[i][idx];
        }
        u[i] = silu(acc);
    }
    s->conv_head = (unsigned char)((head + 1) % SSM_CONV_K);

    /* 2) 입력의존 투영: Δ_i = softplus(W_dt·u + b), B_n=W_B·u, C_n=W_C·u. (matvec) */
    for (i = 0; i < SSM_D_INNER; ++i) {
        float acc = w->b_dt[i];
        for (k = 0; k < SSM_D_INNER; ++k) acc += w->W_dt[i][k] * u[k];
        dt[i] = softplus(acc);
    }
    for (n = 0; n < SSM_D_STATE; ++n) {
        float ab = 0.0f, ac = 0.0f;
        for (k = 0; k < SSM_D_INNER; ++k) { ab += w->W_B[n][k] * u[k]; ac += w->W_C[n][k] * u[k]; }
        Bv[n] = ab; Cv[n] = ac;
    }

    /* 3) 선택적 상태 갱신 + 읽기 (채널별 IIR 뱅크).
     *    Ā_in=exp(Δ_i·A_in)∈(0,1)(A<0), h=Ā·h + (Δ·B)·u, y=Σ C·h + D·u. */
    for (i = 0; i < SSM_D_INNER; ++i) {
        float yi = w->D[i] * u[i];
        float dti = dt[i];
        for (n = 0; n < SSM_D_STATE; ++n) {
            float abar = expf(dti * w->A[i][n]);        /* [FX] LUT: Δ·A<0 → (0,1) */
            float bbar = dti * Bv[n];
            s->h[i][n] = abar * s->h[i][n] + bbar * u[i];
            yi += Cv[n] * s->h[i][n];
        }
        y[i] = yi;
    }
}
