#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selective-SSM 센서 선택기 — mamba_selective 의 **같은 S6 코어**를 (d_in→d_out) 로 일반화.

thesis 복귀: 손 규칙이 아니라 **selective state-space model(Mamba S6)**이 관측 시퀀스를 읽어
센서 선택을 낸다. Δ,B,C 가 입력의존 → Abar=exp(Δ·A) 의 exp 가 다시 등장(ssm/ exp_unit 로 감).
순수 numpy + 수동 BPTT. 출력은 시그모이드(센서 결정 확률) + BCE 손실.

이것은 sar 검증환경으로 **학습**되는 정책이다(관측만 입력, truth 는 학습 라벨에만 — 배포 시 안 씀).
"""
from __future__ import annotations
import math
import numpy as np


def _softplus(u):
    return np.log1p(np.exp(-np.abs(u))) + np.maximum(u, 0)


def _dsoftplus(u):
    return 1.0 / (1.0 + np.exp(-u))


def _silu(u):
    return u / (1.0 + np.exp(-u))


def _dsilu(u):
    s = 1.0 / (1.0 + np.exp(-u))
    return s * (1 + u * (1 - s))


def _sigmoid(u):
    return 1.0 / (1.0 + np.exp(-np.clip(u, -30, 30)))


def init(d_in, d_out=1, M=8, seed=11):
    rng = np.random.default_rng(seed)
    return {"W_in": rng.normal(0, 0.5, (M, d_in)), "W_D": rng.normal(0, 0.3, (M, d_in)), "bD": np.zeros(M),
            "W_B": rng.normal(0, 0.4, (M, d_in)), "W_C": rng.normal(0, 0.5, (M, d_in)),
            "A_raw": rng.uniform(-3.5, -0.5, M),
            "W_g": rng.normal(0, 0.5, (M, d_in)), "bg": np.zeros(M),
            "W_out": rng.normal(0, 0.3, (d_out, M)), "D": rng.normal(0, 0.1, (d_out, d_in))}


def forward(P, O):
    """O:(B,T,d_in) → logits:(B,T,d_out) + cache. 대각 selective SSM(입력의존 Δ,B,C)."""
    B, T, _ = O.shape
    M = P["A_raw"].shape[0]
    A = -_softplus(P["A_raw"])
    X = O @ P["W_in"].T
    pD = O @ P["W_D"].T + P["bD"]; Dt = _softplus(pD)
    Bt = O @ P["W_B"].T
    Ct = O @ P["W_C"].T
    U = O @ P["W_g"].T + P["bg"]; G = _silu(U)
    Abar = np.exp(Dt * A)
    Bbar = Dt * Bt
    H = np.zeros((B, T, M)); h = np.zeros((B, M))
    for t in range(T):
        h = Abar[:, t, :] * h + Bbar[:, t, :] * X[:, t, :]
        H[:, t, :] = h
    Y = Ct * H; Z = Y * G
    logits = Z @ P["W_out"].T + O @ P["D"].T
    return logits, dict(O=O, A=A, X=X, pD=pD, Dt=Dt, Bt=Bt, Ct=Ct, U=U, G=G, Abar=Abar, Bbar=Bbar, H=H, Y=Y, Z=Z)


def backward(P, c, dlogits):
    O, A, X, pD, Dt, Bt, Ct, U, G, Abar, Bbar, H, Y, Z = (c[k] for k in
        ("O", "A", "X", "pD", "Dt", "Bt", "Ct", "U", "G", "Abar", "Bbar", "H", "Y", "Z"))
    B, T, _ = O.shape; M = A.shape[0]
    g = {k: np.zeros_like(v) for k, v in P.items()}
    g["W_out"] += np.einsum("btk,btm->km", dlogits, Z)
    g["D"] += np.einsum("btk,btj->kj", dlogits, O)
    dZ = dlogits @ P["W_out"]
    dY = dZ * G; dG = dZ * Y
    dU = dG * _dsilu(U); g["W_g"] += np.einsum("btm,btj->mj", dU, O); g["bg"] += dU.sum((0, 1))
    dCt = dY * H
    dH = dY * Ct
    dAbar = np.zeros((B, T, M)); dBbar = np.zeros((B, T, M)); dX = np.zeros((B, T, M))
    dh_next = np.zeros((B, M))
    for t in range(T - 1, -1, -1):
        dh = dH[:, t, :] + dh_next
        h_prev = H[:, t - 1, :] if t > 0 else np.zeros((B, M))
        dAbar[:, t, :] = dh * h_prev
        dBbar[:, t, :] = dh * X[:, t, :]
        dX[:, t, :] = dh * Bbar[:, t, :]
        dh_next = dh * Abar[:, t, :]
    dDt = dAbar * Abar * A
    dA = np.sum(dAbar * Abar * Dt, axis=(0, 1))
    dDt += dBbar * Bt
    dBt = dBbar * Dt
    dpD = dDt * _dsoftplus(pD)
    g["W_D"] += np.einsum("btm,btj->mj", dpD, O); g["bD"] += dpD.sum((0, 1))
    g["W_B"] += np.einsum("btm,btj->mj", dBt, O)
    g["W_C"] += np.einsum("btm,btj->mj", dCt, O)
    g["W_in"] += np.einsum("btm,btj->mj", dX, O)
    g["A_raw"] += dA * (-_dsoftplus(P["A_raw"]))
    return g


def predict(P, seq):
    """단일 시퀀스 seq:(T,d_in) → 확률:(T,d_out)."""
    logits, _ = forward(P, seq[None, :, :])
    return _sigmoid(logits)[0]


def forward_step(P, o, h):
    """스트리밍 단일스텝(상태 h 이월) — 롤아웃/배포 추론. 반환 (logits(d_out,), h_new(M,)).
    이게 곧 bare-metal 추론 커널의 한 스텝(ssm/fw/ssm.c 와 동형): 힙 없음, 결정적."""
    A = -_softplus(P["A_raw"])
    x = P["W_in"] @ o
    Dt = _softplus(P["W_D"] @ o + P["bD"]); Bt = P["W_B"] @ o; Ct = P["W_C"] @ o
    G = _silu(P["W_g"] @ o + P["bg"])
    Abar = np.exp(Dt * A); Bbar = Dt * Bt
    h = Abar * h + Bbar * x
    z = (Ct * h) * G
    return P["W_out"] @ z + P["D"] @ o, h


def state_dim(P):
    return P["A_raw"].shape[0]


def _softmax(logits):
    z = logits - logits.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / (e.sum(axis=-1, keepdims=True) + 1e-9)


def predict_class(P, seq):
    """단일 시퀀스 → 스텝별 클래스 인덱스:(T,). d_out=클래스 수(softmax)."""
    logits, _ = forward(P, seq[None, :, :])
    return np.argmax(logits[0], axis=-1)


def _macro_recall(P, O, Yidx, n_class):
    """클래스 불균형에 강한 지표: 각 클래스 recall 의 평균(다수클래스 붕괴를 벌한다). + raw acc."""
    logits, _ = forward(P, O); pred = np.argmax(logits, -1)
    recs = []
    for c in range(n_class):
        mask = (Yidx == c)
        if mask.sum() > 0:
            recs.append(float((pred[mask] == c).mean()))
    return (float(np.mean(recs)) if recs else 0.0), float((pred == Yidx).mean())


# 학습 노브(요청): AdamW(decoupled weight decay) · gradient clipping · cosine LR schedule + warmup ·
# class weight(불균형 교정). 전부 순수 numpy. 코어는 selective SSM(상태재귀) — MLP 아님.
_DECAY_KEYS = ("W_in", "W_D", "W_B", "W_C", "W_g", "W_out", "D")   # 행렬만 weight decay(bias·A_raw 제외)


def train_ce(O, Yidx, n_class, epochs=40, batch=16, lr=0.05, M=8, seed=11, val=None, log=None, quiet=False,
             weight_decay=1e-2, grad_clip=1.0, warmup_frac=0.1, lr_min_frac=0.1, class_weight=True):
    """다중클래스 Mamba(softmax CE) — AdamW·grad clip·cosine+warmup·class weight.

    O:(B,T,d_in), Yidx:(B,T) int. **MLP 아님**: 코어는 상태 재귀(selective scan, forward 의 h=Ā·h+B̄·x)."""
    d_in = O.shape[2]; B = O.shape[0]
    P = init(d_in, n_class, M, seed)
    onehot = np.eye(n_class)[Yidx.astype(int)]
    # class weight: 희소 클래스를 키워 다수(RGB) 붕괴를 막는다. w_c = median(freq)/freq_c, [0.2,8] 클립.
    freq = np.array([max(1, int((Yidx == c).sum())) for c in range(n_class)], dtype=float)
    cw = np.clip(np.median(freq) / freq, 0.2, 8.0) if class_weight else np.ones(n_class)
    m = {k: np.zeros_like(v) for k, v in P.items()}; v = {k: np.zeros_like(v) for k, v in P.items()}
    b1, b2, eps = 0.9, 0.999, 1e-8
    rng = np.random.default_rng(seed)
    steps_per_ep = max(1, (B + batch - 1) // batch); total = epochs * steps_per_ep
    warmup = max(1, int(warmup_frac * total)); step = 0
    def lr_at(t):
        if t < warmup:
            return lr * t / warmup                                   # 선형 warmup
        p = (t - warmup) / max(1, total - warmup)                    # cosine decay → lr_min
        return lr * (lr_min_frac + (1 - lr_min_frac) * 0.5 * (1 + math.cos(math.pi * p)))
    for ep in range(1, epochs + 1):
        idx = rng.permutation(B)
        for s in range(0, B, batch):
            mb = idx[s:s + batch]; Om = O[mb]; Ym = onehot[mb]; Yi = Yidx[mb]
            logits, c = forward(P, Om); sm = _softmax(logits)
            w = cw[Yi][:, :, None]                                   # 샘플별 class weight
            dlogits = w * (sm - Ym) / (Om.shape[0] * Om.shape[1])
            g = backward(P, c, dlogits); step += 1
            gn = math.sqrt(sum(float(np.sum(gg * gg)) for gg in g.values())) + 1e-12   # global grad norm
            scale = min(1.0, grad_clip / gn) if grad_clip else 1.0   # gradient clipping
            cur = lr_at(step)
            for k in P:
                gk = g[k] * scale
                m[k] = b1 * m[k] + (1 - b1) * gk; v[k] = b2 * v[k] + (1 - b2) * gk ** 2
                upd = (m[k] / (1 - b1 ** step)) / (np.sqrt(v[k] / (1 - b2 ** step)) + eps)
                P[k] -= cur * upd
                if weight_decay and k in _DECAY_KEYS:               # AdamW: decoupled weight decay
                    P[k] -= cur * weight_decay * P[k]
        if not quiet and (ep % max(1, epochs // 8) == 0 or ep == 1):
            mr, acc = _macro_recall(P, O, Yidx, n_class)
            msg = "  epoch %3d  lr %.4f  macro_recall %.3f  acc %.3f" % (ep, lr_at(step), mr, acc)
            if val is not None:
                vmr, vacc = _macro_recall(P, val[0], val[1], n_class); msg += "  val_macroR %.3f  val_acc %.3f" % (vmr, vacc)
            (log or print)(msg)
    return P


def _ce_acc(P, O, Yidx):
    logits, _ = forward(P, O); sm = _softmax(logits)
    loss = float(-np.mean(np.log(sm[np.eye(sm.shape[-1])[Yidx.astype(int)] > 0.5] + 1e-9)))
    return loss, float(np.argmax(logits, -1).__eq__(Yidx).mean())


def predict_reg(P, seq):
    """ReAct 'reason': 단일 시퀀스 → 스텝별 **유틸리티 벡터 예측**:(T,d_out) (선형 출력, sigmoid/softmax 없음)."""
    logits, _ = forward(P, seq[None, :, :])
    return logits[0]


def train_mse(O, Yvec, epochs=60, batch=16, lr=0.05, M=8, seed=11, val=None, log=None, quiet=False,
              weight_decay=1e-2, grad_clip=1.0, warmup_frac=0.1, lr_min_frac=0.1):
    """ReAct 유틸리티 회귀(MSE) — Mamba 가 센서별 D̂(a,s) 를 예측(=reason). 행동은 정책이 argmax(D̂−λC−μE).
    AdamW·grad clip·cosine+warmup. O:(B,T,d_in), Yvec:(B,T,d_out) 연속 타깃. **MLP 아님**(상태재귀)."""
    d_in = O.shape[2]; d_out = Yvec.shape[2]; B = O.shape[0]
    P = init(d_in, d_out, M, seed)
    m = {k: np.zeros_like(v) for k, v in P.items()}; v = {k: np.zeros_like(v) for k, v in P.items()}
    b1, b2, eps = 0.9, 0.999, 1e-8
    rng = np.random.default_rng(seed)
    steps_per_ep = max(1, (B + batch - 1) // batch); total = epochs * steps_per_ep
    warmup = max(1, int(warmup_frac * total)); step = 0
    def lr_at(t):
        if t < warmup:
            return lr * t / warmup
        p = (t - warmup) / max(1, total - warmup)
        return lr * (lr_min_frac + (1 - lr_min_frac) * 0.5 * (1 + math.cos(math.pi * p)))
    for ep in range(1, epochs + 1):
        idx = rng.permutation(B)
        for s in range(0, B, batch):
            mb = idx[s:s + batch]; Om = O[mb]; Ym = Yvec[mb]
            logits, c = forward(P, Om)
            dlogits = 2.0 * (logits - Ym) / (Om.shape[0] * Om.shape[1] * d_out)
            g = backward(P, c, dlogits); step += 1
            gn = math.sqrt(sum(float(np.sum(gg * gg)) for gg in g.values())) + 1e-12
            scale = min(1.0, grad_clip / gn) if grad_clip else 1.0; cur = lr_at(step)
            for k in P:
                gk = g[k] * scale
                m[k] = b1 * m[k] + (1 - b1) * gk; v[k] = b2 * v[k] + (1 - b2) * gk ** 2
                P[k] -= cur * (m[k] / (1 - b1 ** step)) / (np.sqrt(v[k] / (1 - b2 ** step)) + eps)
                if weight_decay and k in _DECAY_KEYS:
                    P[k] -= cur * weight_decay * P[k]
        if not quiet and (ep % max(1, epochs // 8) == 0 or ep == 1):
            tr = float(np.mean((forward(P, O)[0] - Yvec) ** 2))
            msg = "  epoch %3d  lr %.4f  MSE %.4f" % (ep, lr_at(step), tr)
            if val is not None:
                msg += "  val_MSE %.4f" % float(np.mean((forward(P, val[0])[0] - val[1]) ** 2))
            (log or print)(msg)
    return P


def train(O, Yt, iters=400, lr=0.03, M=8, seed=11, val=None, log=None):
    """O:(B,T,d_in), Yt:(B,T,d_out)∈{0,1}. BCE 로 학습. Adam. 로그(loss·train acc·val acc)."""
    d_in = O.shape[2]; d_out = Yt.shape[2]
    P = init(d_in, d_out, M, seed)
    m = {k: np.zeros_like(v) for k, v in P.items()}; v = {k: np.zeros_like(v) for k, v in P.items()}
    b1, b2, eps = 0.9, 0.999, 1e-8; N = O.shape[0] * O.shape[1] * d_out
    hist = []
    for it in range(1, iters + 1):
        logits, c = forward(P, O)
        p = _sigmoid(logits)
        loss = float(-np.mean(Yt * np.log(p + 1e-9) + (1 - Yt) * np.log(1 - p + 1e-9)))
        dlogits = (p - Yt) / N
        g = backward(P, c, dlogits)
        for k in P:
            m[k] = b1 * m[k] + (1 - b1) * g[k]; v[k] = b2 * v[k] + (1 - b2) * g[k] ** 2
            P[k] -= lr * (m[k] / (1 - b1 ** it)) / (np.sqrt(v[k] / (1 - b2 ** it)) + eps)
        if it % 50 == 0 or it == 1:
            tr_acc = float(np.mean((p > 0.5) == (Yt > 0.5)))
            msg = "  iter %4d  BCE %.4f  train_acc %.3f" % (it, loss, tr_acc)
            if val is not None:
                vp = _sigmoid(forward(P, val[0])[0])
                va = float(np.mean((vp > 0.5) == (val[1] > 0.5)))
                msg += "  val_acc %.3f" % va
            hist.append(msg)
            if log is not None:
                log(msg)
            else:
                print(msg)
    return P, hist


if __name__ == "__main__":
    # 자기점검: 합성 시퀀스(가시 낮으면 SAR=1 라벨)에서 학습되는지
    rng = np.random.default_rng(0)
    B, T = 64, 20
    vis = rng.random((B, T, 1))
    O = np.concatenate([vis, rng.random((B, T, 3))], axis=2)   # d_in=4, 첫 채널=vis
    Y = (vis < 0.4).astype(float)                              # 가시 낮으면 SAR
    P, hist = train(O, Y, iters=200)
    p = predict(P, O[0])
    print("자기점검 완료 — 마지막:", hist[-1])
