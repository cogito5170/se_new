/* safety.c — FDIR 커널(도메인 무관): 센서 freeze/stale 검출 + 건강 엣지 이벤트.
 * 임계 기반 SafetyState 전이와 최종 하드 필터는 프로파일(bb->spec)이 한다(도메인 정책). */
#include "safety.h"
#include "evidence.h"   /* FW_STALE_N */
#include "policy_spec.h"

void fw_stale_update(Blackboard *bb, EventQueue *q)
{
    int i;
    int changed[FW_N_SENSOR];
    int any_changed = 0;
    /* 1) 센서별 값-정지(byte-동일 반복) 추적. 값이 바뀌면 run 리셋+저장, 같으면 run++. */
    for (i = 0; i < FW_N_SENSOR; i++) {
        changed[i] = 0;
        if (bb->obs[i].present) {
            if (bb->obs[i].evidence == bb->stale[i].ev &&
                bb->obs[i].x == bb->stale[i].x && bb->obs[i].y == bb->stale[i].y) {
                if (bb->stale[i].run < 1000000) bb->stale[i].run += 1;
            } else {
                bb->stale[i].run = 0;
                bb->stale[i].ev = bb->obs[i].evidence;
                bb->stale[i].x  = bb->obs[i].x;
                bb->stale[i].y  = bb->obs[i].y;
                changed[i] = 1;
            }
        } else {
            bb->stale[i].run = 0;   /* 관측 없음: freeze 아님(그냥 부재) */
        }
        if (changed[i]) any_changed = 1;
    }
    /* 2) 차등 freeze 격리: '다른' present 채널이 변한 스텝에 얼어붙어 있는(run≥N) 채널만 stuck 으로 본다.
       모두-정지(변하는 기준 채널이 없음)면 아무 것도 안 건드린다 — 정지한 '실표적'을 죽이지 않는다.
       정지·전-서명 가짜와 정지 실표적을 반복만으로는 못 가른다(그건 §6 liveness 몫, 정직). */
    if (any_changed) {
        for (i = 0; i < FW_N_SENSOR; i++) {
            if (bb->obs[i].present && !changed[i] && bb->stale[i].run >= FW_STALE_N) {
                bb->health.health[i] = 0.0f;                 /* frozen 센서 격리(이번 스텝 융합서 제외) */
                fw_evq_push(q, EV_SENSOR_STALE, i, bb->world.t);
            }
        }
    }
}

void fw_safety_update(Blackboard *bb, EventQueue *q, const SensorHealth *prev)
{
    int i;
    /* 커널(도메인 무관) FDIR: 센서 건강 엣지(정상↔고장) 이벤트. 임계는 일반적 헬스 임계. */
    for (i = 0; i < FW_N_SENSOR; i++) {
        float now = bb->health.health[i];
        float was = prev ? prev->health[i] : 1.0f;
        if (was >= FW_HEALTH_FAIL && now < FW_HEALTH_FAIL)
            fw_evq_push(q, EV_SENSOR_FAIL, i, bb->world.t);
        else if (was < FW_HEALTH_FAIL && now >= FW_HEALTH_FAIL)
            fw_evq_push(q, EV_SENSOR_RECOVER, i, bb->world.t);
    }
    /* 도메인 FDIR: 충돌·전력·구동계 이벤트 + SafetyState 전이(임계·정책은 프로파일). */
    if (bb->spec && bb->spec->safety_update)
        bb->spec->safety_update(bb, q);
}

Action fw_safety_filter(const Blackboard *bb, Action proposed)
{
    /* 최종 하드 override 는 도메인 정책(어떤 제약→어떤 안전행동). 프로파일이 결정. */
    return (Action)bb->spec->safety_filter(bb, (int)proposed);
}
