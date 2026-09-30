/* arbiter.h — 중재: 안전 제약(하드) 위에 효용(소프트).
 *
 * BT 가 우선순위로 제안한 행동을 받아, 그 행동의 precondition 이 서면 그대로 쓰고,
 * 안 서면 **precondition 을 만족하는 행동 중 효용 최대**로 대체한다. 효용은
 *   U(a) = mission_value(a) − 충돌벌 − 에너지벌 − 불확실도벌
 * 로, sar/ivv 의 U=D−λC−μE 와 같은 꼴. safety_filter(최종 하드 override)와 분리된다:
 * 여기는 '고를 수 있는 것 중 무엇이 나은가', 거기는 '무엇을 절대 하면 안 되나'.
 */
#ifndef FW_ARBITER_H
#define FW_ARBITER_H

#include "blackboard.h"

/* precondition·utility 는 프로파일(policy_spec.h)로 옮겼다 — 도메인마다 다르므로. */
Action fw_arbitrate(const Blackboard *bb, Action proposed);   /* 커널 argmax(bb->spec 사용) */

#endif /* FW_ARBITER_H */
