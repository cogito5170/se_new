/* profile_sar.c — SAR-UAV 도메인 프로파일. 커널이 이 vtable(FW_PROFILE_SAR)로만 도메인에 닿는다.
 * 여기 담긴 것이 곧 "SAR 정책의 내용": 행동 집합·우선순위 트리·precondition·효용·안전 불변식·
 * 계획 단계·지각 가중. 커널(estimator·bt·evidence 융합·arbiter argmax·FDIR 엔진)은 안 건드린다.
 * 이 파일을 통째로 갈아끼우면(profile_<도메인>.c) 같은 커널이 다른 도메인 정책을 돈다.
 * (POLICY.md = 이 프로파일의 명세, POLICY_TOOLKIT.md = 새 프로파일 작성법) */
#include "policy_spec.h"
#include "arbiter.h"
#include "safety.h"
#include "evidence.h"
#include "planner.h"
#include "estimator.h"

#define SAR_PRECOND_BATT_SEARCH 0.15f   /* 이 아래면 탐색조차 멈춘다(안전행동만) */

/* ── 지각 가중(도메인): 위치 정밀·신뢰 순. RGB 정밀 ↔ Audio 방위만 ── */
static const float SAR_VOTE_W[FW_N_SENSOR] = { 1.00f, 0.70f, 0.80f, 0.50f, 0.35f };

static const char *const SAR_ACTION_NAMES[ACT_N] = {
    "NONE", "SEARCH", "APPROACH", "INSPECT", "RETURN", "AVOID", "RELOCALIZE", "EMERGENCY", "ABSTAIN"
};

/* ── BT 조건 술어(블랙보드만 읽는다) ── */
static bool cond_emergency(const Blackboard *bb) { return bb->safety == SAFE_EMERGENCY; }
static bool cond_return(const Blackboard *bb)    { return bb->safety == SAFE_RETURN; }
static bool cond_recovery(const Blackboard *bb)
{
    return bb->safety == SAFE_DEGRADED || !bb->world.imu_valid || !bb->world.gps_valid;
}
static bool cond_confirmed(const Blackboard *bb) { return bb->belief.confirmed; }
static bool cond_abstain(const Blackboard *bb)   { return bb->belief.unconf_run >= FW_ABSTAIN_N; }
static bool cond_candidate(const Blackboard *bb) { return bb->belief.target_conf > 0.5f; }

/* ── 우선순위 행동트리(SELECTOR[SEQUENCE[조건→행동]...], 마지막은 SEARCH fallback) ── */
static void sar_build_bt(BtTree *t)
{
    int root, br, cnd, act;
    fw_bt_reset(t);
    root = fw_bt_add(t, BT_SELECTOR, 0, ACT_NONE);

    br = fw_bt_add(t, BT_SEQUENCE, 0, ACT_NONE);
    cnd = fw_bt_add(t, BT_CONDITION, cond_emergency, ACT_NONE);
    act = fw_bt_add(t, BT_ACTION, 0, ACT_EMERGENCY);
    fw_bt_child(t, br, cnd); fw_bt_child(t, br, act); fw_bt_child(t, root, br);

    br = fw_bt_add(t, BT_SEQUENCE, 0, ACT_NONE);
    cnd = fw_bt_add(t, BT_CONDITION, cond_return, ACT_NONE);
    act = fw_bt_add(t, BT_ACTION, 0, ACT_RETURN);
    fw_bt_child(t, br, cnd); fw_bt_child(t, br, act); fw_bt_child(t, root, br);

    br = fw_bt_add(t, BT_SEQUENCE, 0, ACT_NONE);
    cnd = fw_bt_add(t, BT_CONDITION, cond_recovery, ACT_NONE);
    act = fw_bt_add(t, BT_ACTION, 0, ACT_RELOCALIZE);
    fw_bt_child(t, br, cnd); fw_bt_child(t, br, act); fw_bt_child(t, root, br);

    br = fw_bt_add(t, BT_SEQUENCE, 0, ACT_NONE);
    cnd = fw_bt_add(t, BT_CONDITION, cond_confirmed, ACT_NONE);
    act = fw_bt_add(t, BT_ACTION, 0, ACT_INSPECT);
    fw_bt_child(t, br, cnd); fw_bt_child(t, br, act); fw_bt_child(t, root, br);

    br = fw_bt_add(t, BT_SEQUENCE, 0, ACT_NONE);
    cnd = fw_bt_add(t, BT_CONDITION, cond_abstain, ACT_NONE);
    act = fw_bt_add(t, BT_ACTION, 0, ACT_ABSTAIN);
    fw_bt_child(t, br, cnd); fw_bt_child(t, br, act); fw_bt_child(t, root, br);

    br = fw_bt_add(t, BT_SEQUENCE, 0, ACT_NONE);
    cnd = fw_bt_add(t, BT_CONDITION, cond_candidate, ACT_NONE);
    act = fw_bt_add(t, BT_ACTION, 0, ACT_APPROACH);
    fw_bt_child(t, br, cnd); fw_bt_child(t, br, act); fw_bt_child(t, root, br);

    act = fw_bt_add(t, BT_ACTION, 0, ACT_SEARCH);
    fw_bt_child(t, root, act);
}

