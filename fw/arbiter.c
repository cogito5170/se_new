/* arbiter.c — 중재 커널(도메인 무관): precondition + 효용 argmax.
 * 행동별 precondition·효용은 프로파일(bb->spec)이 준다. 여기는 순수 메커니즘:
 * "제안이 실행 가능하면 존중, 아니면 실행 가능 행동 중 효용 최대". */
#include "arbiter.h"
#include "policy_spec.h"

Action fw_arbitrate(const Blackboard *bb, Action proposed)
{
    const PolicySpec *sp = bb->spec;

    /* 제안이 precondition 을 만족하면 그대로(BT 우선순위 존중). */
    if ((int)proposed != sp->act_none && sp->precondition(bb, (int)proposed))
        return proposed;

    /* 아니면 precondition 만족 행동 중 효용 최대(안전 위에 효용). no-op 은 경쟁서 제외. */
    Action best = (Action)sp->act_fallback; float bu = -1e30f;
    int a;
    for (a = 0; a < sp->n_actions; a++) {
        if (a == sp->act_none) continue;
        if (!sp->precondition(bb, a)) continue;
        float u = sp->utility(bb, a);
        if (u > bu) { bu = u; best = (Action)a; }
    }
    return best;
}
