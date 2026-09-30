/* planner.h — 임무 계획(HTN 식 순차 + 재계획). 3T 의 sequencer / Remote Agent executive 층.
 *
 * 반응형 HFSM(상태만 보고 모드 결정)을 **기억 있는 순차 계획**으로 승격: MISSION 을 단계열
 * (SEARCH→APPROACH→INSPECT→REPORT→다시 SEARCH)로 분해해 진행을 추적하고, 상위 목표가 이뤄지면
 * 다음 단계로 넘어간다. 컨틴전시(저전력·센서열화)엔 계획을 갈아엎는다(재계획). 실행은 아래
 * BT/arbiter/safety 가 한다 — planner 는 '무엇을 향하는가', 그들은 '지금 무엇을 하는가'.
 */
#ifndef FW_PLANNER_H
#define FW_PLANNER_H

#include "blackboard.h"

typedef enum {
    PH_SEARCH = 0, PH_APPROACH, PH_INSPECT, PH_REPORT, PH_RELOCALIZE, PH_RETURN, PH_N
} PlanPhase;

#define FW_INSPECT_DWELL 2   /* INSPECT 를 이만큼 유지하면 REPORT 로(관측 완료) */

void        fw_plan_init(Blackboard *bb);
void        fw_plan_update(Blackboard *bb);   /* 진행/재계획 → bb->plan_phase, bb->mode */
const char *fw_plan_name(int phase);

#endif /* FW_PLANNER_H */
