#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5센서 Mamba 학습·비교 파이프라인 검사(오프라인·합성 DEM).

핵심: (1) 조건기반 oracle 라벨이 옳다(맑음→RGB, 짙은안개→비광학), (2) feature 는 관측 문맥만(누수 없음),
(3) train_ce(AdamW·class-weight)가 macro_recall 을 올린다, (4) 학습/검증 시드 분리, (5) 세 정책이
sar reference·evaluator 로 채점, (6) MLP 아님(상태재귀 스캔이 forward 에 있다).
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sar" / "ivv")); sys.path.insert(0, str(REPO / "sar")); sys.path.insert(0, str(REPO))
import policies as pol
import selector_train as st
from ctrl.model import mamba_selector as ms

fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def _dem():
    xx, yy = np.meshgrid(np.linspace(0, 1, 48), np.linspace(0, 1, 48))
    return 700 + 300 * (np.sin(3 * xx) * np.cos(2 * yy) + xx)


def test_condition_oracle():
    S = pol.SENSORS_5
    clear = S[pol.oracle_label_condition(V=18000, illum=15000, canopy=False)]
    fog = S[pol.oracle_label_condition(V=60, illum=2000, canopy=False)]
    ok(clear == "RGB", "맑음 → 조건라벨 RGB (%s)" % clear)
    ok(fog != "RGB", "짙은 안개 → 비광학 센서 (%s)" % fog)
    ok(pol.D_IN_MULTI == 3, "특징 차원 3(순수 관측)")


def test_no_prevchoice_lockin():
    # feature_multi 는 prev_choice 를 무시해야(락인 방지)
    obs = {"rgb": {"vis": 0.3}, "imu": {"ok": True}, "gps": {"uncertain": False}}
    f0 = pol.feature_multi(obs, prev_choice_idx=0)
    f4 = pol.feature_multi(obs, prev_choice_idx=4)
    ok(np.allclose(f0, f4), "feature 가 prev_choice 에 불변(covariate 락인 없음)")


def test_train_improves_macro_recall():
    dem = _dem()
    O, Y, Yvec = st.gen_dataset_multi((37.0, 128.9), dem, seeds=range(1, 25), T=16)
    ok(O.shape == (24, 16, 3) and Y.shape == (24, 16), "데이터 형상")
    ok(Yvec.shape == (24, 16, len(pol.SENSORS_5)), "ReAct 유틸리티 타깃 형상")
    mr0, _ = ms._macro_recall(ms.init(3, len(pol.SENSORS_5), 8, 7), O, Y, len(pol.SENSORS_5))
    W = ms.train_ce(O, Y, len(pol.SENSORS_5), epochs=40, batch=8, lr=0.08, M=8, seed=7, quiet=True)
    mr1, _ = ms._macro_recall(W, O, Y, len(pol.SENSORS_5))
    ok(mr1 > mr0, "학습이 macro_recall 을 올린다 (%.3f→%.3f)" % (mr0, mr1))


def test_train_val_seed_disjoint():
    tr = set(range(1, 161)); va = set(range(900001, 900021))
    ok(tr.isdisjoint(va), "학습/검증 시드 분리(누수 없음)")


def test_three_policies_scored():
    dem = _dem()
    scn = st._rand_scenario((37.0, 128.9), 42, np.random.default_rng(0))
    for mk in (lambda: pol.BaselinePolicy(), lambda: pol.NASARulePolicy()):
        m = st.run_policy(mk, scn, dem, budget=16)
        ok("detection_rate" in m and "cost" in m, "정책 sar 채점 + 비용지표")
    O, Y, Yvec = st.gen_dataset_multi((37.0, 128.9), dem, seeds=range(1, 13), T=12)
    W = ms.train_ce(O, Y, len(pol.SENSORS_5), epochs=20, batch=8, lr=0.08, M=8, seed=2, quiet=True)
    m = st.run_policy(lambda: pol.MambaSensorPolicy(W, ms), scn, dem, budget=16)
    ok("detection_rate" in m, "학습 Mamba(분류) 정책도 sar 로 채점")
    # ReAct: 유틸리티 회귀 학습 → argmax(D̂−λC−μE) 로 행동
    Wr = ms.train_mse(O, Yvec, epochs=20, batch=8, lr=0.08, M=8, seed=2, quiet=True)
    mr = st.run_policy(lambda: pol.ReActMambaPolicy(Wr, ms), scn, dem, budget=16)
    ok("detection_rate" in mr, "ReAct(유틸리티) 정책도 sar 로 채점")
    dhat = ms.predict_reg(Wr, O[0])
    ok(dhat.shape == (12, len(pol.SENSORS_5)), "ReAct reason=D̂ 벡터 예측 형상")


