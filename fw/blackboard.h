/* blackboard.h — 모든 계층이 공유하는 정적 상태(malloc 없음).
 *
 * LLM 없는 자율 결정 executive 의 중심. 센서→증거→믿음→항법·건강→모드→행동이
 * 전부 이 한 구조체를 읽고 쓴다. bare-metal(RTOS 없음)이라 동적할당·부동 예외를
 * 피하고, 크기가 컴파일 시점에 고정된다.
 *
 * 개념 근거: POMDP belief(분포 대신 평균·불확실도·신뢰·나이만), Subsumption/3T 의
 * 계층 상태, cFS 의 component 공유 blackboard. (paper/선행조사/무LLM_자율결정구조.md)
 */
#ifndef FW_BLACKBOARD_H
#define FW_BLACKBOARD_H

#include <stdint.h>
#include <stdbool.h>
#include "estimator.h"

/* 정책 프로파일(도메인의 '무엇'). 본문은 policy_spec.h; 여기선 전방선언만(순환 방지). */
struct PolicySpec;
typedef struct PolicySpec PolicySpec;

#define FW_N_SENSOR 5   /* 센서 채널 용량(프로파일이 ≤ 이 수를 쓴다). SAR: RGB,THERMAL,LIDAR,SAR,AUDIO */

typedef enum { SEN_RGB = 0, SEN_THERMAL, SEN_LIDAR, SEN_SAR, SEN_AUDIO } SensorId;

/* 한 센서의 이번 스텝 관측: 표적 증거(0..1)·위치주장(격자)·유효성 */
typedef struct {
    float evidence;   /* 이 센서가 준 표적 증거 0..1 */
    float x, y;       /* 위치 주장(격자 좌표) */
    bool  present;    /* 이번 스텝에 관측이 있나(센서가 켜져 데이터를 줬나) */
} SensorObs;

/* 센서 건강도. 0=죽음, 1=정상. 융합 가중에 곱해져 고장 센서를 자동 배제. */
typedef struct { float health[FW_N_SENSOR]; } SensorHealth;

/* 믿음 상태(POMDP belief 축약): 분포 대신 신뢰·위치·불확실도·나이·시간일관성. */
typedef struct {
    float    target_conf;   /* 융합 신뢰 0..1 */
    float    px, py;        /* 융합 위치(신뢰가중 무게중심) */
    float    sigma;         /* 위치 불확실도(√trP) */
    float    speed;         /* KF 추정 속도 크기 |v| */
    float    nis;           /* 마지막 측정의 운동 일관성(innovation consistency, 2-DOF) */
    uint32_t age;           /* 마지막 유효 갱신 이후 스텝 수 */
    int      confirm_run;   /* 연속 임계초과 카운터(시간적 일관성) */
    int      unconf_run;    /* 후보(conf>0.5)인데 확인이 못 붙는 연속 스텝(§7 ABSTAIN 트리거) */
    bool     confirmed;     /* 시간적으로 확인됨(플리커 오경보 제거) */
} Belief;

/* 항법·건강·환경 상태 */
typedef struct {
    float    battery;        /* 0..1 */
    float    collision_risk; /* 0..1 */
    float    position_error; /* 항법 오차(격자) */
    bool     gps_valid, imu_valid;
    bool     actuator_ok;    /* 구동계 가용(false=액추에이터 고장→안전 정지) */
    uint32_t t;              /* 스텝 카운터 */
} WorldState;

typedef enum {
    ACT_NONE = 0, ACT_SEARCH, ACT_APPROACH, ACT_INSPECT,
    ACT_RETURN, ACT_AVOID, ACT_RELOCALIZE, ACT_EMERGENCY,
    ACT_ABSTAIN,   /* 후보를 사람이라 확정 거부(보류). 별도 primitive — NONE/SEARCH 와 구분(§1·§7) */
    ACT_N
} Action;

typedef enum {
    MODE_SEARCH = 0, MODE_INVESTIGATE, MODE_RETURN, MODE_RECOVERY, MODE_EMERGENCY, MODE_N
} Mode;

typedef enum { SAFE_NORMAL = 0, SAFE_DEGRADED, SAFE_RETURN, SAFE_EMERGENCY } SafetyState;

/* 튜닝 파라미터(런타임 설정 가능). 기본은 evidence.h 의 매크로. */
typedef struct {
    int      confirm_n;    /* 연속 몇 스텝 임계초과라야 confirmed(시간적 확인창) */
    float    confirm_th;   /* 이 신뢰 이상이면 이번 스텝 '초과' */
    float    nis_gate;     /* >0 이면 NIS>이 값인 측정은 운동 모순으로 확인서 제외(0=off) */
    int      cmpc_min;     /* 교차모달 최소 채널 수(0=off, 2=CMPC). 가림-강 채널만이면 조건부 1 완화 */
    bool     require_live; /* true 면 liveness(호흡·심박) 근접 없이는 확인 안 됨(전-서명 decoy 차단) */
    uint32_t version;      /* 정책 설정 판번호(§10; 트레이스에 어느 설정이 돌았나 묶기용) */
} Config;

/* 센서별 값-정지(freeze) 추적: 직전 (ev,x,y) 와 byte-동일 반복 횟수. stale/frozen 센서 검출(§2·§4). */
typedef struct { float ev, x, y; int run; } StaleTrack;

/* liveness 채널 관측(호흡·심박 미세운동): 실 표적만, 전-서명 decoy 는 없다. */
typedef struct { bool present; float x, y; } LiveObs;

/* 블랙보드: 정적 공용 상태. 계층들이 인터페이스(이 구조체)로만 소통한다. */
typedef struct {
    SensorObs    obs[FW_N_SENSOR];
    SensorHealth health;
    Belief       belief;
    WorldState   world;
    Mode         mode;
    SafetyState  safety;
    Config       cfg;
    KalmanCV     kf;         /* 표적 위치·속도 상태 추정(belief 의 수치 기반) */
    LiveObs      live;       /* liveness 관측(교차모달 최종 판별) */
    StaleTrack   stale[FW_N_SENSOR];  /* 센서 freeze 추적(FDIR stale 검출) */
    int          plan_phase; /* 현재 임무 단계(planner; PlanPhase 값) */
    int          plan_ticks; /* 현재 단계 경과 스텝(dwell 계수) */
    const PolicySpec *spec;  /* 이 belief 를 모는 도메인 정책 프로파일(기본 FW_PROFILE_SAR) */
} Blackboard;

void        fw_bb_init(Blackboard *bb);       /* 건강 1, 나머지 0 으로 초기화 */
uint32_t    fw_cfg_hash(const Config *c);     /* 설정 해시(§10; FNV-1a, 트레이스 스탬프) */
const char *fw_action_name(Action a);
const char *fw_mode_name(Mode m);
const char *fw_safety_name(SafetyState s);

#endif /* FW_BLACKBOARD_H */
