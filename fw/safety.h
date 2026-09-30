/* safety.h — 안전 감독자(Safety Supervisor) + FDIR + 최종 명령 필터.
 *
 * 결정 executive 와 분리된 별도 FSM. 결정 논리가 버그를 내도 이 층이 마지막 방어선이다:
 *   safety_filter(제안행동) → 하드 제약(충돌·저전력·센서고장) 위반이면 안전행동으로 덮어쓴다.
 * FDIR: 센서 건강 급락을 이벤트로 올리고 상태를 DEGRADED/RETURN/EMERGENCY 로 전이한다.
 * 근거(선행조사): NASA autonomy 의 fault detection/isolation/recovery + Subsumption 의
 * 상위 억제(subsume) 개념.
 */
#ifndef FW_SAFETY_H
#define FW_SAFETY_H

#include "blackboard.h"
#include "event.h"

#define FW_COLLISION_HARD   0.80f   /* 이 이상이면 무조건 회피 */
#define FW_BATTERY_RETURN   0.25f   /* 이 아래면 귀환 */
#define FW_BATTERY_EMERG    0.10f   /* 이 아래면 비상 */
#define FW_HEALTH_FAIL      0.30f   /* 이 아래면 센서 고장 판정 */

/* 센서 값-정지(frozen)를 차등 검출해 stuck 채널을 격리한다(융합 전에 호출). §2·§4 stale. */
void fw_stale_update(Blackboard *bb, EventQueue *q);

/* 건강·충돌·전력을 읽어 FDIR 이벤트를 큐에 올리고 safety 상태를 갱신한다. */
void fw_safety_update(Blackboard *bb, EventQueue *q, const SensorHealth *prev);

/* 제안 행동을 하드 제약으로 검사해, 위반이면 안전행동으로 덮어쓴다(최종 방어선). */
Action fw_safety_filter(const Blackboard *bb, Action proposed);

#endif /* FW_SAFETY_H */
