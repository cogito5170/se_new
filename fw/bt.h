/* bt.h — 최소 Behavior Tree(정적, malloc 없음).
 *
 * 노드는 배열에 담기고(자식은 인덱스), tick 은 재귀 없이 스택으로 순회한다. leaf 는
 * CONDITION(블랙보드 술어)과 ACTION(고를 행동). SELECTOR 는 첫 SUCCESS 까지, SEQUENCE 는
 * 첫 FAILURE 까지. ACTION 이 성공하면 tree->chosen 에 그 행동을 남긴다.
 *
 * BT 를 쓰는 이유(선행조사): condition/action 구조가 명시적이고 modular·hierarchical 이라,
 * 손 if 사슬을 무한히 늘리지 않고 우선순위를 selector 순서로 표현한다.
 */
#ifndef FW_BT_H
#define FW_BT_H

#include "blackboard.h"

typedef enum { BT_SEQUENCE = 0, BT_SELECTOR, BT_CONDITION, BT_ACTION } BtType;
typedef enum { BT_FAILURE = 0, BT_SUCCESS, BT_RUNNING } BtStatus;

typedef bool (*BtCond)(const Blackboard *bb);

#define BT_MAX_NODES 32
#define BT_MAX_CHILD 8

typedef struct {
    BtType type;
    BtCond cond;                 /* BT_CONDITION 용 */
    Action act;                  /* BT_ACTION 용 */
    int    child[BT_MAX_CHILD];
    int    nchild;
} BtNode;

typedef struct {
    BtNode node[BT_MAX_NODES];
    int    count;
    int    root;
    Action chosen;               /* tick 후 고른 행동(없으면 ACT_NONE) */
} BtTree;

void     fw_bt_reset(BtTree *t);
int      fw_bt_add(BtTree *t, BtType type, BtCond cond, Action act);  /* 노드 id 반환 */
void     fw_bt_child(BtTree *t, int parent, int child);
BtStatus fw_bt_tick(BtTree *t, const Blackboard *bb);   /* root 부터 tick, chosen 갱신 */

#endif /* FW_BT_H */
