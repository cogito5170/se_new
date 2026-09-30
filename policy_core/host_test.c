/* host_test.c -- 데스크톱에서 policy_core 를 돌려 창발·RTA·belief 갱신을 증명.
 * "C 코어가 Python 시뮬(recon/sensor_agnostic.py)과 같은 행동을 낸다"를 붙든다.
 * UGV 현실 센서 3종 어댑터(Camera·LiDAR·Thermal)와 조명 노브(낮->밤)로 센서선택이
 * 손코딩 없이 창발하는지 본다. 정책 코어는 이 어댑터들이 무엇인지 모른다. */
#include "policy_core.h"
#include <math.h>
#include <stdio.h>

/* ── 관측모델 어댑터: 유일한 센서-특정 조각. 코어는 함수포인터만 본다 ── */
/* Camera: 고해상, 조명 의존(밤에 죽음). */
static float cam_p(const void *c, float r, float a, const PC_Env *e) {
    (void)c; (void)a; return 0.92f * expf(-(r / 25.f) * (r / 25.f)) * e->illum;
}
static float cam_s(const void *c, float r) { (void)c; return 0.30f + 0.010f * r; }
/* LiDAR: 조명 무관(능동), 중간 해상, 거리 제한. */
static float lid_p(const void *c, float r, float a, const PC_Env *e) {
    (void)c; (void)a; (void)e; return 0.80f * expf(-(r / 18.f) * (r / 18.f));
}
static float lid_s(const void *c, float r) { (void)c; return 0.50f + 0.020f * r; }
/* Thermal: 조명 무관(주야), 중고해상. */
static float thr_p(const void *c, float r, float a, const PC_Env *e) {
    (void)c; (void)a; (void)e; return 0.85f * expf(-(r / 22.f) * (r / 22.f));
}
static float thr_s(const void *c, float r) { (void)c; return 0.40f + 0.015f * r; }

static int inside_keepout(float x, float y, float tx, float ty, float ko) {
    float dx = x - tx, dy = y - ty; return (dx * dx + dy * dy) < ko * ko;
}
static PC_Cfg mkcfg(void) {
    PC_Cfg c; c.alpha = 1.f; c.beta = 0.02f; c.gamma = 0.01f;
    c.cell_m = 5.f; c.r_max_cells = 9.f; c.v_nom = 1.f;   /* 5m/셀, 1m/s -> 5s/셀 이동 */
    c.t_obs = 0.5f;                                        /* 관측 한 번 0.5s */
    c.n_look_max = 6;                                      /* 내부 tau* 가 보이게 */
    c.cost_uncert_pow = 0;                                 /* NOW-1 τ 잠금: 적응 끔(full 비용) */
    c.v_min = 0.2f;                                        /* 가변속도 하한 */
    c.safe_slow_cells = 4.f;                               /* keep-out 4셀 안이면 감속 */
    return c;
}
static void belief_bump(PC_Belief *b, float cx, float cy, float s) {
    int gx, gy; float sum = 0.f;
    for (gy = 0; gy < PC_GRID_H; ++gy) for (gx = 0; gx < PC_GRID_W; ++gx) {
        float d2 = (gx - cx) * (gx - cx) + (gy - cy) * (gy - cy);
        float v = expf(-d2 / (2.f * s * s)) + 0.02f;
        b->p[gy * PC_GRID_W + gx] = v; sum += v;
    }
    { int i; for (i = 0; i < PC_GRID_N; ++i) b->p[i] /= sum; }
}

/* 가치 head '살아있음' 시험용 더미(무상태). SSM 없이 코어 배선만 본다:
 * feat[2]=목적지belief/첨두 비율을 크게 상/하로 매기면 첫 이동 선택이 갈려야 한다. */
static float dummy_val_pos(const void *s, const float *f, uint8_t n) { (void)s; (void)n; return 1000.0f * f[2]; }
static float dummy_val_neg(const void *s, const float *f, uint8_t n) { (void)s; (void)n; return -1000.0f * f[2]; }

