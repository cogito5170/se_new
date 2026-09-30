/* estimator.h — 등속(constant-velocity) 칼만. 위치 + 속도 + 운동 일관성(NIS).
 *
 * 계보: Kalman(1960) → belief 의 수치 기반. 정위치 모델(이전)은 움직이는 표적을 못 따라가
 * RMSE 개선에만 썼다. 여기서는 축별 2상태 CV 필터(상태 [p,v])로 **속도**를 추정하고, 매 갱신의
 * **innovation consistency d²=rᵀS⁻¹r(NIS)** 를 낸다 — 측정이 예측 궤적과 얼마나 어긋나나.
 * NIS 는 motion consistency 를 decision evidence 로 승격시키는 양이다(점프·불가능 운동 = 큰 NIS).
 *
 * 축을 분리(x,y 독립)해 행렬역 없이 닫힌 꼴로 푼다. NIS(2자유도)=NIS_x+NIS_y.
 */
#ifndef FW_ESTIMATOR_H
#define FW_ESTIMATOR_H

#include <stdbool.h>

typedef struct {
    /* x축 상태 [p,v] 와 공분산 2x2, y축 동일 */
    float xp, xv;  float Px[2][2];
    float yp, yv;  float Py[2][2];
    float q;       /* 프로세스(가속) 잡음 세기 */
    float nis;     /* 마지막 갱신의 innovation consistency(2-DOF) */
    bool  init;
} KalmanCV;

void  fw_kf_init(KalmanCV *kf, float q);
void  fw_kf_predict(KalmanCV *kf);                          /* p+=v(dt=1), 공분산 성장 */
float fw_kf_update(KalmanCV *kf, float zx, float zy, float r);  /* 반환=이번 측정의 NIS */
float fw_kf_sigma(const KalmanCV *kf);                      /* sqrt(Px00+Py00) 위치 불확실도 */
float fw_kf_speed(const KalmanCV *kf);                      /* 추정 속도 크기 |v| */
float fw_kf_nis(const KalmanCV *kf);                        /* 마지막 NIS */

#endif /* FW_ESTIMATOR_H */
