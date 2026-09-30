#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""학습·비교 — 5센서 cost-aware Mamba(selective SSM, **MLP 아님**)를 sar 검증환경으로 학습·비교.

과접합 방지: 학습은 훈련지역 random seed, 비교는 완전히 다른 지역(held-out). cost 규율은 라벨에
심는다(oracle_label_cost = 탐지되는 센서 중 가장 싼 것; 아무도 안 되면 RGB → 비싼 센서 과다사용 금지).

HP 스윕: **epoch · batch size · learning rate**(+상태차원 M) 를 train/val 로 고르고, 최적으로
최종 학습 후 가중치 저장. 모델 코어는 상태 재귀(selective scan)라 MLP 가 아니다.
"""
from __future__ import annotations
import os
import sys
import datetime
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import reference as _ref
import evaluator as _eval
import policies as _pol
from ctrl.model import mamba_selector as _ms

TRAIN_LOC = (37.0966, 128.9456)     # 태백산(학습)
TEST_LOC = (35.3386, 127.7300)      # 지리산(검증 — 완전히 다른 곳)
NC = len(_pol.SENSORS_5)            # 클래스 수(=5센서)


def _dem_for(loc, patch_half=3000.0):
    try:
        import terrain
        dem, _, _ = terrain.fetch_dem(loc[0], loc[1], patch_half, zoom=13); return dem, "real"
    except Exception:                                       # noqa: BLE001
        rng = np.random.default_rng(int(abs(loc[0]) * 1000))
        xx, yy = np.meshgrid(np.linspace(0, 1, 64), np.linspace(0, 1, 64))
        return 700 + 300 * (np.sin(3 * xx) * np.cos(2 * yy) + xx) + 20 * rng.standard_normal((64, 64)), "synthetic"


def _rand_scenario(loc, seed, rng):
    return dict(seed=int(seed), lat=loc[0], lon=loc[1], V=float(10 ** rng.uniform(1.6, 4.2)),
                illum=float(10 ** rng.uniform(0.5, 4.3)), agl=120.0,
                sensors=["RGB", "SAR", "IMU", "Thermal", "LiDAR", "Audio"],
                n_target=int(rng.integers(1, 3)),
                targets_spec=[dict(bearing_deg=float(rng.uniform(0, 360)),
                                   range_m=float(rng.uniform(120, 260)),
                                   canopy=bool(rng.random() < 0.4)) for _ in range(int(rng.integers(1, 3)))])


def gen_dataset_multi(loc, dem, seeds, T=32):
    """OraclePolicy(cost-aware)로 5센서 학습 데이터. **에피소드는 seed 가 완전히 결정**(재현·분리 가능).
    seeds: 명시적 시드 목록. 서로 다른 seed = 서로 다른 시나리오(표적·조건). 학습/검증 시드는 분리."""
    seeds = list(seeds); n_ep = len(seeds)
    O = np.zeros((n_ep, T, _pol.D_IN_MULTI)); Y = np.zeros((n_ep, T), dtype=int)
    Yvec = np.zeros((n_ep, T, NC))                          # ReAct 회귀 타깃(센서별 유틸리티 D)
    for e, seed in enumerate(seeds):
        rng = np.random.default_rng(int(seed))              # 에피소드 RNG = 그 seed (완전 결정)
        scn = _rand_scenario(loc, int(seed), rng)
        # **조건 기반 proactive 라벨/유틸리티**(에피소드 상수): truth 아는 oracle. detection event 아님.
        canopy = any(t.get("canopy") for t in scn["targets_spec"])
        lab = _pol.oracle_label_condition(scn["V"], scn["illum"], canopy)
        D = _pol.sensor_utilities(scn["V"], scn["illum"], canopy)
        dvec = np.array([D[s] for s in _pol.SENSORS_5])
        ref = _ref.Reference(scn, dem=dem); pol = _pol.BaselinePolicy()   # 탐색 항법(라벨과 무관)
        for t in range(T):
            obs = ref.observe(pol.veh)
            O[e, t, :] = _pol.feature_multi({k: v for k, v in obs.items() if k != "truth"})
            Y[e, t] = lab; Yvec[e, t, :] = dvec
            pol.step({k: v for k, v in obs.items() if k != "truth"})
    return O, Y, Yvec


def run_policy(make_policy, scn, dem, budget=32):
    ref = _ref.Reference(scn, dem=dem); pol = make_policy(); truth = ref.truth(); log = []
    use = {}; cost_acc = 0.0
    for _ in range(budget):
        obs = ref.observe(pol.veh)
        out = pol.step({k: v for k, v in obs.items() if k != "truth"})
        log.append(out)
        tel = out["telemetry"]
        s = tel.get("primary_sensor", "RGB"); use[s] = use.get(s, 0) + 1
        # 비용: 투표가 확인집합을 함께 켰으면(consulted) 그 전체를, 아니면 primary 하나만 계상(정직).
        cons = tel.get("consulted")
        cost_acc += sum(_pol.COST_NORM.get(x, 0) for x in cons) if cons else _pol.COST_NORM.get(s, 0)
        if out.get("detections"):
            use["det_" + s] = use.get("det_" + s, 0) + len(out["detections"])
    m = _eval.evaluate(truth, log)
    tot = max(1, budget); m["cost"] = cost_acc / tot      # 평균 센서비용/스텝(cost 규율 지표)
    m["use"] = use
    return m


def compare(loc, dem, W_cls, W_react, W_rl=None, n_ep=12, budget=32, master_seed=9999):
    rng = np.random.default_rng(master_seed)
    cand = {"Baseline(RGB전용)": lambda: _pol.BaselinePolicy(),
            "NASA-rule(5센서)": lambda: _pol.NASARulePolicy(),
            "Mamba-cls(분류)": lambda: _pol.MambaSensorPolicy(W_cls, _ms),
            "Mamba-ReAct(유틸)": lambda: _pol.ReActMambaPolicy(W_react, _ms)}
    if W_rl is not None:
        cand["Mamba-RL(보상)"] = lambda: _pol.MambaSensorPolicy(W_rl, _ms)
        # RL 위에 센서융합 확인층 — 오경보↓ 목표(대가: 확인집합 함께 켜 비용↑, 합의요구로 탐지↓ 가능)
        cand["RL+HardVote(k2)"] = lambda: _pol.VotingPolicy(_pol.MambaSensorPolicy(W_rl, _ms), mode="hard", k=2)
        cand["RL+SoftVote(t0.9)"] = lambda: _pol.VotingPolicy(_pol.MambaSensorPolicy(W_rl, _ms), mode="soft", tau=0.9)
    agg = {k: [] for k in cand}
    for _ in range(n_ep):
        scn = _rand_scenario(loc, rng.integers(1, 10_000_000), rng)
        for name, mk in cand.items():
            agg[name].append(run_policy(mk, scn, dem, budget))
    out = {}
    for name, rows in agg.items():
        s = _eval.summarize(rows)
        u = {k: sum(r["use"].get(k, 0) for r in rows) for k in _pol.SENSORS_5}
        ud = {k: sum(r["use"].get("det_" + k, 0) for r in rows) for k in _pol.SENSORS_5}
        tot = max(1, sum(u.values()))
        s["pct"] = {k: 100.0 * u[k] / tot for k in _pol.SENSORS_5}; s["use_det"] = ud
        s["cost"] = float(np.mean([r["cost"] for r in rows]))
        out[name] = s
    return out


def rollout(P, scn, dem, T=32, greedy=False, rng=None):
    """현재 정책으로 한 에피소드 시뮬 롤아웃(on-policy). 스텝별 sensor 를 샘플/argmax 로 고르고
    reference 로 관측·claim. 보상 r_t = (새 탐지 수) − λ·C − μ·E. 반환 (feats(T,3), acts(T,), rews(T,)).

    (위치오차·오경보 패널티는 실험 뒤 되돌림 — 사용자 요청. 보상은 탐지수−비용 단순형으로 복귀.)"""
    rng = rng or np.random.default_rng(0)
    ref = _ref.Reference(scn, dem=dem); pol = _pol.ForcedSensorPolicy()
    M = _ms.state_dim(P); h = np.zeros(M)
    feats = np.zeros((T, _pol.D_IN_MULTI)); acts = np.zeros(T, dtype=int); rews = np.zeros(T)
    for t in range(T):
        obs = {k: v for k, v in ref.observe(pol.veh).items() if k != "truth"}
        f = _pol.feature_multi(obs); feats[t] = f
        logits, h = _ms.forward_step(P, f, h)
        p = _ms._softmax(logits[None])[0]
        a = int(np.argmax(p)) if greedy else int(rng.choice(NC, p=p))
        acts[t] = a; s = _pol.SENSORS_5[a]; pol.forced = s
        out = pol.step(obs)
        n_det = len(out.get("detections", []))
        rews[t] = n_det - _pol.LAM_COST * _pol.COST_NORM[s] - _pol.MU_ENERGY * _pol.ENERGY_NORM[s]
    return feats, acts, rews


def train_reinforce(loc, dem, seeds, T=32, epochs=40, batch=16, lr=0.03, M=8, gamma=0.9, seed=7,
                    val_seeds=None, log=None, grad_clip=1.0, warmup_frac=0.1, lr_min_frac=0.1):
    """**Sequential reward RL(REINFORCE)** — oracle 모방이 아니라 시뮬 보상(누적 U−cost)을 최대화.
    max_π E[Σ_t r_t], r_t=탐지−λC−μE. 온폴리시: 매 에폭 현재 정책으로 롤아웃→return→정책경사.
    AdamW·grad clip·cosine+warmup. 정책=Mamba(상태재귀) softmax."""
    import math as _m
    P = _ms.init(_pol.D_IN_MULTI, NC, M, seed)
    mom = {k: np.zeros_like(v) for k, v in P.items()}; vel = {k: np.zeros_like(v) for k, v in P.items()}
    b1, b2, eps = 0.9, 0.999, 1e-8
    rng = np.random.default_rng(seed); seeds = list(seeds)
    steps_per_ep = max(1, (len(seeds) + batch - 1) // batch); total = epochs * steps_per_ep; warmup = max(1, int(warmup_frac * total)); gstep = 0
    def lr_at(t):
        if t < warmup:
            return lr * t / warmup
        pp = (t - warmup) / max(1, total - warmup)
        return lr * (lr_min_frac + (1 - lr_min_frac) * 0.5 * (1 + _m.cos(_m.pi * pp)))
    for ep in range(1, epochs + 1):
        order = rng.permutation(len(seeds)); ep_ret = []
        for s0 in range(0, len(seeds), batch):
            mb = [seeds[i] for i in order[s0:s0 + batch]]; B = len(mb)
            O = np.zeros((B, T, _pol.D_IN_MULTI)); A = np.zeros((B, T), dtype=int); G = np.zeros((B, T))
            for bi, sd in enumerate(mb):
                r = np.random.default_rng(int(sd)); scn = _rand_scenario(loc, int(sd), r)
                f, a, rew = rollout(P, scn, dem, T, greedy=False, rng=r)
                O[bi] = f; A[bi] = a
                g = 0.0
                for t in range(T - 1, -1, -1):          # 할인 누적보상(return)
                    g = rew[t] + gamma * g; G[bi, t] = g
                ep_ret.append(float(rew.sum()))
            adv = G - G.mean(axis=0, keepdims=True)      # per-timestep 베이스라인(분산↓)
            logits, c = _ms.forward(P, O); sm = _ms._softmax(logits)
            onehot = np.eye(NC)[A]
            dlogits = adv[:, :, None] * (sm - onehot) / (B * T)   # REINFORCE: ∇(−Σ A logπ)
            gr = _ms.backward(P, c, dlogits); gstep += 1
            gn = _m.sqrt(sum(float(np.sum(x * x)) for x in gr.values())) + 1e-12
            scale = min(1.0, grad_clip / gn); cur = lr_at(gstep)
            for k in P:
                gk = gr[k] * scale
                mom[k] = b1 * mom[k] + (1 - b1) * gk; vel[k] = b2 * vel[k] + (1 - b2) * gk ** 2
                P[k] -= cur * (mom[k] / (1 - b1 ** gstep)) / (np.sqrt(vel[k] / (1 - b2 ** gstep)) + eps)
        if log and (ep % max(1, epochs // 8) == 0 or ep == 1):
            msg = "  epoch %3d  lr %.4f  train_return %.3f" % (ep, lr_at(gstep), float(np.mean(ep_ret)))
            if val_seeds is not None:
                vr = [rollout(P, _rand_scenario(loc, int(sd), np.random.default_rng(int(sd))), dem, T, greedy=True,
                              rng=np.random.default_rng(int(sd)))[2].sum() for sd in val_seeds]
                msg += "  val_return(greedy) %.3f" % float(np.mean(vr))
            log(msg)
    return P


def sweep(O, Y, val, log, grid=None):
    """HP 스윕: epoch·batch·lr·M 을 val_acc 로 고른다. 각 후보를 로그."""
    if grid is None:
        grid = [dict(epochs=e, batch=b, lr=l, M=m)
                for e in (30, 60) for b in (8, 16) for l in (0.03, 0.08) for m in (8, 12)]
    best = None
    log("  %-34s val_macroR  val_acc" % "HP(epoch,batch,lr,M)")
    for hp in grid:
        W = _ms.train_ce(O, Y, NC, epochs=hp["epochs"], batch=hp["batch"], lr=hp["lr"], M=hp["M"], seed=7, quiet=True)
        mr, acc = _ms._macro_recall(W, val[0], val[1], NC)      # 불균형에 강한 지표로 선택
        log("  e=%-3d b=%-3d lr=%-4.2f M=%-3d            %.3f      %.3f" % (hp["epochs"], hp["batch"], hp["lr"], hp["M"], mr, acc))
        if best is None or mr > best[0]:
            best = (mr, hp, W)
    return best


def demo(max_seeds=160, T=32, n_test=14):
    REPO = os.path.dirname(os.path.dirname(HERE)); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S"); lines = []
    def log(m):
        print(m); lines.append(m)
    log("== 5센서 cost-aware Mamba(selective SSM, MLP 아님) 학습·비교 ==")
    tr_dem, tr_src = _dem_for(TRAIN_LOC); te_dem, te_src = _dem_for(TEST_LOC)
    log("학습 태백산 DEM=%s%s · 검증 지리산 DEM=%s%s (완전히 다른 곳)" % (tr_dem.shape, tr_src, te_dem.shape, te_src))
    # ── 학습/검증 시드 **완전 분리**(누수 방지). 검증은 학습에 없는 시드에서만. ──
    TRAIN_SEEDS = list(range(1, max_seeds + 1))
    VAL_SEEDS = list(range(900001, 900021))                 # 학습 어떤 N 에도 안 들어가는 시드
    assert set(TRAIN_SEEDS).isdisjoint(VAL_SEEDS), "학습/검증 시드가 겹친다"
    log("--- 데이터(seed 가 에피소드를 결정). 학습시드 1..%d · 검증시드 900001..900020 (분리 확인 OK) ---" % max_seeds)
    Oval, Yval, Yvval = gen_dataset_multi(TRAIN_LOC, tr_dem, VAL_SEEDS, T)     # 검증(고정, 분리)
    Ofull, Yfull, Yvfull = gen_dataset_multi(TRAIN_LOC, tr_dem, TRAIN_SEEDS, T)  # 학습 풀(최대)
    dist = {s: int((Yfull == i).sum()) for i, s in enumerate(_pol.SENSORS_5)}
    log("검증 %d · 학습풀 %d · 라벨분포(학습) %s" % (len(VAL_SEEDS), max_seeds, dist))
    log("--- [분류 Mamba] HP 스윕 (epoch·batch·lr·M; AdamW·grad-clip·cosine+warmup·class-weight) → val_macroR ---")
    hp_n = min(96, max_seeds)
    va, hp, _ = sweep(Ofull[:hp_n], Yfull[:hp_n], (Oval, Yval), log)
    log("최적 HP: epoch=%d batch=%d lr=%.2f M=%d (val_macroR %.3f)" % (hp["epochs"], hp["batch"], hp["lr"], hp["M"], va))
    log("--- 랜덤시드 개수 sweep (몇 개면 충분한가; 검증은 분리된 시드 고정) ---")
    log("  N(학습시드) | val_macroR | val_acc")
    for n in [x for x in (24, 48, 96, 160) if x <= max_seeds]:
        Wn = _ms.train_ce(Ofull[:n], Yfull[:n], NC, epochs=hp["epochs"], batch=hp["batch"], lr=hp["lr"], M=hp["M"], seed=7, quiet=True)
        mr, acc = _ms._macro_recall(Wn, Oval, Yval, NC)
        log("  %-11d | %.3f | %.3f" % (n, mr, acc))
    log("--- [분류 Mamba] 최적 HP 로 최종 학습 ---")
    W_cls = _ms.train_ce(Ofull, Yfull, NC, epochs=hp["epochs"], batch=hp["batch"], lr=hp["lr"], M=hp["M"], seed=7, val=(Oval, Yval), log=log)
    log("--- [ReAct Mamba] 유틸리티 회귀 학습(MSE) — reason=D̂ 예측, act=argmax(D̂−λC−μE) ---")
    W_react = _ms.train_mse(Ofull, Yvfull, epochs=hp["epochs"], batch=hp["batch"], lr=hp["lr"], M=hp["M"], seed=7, val=(Oval, Yvval), log=log)
    wpath = os.path.join(os.path.dirname(os.path.dirname(HERE)), "ctrl", "model", "mamba_selector_5sensor.npz")
    np.savez(wpath, **W_cls); log("가중치 저장(분류): %s" % os.path.relpath(wpath, REPO))
    wpath2 = os.path.join(os.path.dirname(os.path.dirname(HERE)), "ctrl", "model", "mamba_react_5sensor.npz")
    np.savez(wpath2, **W_react); log("가중치 저장(ReAct): %s" % os.path.relpath(wpath2, REPO))
    log("--- [RL Mamba] sequential reward REINFORCE (r=탐지수−λC−μE; oracle 모방 아님) ---")
    rl_seeds = TRAIN_SEEDS[:min(64, max_seeds)]                # 롤아웃 비용상 부분집합
    W_rl = train_reinforce(TRAIN_LOC, tr_dem, rl_seeds, T, epochs=25, batch=16, lr=0.03, M=hp["M"],
                           val_seeds=VAL_SEEDS[:8], log=log)
    wpath3 = os.path.join(os.path.dirname(os.path.dirname(HERE)), "ctrl", "model", "mamba_rl_5sensor.npz")
    np.savez(wpath3, **W_rl); log("가중치 저장(RL): %s" % os.path.relpath(wpath3, REPO))
    log("--- held-out 검증(지리산, 완전히 다른 곳·다른 seed): 탐지율·센서사용·비용 ---")
    res = compare(TEST_LOC, te_dem, W_cls, W_react, W_rl, n_ep=n_test)
    log("| 정책 | 탐지율 | 위치RMSE | 오경보 | 평균센서비용/스텝 |")
    log("|---|---|---|---|---|")
    best = None
    for name, s in res.items():
        dr = s["detection_rate"][0]; rm = s["loc_rmse_cells"][0]
        log("| %s | %.0f%% | %s | %.1f | %.3f |" % (name, dr, ("%.2f" % rm) if rm == rm else "—", s["false_alarms"][0], s["cost"]))
        if best is None or dr > best[1]:
            best = (name, dr)
    log("--- 각 정책이 쓴 센서(스텝% · 탐지수) ---")
    log("| 정책 | " + " | ".join(_pol.SENSORS_5) + " |")
    log("|---|" + "---|" * NC)
    for name, s in res.items():
        log("| %s | %s |" % (name, " | ".join("%.0f%%(%d)" % (s["pct"][k], s["use_det"][k]) for k in _pol.SENSORS_5)))
    log("--- 결론 ---")
    log("최고 탐지율: **%s** (%.0f%%)" % (best[0], best[1]))
    log("라벨: 조건기반 proactive(oracle_label_condition) — 탐지 순간이 아니라 '이 환경엔 이 센서를 켜라'.")
    log("학습: AdamW·grad-clip·cosine+warmup·class-weight, HP·시드수 sweep(검증 시드 분리). Mamba=selective SSM(상태재귀), MLP 아님.")
    log("정직: material·온도·풍은 대표/유도(domain 한정), 현장 validation 아님. sar 는 절대 레퍼런스(심판).")
    md = "# 5센서 Mamba 학습·비교 (학습 태백산 / 검증 지리산)\n\n```\n" + "\n".join(lines) + "\n```\n"
    rel = "public_agent_memory/mamba5_train_%s.md" % ts
    open(os.path.join(REPO, rel), "w", encoding="utf-8").write(md)
    open(os.path.join(mem, "mamba5_train_%s.log" % ts), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("산출물:", rel)
    return res, best, W_cls, W_react, W_rl


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--demo", action="store_true")
    ap.add_argument("--seeds", type=int, default=160); ap.add_argument("--test", type=int, default=14)
    a, _ = ap.parse_known_args()
    demo(max_seeds=a.seeds, n_test=a.test)
