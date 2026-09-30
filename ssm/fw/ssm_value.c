/* ssm_value.c -- SSM(Mamba 원자) 백엔드로 PC_ValueHead 를 채운다. float 참조 구현.
 * 힙/재귀 없음, 결정적. value()=순수(상태복사 후 버림), advance()=지속 전진. */
#include "ssm_value.h"

/* 특징 벡터 -> SSM 입력 채널(현재 1:1, PC_VH_NFEAT==SSM_D_INNER 를 헤더서 강제). */
static void feat_to_x(const float *feat, uint8_t n_feat, float x[SSM_D_INNER]) {
    int i;
    for (i = 0; i < SSM_D_INNER; ++i)
        x[i] = (i < (int)n_feat) ? feat[i] : 0.0f;
}

/* 스칼라 읽기: value = y[0](최소 head). 실제 학습 head 는 w_out·y. */
static float readout(const float y[SSM_D_INNER]) {
    return y[0];
}

/* PC_ValueHead.value: 지속상태를 '복사'해 한 스텝 -> 스칼라. 지속상태 불변(순수). */
static float vh_value(const void *state, const float *feat, uint8_t n_feat) {
    const SSM_ValueCtx *c = (const SSM_ValueCtx *)state;
    SSM_State tmp = c->st;              /* 이력 문맥 복사(스택, 힙 없음) */
    float x[SSM_D_INNER], y[SSM_D_INNER];
    feat_to_x(feat, n_feat, x);
    ssm_step(&c->w, &tmp, x, y);        /* 복사본을 돌린다 -> c->st 는 그대로 */
    return readout(y);
}

/* PC_ValueHead.advance: 지속상태를 실제로 한 스텝 전진(커밋된 관측주기마다). */
static void vh_advance(void *state, const float *feat, uint8_t n_feat) {
    SSM_ValueCtx *c = (SSM_ValueCtx *)state;
    float x[SSM_D_INNER], y[SSM_D_INNER];
    feat_to_x(feat, n_feat, x);
    ssm_step(&c->w, &c->st, x, y);      /* 지속상태 갱신, y 는 버림 */
}

void ssm_value_init(SSM_ValueCtx *c) {
    ssm_reset(&c->st);
}

PC_ValueHead ssm_value_head(SSM_ValueCtx *c, float lambda) {
    PC_ValueHead vh;
    vh.value   = vh_value;
    vh.advance = vh_advance;
    vh.state   = c;
    vh.w       = &c->w;
    vh.lambda  = lambda;
    return vh;
}