/* ── precondition: a 를 지금 실행해도 되나 ── */
static bool sar_precondition(const Blackboard *bb, int a)
{
    switch (a) {
        case ACT_INSPECT:
            return bb->belief.confirmed && bb->world.collision_risk < 0.5f && bb->world.battery > 0.3f;
        case ACT_APPROACH:
            return bb->belief.target_conf > 0.5f && bb->world.collision_risk < 0.5f && bb->world.battery > 0.25f;
        case ACT_RELOCALIZE:
            return bb->safety == SAFE_DEGRADED || !bb->world.gps_valid || !bb->world.imu_valid
                   || bb->world.position_error > 3.0f;
        case ACT_SEARCH:
            return bb->world.battery > SAR_PRECOND_BATT_SEARCH;
        default:
            return true;   /* RETURN·AVOID·EMERGENCY·NONE·ABSTAIN 은 언제나 가능 */
    }
}

static float sar_energy_cost(int a)
{
    switch (a) {
        case ACT_INSPECT:    return 0.7f;
        case ACT_APPROACH:   return 0.5f;
        case ACT_RELOCALIZE: return 0.3f;
        case ACT_SEARCH:     return 0.2f;
        case ACT_RETURN:     return 0.2f;
        case ACT_AVOID:      return 0.4f;
        case ACT_EMERGENCY:  return 0.1f;
        default:             return 0.0f;
    }
}

/* ── 효용 U = mission − 충돌벌 − 에너지벌 − 불확실도벌 (ABSTAIN 은 argmax 경쟁서 제외) ── */
static float sar_utility(const Blackboard *bb, int a)
{
    if (a == ACT_ABSTAIN) return -1e30f;   /* BT 의 명시적 판정이지 효용 경쟁 대상 아님 */
    float mission = 0.0f;
    switch (a) {
        case ACT_INSPECT:    mission = 1.0f * bb->belief.target_conf; break;
        case ACT_APPROACH:   mission = 0.7f * bb->belief.target_conf; break;
        case ACT_SEARCH:     mission = 0.35f; break;
        case ACT_RELOCALIZE: mission = 0.4f * bb->world.position_error; break;
        case ACT_RETURN:     mission = 0.2f; break;
        default:             mission = 0.0f; break;
    }
    float collision_pen = 1.0f * bb->world.collision_risk;
    float energy_pen    = 0.3f * sar_energy_cost(a);
    float uncert_pen    = 0.2f * bb->belief.sigma;
    return mission - collision_pen - energy_pen - uncert_pen;
}

/* ── 도메인 FDIR: 충돌·전력·구동계 이벤트 + SafetyState 전이(임계는 SAR 정책) ── */
static void sar_safety_update(Blackboard *bb, EventQueue *q)
{
    int i;
    if (bb->world.collision_risk >= FW_COLLISION_HARD)
        fw_evq_push(q, EV_COLLISION, 0, bb->world.t);
    if (bb->world.battery < FW_BATTERY_RETURN)
        fw_evq_push(q, EV_BATTERY_LOW, 0, bb->world.t);
    if (!bb->world.actuator_ok)
        fw_evq_push(q, EV_ACTUATOR_FAIL, 0, bb->world.t);

    if (bb->world.collision_risk >= FW_COLLISION_HARD || bb->world.battery < FW_BATTERY_EMERG) {
        bb->safety = SAFE_EMERGENCY;
    } else if (bb->world.battery < FW_BATTERY_RETURN) {
        bb->safety = SAFE_RETURN;
    } else {
        int dead = 0;
        for (i = 0; i < FW_N_SENSOR; i++) if (bb->health.health[i] < FW_HEALTH_FAIL) dead++;
        if (!bb->world.imu_valid || !bb->world.gps_valid || dead >= 2)
            bb->safety = SAFE_DEGRADED;
        else
            bb->safety = SAFE_NORMAL;
    }
}

