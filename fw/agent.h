/* agent.h — 자율 결정 에이전트: 정적 상태(blackboard·BT·이벤트큐)와 한 스텝 실행.
 *
 * closed loop 한 바퀴:
 *   증거융합 → 안전/ FDIR → HFSM → BT 제안 → 중재(precond+효용) → 안전필터 → 행동
 * 이 순서가 LLM 없는 결정 mechanism 이다: 관측→상태추정→조건평가→후보→제약→선택.
 */
#ifndef FW_AGENT_H
#define FW_AGENT_H

#include "blackboard.h"
#include "bt.h"
#include "event.h"

typedef struct {
    Blackboard   bb;
    BtTree       tree;
    EventQueue   evq;
    SensorHealth prev_health;   /* FDIR 엣지 검출용 직전 건강 */
    Action       last_action;
} Agent;

void   fw_agent_init(Agent *a);                                 /* 기본 프로파일(SAR) */
void   fw_agent_init_profile(Agent *a, const PolicySpec *spec); /* 도메인 프로파일 지정 */
/* obs·health·world 가 이미 bb 에 채워졌다는 전제로 한 스텝 결정. 실행할 행동을 반환. */
Action fw_agent_step(Agent *a);

#endif /* FW_AGENT_H */
