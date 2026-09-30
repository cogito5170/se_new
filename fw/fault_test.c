/* fault_test.c — 결정성 replay + fault injection(호스트). FDIR 이 실제로 존재하는 이유를 검증.
 *
 * 계보: telemetry→replay→IV&V, NASA FDIR. 기록된 장면을 재생하면 동일 행동열(결정적)이 나오고,
 * 각 fault 를 주입하면 executive 가 옳게 열화하는지 본다. **못 막는 fault 는 gap 으로 정직히 기록.**
 */
#include <stdio.h>
#include <math.h>
#include "agent.h"
#include "evidence.h"
#include "planner.h"
#include "safety.h"
#include "event.h"

static int g_fail = 0;
static void ok(int cond, const char *msg)
{
    printf("    %s %s\n", cond ? "OK  " : "FAIL", msg);
    if (!cond) g_fail++;
}

static void clear_obs(Blackboard *bb)
{
    int i;
    for (i = 0; i < FW_N_SENSOR; i++) { bb->obs[i].present = false; bb->obs[i].evidence = 0.0f; }
}
static void set_obs(Blackboard *bb, SensorId s, float ev, float x, float y)
{
    bb->obs[s].present = true; bb->obs[s].evidence = ev; bb->obs[s].x = x; bb->obs[s].y = y;
}
static int has_event(EventQueue *q, EventType t)
{
    Event e; int found = 0;
    while (fw_evq_pop(q, &e)) if (e.type == t) found = 1;
    return found;
}