/* ── 최종 하드 override: 어떤 결정 위에도 안전이 이긴다(위험 우선) ── */
static int sar_safety_filter(const Blackboard *bb, int proposed)
{
    if (!bb->world.actuator_ok)                     return ACT_NONE;
    if (bb->world.collision_risk >= FW_COLLISION_HARD) return ACT_AVOID;
    if (bb->world.battery < FW_BATTERY_EMERG)       return ACT_EMERGENCY;
    if (bb->world.battery < FW_BATTERY_RETURN)      return ACT_RETURN;
    if (!bb->world.imu_valid)                       return ACT_RELOCALIZE;
    if ((proposed == ACT_APPROACH || proposed == ACT_INSPECT) && bb->world.collision_risk >= 0.5f)
        return ACT_SEARCH;
    return proposed;
}

/* ── 계획 단계 순차 + 재계획(SEARCH→APPROACH→INSPECT→REPORT→SEARCH) ── */
static void sar_set_phase(Blackboard *bb, int ph)
{
    if (bb->plan_phase != ph) { bb->plan_phase = ph; bb->plan_ticks = 0; }
}

static void sar_plan_update(Blackboard *bb)
{
    if (bb->safety == SAFE_EMERGENCY) { sar_set_phase(bb, PH_RETURN); bb->mode = MODE_EMERGENCY; return; }
    if (bb->safety == SAFE_RETURN)    { sar_set_phase(bb, PH_RETURN); bb->mode = MODE_RETURN; return; }
    if (bb->safety == SAFE_DEGRADED)  { sar_set_phase(bb, PH_RELOCALIZE); bb->mode = MODE_RECOVERY; return; }

    switch (bb->plan_phase) {
        case PH_RELOCALIZE:
        case PH_RETURN:
            sar_set_phase(bb, PH_SEARCH);
            break;
        case PH_SEARCH:
            if (bb->belief.target_conf > 0.5f) sar_set_phase(bb, PH_APPROACH);
            break;
        case PH_APPROACH:
            if (bb->belief.confirmed) sar_set_phase(bb, PH_INSPECT);
            else if (bb->belief.target_conf <= 0.3f) sar_set_phase(bb, PH_SEARCH);
            break;
        case PH_INSPECT:
            bb->plan_ticks += 1;
            if (bb->plan_ticks >= FW_INSPECT_DWELL) sar_set_phase(bb, PH_REPORT);
            break;
        case PH_REPORT:
            bb->belief.confirmed = false; bb->belief.confirm_run = 0; bb->belief.target_conf = 0.0f;
            fw_kf_init(&bb->kf, bb->kf.q);
            sar_set_phase(bb, PH_SEARCH);
            break;
        default:
            sar_set_phase(bb, PH_SEARCH);
            break;
    }

    switch (bb->plan_phase) {
        case PH_APPROACH:
        case PH_INSPECT:
        case PH_REPORT:     bb->mode = MODE_INVESTIGATE; break;
        case PH_RELOCALIZE: bb->mode = MODE_RECOVERY;    break;
        case PH_RETURN:     bb->mode = MODE_RETURN;      break;
        default:            bb->mode = MODE_SEARCH;      break;
    }
}

const PolicySpec FW_PROFILE_SAR = {
    .name         = "SAR-UAV",
    .n_actions    = ACT_N,
    .action_names = SAR_ACTION_NAMES,
    .act_none     = ACT_NONE,
    .act_fallback = ACT_SEARCH,
    .build_bt      = sar_build_bt,
    .precondition  = sar_precondition,
    .utility       = sar_utility,
    .safety_filter = sar_safety_filter,
    .safety_update = sar_safety_update,
    .plan_update   = sar_plan_update,
    .vote_w        = SAR_VOTE_W,
    .blocked_mask  = (1u << SEN_RGB) | (1u << SEN_THERMAL) | (1u << SEN_LIDAR),
    .allw_mask     = (1u << SEN_SAR) | (1u << SEN_AUDIO),
};
