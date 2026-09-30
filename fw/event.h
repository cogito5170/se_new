/* event.h — 고정 크기 링 이벤트 큐(malloc 없음, 인터럽트/폴링 겸용 패턴).
 *
 * FDIR·센서고장·모드전환 같은 비동기 사건을 결정 executive 가 폴링으로 소비한다.
 * 오버플로는 조용히 버리지 않고 dropped 로 센다(사후 분석·정직).
 */
#ifndef FW_EVENT_H
#define FW_EVENT_H

#include <stdint.h>
#include <stdbool.h>

typedef enum {
    EV_NONE = 0,
    EV_SENSOR_FAIL,     /* arg = SensorId */
    EV_SENSOR_RECOVER,
    EV_COLLISION,
    EV_BATTERY_LOW,
    EV_TARGET_CONFIRMED,
    EV_MODE_CHANGE,
    EV_ACTUATOR_FAIL,    /* 액추에이터 사용 불가 → 안전 정지 */
    EV_SENSOR_STALE      /* arg = SensorId: 값이 얼어붙은(frozen) 센서 — 움직이는 다른 채널 대비 검출 */
} EventType;

typedef struct { EventType type; int32_t arg; uint32_t t; } Event;

#define FW_EVQ_CAP 16   /* 2의 거듭제곱 아니어도 됨(모듈로 인덱스) */

typedef struct {
    Event    buf[FW_EVQ_CAP];
    int      head, tail, size;
    uint32_t dropped;   /* 가득 차서 버린 이벤트 수(정직 지표) */
} EventQueue;

void fw_evq_init(EventQueue *q);
bool fw_evq_push(EventQueue *q, EventType type, int32_t arg, uint32_t t);  /* false=꽉참(dropped++) */
bool fw_evq_pop(EventQueue *q, Event *out);                                /* false=빔 */

#endif /* FW_EVENT_H */
