/* sar_core.c -- SAR 데모용 얇은 C-ABI 껍데기. 논문이 측정한 그 policy_core.c 를 그대로
 * 부른다(정책·belief 는 동일 코어). Python(map_demo.py)이 ctypes 로 부른다.
 *   sar_next   : 현 belief 에서 다음 관측 셀 선택 (pc_policy_step, 명목 카메라 모델로 계획)
 *   sar_update : 관측(탐지/미탐) -> 베이즈 belief 갱신 (pc_belief_update)
 * 관측 자체(탐지 여부·위치)는 Python 이 실제 cv2 탐지기로 만들어 넣는다 -- 여기선 계획만.
 * belief 는 float[PC_GRID_N] 평면 배열로 주고받는다(PC_Belief 와 동일 레이아웃). */
#include "policy_core.h"
#include <math.h>
#include <string.h>

/* 계획용 명목 카메라 관측모델(실제 탐지는 Python cv2). p_useful 은 거리로 감소. */
static float nom_p(const void *c, float r, float a, const PC_Env *e) {
    (void)c; (void)a; (void)e;
    float x = r / 30.0f; float p = 0.9f * expf(-x * x);
    return p < 0.02f ? 0.02f : p;
}
static float nom_s(const void *c, float r) { (void)c; return 0.8f + 0.02f * r; }

static PC_ObsModel MODEL = { nom_p, nom_s, 0, 0 };
static PC_Cfg CFG;
static int INIT = 0;
static void ensure(void) {
    if (INIT) return;
    CFG.alpha = 1.f; CFG.beta = 0.05f; CFG.gamma = 0.01f;
    CFG.cell_m = 5.f; CFG.r_max_cells = 9.f; CFG.v_nom = 1.f; CFG.t_obs = 0.5f;
    CFG.n_look_max = 6; CFG.cost_uncert_pow = 2; CFG.v_min = 0.2f; CFG.safe_slow_cells = 4.f;
    INIT = 1;
}

int sar_grid_w(void) { return PC_GRID_W; }
int sar_grid_h(void) { return PC_GRID_H; }
void sar_set_rmax(float r) { ensure(); CFG.r_max_cells = r; }

void sar_next(const float *belief, float vx, float vy,
              float *out_tx, float *out_ty, int *out_nlook) {
    ensure();
    PC_Belief b; memcpy(b.p, belief, sizeof(float) * PC_GRID_N);
    PC_Vehicle veh; veh.x = vx; veh.y = vy; veh.theta = 0; veh.batt = 1;
    PC_Env env = { 0.f, 1.f, 1.f, 0.f };
    PC_Action a = pc_policy_step(&b, &veh, &MODEL, 1, &env, &CFG);
    *out_tx = a.tgt_x; *out_ty = a.tgt_y; *out_nlook = a.n_look;
}

void sar_update(float *belief, float atx, float aty, int detect, float mx, float my) {
    ensure();
    PC_Belief b; memcpy(b.p, belief, sizeof(float) * PC_GRID_N);
    PC_Vehicle at; at.x = atx; at.y = aty; at.theta = 0; at.batt = 1;
    PC_Env env = { 0.f, 1.f, 1.f, 0.f };
    pc_belief_update(&b, &at, &MODEL, &env, &CFG, detect, mx, my);
    memcpy(belief, b.p, sizeof(float) * PC_GRID_N);
}

float sar_entropy(const float *belief) {
    PC_Belief b; memcpy(b.p, belief, sizeof(float) * PC_GRID_N);
    return pc_belief_entropy(&b);
}
void sar_argmax(const float *belief, float *ax, float *ay, float *ap) {
    PC_Belief b; memcpy(b.p, belief, sizeof(float) * PC_GRID_N);
    pc_belief_argmax(&b, ax, ay, ap);
}
