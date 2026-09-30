/* host_test.c -- 최소 선택적 SSM 커널을 데스크톱서 돌려 성질을 붙든다.
 * 학습 가중치가 없으니 결정적 시험 가중치로 원자의 거동(결정성·IIR 감쇠·안정성)을 본다. */
#include "ssm.h"
#include "ssm_value.h"
#include "policy_core.h"
#include <math.h>
#include <stdio.h>

static int isbad(float v) { return !(v == v) || v > 1e30f || v < -1e30f; } /* NaN/Inf */

static float norm2_h(const SSM_State *s) {
    float a = 0.0f; int i, n;
    for (i = 0; i < SSM_D_INNER; ++i) for (n = 0; n < SSM_D_STATE; ++n) a += s->h[i][n] * s->h[i][n];
    return a;
}

/* 결정적 시험 가중치: A=-0.5(감쇠), Δ 상수(≈0.693), B/C=항등, conv=최신탭, D=0. */
static void mkweights(SSM_Weights *w) {
    int i, n, k;
    for (i = 0; i < SSM_D_INNER; ++i) {
        for (n = 0; n < SSM_D_STATE; ++n) w->A[i][n] = -0.5f;
        for (k = 0; k < SSM_D_INNER; ++k) w->W_dt[i][k] = 0.0f;   /* Δ=softplus(b) */
        w->b_dt[i] = 0.0f;
        w->D[i] = 0.0f;
        for (k = 0; k < SSM_CONV_K; ++k) w->conv_w[i][k] = (k == SSM_CONV_K - 1) ? 1.0f : 0.0f; /* 최신탭=1 */
    }
    for (n = 0; n < SSM_D_STATE; ++n)
        for (k = 0; k < SSM_D_INNER; ++k) { w->W_B[n][k] = (n == k) ? 1.0f : 0.0f; w->W_C[n][k] = (n == k) ? 1.0f : 0.0f; }
}

/* --- 가치 head <-> policy_core 배선 시험용 최소 관측모델 --- */
static float t_puseful(const void *cfg, float range_m, float ang, const PC_Env *e) {
    (void)cfg; (void)ang; (void)e;
    float p = 0.8f - 0.05f * range_m;            /* 근거리 높고 멀수록 낮음 */
    return p < 0.02f ? 0.02f : (p > 0.95f ? 0.95f : p);
}
static float t_prec(const void *cfg, float range_m) {
    (void)cfg; return 1.0f + 0.2f * range_m;     /* 멀수록 흐림[m] */
}
static int act_same(PC_Action a, PC_Action b) {
    return a.sensor == b.sensor && a.n_look == b.n_look &&
           a.tgt_x == b.tgt_x && a.tgt_y == b.tgt_y && a.v == b.v;
}

