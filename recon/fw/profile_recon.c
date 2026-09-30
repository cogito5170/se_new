/* profile_recon.c — RECON-R1 정찰·정보수집 로버 정책 프로파일.
 * SE 저장소 fw/ 커널(blackboard·BT·arbiter·FDIR 엔진)을 **한 줄도 안 고치고** 재사용한다.
 * 이 파일은 저장소 밖(scratchpad)에 있고 저장소의 커널 소스를 읽기만 해서 함께 컴파일한다.
 *
 * 채널 재사용(도메인 재명명 — 표적 융합은 쓰지 않으므로 vote_w=0, present=false):
 *   obs[0] = 탐사 후보   evidence=J_explore(0..1)  x,y=목표[m]
 *   obs[1] = 재방문 후보 evidence=J_revisit        x,y=목표[m]
 *   obs[2] = 제자리 관측 evidence=J_observe        x,y=현재 위치
 *   obs[3] = 임무        evidence=커버리지(0..1)   x=귀환에 필요한 배터리 비율  y=저장소 사용률
 *   obs[4] = 주행        evidence=슬립률(0..1)     x=링크 끊긴 시간/30s        y=경사/한계경사
 *   health = LIDAR, IMU, ENCODER, CAMERA, GNSS  (0..1)
 *   world  = battery, collision_risk(전방 장애·음장애·동적), position_error=자세 σ[m],
 *            gps_valid, imu_valid, actuator_ok
 * 목적함수 J 의 각 항은 호스트(Jetson)가 원시 데이터로 계산한다(recon/sim/policy.py 와 같은 식).
 * 이 커널은 guard → BT 우선순위 → precondition+효용 중재 → 안전 필터를 결정적으로 돈다. */
#include "policy_spec.h"

#define R_HOLD       0
#define R_EXPLORE    1
#define R_OBSERVE    2
#define R_REVISIT    3
#define R_RETURN     4
#define R_AVOID      5
#define R_RELOCALIZE 6
#define R_SAFE_STOP  7
#define R_EMERGENCY  8
#define R_N          9

enum { H_LIDAR = 0, H_IMU, H_ENC, H_CAM, H_GNSS };

/* 임계(가정 — 실험 TEST-05/08 에서 조정할 값) */
#define TH_HEALTH      0.5f
#define TH_COLL_AVOID  0.60f
#define TH_COLL_STOP   0.92f
#define TH_SLIP_AVOID  0.45f
#define TH_TILT_AVOID  0.80f
#define TH_TILT_STOP   1.00f
#define TH_SIGMA_RELOC 0.35f   /* m */
#define TH_SIGMA_STOP  1.20f   /* m: 이 이상이면 지도에 쓰는 것 자체가 해롭다 */
#define BAT_MARGIN     0.08f
#define BAT_CRIT       0.05f
#define COV_DONE       0.92f
#define STORE_FULL     0.98f
#define LINK_LOST      1.0f    /* 30 s */

static const char *const R_NAMES[R_N] = {
    "HOLD", "EXPLORE", "OBSERVE", "REVISIT", "RETURN", "AVOID", "RELOCALIZE", "SAFE_STOP", "EMERGENCY" };
static const float R_VOTE_W[FW_N_SENSOR] = { 0, 0, 0, 0, 0 };

#define J_EXP(bb)   ((bb)->obs[0].evidence)
#define J_REV(bb)   ((bb)->obs[1].evidence)
#define J_OBS(bb)   ((bb)->obs[2].evidence)
#define COV(bb)     ((bb)->obs[3].evidence)
#define BAT_NEED(bb)((bb)->obs[3].x)
#define STORE(bb)   ((bb)->obs[3].y)
#define SLIP(bb)    ((bb)->obs[4].evidence)
#define LINK(bb)    ((bb)->obs[4].x)
#define TILT(bb)    ((bb)->obs[4].y)
#define HOK(bb, i)  ((bb)->health.health[i] >= TH_HEALTH)

/* ── guard (조건) ── */
static bool g_emerg(const Blackboard *bb) { return !bb->world.actuator_ok || bb->world.battery < BAT_CRIT; }
static bool g_nav_lost(const Blackboard *bb)
{   /* 자세를 이어 갈 수단이 하나도 없다: LiDAR·엔코더·IMU 모두 죽음 또는 σ 폭주 */
    int alive = HOK(bb, H_LIDAR) + HOK(bb, H_ENC) + (HOK(bb, H_IMU) && bb->world.imu_valid);
    return alive == 0 || bb->world.position_error > TH_SIGMA_STOP;
}
static bool g_stop(const Blackboard *bb)
{ return bb->world.collision_risk > TH_COLL_STOP || TILT(bb) >= TH_TILT_STOP || g_nav_lost(bb); }
static bool g_avoid(const Blackboard *bb)
{ return bb->world.collision_risk > TH_COLL_AVOID || SLIP(bb) > TH_SLIP_AVOID || TILT(bb) > TH_TILT_AVOID; }
/* 배터리 귀환은 걸쇠다: 한 번 SAFE_RETURN 이 되면 여유 +5 % 까지 풀리지 않는다.
 * 첫 판은 집으로 갈수록 '귀환 필요' 가 줄어 guard 가 풀리고 다시 탐사로 나가 12 번 오갔다(F09). */
static bool bat_low(const Blackboard *bb)
{
    float th = BAT_NEED(bb) + BAT_MARGIN + (bb->safety == SAFE_RETURN ? 0.05f : 0.0f);
    return bb->world.battery < th;
}
static bool g_return(const Blackboard *bb)
{
    return bat_low(bb) || STORE(bb) >= STORE_FULL ||
           LINK(bb) >= LINK_LOST || COV(bb) >= COV_DONE || !HOK(bb, H_LIDAR);
}
static bool g_reloc(const Blackboard *bb) { return bb->world.position_error > TH_SIGMA_RELOC; }

