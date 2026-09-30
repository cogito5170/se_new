/* bridge.c — 호스트 검증(V&V) 전용 ctypes 글루. 실타깃 펌웨어 경로가 아니다.
 *
 * sar/ 검증환경(심판)이 낸 관측을 파이썬이 이 함수로 fw 결정 executive 에 먹이고,
 * fw 가 낸 확인 탐지(belief)를 돌려받아 sar evaluator 로 채점한다. 즉 **실제 C 코드**를
 * sar 로 V&V 한다(파이썬 재구현이 아니라). malloc 은 여기(호스트 글루)만 쓴다 — fw 코어는
 * 여전히 malloc 없음.
 */
#include <stdlib.h>
#include "agent.h"
#include "blackboard.h"

Agent *fw_bridge_new(void)
{
    Agent *a = (Agent *)malloc(sizeof(Agent));
    if (a) fw_agent_init(a);
    return a;
}

void fw_bridge_free(Agent *a) { free(a); }

/* 확인창(연속 스텝 N)·임계 th 를 런타임 설정. sar 관측 케이던스에 맞춰 V&V 스윕용. */
void fw_bridge_set_confirm(Agent *a, int n, float th)
{
    if (!a) return;
    a->bb.cfg.confirm_n = n;
    a->bb.cfg.confirm_th = th;
}

/* NIS 게이트(운동 일관성): >0 이면 NIS>gate 측정을 확인서 제외. 0=off. */
void fw_bridge_set_nisgate(Agent *a, float gate)
{
    if (!a) return;
    a->bb.cfg.nis_gate = gate;
}

/* CMPC(교차모달) 설정: cmpc_min(0=off,2=CMPC) + require_live(liveness 요구). */
void fw_bridge_set_cmpc(Agent *a, int cmpc_min, int require_live)
{
    if (!a) return;
    a->bb.cfg.cmpc_min = cmpc_min;
    a->bb.cfg.require_live = require_live ? true : false;
}

/* §10 설정 판번호 지정(트레이스 스탬프용). */
void fw_bridge_set_version(Agent *a, unsigned version)
{
    if (!a) return;
    a->bb.cfg.version = (uint32_t)version;
}

/* §10 현재 설정 해시(FNV-1a). 같은 설정→같은 해시. 트레이스에 어느 정책이 돌았나 묶는다. */
unsigned fw_bridge_cfg_hash(const Agent *a)
{
    if (!a) return 0u;
    return (unsigned)fw_cfg_hash(&a->bb.cfg);
}

/* 센서 배열은 길이 FW_N_SENSOR(RGB,THERMAL,LIDAR,SAR,AUDIO). 반환=Action(int).
 * belief 를 out_* 로 돌려준다(확인된 표적의 융합 위치·신뢰). */
int fw_bridge_step(Agent *a,
                   const float *ev, const float *x, const float *y, const int *present,
                   const float *health, float battery, float collision,
                   int imu_valid, int gps_valid, float pos_err,
                   int live_present, float live_x, float live_y,
                   float *out_px, float *out_py, int *out_conf, float *out_tconf, float *out_nis)
{
    int i;
    Action act;
    for (i = 0; i < FW_N_SENSOR; i++) {
        a->bb.obs[i].present  = present[i] ? true : false;
        a->bb.obs[i].evidence = ev[i];
        a->bb.obs[i].x = x[i];
        a->bb.obs[i].y = y[i];
        a->bb.health.health[i] = health[i];
    }
    a->bb.live.present = live_present ? true : false;
    a->bb.live.x = live_x; a->bb.live.y = live_y;
    a->bb.world.battery        = battery;
    a->bb.world.collision_risk = collision;
    a->bb.world.imu_valid      = imu_valid ? true : false;
    a->bb.world.gps_valid      = gps_valid ? true : false;
    a->bb.world.position_error = pos_err;

    act = fw_agent_step(a);

    *out_px    = a->bb.belief.px;
    *out_py    = a->bb.belief.py;
    *out_conf  = a->bb.belief.confirmed ? 1 : 0;
    *out_tconf = a->bb.belief.target_conf;
    *out_nis   = a->bb.belief.nis;
    return (int)act;
}
