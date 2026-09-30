#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""!시나리오 배경 실행기 — 한 번의 simulate() 로 실시간·사후 산출물을 모두 낸다.

  realtime.gif : RGB 카메라 장면 + IMU/GPS 상황표시(원시값 아님, 나침반·위치신뢰도) + SAR 무전, 프레임 재생
  postmission.png : 시간축 정책·센서 타임라인(실패/회복 구간)
  .md : 해석·판정·센서요약·무전 로그

셋 다 public_agent_memory/ 에 쓴다 — 봇의 relay.산출물꼴 이 이 경로를 첨부한다.
한 simulate() 를 셋이 공유하므로 실시간 영상과 사후 보고가 같은 임무다(따로 돌려 어긋나지 않는다).
"""
import os, sys, argparse, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import playback, postmission, radar

PAM = os.path.normpath(os.path.join(HERE, "..", "public_agent_memory"))


def _report_md(V, r, gif_rel, png_rel):
    sc = V["sc"]; ph = V["phys"]; frames = V["frames"]
    n_evt = sum(1 for f in frames if f["event"])
    L = []
    L.append("# SAR 임무 — %s · %s" % (sc["place"], sc["condition"]))
    L.append("")
    L.append("> **[검증 한계 — 반드시 읽을 것]** 이것은 **모델-내부 VERIFICATION**(정책이 물리모델대로 도는가)"
             "이지 **현장 VALIDATION 이 아니다.** 시나리오·관측·판정이 모두 같은 시뮬 안에 있다(자기채점). "
             "NASA-STD-7009(M&S 신뢰성)·SE Handbook(V&V) 기준으로, 물리모델(Beer-Lambert·Koschmieder·"
             "FMCW-SAR·IMU 랜덤워크)이 **실측 referent 로 검증되지 않았다.** 아래 수치는 전부 **모델 조건부**다 — "
             "현장 성능으로 읽지 말 것. 진짜 validation 은 §검증계획 참조.")
    L.append("")
    L.append("- 해석: 장소=%s, 조건=%s, 조난자 %d명 (좌표 %.5f,%.5f 일대 랜덤)"
             % (sc["place"], sc["condition"], len(V["survs"]), V["LAT"], V["LON"]))
    L.append("- 판정: %s  (조난자 %d/%d 확보, 커버리지 %.0f%%)"
             % (r["verdict"], len(V["confirmed"]), len(V["survs"]), r["covpct"]))
    L.append("- 정책: 재계획(REPLAN) %d회, 체공/최소위험(HOLD) %d회, 사건 %d건"
             % (r["n_replan"], r["n_hold"], n_evt))
    L.append("- 물리 조건: 가시거리 V=%.0fm, 조도 %.0flux, 글레어 %.2f"
             % (ph["V"], ph["lux"], ph["glare"]))
    L.append("")
    L.append("## 실시간 화면 (RGB 장면 + IMU/GPS 상황표시 + SAR 무전)")
    L.append("![realtime](%s)" % gif_rel)
    L.append("")
    L.append("## 사후 보고 (시간축: 정책·센서 타임라인, 실패/회복 구간)")
    L.append("![postmission](%s)" % png_rel)
    L.append("")
    cfg = radar.RadarCfg()
    import math as _m
    R0 = _m.hypot(130.0, playback.AGL)                     # 대표 경사거리(측방 Rg≈130m, 고도)
    L.append("## 레이더(SAR) 제원 — 전천후(안개·연기·야간 무관)")
    L.append("- 방식: X-대역 **FMCW 합성개구레이더**(개구면 합성), raw I/Q 합성 → 거리압축 → 백프로젝션")
    L.append("- 반송 %.1f GHz, 대역폭 %.0f MHz → **거리해상도 δr=%.2f m**(=c/2B)"
             % (cfg.fc / 1e9, cfg.B / 1e6, cfg.range_res))
    L.append("- 합성개구 L_sa=%.1f m → **방위해상도 δa=%.2f m**(=λR/2L, R≈%.0f m)"
             % (cfg.L_sa, cfg.az_res(R0), R0))
    L.append("- 비모호 거리 %.0f m, DOA 비모호 ±%.0f°·각해상도 %.1f°(Rx %d소자, d=λ/2)"
             % (cfg.unambiguous_range, cfg.doa_unambiguous_deg, cfg.doa_res_deg, cfg.n_rx))
    L.append("- calibration(위상오차·모션보상)은 해결 가정. 지면 z=0 평면 근사(완만지형).")
    L.append("- RGB 가 안개로 실명한 프레임에서도 SAR 은 표적 반사를 잡는다(실시간 화면 ③ 패널).")
    L.append("")
    L.append("## 검증계획 — 이 시뮬을 현장 VALIDATION 으로 끌어올리려면 (자기채점 탈피)")
    L.append("- **모델 검증(NASA-STD-7009)**: 각 물리모델을 독립 실측과 맞춘다 — 안개 haze↔실 안개 영상 투과율, "
             "FMCW-SAR 백프로젝션↔실 SAR 데이터셋(예: Sandia/UAVSAR), IMU 드리프트↔실 IMU 로그. "
             "신뢰성 평가(verification·validation·불확실도 정량)를 통과해야 시뮬 수치가 증거가 된다.")
    L.append("- **독립 오라클(IV&V)**: 판정을 정책과 **분리**한다 — 다른 팀/다른 구현이 성공을 채점하거나, "
             "held-out 실측 ground truth 로 판정. 지금은 같은 코드가 만들고 채점한다(순환).")
    L.append("- **현장 시험**: 규정/relevant 환경에서 실기 비행 + 실 센서 + 실제(또는 마네킹) 표적. "
             "그때 비로소 Reliability/Robustness/Resilience 가 '현장 수치'가 된다.")
    L.append("- 지금 정당한 것: 독립 대조가 붙은 조각만 — 예 SAR 초점폭(측정) ↔ δa=λR/2L(식). 이건 verification 이다.")
    L.append("")
    L.append("## SAR 무전 로그")
    for m in V["radio"]:
        L.append("- " + m)
    L.append("")
    L.append("## 매스텝 판단 로그 (상황표시 — 원시값 아님)")
    L.append("| t | 정책 | RGB 가시도 | 위치신뢰(IMU/GPS) | 방위 | 사건 |")
    L.append("|---|---|---|---|---|---|")
    for i, f in enumerate(frames):
        vis = "양호" if f["rho"] >= 0.6 else ("저하" if f["rho"] >= 0.25 else "불량")
        sig = f["sig"]; conf = "소실" if sig >= 99 else ("높음" if sig < 15 else ("보통" if sig < 30 else "낮음"))
        L.append("| %02d | %s | %s | %s | %03d° | %s |"
                 % (i, f["state"], vis, conf, int(f["heading"]) % 360, f["event"] or "-"))
    return "\n".join(L) + "\n"


def _p(msg):
    """진행 스트림 한 줄. 봇 watcher 가 [[STREAM]] 을 보면 매 폴에서 이 줄들을 채널에 민다."""
    print("진행> " + msg, flush=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--nl", required=True); ap.add_argument("--seed", type=int, default=None)
    a, _ = ap.parse_known_args()
    os.makedirs(PAM, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    print("[[STREAM]] 실시간 임무 텔레메트리 (시뮬 — 현장 검증 아님)", flush=True)
    V = playback.simulate(a.nl, a.seed)
    sc0 = V["sc"]
    _p("임무 개시: %s · %s · 조난자 %d명 · 좌표(%.4f,%.4f)"
       % (sc0["place"], sc0["condition"], len(V["survs"]), V["LAT"], V["LON"]))
    # 매스텝 서사(무전·상태)를 실시간 줄로 — watcher 가 폴마다 새 줄만 민다
    for i, f in enumerate(V["frames"]):
        cov = 100.0 * f["cov"].sum() / (playback.GW * playback.GH)
        last = f["radio"][-1] if f["radio"] else ""
        _p("t=%02d/%d %-9s 커버리지%3.0f%% 조난자%d/%d 방위%03d° | %s"
           % (i, len(V["frames"]), f["state"], cov, f["found"], len(V["survs"]),
              int(f["heading"]) % 360, last[:70]))
    _p("탐색 종료 — 영상 합성 시작(실시간 GIF · 사후 보고)")
    gif = os.path.join(PAM, ts + "_realtime.gif")
    png = os.path.join(PAM, ts + "_postmission.png")
    md = os.path.join(PAM, ts + "_SAR.md")
    playback.render_gif(V, gif, on_frame=lambda i, n: (i % 6 == 0) and _p("[렌더] 실시간 화면 %d/%d 합성" % (i, n)))
    _p("사후 보고 합성")
    r = postmission.render(V, png)
    gif_rel = "public_agent_memory/" + os.path.basename(gif)
    png_rel = "public_agent_memory/" + os.path.basename(png)
    md_rel = "public_agent_memory/" + os.path.basename(md)
    open(md, "w", encoding="utf-8").write(_report_md(V, r, gif_rel, png_rel))
    sc = V["sc"]
    print("장소=%s 조건=%s 조난자 %d/%d 판정=%s"
          % (sc["place"], sc["condition"], len(V["confirmed"]), len(V["survs"]), r["verdict"]))
    # relay.산출물꼴 이 붙이는 경로(마지막 4개). md·gif·png 모두 public_agent_memory/ 아래.
    for rel in (md_rel, gif_rel, png_rel):
        print("산출물:", rel)


if __name__ == "__main__":
    main()
