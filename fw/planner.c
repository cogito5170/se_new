/* planner.c — 계획 커널: init/name 은 일반적, 진행/재계획(plan_update)은 프로파일이 준다.
 * 단계열·전이 규칙은 도메인마다 다르므로 bb->spec->plan_update 로 위임한다. */
#include "planner.h"
#include "policy_spec.h"

void fw_plan_init(Blackboard *bb)
{
    bb->plan_phase = 0;                    /* 프로파일의 첫 단계(SAR: PH_SEARCH) */
    bb->plan_ticks = 0;
    bb->mode = MODE_SEARCH;
}

void fw_plan_update(Blackboard *bb)
{
    if (bb->spec && bb->spec->plan_update)
        bb->spec->plan_update(bb);          /* 도메인 계획 진행/재계획 */
}

const char *fw_plan_name(int phase)
{
    switch (phase) {
        case PH_SEARCH:     return "SEARCH";
        case PH_APPROACH:   return "APPROACH";
        case PH_INSPECT:    return "INSPECT";
        case PH_REPORT:     return "REPORT";
        case PH_RELOCALIZE: return "RELOCALIZE";
        case PH_RETURN:     return "RETURN";
        default:            return "?";
    }
}
