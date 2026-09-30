/* recon_bridge.c — 호스트(파이썬 ctypes) ↔ RECON 프로파일. 커널 스텝 순서를 그대로 밟되
 * BT 제안·중재 결과·안전필터 결과를 따로 돌려준다(데모 화면의 '정책 상태' 칸). */
#include <stdlib.h>
#include "agent.h"
#include "policy_spec.h"
#include "evidence.h"
#include "decision.h"
#include "planner.h"
#include "arbiter.h"
#include "safety.h"

extern const PolicySpec FW_PROFILE_RECON;

typedef struct {
    float cand[5][3];       /* obs[i] = {evidence, x, y} */
    float health[5];
    float battery, collision, pos_sigma;
    int   gps_valid, imu_valid, actuator_ok;
} ReconIn;

typedef struct { int bt, arb, act, safety, mode, plan_ticks, ev_mask, ev_sensor_mask; } ReconOut;

Agent *recon_new(void)
{
    Agent *a = (Agent *)calloc(1, sizeof(Agent));
    if (a) fw_agent_init_profile(a, &FW_PROFILE_RECON);
    return a;
}
void recon_free(Agent *a) { free(a); }
int  recon_sizeof_agent(void) { return (int)sizeof(Agent); }
const char *recon_action_name(int a) { return (a >= 0 && a < FW_PROFILE_RECON.n_actions) ? FW_PROFILE_RECON.action_names[a] : "?"; }

int recon_step(Agent *a, const ReconIn *in, ReconOut *out)
{
    Blackboard *bb = &a->bb;
    int i; Action cand, arb, act;
    for (i = 0; i < FW_N_SENSOR; i++) {
        bb->obs[i].present  = false;
        bb->obs[i].evidence = in->cand[i][0];
        bb->obs[i].x = in->cand[i][1];
        bb->obs[i].y = in->cand[i][2];
        bb->health.health[i] = in->health[i];
    }
    bb->world.battery = in->battery;
    bb->world.collision_risk = in->collision;
    bb->world.position_error = in->pos_sigma;
    bb->world.gps_valid = in->gps_valid != 0;
    bb->world.imu_valid = in->imu_valid != 0;
    bb->world.actuator_ok = in->actuator_ok != 0;
    /* fw_agent_step 과 같은 순서 */
    bb->world.t += 1;
    fw_stale_update(bb, &a->evq);
    fw_evidence_update(bb);
    fw_safety_update(bb, &a->evq, &a->prev_health);
    a->prev_health = bb->health;
    fw_plan_update(bb);
    cand = fw_decision_propose(bb, &a->tree);
    arb  = fw_arbitrate(bb, cand);
    act  = fw_safety_filter(bb, arb);
    a->last_action = act;
    out->bt = (int)cand; out->arb = (int)arb; out->act = (int)act;
    out->safety = (int)bb->safety; out->mode = (int)bb->mode; out->plan_ticks = bb->plan_ticks;
    { Event e; out->ev_mask = 0; out->ev_sensor_mask = 0;
      while (fw_evq_pop(&a->evq, &e)) {             /* 이벤트 비우기: 종류 비트 + 고장 센서 비트 */
          out->ev_mask |= 1 << (int)e.type;
          if (e.type == EV_SENSOR_FAIL || e.type == EV_SENSOR_STALE) out->ev_sensor_mask |= 1 << e.arg;
      } }
    return (int)act;
}
