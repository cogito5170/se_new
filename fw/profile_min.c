/* profile_min.c — 최소 예시 프로파일. **새 프로젝트가 SAR 와 무관한 도메인을 커널 재사용으로
 * 세우는 것**을 증명한다. 커널(estimator·bt·evidence 융합·arbiter argmax·FDIR 엔진)은 한 줄도
 * 안 건드리고, 이 파일 하나로 전혀 다른 행동 집합·정책을 돌린다.
 *
 * 도메인(가상): 일반 감시 노드 — 증거가 확인되면 ACT, 아니면 OBSERVE, 전력 낮으면 STOP.
 * 행동 id 공간(0..)을 자기 이름으로 재명명한다(SAR 의 NONE/SEARCH/… 와 같은 정수, 다른 의미). */
#include "policy_spec.h"

/* 행동 id(정수). Action enum(SAR)과 같은 정수 공간을 이 도메인 이름으로 재사용한다. */
#define MIN_HOLD    0
#define MIN_OBSERVE 1
#define MIN_ACT     2
#define MIN_STOP    3
#define MIN_N       4

static const char *const MIN_ACTION_NAMES[MIN_N] = { "HOLD", "OBSERVE", "ACT", "STOP" };
static const float MIN_VOTE_W[FW_N_SENSOR] = { 1.0f, 1.0f, 0.0f, 0.0f, 0.0f };  /* 두 채널만 쓰는 도메인 */

static bool cond_stop(const Blackboard *bb) { return bb->world.battery < 0.10f; }
static bool cond_go(const Blackboard *bb)   { return bb->belief.confirmed; }

static void min_build_bt(BtTree *t)
{
    int root, br, cnd, act;
    fw_bt_reset(t);
    root = fw_bt_add(t, BT_SELECTOR, 0, MIN_HOLD);

    br = fw_bt_add(t, BT_SEQUENCE, 0, MIN_HOLD);
    cnd = fw_bt_add(t, BT_CONDITION, cond_stop, MIN_HOLD);
    act = fw_bt_add(t, BT_ACTION, 0, MIN_STOP);
    fw_bt_child(t, br, cnd); fw_bt_child(t, br, act); fw_bt_child(t, root, br);

    br = fw_bt_add(t, BT_SEQUENCE, 0, MIN_HOLD);
    cnd = fw_bt_add(t, BT_CONDITION, cond_go, MIN_HOLD);
    act = fw_bt_add(t, BT_ACTION, 0, MIN_ACT);
    fw_bt_child(t, br, cnd); fw_bt_child(t, br, act); fw_bt_child(t, root, br);

    act = fw_bt_add(t, BT_ACTION, 0, MIN_OBSERVE);   /* fallback */
    fw_bt_child(t, root, act);
}

static bool min_precondition(const Blackboard *bb, int a)
{
    if (a == MIN_ACT) return bb->belief.confirmed;   /* 확인돼야 행동 */
    return true;
}

static float min_utility(const Blackboard *bb, int a)
{
    switch (a) {
        case MIN_ACT:     return 1.0f * bb->belief.target_conf;
        case MIN_OBSERVE: return 0.3f;
        default:          return -1e30f;              /* STOP/HOLD 는 argmax 경쟁 제외 */
    }
}

static int min_safety_filter(const Blackboard *bb, int proposed)
{
    if (bb->world.battery < 0.10f) return MIN_STOP;   /* 전력 소진 → 정지 */
    return proposed;
}

static void min_safety_update(Blackboard *bb, EventQueue *q)
{
    (void)q;
    if (bb->world.battery < 0.10f)      bb->safety = SAFE_EMERGENCY;
    else if (bb->world.battery < 0.25f) bb->safety = SAFE_RETURN;
    else                                bb->safety = SAFE_NORMAL;
}

static void min_plan_update(Blackboard *bb) { bb->mode = MODE_SEARCH; }  /* 단계 없음(무상태) */

const PolicySpec FW_PROFILE_MIN = {
    .name         = "min-monitor",
    .n_actions    = MIN_N,
    .action_names = MIN_ACTION_NAMES,
    .act_none     = MIN_HOLD,
    .act_fallback = MIN_OBSERVE,
    .build_bt      = min_build_bt,
    .precondition  = min_precondition,
    .utility       = min_utility,
    .safety_filter = min_safety_filter,
    .safety_update = min_safety_update,
    .plan_update   = min_plan_update,
    .vote_w        = MIN_VOTE_W,
    .blocked_mask  = 0u,
    .allw_mask     = 0u,
};