static void branch(BtTree *t, int root, BtCond c, int a)
{
    int br = fw_bt_add(t, BT_SEQUENCE, 0, R_HOLD);
    int cn = fw_bt_add(t, BT_CONDITION, c, R_HOLD);
    int ac = fw_bt_add(t, BT_ACTION, 0, (Action)a);
    fw_bt_child(t, br, cn); fw_bt_child(t, br, ac); fw_bt_child(t, root, br);
}

static void r_build_bt(BtTree *t)
{
    int root;
    fw_bt_reset(t);
    root = fw_bt_add(t, BT_SELECTOR, 0, R_HOLD);
    branch(t, root, g_emerg,  R_EMERGENCY);
    branch(t, root, g_stop,   R_SAFE_STOP);
    branch(t, root, g_avoid,  R_AVOID);
    branch(t, root, g_return, R_RETURN);
    branch(t, root, g_reloc,  R_RELOCALIZE);
    fw_bt_child(t, root, fw_bt_add(t, BT_ACTION, 0, R_HOLD));  /* HOLD → 중재기가 효용 argmax */
}

static bool r_precondition(const Blackboard *bb, int a)
{
    switch (a) {
        case R_EXPLORE:  return HOK(bb, H_LIDAR) && J_EXP(bb) > 0.0f && bb->safety != SAFE_RETURN;
        case R_REVISIT:  return HOK(bb, H_LIDAR) && J_REV(bb) > 0.0f && bb->safety != SAFE_RETURN;
        case R_OBSERVE:  return (HOK(bb, H_LIDAR) || HOK(bb, H_CAM)) && J_OBS(bb) > 0.0f;
        case R_RETURN:   return true;
        case R_RELOCALIZE: return (HOK(bb, H_LIDAR) || HOK(bb, H_GNSS)) && bb->world.position_error > 0.5f * TH_SIGMA_RELOC;
        case R_AVOID:    return true;
        default:         return false;   /* HOLD/SAFE_STOP/EMERGENCY 는 argmax 경쟁 밖 */
    }
}

static float r_utility(const Blackboard *bb, int a)
{
    /* 에너지 압력: 남은 여유가 줄수록 RETURN 효용이 오른다 */
    float slack = bb->world.battery - BAT_NEED(bb);
    float press = slack < 0.12f ? (0.12f - slack) * 8.0f : 0.0f;   /* 여유 12 % 아래서만 (첫 판 30 %: 14 % 로 출발하면 2.4 m 만 가고 귀환) */
    switch (a) {
        case R_EXPLORE: return J_EXP(bb) - 0.5f * press;
        case R_REVISIT: return J_REV(bb) - 0.5f * press;
        case R_OBSERVE: return J_OBS(bb) - 0.2f * press;
        case R_RETURN:  return 0.02f + press;
        case R_RELOCALIZE: return bb->world.position_error;   /* σ[m] 그대로 */
        case R_AVOID:   return -1.0f;
        default:        return -1e30f;
    }
}

static int r_safety_filter(const Blackboard *bb, int p)
{
    if (!bb->world.actuator_ok || bb->world.battery < BAT_CRIT) return R_EMERGENCY;
    if (bb->world.collision_risk > TH_COLL_STOP || TILT(bb) >= TH_TILT_STOP) return R_SAFE_STOP;
    if (g_nav_lost(bb)) return R_SAFE_STOP;
    /* 이동 행동인데 전방 위험이 높으면 회피로 강제 (정책 버그의 마지막 방어선) */
    if ((p == R_EXPLORE || p == R_REVISIT || p == R_RETURN) && bb->world.collision_risk > TH_COLL_AVOID)
        return R_AVOID;
    return p;
}

static void r_safety_update(Blackboard *bb, EventQueue *q)
{
    int degraded = bb->health.health[H_LIDAR] < 0.8f || !HOK(bb, H_ENC) || !HOK(bb, H_CAM) || !HOK(bb, H_GNSS) || !HOK(bb, H_IMU) ||
                   SLIP(bb) > 0.25f || STORE(bb) > 0.85f || LINK(bb) > 0.2f;
    if (!bb->world.actuator_ok && bb->safety != SAFE_EMERGENCY) fw_evq_push(q, EV_ACTUATOR_FAIL, 0, bb->world.t);
    if (g_emerg(bb) || g_stop(bb))  bb->safety = SAFE_EMERGENCY;
    else if (g_return(bb))          bb->safety = SAFE_RETURN;
    else if (degraded)              bb->safety = SAFE_DEGRADED;   /* 호스트: 속도 제한 0.5x */
    else                            bb->safety = SAFE_NORMAL;
}

static void r_plan_update(Blackboard *bb)
{
    int ph = bb->safety == SAFE_EMERGENCY ? MODE_EMERGENCY :
             bb->safety == SAFE_RETURN    ? MODE_RETURN :
             g_reloc(bb)                  ? MODE_RECOVERY : MODE_SEARCH;
    if (ph == bb->plan_phase) bb->plan_ticks++; else { bb->plan_phase = ph; bb->plan_ticks = 0; }
    bb->mode = (Mode)ph;
}

const PolicySpec FW_PROFILE_RECON = {
    .name = "recon-rover", .n_actions = R_N, .action_names = R_NAMES,
    .act_none = R_HOLD, .act_fallback = R_OBSERVE,
    .build_bt = r_build_bt, .precondition = r_precondition, .utility = r_utility,
    .safety_filter = r_safety_filter, .safety_update = r_safety_update, .plan_update = r_plan_update,
    .vote_w = R_VOTE_W, .blocked_mask = 0u, .allw_mask = 0u,
};
