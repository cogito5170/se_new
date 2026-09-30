/* policy_spec.h — 정책 프로파일 인터페이스(도메인의 '무엇').
 *
 * 이 파일이 fw 를 **정책을 세우는 tool** 로 만든다. 커널(estimator·bt 엔진·evidence 융합수학·
 * arbiter argmax·FDIR 엔진·stale 검출·결정성·설정해시)은 도메인을 모른다 — 오직 이 `PolicySpec`
 * vtable 을 통해서만 "무엇을 할지"(행동·효용·불변식·트리·계획·지각가중)에 닿는다.
 *
 * **새 프로젝트는 C 커널을 한 줄도 안 건드린다.** `PolicySpec` 하나를 채워(profile_<도메인>.c)
 * `bb->spec` 에 꽂으면(`fw_agent_init_profile`) 커널 전체를 그대로 재사용한다. SAR 는 그 프로파일의
 * 하나(`FW_PROFILE_SAR`)일 뿐이고, 착륙선·로버·다른 도메인은 자기 프로파일만 쓴다.
 * 작성법: fw/POLICY_TOOLKIT.md.
 *
 * 행동은 정수 id(0..n_actions-1). 이름·의미는 프로파일이 정한다(같은 id 공간을 도메인마다 재명명).
 */
#ifndef FW_POLICY_SPEC_H
#define FW_POLICY_SPEC_H

#include "blackboard.h"
#include "bt.h"
#include "event.h"

struct PolicySpec {
    const char        *name;              /* 프로파일 이름(로그·트레이스) */
    int                n_actions;         /* 행동 id 공간 크기(≤ ACT_N) */
    const char *const *action_names;      /* [n_actions] id→이름 */
    int                act_none;          /* no-op 행동 id(argmax 제외) */
    int                act_fallback;      /* precondition 만족 행동이 없을 때 기본(정상 탐색류) */

    /* ── 결정 정책 훅(도메인이 채운다) ── */
    void  (*build_bt)(BtTree *t);                              /* 우선순위 행동트리 구성 */
    bool  (*precondition)(const Blackboard *bb, int a);        /* a 를 지금 실행해도 되나 */
    float (*utility)(const Blackboard *bb, int a);             /* a 효용(에너지 포함, 클수록 선호) */
    int   (*safety_filter)(const Blackboard *bb, int proposed);/* 최종 하드 override → 행동 id */
    void  (*safety_update)(Blackboard *bb, EventQueue *q);     /* 도메인 FDIR: 임계→이벤트 + SafetyState */
    void  (*plan_update)(Blackboard *bb);                      /* 계획 진행/재계획 → plan_phase·mode */

    /* ── 지각 프로파일(evidence 융합이 읽는 도메인 상수) ── */
    const float *vote_w;                  /* [FW_N_SENSOR] 센서 기저 가중 */
    uint32_t     blocked_mask;            /* 가림-약 채널 비트(이게 게이트에 있으면 CMPC 완화 불가) */
    uint32_t     allw_mask;               /* 가림-강 채널 비트(단독이면 조건부 1채널 완화) */
};

extern const PolicySpec FW_PROFILE_SAR;   /* SAR-UAV 참조 프로파일 (profile_sar.c) */
extern const PolicySpec FW_PROFILE_MIN;   /* 최소 예시 프로파일 — 새 도메인 배선 증명 (profile_min.c) */

#endif /* FW_POLICY_SPEC_H */
