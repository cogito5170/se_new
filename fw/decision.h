/* decision.h — 결정 executive: HFSM(mission mode) + BT(guarded action 제안).
 *
 * HFSM 이 큰 모드를 정하고, BT 가 우선순위 selector 로 구체 행동을 제안한다. 제안은
 * arbiter 가 precondition·효용으로 다듬고, safety_filter 가 최종 하드 override 한다.
 * BT 는 한 번 짓고(fw_decision_init) 매 스텝 재사용한다(정적).
 */
#ifndef FW_DECISION_H
#define FW_DECISION_H

#include "blackboard.h"
#include "bt.h"

/* BT 트리 구성은 프로파일(policy_spec.h: build_bt)로 옮겼다 — 도메인마다 우선순위가 다르므로. */
Action fw_decision_propose(Blackboard *bb, BtTree *t);  /* BT tick → 제안 행동(커널) */

#endif /* FW_DECISION_H */
