/* evidence.c — health 가중 soft vote + 신뢰가중 무게중심 + 시간적 확인. (도메인 무관 융합수학:
 * 센서 가중·CMPC 채널역할은 bb->spec 프로파일에서 읽는다.) */
#include "evidence.h"
#include "policy_spec.h"

static float clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

void fw_evidence_update(Blackboard *bb)
{
    /* 1) 가장 강한 present 센서를 앵커로 잡는다(가중×건강×증거 최대). */
    int   anchor = -1;
    float best = -1.0f;
    int   i;
    for (i = 0; i < FW_N_SENSOR; i++) {
        if (!bb->obs[i].present) continue;
        float w = bb->spec->vote_w[i] * bb->health.health[i] * bb->obs[i].evidence;
        if (w > best) { best = w; anchor = i; }
    }

    float th = bb->cfg.confirm_th;
    int   need = bb->cfg.confirm_n;

    if (anchor < 0) {
        /* 이번 스텝 관측 없음: 예측만(공분산 성장 → sigma↑), 신뢰 감쇠, 연속성 깨짐. */
        fw_kf_predict(&bb->kf);
        bb->belief.age += 1;
        bb->belief.target_conf *= 0.7f;
        bb->belief.sigma = fw_kf_sigma(&bb->kf);
        bb->belief.confirm_run = 0;
        bb->belief.unconf_run = 0;   /* 이번 스텝 관측 없음 → 후보-미확정 연속 끊김(ABSTAIN 은 관측 있는데 못 붙을 때) */
        if (bb->belief.target_conf < th) bb->belief.confirmed = false;
        return;
    }

    /* 2) 앵커 게이트 안의 present 센서를 융합: num=Σ w·health·evidence, 위치=그 가중 무게중심.
       in_gate[i]=이 센서가 융합에 참여했나(교차모달 채널 수 세기용). */
    float ax = bb->obs[anchor].x, ay = bb->obs[anchor].y;
    float num = 0.0f, xw = 0.0f, yw = 0.0f, wsum = 0.0f;
    int in_gate[FW_N_SENSOR];
    for (i = 0; i < FW_N_SENSOR; i++) in_gate[i] = 0;
    for (i = 0; i < FW_N_SENSOR; i++) {
        if (!bb->obs[i].present) continue;
        float dx = bb->obs[i].x - ax, dy = bb->obs[i].y - ay;
        if (dx * dx + dy * dy > FW_GATE2) continue;   /* 다른 표적 → 이번 융합서 제외 */
        in_gate[i] = 1;
        float w = bb->spec->vote_w[i] * bb->health.health[i] * bb->obs[i].evidence;
        num += w;
        xw += w * bb->obs[i].x; yw += w * bb->obs[i].y; wsum += w;
    }

    float conf = clampf(num, 0.0f, 1.0f);   /* soft vote 합(임계는 CONFIRM_TH) */
    bb->belief.target_conf = conf;
    bool motion_ok = true;
    bool detected = (conf >= th);           /* 기본(CMPC off): soft-vote 임계. CMPC on 이면 아래서 대체 */
    if (wsum > 1e-6f) {
        float mx = xw / wsum, my = yw / wsum;         /* 융합 측정(신뢰가중 무게중심) */
        float r = 0.2f + 2.0f * (1.0f - conf);        /* 측정잡음: 신뢰 높을수록 작다 */
        fw_kf_predict(&bb->kf);
        float d2 = fw_kf_update(&bb->kf, mx, my, r);  /* 칼만 갱신 → 평활 위치·속도·NIS */
        bb->belief.px = bb->kf.xp;
        bb->belief.py = bb->kf.yp;
        bb->belief.sigma = fw_kf_sigma(&bb->kf);      /* 원리적 위치 불확실도(√trP) */
        bb->belief.speed = fw_kf_speed(&bb->kf);
        bb->belief.nis = d2;                          /* 운동 일관성(evidence) */
        bb->belief.age = 0;
        /* motion consistency 게이트: 확립된 추적(age 진행)에서 NIS 가 임계 초과면 이 측정은
           궤적과 모순(점프/불가능 운동) → 확인 카운트에 안 넣는다(motion 을 decision evidence 로). */
        if (bb->cfg.nis_gate > 0.0f && d2 > bb->cfg.nis_gate)
            motion_ok = false;

        /* 교차모달 물리 일관성(CMPC): "몇 개 봤나"가 아니라 서로 다른 물리채널 ≥ 요구치인가.
           단일센서 주장(고착·다중경로·단일모달 clutter)을 거른다. 가림-강(SAR/Audio)만이면 조건부
           완화(수관 진짜 보존). require_live 면 liveness(호흡·심박)가 근접해야 — 전-서명 decoy 차단. */
        if (bb->cfg.cmpc_min > 0) {
            int n_modal = 0;
            for (i = 0; i < FW_N_SENSOR; i++) n_modal += in_gate[i];
            int any_blocked = 0, any_allw = 0;   /* 채널 역할은 프로파일 마스크에서(도메인 무관) */
            for (int k = 0; k < FW_N_SENSOR; k++) {
                if (!in_gate[k]) continue;
                if (bb->spec->blocked_mask & (1u << k)) any_blocked = 1;
                if (bb->spec->allw_mask & (1u << k))    any_allw = 1;
            }
            int required = bb->cfg.cmpc_min;
            if (bb->cfg.cmpc_min >= 2 && !any_blocked && any_allw)
                required = 1;                          /* 가림-강 채널 단독 → 진짜 보존 */
            detected = (n_modal >= required);          /* CMPC on: 채널 수가 판별기준(soft-vote 대체) */
        }
        if (bb->cfg.require_live) {
            float ldx = bb->live.x - mx, ldy = bb->live.y - my;
            if (!(bb->live.present && ldx * ldx + ldy * ldy <= FW_GATE2))
                detected = false;                      /* liveness 없음(전-서명 decoy) → 확인 안 함 */
        }
    }

    /* 3) 시간적 일관성: 연속 N 스텝 (검출 + 운동 일관성)이라야 confirmed. */
    if (detected && motion_ok) {
        if (bb->belief.confirm_run < 1000000) bb->belief.confirm_run += 1;
    } else {
        bb->belief.confirm_run = 0;
    }
    bb->belief.confirmed = (bb->belief.confirm_run >= need);
    /* 공분산 폭발 가드(FDIR): 위치 불확실도가 상한을 넘으면 확인 취소(오래 못 본 추적에 행동 금지). */
    if (bb->belief.sigma > FW_SIGMA_MAX) bb->belief.confirmed = false;

    /* §7 ABSTAIN: 후보(conf>임계)가 관측되는데도 확인이 **못 붙는**(confirm_run 0) 스텝이 이어지면
       세어 둔다. liveness 부재·CMPC 미달·운동 모순처럼 확인이 원리적으로 막힌 경우다. confirm_run 이
       진행 중이면(확인 쌓는 중) 0 으로 리셋 — 정상 확인 지연을 기권으로 오인하지 않는다. */
    if (bb->belief.target_conf > FW_CAND_TH && bb->belief.confirm_run == 0) {
        if (bb->belief.unconf_run < 1000000) bb->belief.unconf_run += 1;
    } else {
        bb->belief.unconf_run = 0;
    }
}
