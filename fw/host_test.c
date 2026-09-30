/* host_test.c — 결정 executive 의 행동을 재서 검증(호스트 gcc). 스텁이 아니라 실제 파이프라인.
 *
 * 검사하는 것:
 *   1) 외로운 Audio 는 확인 안 됨 → SEARCH 유지(오경보 억제; PR #439 를 C 로)
 *   2) RGB+Thermal 코로보 N스텝 → confirmed → INSPECT
 *   3) 플리커(간헐 관측)는 confirmed 안 됨
 *   4) 저전력 → RETURN override(확인된 표적이어도)
 *   5) 충돌 임박 → AVOID override
 *   6) 센서 2개 고장 → FDIR 이벤트 + DEGRADED + RECOVERY(RELOCALIZE)
 *   7) IMU 무효 → RELOCALIZE
 *   8) 이벤트 큐 오버플로 → dropped 계상
 *   9) arbiter: 미확인인데 INSPECT 제안 → precond 실패 → 안전 효용행동으로 대체
 *  10) 건강 가중: 죽은 카메라의 강한 증거는 신뢰로 안 올라감
 */
#include <stdio.h>
#include <math.h>
#include "agent.h"
#include "evidence.h"
#include "estimator.h"
#include "planner.h"
#include "arbiter.h"
#include "safety.h"
#include "policy_spec.h"

static int g_fail = 0;

static void ok(int cond, const char *msg)
{
    printf("    %s %s\n", cond ? "OK  " : "FAIL", msg);
    if (!cond) g_fail++;
}

/* 모든 센서 present=false 로 지운다 */
static void clear_obs(Blackboard *bb)
{
    int i;
    for (i = 0; i < FW_N_SENSOR; i++) { bb->obs[i].present = false; bb->obs[i].evidence = 0.0f; }
}

static void set_obs(Blackboard *bb, SensorId s, float ev, float x, float y)
{
    bb->obs[s].present = true; bb->obs[s].evidence = ev; bb->obs[s].x = x; bb->obs[s].y = y;
}