int main(void) {
    PC_ObsModel M[3];
    M[0].p_useful = cam_p; M[0].precision = cam_s; M[0].cfg = 0; M[0].id = 0; /* Camera */
    M[1].p_useful = lid_p; M[1].precision = lid_s; M[1].cfg = 0; M[1].id = 1; /* LiDAR  */
    M[2].p_useful = thr_p; M[2].precision = thr_s; M[2].cfg = 0; M[2].id = 2; /* Thermal*/
    const char *NAME[3] = { "Camera", "LiDAR", "Thermal" };
    PC_Cfg cfg = mkcfg();
    PC_Vehicle veh = { 5.f, 5.f, 0.f, 1.f };
    PC_Belief b; belief_bump(&b, 9.f, 9.f, 1.2f);   /* 표적 질량 근처(관측반경 안) */
    int fails = 0;

    /* 1. 창발: 조명 쓸기서 정책이 고르는 센서 (손코딩 규칙 없음) */
    printf("[emergence] illum 1.0(day)->0.0(night) 에서 pi(s) 가 고르는 센서:\n");
    int day_sensor = -1, night_sensor = -1;
    for (int i = 0; i <= 10; ++i) {
        float illum = 1.0f - 0.1f * i;
        PC_Env env = { 0.f, illum, 0.f, 0.f };
        PC_Action a = pc_policy_step(&b, &veh, M, 3, &env, &cfg);
        printf("   illum=%.1f -> %s (n_look=%u)\n", illum, NAME[a.sensor], a.n_look);
        if (i == 0)  day_sensor = a.sensor;
        if (i == 10) night_sensor = a.sensor;
    }
    if (day_sensor != 0) { printf("FAIL: day 에 Camera 안 고름\n"); fails++; }
    if (night_sensor == 0) { printf("FAIL: night 에 Camera 고름(죽었는데)\n"); fails++; }
    if (night_sensor != 2) { printf("FAIL: night 에 Thermal 안 고름(=%d)\n", night_sensor); fails++; }
    printf("  => day=%s, night=%s  (창발: 조명서 센서선택이 손코딩 없이 뒤바뀜)\n",
           NAME[day_sensor], NAME[night_sensor]);

    /* 1b. tau 트레이드오프: 관측시간 tau 가 긴급도(beta)·장면에서 손코딩 없이 갈린다.
     * (예전엔 항상 최대로 포화 -- T_search 를 실제 시간 t_move+tau*t_obs 로 바꿔 고침) */
    printf("\n[tau-sweep] beta(초당가치) 올리며 pi 가 고르는 n_look (day, blob@(9,9)):\n");
    {
        float betas[] = {0.005f, 0.01f, 0.02f, 0.05f, 0.1f, 0.2f, 0.5f, 1.0f};
        int nb = (int)(sizeof(betas)/sizeof(betas[0]));
        PC_Env day = { 0.f, 1.f, 0.f, 0.f };
        uint8_t nl[8]; int i2;
        for (i2 = 0; i2 < nb; ++i2) {
            PC_Cfg cc = cfg; cc.beta = betas[i2];
            PC_Action a = pc_policy_step(&b, &veh, M, 3, &day, &cc);
            nl[i2] = a.n_look;
            printf("   beta=%.3f -> n_look=%u\n", betas[i2], a.n_look);
        }
        /* (a) 저긴급이면 최대까지 본다 */
        if (nl[0] != cfg.n_look_max) { printf("FAIL: 저긴급(beta=0.005)서 최대 관측 안 함\n"); fails++; }
        /* (b) 고긴급이면 한 번 보고 뜬다 */
        if (nl[nb-1] != 1) { printf("FAIL: 고긴급(beta=1.0)서 n_look=1 아님(=%u)\n", nl[nb-1]); fails++; }
        /* (c) 긴급도에 단조 반응(잡음 아님) */
        for (i2 = 1; i2 < nb; ++i2)
            if (nl[i2] > nl[i2-1]) { printf("FAIL: n_look 이 beta 에 단조감소 아님\n"); fails++; break; }
        /* (d) 내부값이 실제로 존재(1<tau*<max) -- 포화도 1도 아닌 진짜 트레이드오프 */
        { int interior = 0; for (i2 = 0; i2 < nb; ++i2) if (nl[i2] > 1 && nl[i2] < cfg.n_look_max) interior = 1;
          if (!interior) { printf("FAIL: 내부 tau*(1<tau<max) 가 어느 beta 서도 안 나옴\n"); fails++; } }
        printf("  => tau* 가 6..1 로 갈림(긴급도서 창발). 이유: EV(tau)=1-(1-p1)^tau 오목,\n"
               "     시간비용 beta*t_obs 선형 -> 한계정보 < 시간비용서 멈춤(MVT).\n");
    }
    printf("[scene-sweep] 고정 beta=0.05, 표적 거리별 n_look (근접=정보 빨리 포화):\n");
    {
        float nl_near, nl_far;
        PC_Env day = { 0.f, 1.f, 0.f, 0.f };
        PC_Cfg cc = cfg; cc.beta = 0.05f;
        PC_Belief bn; belief_bump(&bn, 6.f, 6.f, 1.2f);   /* 근접(약1.4셀) */
        PC_Belief bf; belief_bump(&bf, 5.f, 12.f, 1.2f);  /* 원거리(7셀) */
        PC_Action an = pc_policy_step(&bn, &veh, M, 3, &day, &cc);
        PC_Action af = pc_policy_step(&bf, &veh, M, 3, &day, &cc);
        nl_near = an.n_look; nl_far = af.n_look;
        printf("   근접 blob@(6,6) -> n_look=%u,  원거리 blob@(5,12) -> n_look=%u\n",
               an.n_look, af.n_look);
        /* 근접(고p1, 정보 포화)은 원거리(저p1)보다 덜 본다 */
        if (!(nl_near < nl_far)) { printf("FAIL: 근접이 원거리보다 덜 보지 않음(%g>=%g)\n", nl_near, nl_far); fails++; }
        printf("  => 근접일수록 덜 본다(정보 포화). 장면서 tau 창발, 손코딩 없음.\n");
    }

    /* 1c. cold-start freeze 고침: 확산 belief(먼 곳에 질량) + 비용 β=0.05 에서
     * 적응 끄면(pow=0) 근시안 정책이 제자리에 얼고, 켜면(pow=2) 질량 쪽으로 움직인다. */
    printf("[freeze-fix] 확산 belief(blob@(18,18)), veh@(5,5), beta=0.05:\n");
    {
        PC_Env day = { 0.f, 1.f, 0.f, 0.f };
        PC_Belief bd; belief_bump(&bd, 18.f, 18.f, 5.0f);   /* 넓고 먼 질량(고엔트로피) */
        PC_Cfg c_off = cfg; c_off.beta = 0.05f; c_off.gamma = 0.01f; c_off.cost_uncert_pow = 0;
        PC_Cfg c_on  = c_off; c_on.cost_uncert_pow = 2;
        PC_Action a_off = pc_policy_step(&bd, &veh, M, 3, &day, &c_off);
        PC_Action a_on  = pc_policy_step(&bd, &veh, M, 3, &day, &c_on);
        float mv_off = sqrtf((a_off.tgt_x-veh.x)*(a_off.tgt_x-veh.x)+(a_off.tgt_y-veh.y)*(a_off.tgt_y-veh.y));
        float mv_on  = sqrtf((a_on.tgt_x -veh.x)*(a_on.tgt_x -veh.x)+(a_on.tgt_y -veh.y)*(a_on.tgt_y -veh.y));
        float d_off  = sqrtf((a_off.tgt_x-18.f)*(a_off.tgt_x-18.f)+(a_off.tgt_y-18.f)*(a_off.tgt_y-18.f));
        float d_on   = sqrtf((a_on.tgt_x -18.f)*(a_on.tgt_x -18.f)+(a_on.tgt_y -18.f)*(a_on.tgt_y -18.f));
        float d_veh  = sqrtf((veh.x-18.f)*(veh.x-18.f)+(veh.y-18.f)*(veh.y-18.f));
        printf("   pow=0 -> tgt=(%.0f,%.0f) 이동 %.1f셀 | pow=2 -> tgt=(%.0f,%.0f) 이동 %.1f셀\n",
               a_off.tgt_x, a_off.tgt_y, mv_off, a_on.tgt_x, a_on.tgt_y, mv_on);
        if (mv_off > 0.5f) { printf("FAIL: pow=0 인데 얼지 않음(이동 %.1f)\n", mv_off); fails++; }
        if (mv_on <= 1.0f) { printf("FAIL: pow=2 인데 안 움직임(이동 %.1f)\n", mv_on); fails++; }
        if (!(d_on < d_veh)) { printf("FAIL: pow=2 가 질량 쪽으로 안 감(%.1f>=%.1f)\n", d_on, d_veh); fails++; }
        (void)d_off;
        printf("  => pow=0 얼음, pow=2 질량 쪽으로 탐색(불확실할 때 비용↓ -> freeze 고침).\n");
    }

    /* 2. RTA: 위협 keep-out 이 표적 방향에 있으면 안전행동으로 대체 */
    float dx[PC_MAX_MOVES], dy[PC_MAX_MOVES]; uint8_t nmv; pc_default_moves(dx, dy, &nmv);
    PC_Env night = { 0.f, 0.f, 0.f, 0.f };
    PC_Action a = pc_policy_step(&b, &veh, M, 3, &night, &cfg);
    PC_Safety saf = { a.tgt_x, a.tgt_y, 3.f, 1 };   /* 정책이 가려던 바로 그 셀을 keep-out 로 */
    PC_Action as = pc_rta_filter(a, &veh, &saf, &cfg, dx, dy, nmv);
    if (!as.rta_tripped) { printf("FAIL: RTA 가 keep-out 침범을 안 막음\n"); fails++; }
    if (inside_keepout(as.tgt_x, as.tgt_y, saf.thr_x, saf.thr_y, saf.keepout_cells)) {
        printf("FAIL: RTA 대체 후에도 keep-out 안\n"); fails++;
    }
    printf("[RTA] keep-out 침범 -> 대체 %s (tgt (%.0f,%.0f)->(%.0f,%.0f))\n",
           as.rta_tripped ? "발동" : "미발동", a.tgt_x, a.tgt_y, as.tgt_x, as.tgt_y);

    /* 2b. 가변속도: belief 첨두로 갈수록 느리게, keep-out 경계 근처면 감속-상한 */
    {
        PC_Belief bsp; belief_bump(&bsp, 12.f, 12.f, 1.2f);   /* 첨두 (12,12) */
        float v_peak = pc_belief_speed(&bsp, 12.f, 12.f, &cfg);   /* 첨두로 -> 느림 */
        float v_far  = pc_belief_speed(&bsp,  2.f,  2.f, &cfg);   /* 빈 곳 -> 빠름 */
        float mid = 0.5f * (cfg.v_nom + cfg.v_min);
        if (!(v_peak < v_far)) { printf("FAIL: 첨두서 감속 안 함(%.2f>=%.2f)\n", v_peak, v_far); fails++; }
        if (!(v_peak < mid))   { printf("FAIL: 첨두 속도가 하한 근처 아님(%.2f)\n", v_peak); fails++; }
        if (!(v_far > mid))    { printf("FAIL: 빈 곳 속도가 상한 근처 아님(%.2f)\n", v_far); fails++; }
        /* 안전 속도상한: keep-out(12,12,r3) 경계 근처 목적지(17,12, d_edge=2<4) -> 감속 */
        PC_Safety sk = { 12.f, 12.f, 3.f, 1 };
        PC_Action an; an.sensor=0; an.n_look=1; an.w=0; an.rta_tripped=0;
        an.v = cfg.v_nom; an.tgt_x = 17.f; an.tgt_y = 12.f;      /* keep-out 밖(대체 없음), 경계 근처 */
        PC_Action ac = pc_rta_filter(an, &veh, &sk, &cfg, dx, dy, nmv);
        if (!(ac.v < cfg.v_nom)) { printf("FAIL: keep-out 근처서 속도상한 안 걸림(%.2f)\n", ac.v); fails++; }
        an.tgt_x = 23.f; an.tgt_y = 12.f; an.v = cfg.v_nom;      /* 멀리(d_edge=8>=4) -> 상한 없음 */
        PC_Action af = pc_rta_filter(an, &veh, &sk, &cfg, dx, dy, nmv);
        if (af.v < cfg.v_nom - 1e-3f) { printf("FAIL: 먼 곳인데 속도상한 걸림(%.2f)\n", af.v); fails++; }
        printf("[speed] belief 첨두 v=%.2f < 빈곳 v=%.2f | keep-out 근처 v=%.2f < 먼곳 v=%.2f (감속)\n",
               v_peak, v_far, ac.v, af.v);
    }

    /* 3. belief 갱신: 탐지 시 엔트로피 감소(정보이득) */
    float H0 = pc_belief_entropy(&b);
    PC_Belief b2 = b;
    pc_belief_update(&b2, &veh, &M[2], &night, &cfg, 1, 9.f, 9.f);
    float H1 = pc_belief_entropy(&b2);
    if (!(H1 < H0)) { printf("FAIL: 탐지 후 엔트로피 안 줄음 %.3f->%.3f\n", H0, H1); fails++; }
    printf("[belief] 탐지 관측 -> 엔트로피 %.3f -> %.3f (정보이득)\n", H0, H1);

    /* 4. 학습 가치 head 배선: (a) vh=NULL/λ=0 은 la2 와 '동일 행동'(하위호환 불변식),
     *    (b) λ>0 이면 head 가 첫 이동을 실제로 바꾼다(죽은 코드 아님). RTA 는 별개로 무조건. */
    {
        PC_Belief bv; belief_bump(&bv, 12.f, 6.f, 1.2f);
        PC_Action a_la2  = pc_policy_step_la2(&bv, &veh, M, 3, &night, &cfg, 0.9f);
        PC_ValueHead vh0; vh0.value = dummy_val_pos; vh0.advance = 0; vh0.state = 0; vh0.w = 0; vh0.lambda = 0.0f;
        PC_Action a_l0   = pc_policy_step_val(&bv, &veh, M, 3, &night, &cfg, 0.9f, &vh0);
        PC_Action a_null = pc_policy_step_val(&bv, &veh, M, 3, &night, &cfg, 0.9f, 0);
        int same0 = (a_l0.sensor==a_la2.sensor && a_l0.n_look==a_la2.n_look &&
                     a_l0.tgt_x==a_la2.tgt_x && a_l0.tgt_y==a_la2.tgt_y && a_l0.v==a_la2.v);
        int samen = (a_null.sensor==a_la2.sensor && a_null.tgt_x==a_la2.tgt_x && a_null.tgt_y==a_la2.tgt_y);
        if (!same0 || !samen) { printf("FAIL: λ=0/vh=NULL 이 la2 와 다름(하위호환 깨짐)\n"); fails++; }

        PC_ValueHead vhp; vhp.value = dummy_val_pos; vhp.advance = 0; vhp.state = 0; vhp.w = 0; vhp.lambda = 1.0f;
        PC_ValueHead vhn; vhn.value = dummy_val_neg; vhn.advance = 0; vhn.state = 0; vhn.w = 0; vhn.lambda = 1.0f;
        PC_Action a_pos = pc_policy_step_val(&bv, &veh, M, 3, &night, &cfg, 0.9f, &vhp);
        PC_Action a_neg = pc_policy_step_val(&bv, &veh, M, 3, &night, &cfg, 0.9f, &vhn);
        if (a_pos.tgt_x==a_neg.tgt_x && a_pos.tgt_y==a_neg.tgt_y) {
            printf("FAIL: 반대 부호 가치 head 가 같은 첫 이동(head 가 죽어있음)\n"); fails++; }
        printf("[valhead] λ=0==la2, 반대부호 head 는 첫 이동 갈림 (%g,%g)vs(%g,%g) -- 살아있음\n",
               a_pos.tgt_x, a_pos.tgt_y, a_neg.tgt_x, a_neg.tgt_y);
    }

    printf(fails ? "\npolicy_core host_test: %d FAIL\n" : "\npolicy_core host_test: ALL PASS\n", fails);
    return fails ? 1 : 0;
}