int main(void)
{
    /* 1) 기록 장면 → 결정성 replay: 동일 입력이면 동일 행동열(IV&V invariant 의 기반) */
    {
        /* 스크립트 장면(기록): 스텝별 (present, ev, x, y) for RGB·Thermal */
        int   pres[10] = {1, 1, 0, 1, 1, 1, 0, 1, 1, 1};
        float ex[10]   = {10, 10, 0, 10, 10, 10, 0, 10, 10, 10};
        Agent a1, a2; fw_agent_init(&a1); fw_agent_init(&a2);
        int match = 1, i;
        Action tr1[10];
        for (i = 0; i < 10; i++) {
            clear_obs(&a1.bb); clear_obs(&a2.bb);
            if (pres[i]) {
                set_obs(&a1.bb, SEN_RGB, 0.9f, ex[i], 10.0f); set_obs(&a1.bb, SEN_THERMAL, 0.8f, ex[i] + 0.1f, 10.0f);
                set_obs(&a2.bb, SEN_RGB, 0.9f, ex[i], 10.0f); set_obs(&a2.bb, SEN_THERMAL, 0.8f, ex[i] + 0.1f, 10.0f);
            }
            tr1[i] = fw_agent_step(&a1);
            Action x2 = fw_agent_step(&a2);
            if (tr1[i] != x2) match = 0;
        }
        printf("[1 replay] deterministic=%d\n", match);
        ok(match, "기록 장면 재생 → 동일 행동열(결정적, IV&V 기반)");
    }

    /* 2) fault: 센서 dropout + 복구 → FDIR 이벤트, 남은 센서로 융합 계속 */
    {
        Agent a; fw_agent_init(&a); a.bb.cfg.confirm_n = 1;
        int i;
        for (i = 0; i < 3; i++) {
            clear_obs(&a.bb); set_obs(&a.bb, SEN_RGB, 0.9f, 10, 10); set_obs(&a.bb, SEN_THERMAL, 0.8f, 10, 10);
            fw_agent_step(&a);
        }
        clear_obs(&a.bb); set_obs(&a.bb, SEN_RGB, 0.9f, 10, 10); set_obs(&a.bb, SEN_THERMAL, 0.8f, 10, 10);
        a.bb.health.health[SEN_RGB] = 0.0f;             /* RGB dropout */
        fw_agent_step(&a);
        int fail_ev = has_event(&a.evq, EV_SENSOR_FAIL);
        printf("[2 dropout] fail_ev=%d conf=%.2f\n", fail_ev, a.bb.belief.target_conf);
        ok(fail_ev, "센서 dropout → FDIR EV_SENSOR_FAIL");
        ok(a.bb.belief.target_conf > 0.0f, "dropout 후에도 남은 센서(Thermal)로 융합 계속");
        a.bb.health.health[SEN_RGB] = 1.0f;             /* 복구 */
        clear_obs(&a.bb); set_obs(&a.bb, SEN_RGB, 0.9f, 10, 10);
        fw_agent_step(&a);
        ok(has_event(&a.evq, EV_SENSOR_RECOVER), "센서 복구 → EV_SENSOR_RECOVER");
    }

    /* 3) fault: KF 공분산 폭발(장기 blind) → sigma 유한·상한 초과 시 confirmed 취소·무크래시 */
    {
        Agent a; fw_agent_init(&a); a.bb.cfg.confirm_n = 1;
        int i;
        clear_obs(&a.bb); set_obs(&a.bb, SEN_RGB, 0.9f, 10, 10); set_obs(&a.bb, SEN_THERMAL, 0.8f, 10, 10);
        fw_agent_step(&a);
        int was_conf = a.bb.belief.confirmed;
        for (i = 0; i < 40; i++) { clear_obs(&a.bb); fw_agent_step(&a); }  /* 장기 관측 없음 */
        printf("[3 cov폭발] was_conf=%d sigma=%.2f finite=%d conf=%d\n",
               was_conf, a.bb.belief.sigma, isfinite(a.bb.belief.sigma), a.bb.belief.confirmed);
        ok(isfinite(a.bb.belief.sigma), "장기 blind 후 sigma 유한(수치 안정)");
        ok(a.bb.belief.sigma > FW_SIGMA_MAX, "blind 로 공분산 성장(불확실도↑)");
        ok(!a.bb.belief.confirmed, "과불확실 추적엔 행동 안 함(confirmed 취소 가드)");
    }

    /* 4) fault: planner 상태 오염 → 유효 단계로 복구(방어적 default) */
    {
        Agent a; fw_agent_init(&a);
        a.bb.plan_phase = 999;                          /* 오염 */
        clear_obs(&a.bb); fw_agent_step(&a);
        printf("[4 planner오염] phase=%d\n", a.bb.plan_phase);
        ok(a.bb.plan_phase >= 0 && a.bb.plan_phase < PH_N, "오염된 plan_phase → 유효 단계로 복구");
    }

    /* 5) fault: 액추에이터 사용 불가 → 안전 정지 + 이벤트 */
    {
        Agent a; fw_agent_init(&a);
        clear_obs(&a.bb); set_obs(&a.bb, SEN_RGB, 0.9f, 10, 10);
        a.bb.world.actuator_ok = false;
        Action act = fw_agent_step(&a);
        printf("[5 actuator] act=%s ev=%d\n", fw_action_name(act), has_event(&a.evq, EV_ACTUATOR_FAIL));
        ok(act == ACT_NONE, "구동계 고장 → 안전 정지(ACT_NONE)");
    }

    /* 6) 잔여 GAP(정직): '모두-정지'(변하는 기준 채널 없음)는 stale 검출로 못 가른다.
       정지 실표적과 구분이 반복만으로는 불가 — 이건 §6 liveness 몫이지 stale detector 로 못 닫는다. */
    {
        Agent a; fw_agent_init(&a); a.bb.cfg.confirm_n = 2;
        int i;
        for (i = 0; i < 4; i++) {                        /* 두 채널 모두 동일(stuck) 값 = 변하는 기준 없음 */
            clear_obs(&a.bb); set_obs(&a.bb, SEN_RGB, 0.9f, 10, 10); set_obs(&a.bb, SEN_THERMAL, 0.8f, 10, 10);
            fw_agent_step(&a);
        }
        printf("[6 모두-정지 GAP] confirmed=%d (변하는 기준 없어 stale 로 못 가름 → liveness 몫)\n",
               a.bb.belief.confirmed);
        ok(a.bb.belief.confirmed,
           "GAP: 모두-정지는 stale 로 못 거른다(정지 실표적과 반복만으로 구분 불가 — §6 liveness)");
    }

    /* 7) stale 차등 검출: 한 채널이 얼어붙고(frozen) 다른 채널은 변하면 → frozen 채널 격리 + EV_SENSOR_STALE.
       모두-정지(6)와 달리 '살아있는 기준'이 있어 stuck 을 가려낸다 — R-03 계열의 부분 폐쇄. */
    {
        Agent a; fw_agent_init(&a); a.bb.cfg.confirm_n = 2;
        int i;
        for (i = 0; i < FW_STALE_N + 1; i++) {
            clear_obs(&a.bb);
            set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);                    /* RGB 고정(stuck) */
            set_obs(&a.bb, SEN_THERMAL, 0.8f, 10.0f + 0.1f * (float)i, 10.0f); /* THERMAL 움직임(기준) */
            fw_agent_step(&a);
        }
        int stale_ev = has_event(&a.evq, EV_SENSOR_STALE);
        printf("[7 stale 차등] RGB health=%.1f stale_ev=%d\n", a.bb.health.health[SEN_RGB], stale_ev);
        ok(stale_ev, "얼어붙은 채널(RGB) 대 움직이는 채널(THERMAL) → EV_SENSOR_STALE 검출");
        ok(a.bb.health.health[SEN_RGB] == 0.0f, "frozen 센서(RGB) 격리(health→0, 융합서 제외)");
    }

    if (g_fail) { printf("\nFAIL %d개\n", g_fail); return 1; }
    printf("\nfw fault-injection replay 검사 통과(결정성·dropout·공분산폭발·planner오염·actuator·stale 차등검출·모두정지 gap)\n");
    return 0;
}
