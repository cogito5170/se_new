/* estimator.c — 축별 2상태 등속 칼만(닫힌 꼴, 행렬역 없음) + NIS. */
#include <math.h>
#include "estimator.h"

#define KF_V0        4.0f    /* 초기 속도 불확실도 */
#define KF_REINIT_D2 50.0f   /* NIS 가 이보다 크면 추적 상실/새 표적 → 재초기화 */

static void axis_init(float *p, float *v, float P[2][2], float z, float r)
{
    *p = z; *v = 0.0f;
    P[0][0] = r;   P[0][1] = 0.0f;
    P[1][0] = 0.0f; P[1][1] = KF_V0;
}

void fw_kf_init(KalmanCV *kf, float q)
{
    kf->xp = kf->xv = 0.0f; kf->yp = kf->yv = 0.0f;
    kf->Px[0][0] = KF_V0; kf->Px[0][1] = 0; kf->Px[1][0] = 0; kf->Px[1][1] = KF_V0;
    kf->Py[0][0] = KF_V0; kf->Py[0][1] = 0; kf->Py[1][0] = 0; kf->Py[1][1] = KF_V0;
    kf->q = q; kf->nis = 0.0f; kf->init = false;
}

/* 한 축 예측: p+=v, P = F P F^T + Q. F=[[1,1],[0,1]], Q=q*[[1/4,1/2],[1/2,1]] (가속 잡음) */
static void axis_predict(float *p, float v, float P[2][2], float q)
{
    *p += v;
    float p00 = P[0][0], p01 = P[0][1], p10 = P[1][0], p11 = P[1][1];
    P[0][0] = p00 + p01 + p10 + p11 + 0.25f * q;
    P[0][1] = p01 + p11 + 0.5f * q;
    P[1][0] = p10 + p11 + 0.5f * q;
    P[1][1] = p11 + q;
}

void fw_kf_predict(KalmanCV *kf)
{
    axis_predict(&kf->xp, kf->xv, kf->Px, kf->q);
    axis_predict(&kf->yp, kf->yv, kf->Py, kf->q);
}

/* 한 축 갱신(측정 z, 잡음 r). 반환=이 축 innovation 제곱/ S (NIS 기여). */
static float axis_update(float *p, float *v, float P[2][2], float z, float r)
{
    float y = z - *p;            /* innovation */
    float S = P[0][0] + r;       /* innovation 공분산 */
    float K0 = P[0][0] / S, K1 = P[1][0] / S;
    *p += K0 * y; *v += K1 * y;
    float p00 = P[0][0], p01 = P[0][1];
    P[0][0] = (1.0f - K0) * p00;
    P[0][1] = (1.0f - K0) * p01;
    P[1][0] = P[1][0] - K1 * p00;
    P[1][1] = P[1][1] - K1 * p01;
    return y * y / S;
}

float fw_kf_update(KalmanCV *kf, float zx, float zy, float r)
{
    if (!kf->init) {
        axis_init(&kf->xp, &kf->xv, kf->Px, zx, r);
        axis_init(&kf->yp, &kf->yv, kf->Py, zy, r);
        kf->init = true; kf->nis = 0.0f;
        return 0.0f;
    }
    /* NIS 를 갱신 전에 예측 잔차로 잰다(= 이 측정이 궤적에 얼마나 어긋나나). */
    float rx = zx - kf->xp, ry = zy - kf->yp;
    float d2 = rx * rx / (kf->Px[0][0] + r) + ry * ry / (kf->Py[0][0] + r);
    kf->nis = d2;
    if (d2 > KF_REINIT_D2) {     /* 추적 상실/새 표적: 재초기화(그 자리에서 새 궤적) */
        axis_init(&kf->xp, &kf->xv, kf->Px, zx, r);
        axis_init(&kf->yp, &kf->yv, kf->Py, zy, r);
        return d2;
    }
    axis_update(&kf->xp, &kf->xv, kf->Px, zx, r);
    axis_update(&kf->yp, &kf->yv, kf->Py, zy, r);
    return d2;
}

float fw_kf_sigma(const KalmanCV *kf) { return sqrtf(kf->Px[0][0] + kf->Py[0][0]); }
float fw_kf_speed(const KalmanCV *kf) { return sqrtf(kf->xv * kf->xv + kf->yv * kf->yv); }
float fw_kf_nis(const KalmanCV *kf)   { return kf->nis; }
