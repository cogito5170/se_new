/* event.c — 링 큐. size 로 빈/꽉 판정(head==tail 모호성 제거). */
#include "event.h"

void fw_evq_init(EventQueue *q)
{
    q->head = 0; q->tail = 0; q->size = 0; q->dropped = 0;
}

bool fw_evq_push(EventQueue *q, EventType type, int32_t arg, uint32_t t)
{
    if (q->size >= FW_EVQ_CAP) { q->dropped += 1; return false; }
    q->buf[q->tail].type = type;
    q->buf[q->tail].arg = arg;
    q->buf[q->tail].t = t;
    q->tail = (q->tail + 1) % FW_EVQ_CAP;
    q->size += 1;
    return true;
}

bool fw_evq_pop(EventQueue *q, Event *out)
{
    if (q->size <= 0) return false;
    *out = q->buf[q->head];
    q->head = (q->head + 1) % FW_EVQ_CAP;
    q->size -= 1;
    return true;
}
