/* blackboard.c — 초기화와 이름표(로그·telemetry 용). */
#include "blackboard.h"
#include "evidence.h"
#include "policy_spec.h"

void fw_bb_init(Blackboard *bb)
{
    int i;
    bb->spec = &FW_PROFILE_SAR;            /* 기본 도메인 프로파일(fw_agent_init_profile 로 교체 가능) */
    bb->cfg.confirm_n = FW_CONFIRM_N;      /* 기본 확인창(evidence.h) */
    bb->cfg.confirm_th = FW_CONFIRM_TH;
    bb->cfg.nis_gate = 0.0f;               /* 기본 off(운동 게이트 안 씀) */
    bb->cfg.cmpc_min = 0;                  /* 기본 off(교차모달 게이트 안 씀) */
    bb->cfg.require_live = false;
    bb->cfg.version = 0;                    /* 설정 판번호 기본 0(§10) */
    bb->live.present = false; bb->live.x = 0.0f; bb->live.y = 0.0f;
    for (i = 0; i < FW_N_SENSOR; i++) {
        bb->obs[i].evidence = 0.0f; bb->obs[i].x = 0.0f; bb->obs[i].y = 0.0f;
        bb->obs[i].present = false;
        bb->health.health[i] = 1.0f;   /* 시작은 전 센서 정상 */
        bb->stale[i].ev = 0.0f; bb->stale[i].x = 0.0f; bb->stale[i].y = 0.0f; bb->stale[i].run = 0;
    }
    bb->belief.target_conf = 0.0f; bb->belief.px = 0.0f; bb->belief.py = 0.0f;
    bb->belief.sigma = 0.0f; bb->belief.speed = 0.0f; bb->belief.nis = 0.0f;
    bb->belief.age = 0; bb->belief.confirm_run = 0; bb->belief.unconf_run = 0; bb->belief.confirmed = false;
    bb->world.battery = 1.0f; bb->world.collision_risk = 0.0f; bb->world.position_error = 0.0f;
    bb->world.gps_valid = true; bb->world.imu_valid = true; bb->world.actuator_ok = true; bb->world.t = 0;
    bb->mode = MODE_SEARCH; bb->safety = SAFE_NORMAL;
    fw_kf_init(&bb->kf, 0.05f);       /* 표적 위치 칼만(정위치, 작은 프로세스잡음) */
    bb->plan_phase = 0;               /* PH_SEARCH */
    bb->plan_ticks = 0;
}

const char *fw_action_name(Action a)
{
    switch (a) {
        case ACT_NONE:       return "NONE";
        case ACT_SEARCH:     return "SEARCH";
        case ACT_APPROACH:   return "APPROACH";
        case ACT_INSPECT:    return "INSPECT";
        case ACT_RETURN:     return "RETURN";
        case ACT_AVOID:      return "AVOID";
        case ACT_RELOCALIZE: return "RELOCALIZE";
        case ACT_EMERGENCY:  return "EMERGENCY";
        case ACT_ABSTAIN:    return "ABSTAIN";
        default:             return "?";
    }
}

/* 설정 해시(§10) — FNV-1a 32bit. 같은 설정→같은 해시, 임계 하나만 바뀌어도 달라진다.
 * 트레이스에 스탬프해 "어느 정책 설정이 이 행동열을 냈나"를 외부 검증에 묶는다(결정성 §9 보강).
 * 부동소수는 비트로 재해석해 넣는다(글꼴·반올림에 안 기댐). */
uint32_t fw_cfg_hash(const Config *c)
{
    uint32_t h = 2166136261u;                    /* FNV offset basis */
    union { float f; uint32_t u; } cv;
    int i;
    uint32_t buf[6];
    buf[0] = (uint32_t)c->version;
    buf[1] = (uint32_t)c->confirm_n;
    cv.f = c->confirm_th; buf[2] = cv.u;
    cv.f = c->nis_gate;   buf[3] = cv.u;
    buf[4] = (uint32_t)c->cmpc_min;
    buf[5] = c->require_live ? 1u : 0u;
    for (i = 0; i < 6; i++) {
        int b;
        for (b = 0; b < 4; b++) {
            h ^= (buf[i] >> (8 * b)) & 0xffu;
            h *= 16777619u;                      /* FNV prime */
        }
    }
    return h;
}

const char *fw_mode_name(Mode m)
{
    switch (m) {
        case MODE_SEARCH:      return "SEARCH";
        case MODE_INVESTIGATE: return "INVESTIGATE";
        case MODE_RETURN:      return "RETURN";
        case MODE_RECOVERY:    return "RECOVERY";
        case MODE_EMERGENCY:   return "EMERGENCY";
        default:               return "?";
    }
}

const char *fw_safety_name(SafetyState s)
{
    switch (s) {
        case SAFE_NORMAL:    return "NORMAL";
        case SAFE_DEGRADED:  return "DEGRADED";
        case SAFE_RETURN:    return "RETURN";
        case SAFE_EMERGENCY: return "EMERGENCY";
        default:             return "?";
    }
}