int main(void)
{
    /* 1) 외로운 Audio */
    {
        Agent a; fw_agent_init(&a);
        Action act = ACT_NONE; int i;
        for (i = 0; i < 6; i++) {
            clear_obs(&a.bb);
            set_obs(&a.bb, SEN_AUDIO, 0.9f, 10.0f, 10.0f);   /* Audio 만, 강하게 */
            act = fw_agent_step(&a);
        }
        printf("[1 외로운 Audio] conf=%.3f confirmed=%d act=%s\n",
               a.bb.belief.target_conf, a.bb.belief.confirmed, fw_action_name(act));
        ok(!a.bb.belief.confirmed, "외로운 Audio 는 확인 안 됨(오경보 억제)");
        ok(act == ACT_SEARCH, "외로운 Audio 에도 SEARCH 유지");
    }

    /* 2) RGB+Thermal 코로보 → confirmed → INSPECT */
    {
        Agent a; fw_agent_init(&a);
        Action act = ACT_NONE; int i;
        for (i = 0; i < 4; i++) {
            clear_obs(&a.bb);
            set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);
            set_obs(&a.bb, SEN_THERMAL, 0.8f, 10.2f, 9.9f);
            act = fw_agent_step(&a);
        }
        printf("[2 코로보] conf=%.3f confirmed=%d px=%.2f py=%.2f act=%s\n",
               a.bb.belief.target_conf, a.bb.belief.confirmed, a.bb.belief.px, a.bb.belief.py, fw_action_name(act));
        ok(a.bb.belief.confirmed, "RGB+Thermal 코로보 → confirmed");
        ok(act == ACT_INSPECT, "확인된 표적 → INSPECT");
        ok(a.bb.belief.px > 9.9f && a.bb.belief.px < 10.15f, "융합 위치가 RGB 쪽(신뢰가중)");
    }

    /* 3) 플리커는 confirmed 안 됨 */
    {
        Agent a; fw_agent_init(&a);
        int i;
        for (i = 0; i < 8; i++) {
            clear_obs(&a.bb);
            if (i % 2 == 0) set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);  /* 격스텝만 관측 */
            fw_agent_step(&a);
        }
        printf("[3 플리커] confirmed=%d run=%d\n", a.bb.belief.confirmed, a.bb.belief.confirm_run);
        ok(!a.bb.belief.confirmed, "간헐 관측(플리커)은 확인 안 됨");
    }

    /* 4) 저전력 → RETURN (확인된 표적이어도) */
    {
        Agent a; fw_agent_init(&a);
        Action act = ACT_NONE; int i;
        for (i = 0; i < 4; i++) {   /* 먼저 확인 표적 만들기 */
            clear_obs(&a.bb);
            set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);
            set_obs(&a.bb, SEN_THERMAL, 0.8f, 10.2f, 9.9f);
            act = fw_agent_step(&a);
        }
        a.bb.world.battery = 0.20f;              /* 저전력 */
        clear_obs(&a.bb);
        set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);
        set_obs(&a.bb, SEN_THERMAL, 0.8f, 10.2f, 9.9f);
        act = fw_agent_step(&a);
        printf("[4 저전력] confirmed=%d safety=%s act=%s\n",
               a.bb.belief.confirmed, fw_safety_name(a.bb.safety), fw_action_name(act));
        ok(act == ACT_RETURN, "저전력이면 확인 표적이어도 RETURN override");
    }

    /* 5) 충돌 임박 → AVOID */
    {
        Agent a; fw_agent_init(&a);
        clear_obs(&a.bb);
        set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);
        a.bb.world.collision_risk = 0.90f;
        Action act = fw_agent_step(&a);
        printf("[5 충돌] safety=%s act=%s\n", fw_safety_name(a.bb.safety), fw_action_name(act));
        ok(act == ACT_AVOID, "충돌 임박 → AVOID override");
    }

    /* 6) 센서 2개 고장 → FDIR 이벤트 + DEGRADED + RELOCALIZE */
    {
        Agent a; fw_agent_init(&a);
        clear_obs(&a.bb);
        set_obs(&a.bb, SEN_AUDIO, 0.5f, 10.0f, 10.0f);
        a.bb.health.health[SEN_RGB] = 0.0f;     /* 카메라 죽음 */
        a.bb.health.health[SEN_LIDAR] = 0.0f;   /* 라이다 죽음 */
        Action act = fw_agent_step(&a);
        Event e; int got_fail = 0;
        while (fw_evq_pop(&a.evq, &e)) if (e.type == EV_SENSOR_FAIL) got_fail++;
        printf("[6 고장] safety=%s mode=%s act=%s fail_events=%d\n",
               fw_safety_name(a.bb.safety), fw_mode_name(a.bb.mode), fw_action_name(act), got_fail);
        ok(got_fail == 2, "센서 2개 고장 → FDIR 이벤트 2건");
        ok(a.bb.safety == SAFE_DEGRADED, "다수 고장 → DEGRADED");
        ok(act == ACT_RELOCALIZE, "DEGRADED → RECOVERY(RELOCALIZE)");
    }

    /* 7) IMU 무효 → RELOCALIZE */
    {
        Agent a; fw_agent_init(&a);
        clear_obs(&a.bb);
        set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);
        a.bb.world.imu_valid = false;
        Action act = fw_agent_step(&a);
        printf("[7 IMU무효] act=%s\n", fw_action_name(act));
        ok(act == ACT_RELOCALIZE, "IMU 무효 → RELOCALIZE(전진 금지)");
    }

    /* 8) 이벤트 큐 오버플로 → dropped */
    {
        EventQueue q; int i;
        fw_evq_init(&q);
        for (i = 0; i < FW_EVQ_CAP + 5; i++) fw_evq_push(&q, EV_MODE_CHANGE, i, (uint32_t)i);
        printf("[8 큐] dropped=%u size=%d\n", q.dropped, q.size);
        ok(q.dropped == 5, "오버플로 이벤트를 dropped 로 정직 계상");
    }

    /* 9) arbiter: 미확인 INSPECT 제안 → 안전 효용행동으로 대체 */
    {
        Blackboard bb; fw_bb_init(&bb);
        bb.belief.confirmed = false; bb.belief.target_conf = 0.0f;
        Action a2 = fw_arbitrate(&bb, ACT_INSPECT);
        printf("[9 arbiter] INSPECT(미확인) → %s\n", fw_action_name(a2));
        ok(a2 != ACT_INSPECT, "precond 실패 INSPECT 는 채택 안 됨");
        ok(a2 == ACT_SEARCH, "대체는 효용최대 안전행동(SEARCH)");
    }

    /* 10) 건강 가중: 죽은 카메라의 강한 증거는 신뢰로 안 올라감 */
    {
        Agent a; fw_agent_init(&a);
        clear_obs(&a.bb);
        set_obs(&a.bb, SEN_RGB, 0.95f, 10.0f, 10.0f);   /* 강한 RGB 증거지만 */
        a.bb.health.health[SEN_RGB] = 0.0f;             /* 카메라 죽음 */
        fw_agent_step(&a);
        printf("[10 건강가중] conf=%.3f\n", a.bb.belief.target_conf);
        ok(a.bb.belief.target_conf < FW_CONFIRM_TH, "죽은 센서 증거는 신뢰로 안 올라감(health 가중)");
    }

    /* 11) 등속 Kalman: 움직이는 표적 속도 추정 · 일관 운동 NIS 작음 · 점프 NIS 큼 · 예측 공분산↑ */
    {
        KalmanCV kf; fw_kf_init(&kf, 0.05f);
        int i; float nis_c = 0.0f;
        for (i = 0; i < 14; i++) {                 /* 등속 표적 z=(i,2i): vx=1,vy=2 */
            fw_kf_predict(&kf);
            nis_c = fw_kf_update(&kf, (float)i, 2.0f * (float)i, 0.5f);
        }
        float sp = fw_kf_speed(&kf);
        printf("[11 CV-Kalman] speed=%.3f(참 2.236) NIS_consistent=%.3f\n", sp, nis_c);
        ok(fabsf(sp - 2.236f) < 0.6f, "등속 표적의 속도 추정(|v|≈2.24)");
        ok(nis_c < 6.0f, "일관 등속 운동 → NIS 작음(궤적과 일치)");
        fw_kf_predict(&kf);
        float nis_jump = fw_kf_update(&kf, 100.0f, 100.0f, 0.5f);   /* 불가능 점프 */
        printf("       NIS_jump=%.1f\n", nis_jump);
        ok(nis_jump > 6.0f * (nis_c + 0.1f), "점프(불가능 운동) → NIS 큼(운동 모순 검출)");
        fw_kf_init(&kf, 0.05f); fw_kf_update(&kf, 5.0f, 5.0f, 0.5f);
        float sb = fw_kf_sigma(&kf);
        for (i = 0; i < 5; i++) fw_kf_predict(&kf);
        ok(fw_kf_sigma(&kf) > sb, "관측 없으면 공분산 성장(안 보면 불확실↑)");
    }

    /* 12) Planner: 임무 단계 순차(SEARCH→APPROACH→INSPECT→REPORT) + 저전력 재계획 */
    {
        Agent a; fw_agent_init(&a);
        int seen_ap = 0, seen_in = 0, seen_rp = 0, i;
        for (i = 0; i < 10; i++) {
            clear_obs(&a.bb);
            set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);
            set_obs(&a.bb, SEN_THERMAL, 0.8f, 10.2f, 9.9f);
            fw_agent_step(&a);
            if (a.bb.plan_phase == PH_APPROACH) seen_ap = 1;
            if (a.bb.plan_phase == PH_INSPECT) seen_in = 1;
            if (a.bb.plan_phase == PH_REPORT) seen_rp = 1;
        }
        printf("[12 planner] approach=%d inspect=%d report=%d\n", seen_ap, seen_in, seen_rp);
        ok(seen_ap && seen_in, "planner 순차 SEARCH→APPROACH→INSPECT");
        ok(seen_rp, "INSPECT dwell 후 REPORT(임무 진행)");
        a.bb.world.battery = 0.20f; clear_obs(&a.bb); fw_agent_step(&a);
        printf("       저전력 후 plan=%s\n", fw_plan_name(a.bb.plan_phase));
        ok(a.bb.plan_phase == PH_RETURN, "저전력 → 재계획 RETURN");
    }

    /* 13) Replay 결정성: 동일 입력 → 동일 행동열(재현 가능 = IV&V 기반) */
    {
        Agent a1, a2; fw_agent_init(&a1); fw_agent_init(&a2);
        int match = 1, i;
        for (i = 0; i < 12; i++) {
            float ev = (i % 3 == 0) ? 0.9f : 0.0f;
            clear_obs(&a1.bb); clear_obs(&a2.bb);
            if (ev > 0.0f) {
                set_obs(&a1.bb, SEN_RGB, ev, 10.0f, 10.0f); set_obs(&a2.bb, SEN_RGB, ev, 10.0f, 10.0f);
                set_obs(&a1.bb, SEN_THERMAL, 0.8f, 10.1f, 10.0f); set_obs(&a2.bb, SEN_THERMAL, 0.8f, 10.1f, 10.0f);
            }
            Action x1 = fw_agent_step(&a1); Action x2 = fw_agent_step(&a2);
            if (x1 != x2) match = 0;
        }
        printf("[13 replay] deterministic=%d\n", match);
        ok(match, "동일 입력 → 동일 행동열(결정적·재현 가능, IV&V 기반)");
    }

    /* 14) CMPC 이식(FW-CMPC-001): sar 프로토타입(policies.cmpc_confirm)과 같은 규칙이 C 에서도 */
    {
        /* 단일모달 RGB: cmpc_min=1 확인 / cmpc_min=2 기각 */
        Agent a; fw_agent_init(&a); a.bb.cfg.confirm_n = 1; a.bb.cfg.cmpc_min = 1;
        clear_obs(&a.bb); set_obs(&a.bb, SEN_RGB, 0.9f, 10, 10); fw_agent_step(&a);
        Agent b; fw_agent_init(&b); b.bb.cfg.confirm_n = 1; b.bb.cfg.cmpc_min = 2;
        clear_obs(&b.bb); set_obs(&b.bb, SEN_RGB, 0.9f, 10, 10); fw_agent_step(&b);
        printf("[14 CMPC] RGB단일 min1=%d min2=%d\n", a.bb.belief.confirmed, b.bb.belief.confirmed);
        ok(a.bb.belief.confirmed && !b.bb.belief.confirmed, "단일모달 RGB: cmpc_min=1 확인·2 기각");
        /* SAR 단독: 조건부 완화로 확인(가림-강 채널 진짜 보존) */
        Agent s; fw_agent_init(&s); s.bb.cfg.confirm_n = 1; s.bb.cfg.cmpc_min = 2;
        clear_obs(&s.bb); set_obs(&s.bb, SEN_SAR, 0.5f, 10, 10); fw_agent_step(&s);
        ok(s.bb.belief.confirmed, "SAR 단독: 조건부 완화로 확인(수관 진짜 보존)");
        /* 전-서명 decoy(RGB+Thermal+LiDAR, live 없음): CMPC 통과 / require_live 기각 */
        Agent d; fw_agent_init(&d); d.bb.cfg.confirm_n = 1; d.bb.cfg.cmpc_min = 2;
        clear_obs(&d.bb); set_obs(&d.bb, SEN_RGB, 0.9f, 10, 10);
        set_obs(&d.bb, SEN_THERMAL, 0.7f, 10, 10); set_obs(&d.bb, SEN_LIDAR, 0.8f, 10, 10);
        fw_agent_step(&d);
        Agent e; fw_agent_init(&e); e.bb.cfg.confirm_n = 1; e.bb.cfg.cmpc_min = 2; e.bb.cfg.require_live = true;
        clear_obs(&e.bb); set_obs(&e.bb, SEN_RGB, 0.9f, 10, 10);
        set_obs(&e.bb, SEN_THERMAL, 0.7f, 10, 10); set_obs(&e.bb, SEN_LIDAR, 0.8f, 10, 10);
        e.bb.live.present = false; fw_agent_step(&e);
        printf("       decoy CMPC=%d +live=%d\n", d.bb.belief.confirmed, e.bb.belief.confirmed);
        ok(d.bb.belief.confirmed && !e.bb.belief.confirmed, "decoy: CMPC 통과·liveness 요구 시 기각");
        /* 진짜(같은 서명 + liveness): require_live 통과 */
        Agent f; fw_agent_init(&f); f.bb.cfg.confirm_n = 1; f.bb.cfg.cmpc_min = 2; f.bb.cfg.require_live = true;
        clear_obs(&f.bb); set_obs(&f.bb, SEN_RGB, 0.9f, 10, 10);
        set_obs(&f.bb, SEN_THERMAL, 0.7f, 10, 10); set_obs(&f.bb, SEN_LIDAR, 0.8f, 10, 10);
        f.bb.live.present = true; f.bb.live.x = 10; f.bb.live.y = 10; fw_agent_step(&f);
        ok(f.bb.belief.confirmed, "진짜(liveness 있음): require_live 도 통과");
    }

    /* 15) ABSTAIN(§1·§7): 후보(conf>0.5)인데 liveness 부재로 확인이 못 붙으면 → 사람이라 확정 거부 */
    {
        Agent a; fw_agent_init(&a);
        a.bb.cfg.confirm_n = 2; a.bb.cfg.cmpc_min = 2; a.bb.cfg.require_live = true;
        Action act = ACT_NONE; int i;
        for (i = 0; i < 6; i++) {
            clear_obs(&a.bb);
            set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);
            set_obs(&a.bb, SEN_THERMAL, 0.8f, 10.1f, 10.0f);
            a.bb.live.present = false;                  /* 생체 신호 없음(전-서명 decoy) */
            act = fw_agent_step(&a);
        }
        printf("[15 ABSTAIN] conf=%.2f confirmed=%d unconf=%d act=%s\n",
               a.bb.belief.target_conf, a.bb.belief.confirmed, a.bb.belief.unconf_run, fw_action_name(act));
        ok(!a.bb.belief.confirmed, "liveness 부재 후보는 confirmed 안 됨");
        ok(act == ACT_ABSTAIN, "확인 못 붙는 후보 지속 → ABSTAIN(확정 거부, NONE/SEARCH 와 구분)");
    }

    /* 16) §10 설정 해시: 같은 설정→같은 해시, 임계 하나만 바뀌어도 달라진다(트레이스 스탬프) */
    {
        Blackboard bb; fw_bb_init(&bb);
        Config c1 = bb.cfg, c2 = bb.cfg;
        ok(fw_cfg_hash(&c1) == fw_cfg_hash(&c2), "같은 설정 → 같은 해시(결정적)");
        c2.confirm_th += 0.05f;
        ok(fw_cfg_hash(&c1) != fw_cfg_hash(&c2), "임계(confirm_th) 하나 바뀌면 해시 달라짐");
        c2 = c1; c2.version = 7;
        printf("[16 cfg hash] h=%u (version 7 → %u)\n", fw_cfg_hash(&c1), fw_cfg_hash(&c2));
        ok(fw_cfg_hash(&c1) != fw_cfg_hash(&c2), "판번호 바뀌면 해시 달라짐(어느 설정이 돌았나 스탬프)");
    }

    /* 17) 프로파일 재사용(정책 tool 증명): 같은 커널에 SAR 아닌 최소 도메인(FW_PROFILE_MIN)을
       꽂아도 돈다 — 커널은 한 줄도 안 바꾸고 전혀 다른 행동 집합(OBSERVE/ACT/STOP)이 나온다. */
    {
        Agent a; fw_agent_init_profile(&a, &FW_PROFILE_MIN);
        int i;
        clear_obs(&a.bb);
        Action idle = fw_agent_step(&a);                 /* 관측 없음 → OBSERVE(fallback=1) */
        for (i = 0; i < 4; i++) {                         /* 두 채널 확인 쌓기 → confirmed */
            clear_obs(&a.bb);
            set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);
            set_obs(&a.bb, SEN_THERMAL, 0.8f, 10.0f, 10.0f);
            fw_agent_step(&a);
        }
        clear_obs(&a.bb);
        set_obs(&a.bb, SEN_RGB, 0.9f, 10.0f, 10.0f);
        set_obs(&a.bb, SEN_THERMAL, 0.8f, 10.0f, 10.0f);
        Action go = fw_agent_step(&a);                    /* confirmed → ACT(2) */
        a.bb.world.battery = 0.05f;
        Action stop = fw_agent_step(&a);                  /* 저전력 → STOP(3) override */
        printf("[17 프로파일 재사용] spec=%s idle=%s go=%s stop=%s\n", a.bb.spec->name,
               a.bb.spec->action_names[idle], a.bb.spec->action_names[go], a.bb.spec->action_names[stop]);
        ok(idle == 1, "MIN 프로파일: 유휴 → OBSERVE(같은 커널, 다른 도메인)");
        ok(go == 2,   "MIN 프로파일: 확인 → ACT");
        ok(stop == 3, "MIN 프로파일: 저전력 → STOP(safety_filter override)");
    }

    if (g_fail) { printf("\nFAIL %d개\n", g_fail); return 1; }
    printf("\nfw 결정 executive host_test 전부 통과(외로운센서억제·코로보확인·안전override·FDIR·arbiter·건강가중·ABSTAIN·설정해시·프로파일재사용)\n");
    return 0;
}
