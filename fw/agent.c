/* agent.c — 결정 파이프라인 한 스텝. */
#include "agent.h"
#include "evidence.h"
#include "decision.h"
#include "planner.h"
#include "arbiter.h"
#include "safety.h"
#include "policy_spec.h"

/* 프로파일을 꽂아 초기화 — 새 프로젝트는 자기 PolicySpec 을 넘긴다. 커널은 그대로. */
void fw_agent_init_profile(Agent *a, const PolicySpec *spec)
{
    int i;
    fw_bb_init(&a->bb);
    a->bb.spec = spec;                 /* 기본 SAR 를 이 프로파일로 교체 */
    a->bb.spec->build_bt(&a->tree);    /* 프로파일이 우선순위 트리를 짓는다 */
    fw_plan_init(&a->bb);
    fw_evq_init(&a->evq);
    for (i = 0; i < FW_N_SENSOR; i++) a->prev_health.health[i] = 1.0f;
    a->last_action = ACT_NONE;
}

void fw_agent_init(Agent *a)
{
    fw_agent_init_profile(a, &FW_PROFILE_SAR);   /* 기본 도메인 = SAR-UAV */
}

Action fw_agent_step(Agent *a)
{
    Blackboard *bb = &a->bb;
    Action cand, act;

    bb->world.t += 1;

    /* 0) Freshness/FDIR: 얼어붙은(frozen) 센서를 융합 '전에' 차등 검출·격리(§2·§4 stale). */
    fw_stale_update(bb, &a->evq);

    /* 1) Perception/Fusion: 센서 증거 → 믿음(신뢰·위치·시간일관성). */
    fw_evidence_update(bb);

    /* 2) Safety/FDIR: 건강·충돌·전력 → 이벤트·감독자 상태. (직전 건강과 비교) */
    fw_safety_update(bb, &a->evq, &a->prev_health);
    a->prev_health = bb->health;

    /* 3) Planner(executive): 임무 단계 순차 + 재계획 → mode. (reactive HFSM 을 대체) */
    fw_plan_update(bb);

    /* 4) BT: 우선순위로 행동 제안. */
    cand = fw_decision_propose(bb, &a->tree);

    /* 5) Arbitration: precondition·효용으로 다듬는다(안전 위에 효용). */
    act = fw_arbitrate(bb, cand);

    /* 6) Safety filter: 최종 하드 override(결정 버그의 마지막 방어선). */
    act = fw_safety_filter(bb, act);

    a->last_action = act;
    return act;
}
