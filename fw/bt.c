/* bt.c — 최소 BT 실행(재귀). 노드 수가 작아(≤32) 스택 깊이 안전. */
#include "bt.h"

void fw_bt_reset(BtTree *t)
{
    t->count = 0; t->root = -1; t->chosen = ACT_NONE;
}

int fw_bt_add(BtTree *t, BtType type, BtCond cond, Action act)
{
    int id;
    if (t->count >= BT_MAX_NODES) return -1;
    id = t->count++;
    t->node[id].type = type;
    t->node[id].cond = cond;
    t->node[id].act = act;
    t->node[id].nchild = 0;
    if (t->root < 0) t->root = id;   /* 처음 추가한 노드가 root */
    return id;
}

void fw_bt_child(BtTree *t, int parent, int child)
{
    BtNode *p = &t->node[parent];
    if (parent < 0 || child < 0) return;
    if (p->nchild >= BT_MAX_CHILD) return;
    p->child[p->nchild++] = child;
}

static BtStatus tick_node(BtTree *t, int id, const Blackboard *bb)
{
    BtNode *n = &t->node[id];
    int i;
    switch (n->type) {
        case BT_CONDITION:
            return (n->cond && n->cond(bb)) ? BT_SUCCESS : BT_FAILURE;
        case BT_ACTION:
            t->chosen = n->act;
            return BT_SUCCESS;
        case BT_SELECTOR:
            for (i = 0; i < n->nchild; i++) {
                BtStatus s = tick_node(t, n->child[i], bb);
                if (s != BT_FAILURE) return s;   /* 첫 SUCCESS/RUNNING */
            }
            return BT_FAILURE;
        case BT_SEQUENCE:
            for (i = 0; i < n->nchild; i++) {
                BtStatus s = tick_node(t, n->child[i], bb);
                if (s != BT_SUCCESS) return s;   /* 첫 FAILURE/RUNNING */
            }
            return BT_SUCCESS;
        default:
            return BT_FAILURE;
    }
}

BtStatus fw_bt_tick(BtTree *t, const Blackboard *bb)
{
    t->chosen = ACT_NONE;
    if (t->root < 0) return BT_FAILURE;
    return tick_node(t, t->root, bb);
}
