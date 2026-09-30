/* evidence.h — 센서 융합(증거 누적) + 시간적 일관성 → 믿음 갱신.
 *
 * PR #439 의 health 가중 soft voting 을 C 로 옮긴 것: 여러 센서 증거를 기저가중×건강도로
 * 합쳐 신뢰를 내고, 위치는 신뢰가중 무게중심. 외로운 거친 센서(Audio 단독)는 신뢰가 낮아
 * 확인 임계를 못 넘어 오경보가 억제된다. 시간적으로 연속 확인돼야 confirmed(플리커 제거).
 */
#ifndef FW_EVIDENCE_H
#define FW_EVIDENCE_H

#include "blackboard.h"

#define FW_CONFIRM_TH  0.60f   /* 이 신뢰 이상이면 이번 스텝 '초과' */
#define FW_CONFIRM_N   3       /* 연속 N 스텝 초과 시 confirmed */
#define FW_GATE2       4.0f    /* 공간 게이트(격자 거리^2): 이 안이면 같은 표적으로 융합 */
#define FW_SIGMA_MAX   6.0f    /* 위치 불확실도 상한: 이보다 크면 너무 불확실해 confirmed 취소 */
#define FW_CAND_TH     0.5f    /* 이 신뢰 이상이면 '후보'(candidate) */
#define FW_ABSTAIN_N   4       /* 후보인데 확인이 못 붙는 연속 스텝 ≥ 이 값이면 ABSTAIN(확정 거부) */
#define FW_STALE_N     5       /* 센서 값이 이만큼 연속 byte-동일이면(다른 채널은 변할 때) frozen 판정 */

/* 블랙보드의 obs·health 를 읽어 belief 를 갱신(신뢰·위치·나이·시간일관성). */
void fw_evidence_update(Blackboard *bb);

#endif /* FW_EVIDENCE_H */
