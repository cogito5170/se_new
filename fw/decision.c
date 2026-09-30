/* decision.c — 결정 커널(도메인 무관): BT tick 만. 트리 구성(build_bt)과 조건 술어는
 * 프로파일(bb->spec->build_bt)이 준다. */
#include "decision.h"

Action fw_decision_propose(Blackboard *bb, BtTree *t)
{
    fw_bt_tick(t, bb);
    return t->chosen;
}