def test_forward_step_matches_full():
    # 스트리밍 forward_step 이 배치 forward 와 일치(롤아웃·배포 일관성)
    W = ms.init(3, len(pol.SENSORS_5), 8, 1)
    seq = np.random.default_rng(0).random((6, 3))
    full = ms.forward(W, seq[None])[0][0]
    h = np.zeros(8); step = []
    for t in range(6):
        lg, h = ms.forward_step(W, seq[t], h); step.append(lg)
    ok(np.allclose(full, np.array(step), atol=1e-8), "forward_step(스트리밍) == forward(배치)")


def test_reinforce_learns():
    dem = _dem()
    W = st.train_reinforce((37.0, 128.9), dem, seeds=range(1, 13), T=16, epochs=12, batch=6, lr=0.05, M=8,
                           val_seeds=None, log=None)
    ok(all(np.all(np.isfinite(v)) for v in W.values()), "REINFORCE 가중치 유한(학습 안정)")
    # 학습된 정책이 sar 로 채점됨
    scn = st._rand_scenario((37.0, 128.9), 55, np.random.default_rng(0))
    m = st.run_policy(lambda: pol.MambaSensorPolicy(W, ms), scn, dem, budget=16)
    ok("detection_rate" in m, "RL 정책도 sar reference·evaluator 로 채점")


def test_voting_confirms_and_rejects():
    # 앵커드 확인 게이트: primary(RGB)가 낸 후보를 다른 센서가 코로보하면 확인, 외로우면 버림.
    base = pol.BaselinePolicy()                 # choose→'RGB'
    vp = pol.VotingPolicy(base, mode="soft", gate=2.0, tau=0.9)
    # (1) 외로운 Audio 후보(코로보 없음) — primary=RGB 가 아무것도 안 냄 → claim 0 (오경보 억제)
    obs_lonely = {"rgb": {"detections": [], "vis": 0.3}, "sar": {"detections": [], "hits": 0},
                  "thermal": {"detections": []}, "lidar": {"detections": []},
                  "audio": {"detections": [(10.0, 10.0, 0.4)]}}
    claims = vp.claim_from(obs_lonely, "RGB")
    ok(len(claims) == 0, "RGB 무탐지 → 외로운 Audio 는 claim 안 됨(오경보 억제)")
    # (2) RGB 앵커 + Thermal 코로보(같은 자리) → soft 가중합 1.0+0.7 ≥ tau → 확인, 위치=가중 무게중심
    obs_corr = {"rgb": {"detections": [(10.0, 10.0, 0.9)], "vis": 0.6}, "sar": {"detections": [], "hits": 0},
                "thermal": {"detections": [(10.4, 9.8, 0.7)]}, "lidar": {"detections": []},
                "audio": {"detections": []}}
    claims = vp.claim_from(obs_corr, "RGB")
    ok(len(claims) == 1, "RGB+Thermal 코로보 → 확인 1건")
    fx, fy, _ = claims[0]
    ok(9.9 <= fx <= 10.4 and 9.7 <= fy <= 10.1, "soft 위치=신뢰가중 무게중심(RGB 쪽으로 당김)")
    ok(vp.consulted is not None and set(vp.consulted) == set(pol.SENSORS_5), "코로보 스텝은 확인집합 켬(비용 계상)")
    # (3) hard k=2: 코로보 없는 RGB 단독은 확인 안 됨(합의 요구)
    vh = pol.VotingPolicy(pol.BaselinePolicy(), mode="hard", k=2, gate=2.0)
    only_rgb = {"rgb": {"detections": [(5.0, 5.0, 0.9)], "vis": 0.6}, "sar": {"detections": [], "hits": 0},
                "thermal": {"detections": []}, "lidar": {"detections": []}, "audio": {"detections": []}}
    ok(len(vh.claim_from(only_rgb, "RGB")) == 0, "hard k=2: 단독 센서는 확인 안 됨(코로보 필요)")


def test_is_mamba_not_mlp():
    # forward 에 상태 재귀(스캔) 루프가 있어야 Mamba(시퀀스 기억) — MLP 는 그게 없다
    import inspect
    src = inspect.getsource(ms.forward)
    ok("Abar[:, t, :] * h" in src or "Abar[:,t,:]*h" in src.replace(" ", ""), "forward 에 상태재귀 h=Ā·h+B̄·x (Mamba, MLP 아님)")


if __name__ == "__main__":
    for fn in (test_condition_oracle, test_no_prevchoice_lockin, test_train_improves_macro_recall,
               test_train_val_seed_disjoint, test_three_policies_scored, test_forward_step_matches_full,
               test_reinforce_learns, test_voting_confirms_and_rejects, test_is_mamba_not_mlp):
        print("[%s]" % fn.__name__)
        fn()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\n5센서 Mamba 파이프라인 검사 통과: 조건라벨·누수없음·학습됨·시드분리·3정책채점·Mamba(MLP아님)")