int main(void) {
    SSM_Weights w; mkweights(&w);
    SSM_State s; ssm_reset(&s);
    float y[SSM_D_INNER];
    int fails = 0, i, t;

    /* 1. reset -> 상태 0 */
    if (norm2_h(&s) != 0.0f) { printf("FAIL: reset 후 상태 0 아님\n"); fails++; }
    { int ok = 1; for (i = 0; i < SSM_D_INNER; ++i) if (s.conv_buf[i][0] != 0.0f) ok = 0;
      if (!ok) { printf("FAIL: reset 후 conv 버퍼 0 아님\n"); fails++; } }

    /* 2. 결정성: 같은 입력 스트림 두 번 -> 동일 출력·상태 */
    {
        SSM_State a, b2; ssm_reset(&a); ssm_reset(&b2);
        float ya[SSM_D_INNER], yb[SSM_D_INNER]; int bad = 0;
        for (t = 0; t < 20; ++t) {
            float x[SSM_D_INNER];
            for (i = 0; i < SSM_D_INNER; ++i) x[i] = 0.3f * (float)((t + i) % 5) - 0.5f;
            ssm_step(&w, &a, x, ya); ssm_step(&w, &b2, x, yb);
            for (i = 0; i < SSM_D_INNER; ++i) if (ya[i] != yb[i]) bad = 1;
        }
        if (bad || norm2_h(&a) != norm2_h(&b2)) { printf("FAIL: 비결정적(같은 입력 다른 출력)\n"); fails++; }
    }

    /* 3. NaN/Inf 없음 (거친 입력 스트림) */
    {
        SSM_State a; ssm_reset(&a); int bad = 0;
        for (t = 0; t < 200; ++t) {
            float x[SSM_D_INNER];
            for (i = 0; i < SSM_D_INNER; ++i) x[i] = (float)(((t * 7 + i * 13) % 21) - 10);  /* -10..10 */
            ssm_step(&w, &a, x, y);
            for (i = 0; i < SSM_D_INNER; ++i) if (isbad(y[i])) bad = 1;
            if (isbad(norm2_h(&a))) bad = 1;
        }
        if (bad) { printf("FAIL: 출력/상태에 NaN/Inf\n"); fails++; }
    }

    /* 4. IIR 감쇠: 입력 쌓은 뒤 0 입력 흘리면 상태가 단조 감쇠(Ā<1). */
    {
        SSM_State a; ssm_reset(&a);
        float x1[SSM_D_INNER], x0[SSM_D_INNER];
        for (i = 0; i < SSM_D_INNER; ++i) { x1[i] = 1.0f; x0[i] = 0.0f; }
        for (t = 0; t < 5; ++t) ssm_step(&w, &a, x1, y);   /* 상태 축적 */
        for (t = 0; t < SSM_CONV_K + 1; ++t) ssm_step(&w, &a, x0, y);  /* conv flush -> u=0 */
        float n_prev = norm2_h(&a); int dec = 1;
        for (t = 0; t < 5; ++t) {
            ssm_step(&w, &a, x0, y);
            float nc = norm2_h(&a);
            if (!(nc < n_prev)) dec = 0;
            n_prev = nc;
        }
        if (!dec) { printf("FAIL: 0 입력서 상태가 단조 감쇠 안 함(IIR 아님)\n"); fails++; }
        printf("[decay] 0 입력 흘리면 상태 ||h||^2 단조 감쇠 -> IIR 확인\n");
    }

    /* 5. 안정성: 상수 입력 오래 -> 상태 유계(수렴), 폭주 없음. A<0 라 Ā∈(0,1). */
    {
        SSM_State a; ssm_reset(&a);
        float xc[SSM_D_INNER]; for (i = 0; i < SSM_D_INNER; ++i) xc[i] = 0.7f;
        float n_last = 0.0f;
        for (t = 0; t < 300; ++t) { ssm_step(&w, &a, xc, y); n_last = norm2_h(&a); }
        if (isbad(n_last) || n_last > 1e6f) { printf("FAIL: 상수입력서 상태 폭주(%.3g)\n", n_last); fails++; }
        printf("[stable] 상수 입력 300스텝 -> ||h||^2=%.3f 유계(A<0 감쇠)\n", n_last);
    }

    /* 6. PC_ValueHead 순수성/결정성: value()는 지속상태를 갱신하지 않는다(후보 leaf 여럿을
     *    점수매겨도 재귀 오염 없음). advance()는 갱신한다. value()는 결정적. */
    {
        SSM_ValueCtx c; c.w = w; ssm_value_init(&c);
        PC_ValueHead vh = ssm_value_head(&c, 0.3f);
        float feat[PC_VH_NFEAT] = { 0.9f, 0.05f, 0.2f, 1.0f };
        float n_before = norm2_h(&c.st);
        float v1 = vh.value(vh.state, feat, PC_VH_NFEAT);
        float v2 = vh.value(vh.state, feat, PC_VH_NFEAT);   /* 두 번째 호출도 같은 문맥 */
        float n_after_value = norm2_h(&c.st);
        if (n_after_value != n_before) { printf("FAIL: value()가 지속상태를 바꿈(순수 아님)\n"); fails++; }
        if (v1 != v2 || isbad(v1)) { printf("FAIL: value() 비결정/NaN\n"); fails++; }
        vh.advance(vh.state, feat, PC_VH_NFEAT);            /* 이제 실제 전진 */
        if (norm2_h(&c.st) == n_before) { printf("FAIL: advance()가 지속상태를 안 바꿈\n"); fails++; }
        printf("[valhead] value() 순수(상태불변)·결정적, advance() 전진 확인\n");
    }

    /* 7. 코어 배선: pc_policy_step_val 이 SSM head 를 받아 유효행동을 낸다(NaN 없음).
     *    그리고 하위호환 불변식 -- lambda=0(및 vh=NULL)은 la2 와 '동일 행동'. RTA 는 이후 적용. */
    {
        PC_ObsModel m; m.p_useful = t_puseful; m.precision = t_prec; m.cfg = 0; m.id = 0;
        PC_Env env; env.weather = 0; env.illum = 1; env.extra0 = 0; env.extra1 = 0;
        PC_Cfg cfg; cfg.alpha = 1.0f; cfg.beta = 0.05f; cfg.gamma = 0.01f;
        cfg.cell_m = 1.0f; cfg.r_max_cells = 6.0f; cfg.v_nom = 1.0f; cfg.t_obs = 0.5f;
        cfg.n_look_max = 3; cfg.cost_uncert_pow = 2; cfg.v_min = 0.2f; cfg.safe_slow_cells = 4.0f;
        PC_Belief b; { int j; for (j = 0; j < PC_GRID_N; ++j) b.p[j] = 1.0f / (float)PC_GRID_N; }
        b.p[13 * PC_GRID_W + 15] += 0.2f;   /* 약한 첨두 */
        { float s = 0.0f; int j; for (j = 0; j < PC_GRID_N; ++j) s += b.p[j];
          for (j = 0; j < PC_GRID_N; ++j) b.p[j] /= s; }
        PC_Vehicle veh; veh.x = 5; veh.y = 5; veh.theta = 0; veh.batt = 1.0f;

        PC_Action a_la2  = pc_policy_step_la2(&b, &veh, &m, 1, &env, &cfg, 0.9f);
        SSM_ValueCtx c; c.w = w; ssm_value_init(&c);
        PC_ValueHead vh0 = ssm_value_head(&c, 0.0f);        /* lambda=0 -> no-op */
        PC_Action a_l0   = pc_policy_step_val(&b, &veh, &m, 1, &env, &cfg, 0.9f, &vh0);
        PC_Action a_null = pc_policy_step_val(&b, &veh, &m, 1, &env, &cfg, 0.9f, 0);
        if (!act_same(a_la2, a_l0) || !act_same(a_la2, a_null)) {
            printf("FAIL: lambda=0/vh=NULL 이 la2 와 다름(하위호환 깨짐)\n"); fails++; }

        PC_ValueHead vhx = ssm_value_head(&c, 0.4f);        /* lambda>0 -> head 참여 */
        PC_Action a_vh = pc_policy_step_val(&b, &veh, &m, 1, &env, &cfg, 0.9f, &vhx);
        if (isbad(a_vh.v) || isbad(a_vh.tgt_x) || isbad(a_vh.tgt_y)) {
            printf("FAIL: value head 행동에 NaN\n"); fails++; }
        int in_grid = (a_vh.tgt_x >= 0 && a_vh.tgt_x <= PC_GRID_W - 1 &&
                       a_vh.tgt_y >= 0 && a_vh.tgt_y <= PC_GRID_H - 1);
        if (!in_grid) { printf("FAIL: value head 목적지 격자 밖\n"); fails++; }

        /* RTA 는 학습과 무관하게 무조건 적용: keep-out 안 목적지는 대체된다. */
        float dx[PC_MAX_MOVES], dy[PC_MAX_MOVES]; uint8_t nmv; pc_default_moves(dx, dy, &nmv);
        PC_Safety saf; saf.thr_x = a_vh.tgt_x; saf.thr_y = a_vh.tgt_y; saf.keepout_cells = 3.0f; saf.active = 1;
        PC_Action a_safe = pc_rta_filter(a_vh, &veh, &saf, &cfg, dx, dy, nmv);
        if (!a_safe.rta_tripped) { printf("FAIL: 목적지가 keep-out 인데 RTA 미작동\n"); fails++; }
        printf("[wire] pc_policy_step_val: lambda=0==la2, lambda>0 유효, RTA 무조건 적용 확인\n");
    }

    printf(fails ? "\nssm host_test: %d FAIL\n" : "\nssm host_test: ALL PASS\n", fails);
    return fails ? 1 : 0;
}
