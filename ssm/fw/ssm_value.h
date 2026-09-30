/* ssm_value.h -- 최소 선택적 SSM(Mamba 원자)을 policy_core 의 PC_ValueHead 로 감싼 어댑터.
 *
 * 자리: policy_core 는 belief 수학·RTA 안전을 '결정적'으로 하고, '판단 보강(value-to-go)'
 *   한 조각만 학습에 맡긴다(policy_core.h 의 PC_ValueHead). 이 어댑터가 그 학습 조각을
 *   ssm/fw 커널(선택적 IIR 뱅크)로 채운다. 코어는 여전히 SSM 을 모른다(함수포인터만 봄).
 *
 * 계약 구현:
 *   value():   지속 상태(실제 궤적 이력)를 '복사'해 한 스텝 돌리고 버린다 -> 지속상태 불변.
 *              그래서 lookahead 가 후보 leaf 를 여럿 점수매겨도 재귀가 오염되지 않는다.
 *   advance(): 지속 상태를 실제로 한 스텝 전진(커밋된 관측주기마다 호출).
 *   readout:   스칼라 value = y[0](최소 읽기). 실제 학습 head 는 w_out·y 를 쓰며 그 투영은
 *              학습으로 정해진다 -- 여기선 원자 배선만 증명(가중치 미학습).
 *
 * ⚠ 학습 가중치가 아직 없다. lambda 는 학습 전 0 으로 둘 것(과장방지: 안 잰 이득 안 켬).
 *   host_test 는 '배선/순수성/결정성'만 붙든다. 성능 주장은 학습·측정 후에만.
 */
#ifndef SSM_VALUE_H
#define SSM_VALUE_H

#include "ssm.h"
#include "policy_core.h"

#if PC_VH_NFEAT != SSM_D_INNER
#error "PC_VH_NFEAT 와 SSM_D_INNER 가 다르면 특징->채널 매핑을 명시해야 한다"
#endif

/* 지속 문맥(실제 궤적) + 학습 가중치. 힙 없음, 고정크기. */
typedef struct {
    SSM_Weights w;    /* 오프디바이스 학습 -> export (지금은 시험 가중치) */
    SSM_State   st;   /* 지속 SSM 상태(이력 문맥) */
} SSM_ValueCtx;

/* 상태 0으로(가중치 w 는 호출자가 채운다). 임무 시작마다. */
void ssm_value_init(SSM_ValueCtx *c);

/* c 를 백엔드로 하는 PC_ValueHead 를 만든다. lambda=혼합계수(학습 전 0). */
PC_ValueHead ssm_value_head(SSM_ValueCtx *c, float lambda);

#endif /* SSM_VALUE_H */
