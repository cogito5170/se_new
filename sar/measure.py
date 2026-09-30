#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파이프라인 4계층 실측 — '다양한 공간을 모델링하면서 실시간 multi-sensor 가 되나'를 환경별로 잰다.

사용자(메시지)가 든 네 축을 **지어내지 않고 실측**한다:
  ① World model      : 공간해상도(mpp) · 피처 수 · scene DB 메모리
  ② Sensor data rate : RGB 프레임바이트 · SAR raw I/Q 바이트 (실 배열 nbytes)
  ③ Processing       : RGB·SAR 렌더 지연(벽시계 중앙값) — 추정 FLOPs 아님
  ④ Output           : 탐지정확도(IV&V 평가기, 숨은 truth) — 선택(별도 !독립검증 소유)

과장방지(실측 2026-09-18) 네 검사를 수마다 건다:
  1) 재려던 걸 쟀나 — 지연=실 벽시계, 데이터율=실 nbytes, 해상도=mpp. 추정치 아님.
  2) 동작점 성한가 — 렌더가 유효 이미지/영상을 냈나(NaN 없음, 값역).
  3) 독립 대조 하나 — perf_counter vs process_time; 데이터율 계산값 vs 실 nbytes.
  4) 사소한 설명 죽이기 — DEM·scene 생성은 1회성이라 per-frame 지연에서 뺀다(따로 보고).
     데이터율이 그냥 화면크기(H·W)인 건 자명 → raw I/Q(정보량 다름)도 같이 낸다.

정직: Python/numpy·이 컨테이너 CPU 다 — **임베디드 HW 아님**. 절대 실시간 보장이 아니라
환경 간 **상대 비교**다. fps 는 가정(명시). material·산란은 문헌 대표값 [출처:조각]. 현장 validation 아님.
"""
from __future__ import annotations
import math
import os
import sys
import time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import camera
import radar
import scene as scene_mod

# fps 는 **가정**(설계 선택)이다 — 데이터율을 bytes/s 로 환산할 때만 쓰고, 표에 그대로 명시한다.
RGB_FPS = 5.0        # FPV 갱신 가정
SAR_FPS = 1.0        # SAR 프레임 가정

# 환경별 대표 기상(시정 V[m]·조도 illum[lux]) — land-cover 와 짝지어 다양한 공간을 만든다.
ENVIRONMENTS = [
    ("forest", dict(V=800.0, illum=2000.0)),
    ("desert", dict(V=3000.0, illum=20000.0)),
    ("urban",  dict(V=1500.0, illum=2000.0)),
    ("coast",  dict(V=2000.0, illum=5000.0)),
    ("alpine", dict(V=500.0, illum=8000.0)),
]


def _synth_dem(n=64, seed=0):
    """망 없이 도는 합성 지형(측정용). 실 임무는 terrain.fetch_dem 을 쓴다."""
    rng = np.random.default_rng(seed)
    xx, yy = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n))
    return 700 + 300 * (np.sin(3 * xx) * np.cos(2 * yy) + xx) + 20 * rng.standard_normal((n, n))


def _median_latency(fn, k=5, warmup=1):
    """벽시계 지연 중앙값[ms] + process_time 중앙값[ms](독립 대조). warmup 은 버린다."""
    for _ in range(warmup):
        fn()
    wall = []; cpu = []
    for _ in range(k):
        t0 = time.perf_counter(); c0 = time.process_time()
        fn()
        wall.append((time.perf_counter() - t0) * 1e3); cpu.append((time.process_time() - c0) * 1e3)
    return float(np.median(wall)), float(np.median(cpu))


def measure_environment(landcover, beta=0.005, dem=None, seed=7, W=176, H=104, npx=72, k=5):
    """한 환경(land-cover)의 ①②③ 를 실측. 반환 dict(측정 + 4검사 플래그)."""
    if dem is None:
        dem = _synth_dem(64, seed)
    mpp = 6000.0 / dem.shape[1]
    # ── scene 생성(1회성) — per-frame 지연에서 제외하려고 따로 잰다(검사 4) ──
    t0 = time.perf_counter()
    sdb = scene_mod.SceneDB(dem, mpp, seed=seed, landcover=landcover)
    sdb.generate()
    gen_ms = (time.perf_counter() - t0) * 1e3

    cam = (3000.0, 3000.0)
    n_view = len(sdb.query(cam, 1600.0))
    # ① World model
    feat_bytes = sum(sys_getsize(f) for f in sdb.features()[:50])
    per_feat = feat_bytes / max(1, min(50, len(sdb.features())))
    world = dict(mpp_m=mpp, n_features=len(sdb.features()), n_in_view=n_view,
                 scene_kb=per_feat * len(sdb.features()) / 1024.0)

    # ② Sensor data rate — 실 배열 nbytes (검사 1)
    img = camera.render(dem, mpp, cam, 90.0, 45.0, beta, W=W, H=H, scene=sdb)
    rgb_valid = np.isfinite(img).all() and 0.0 <= float(img.min()) and float(img.max()) <= 1.0    # 검사 2
    rgb_bytes = int(img.nbytes)
    rgb_calc = W * H * 3 * img.dtype.itemsize                                                      # 검사 3(대조)
    cfg = radar.RadarCfg()
    sc = np.array([cam[0], cam[1] + 171.0])
    scat, rcs, _ = radar.scene_from_terrain(sc, 60.0, [], n_clutter=256, rng=np.random.default_rng(1), scene=sdb)
    trk = radar.track(cfg, np.array(cam), 45.0)
    raw = radar.synth_raw(cfg, scat, rcs, trk, 90.0)
    sar_raw_bytes = int(raw.nbytes)
    sar_valid = np.isfinite(raw).all()                                                             # 검사 2
    drate = dict(rgb_frame_B=rgb_bytes, rgb_calc_B=rgb_calc, rgb_Bps=rgb_bytes * RGB_FPS,
                 sar_raw_frame_B=sar_raw_bytes, sar_raw_Bps=sar_raw_bytes * SAR_FPS,
                 rgb_calc_matches=(abs(rgb_bytes - rgb_calc) <= img.dtype.itemsize * 3))

    # ③ Processing latency — 벽시계 중앙값(검사 1), perf vs cpu 대조(검사 3), 생성은 제외(검사 4)
    def _rgb():
        camera.render(dem, mpp, cam, 90.0, 45.0, beta, W=W, H=H, scene=sdb)
    def _sar():
        s2, r2, _ = radar.scene_from_terrain(sc, 60.0, [], n_clutter=256, rng=np.random.default_rng(2), scene=sdb)
        radar.sar_image(cfg, s2, r2, np.array(cam), sc, 45.0, 90.0, half=60.0, npx=npx)
    rgb_ms, rgb_cpu = _median_latency(_rgb, k=k)
    sar_ms, sar_cpu = _median_latency(_sar, k=k)
    latency = dict(rgb_ms=rgb_ms, rgb_cpu_ms=rgb_cpu, sar_ms=sar_ms, sar_cpu_ms=sar_cpu, scene_gen_ms=gen_ms)

    return dict(env=landcover, world=world, drate=drate, latency=latency,
                sound=(rgb_valid and sar_valid), rgb_valid=rgb_valid, sar_valid=sar_valid)


def sys_getsize(obj):
    import sys as _s
    return _s.getsizeof(obj) + sum(_s.getsizeof(v) for v in (obj.values() if isinstance(obj, dict) else []))


def measure_all(k=5):
    return [measure_environment(env, k=k) for env, _wx in ENVIRONMENTS]


def render_md(rows, accuracy=None):
    L = ["# 파이프라인 4계층 실측 — 환경별 (다양한 공간 × 실시간 multi-sensor)", ""]
    L.append("> 네 축을 **지어내지 않고 실측**한다. 지연=벽시계(추정 FLOPs 아님), 데이터율=실 배열 nbytes, "
             "해상도=mpp. **임베디드 HW 아님**(Python/numpy·컨테이너 CPU) — 절대 실시간이 아니라 환경 간 상대 비교다.")
    L.append("")
    L.append("## ①②③ 환경별 측정")
    L.append("| 환경 | mpp[m/px] | 피처수 | 시야내 | RGB frame[KB] | SAR raw[KB] | RGB 지연[ms] | SAR 지연[ms] | 동작점 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        w = r["world"]; d = r["drate"]; la = r["latency"]
        L.append("| %s | %.0f | %d | %d | %.1f | %.0f | %.1f | %.1f | %s |" % (
            r["env"], w["mpp_m"], w["n_features"], w["n_in_view"],
            d["rgb_frame_B"] / 1024.0, d["sar_raw_frame_B"] / 1024.0,
            la["rgb_ms"], la["sar_ms"], "O" if r["sound"] else "X"))
    L.append("")
    L.append("## 데이터율(가정 fps 명시) · bytes/s")
    L.append("- RGB @ %.0f fps, SAR @ %.0f fps (가정 — bytes/s 환산에만 쓴다)." % (RGB_FPS, SAR_FPS))
    for r in rows:
        d = r["drate"]
        L.append("  - %-7s RGB %.1f KB/s · SAR raw %.1f MB/s" % (r["env"], d["rgb_Bps"] / 1024.0, d["sar_raw_Bps"] / 1024.0 / 1024.0))
    L.append("")
    L.append("## 과장방지 4검사 (수마다)")
    L.append("1. **재려던 걸 쟀나**: 지연=`time.perf_counter` 벽시계, 데이터율=`ndarray.nbytes`, 해상도=mpp. 추정치 없음.")
    okcalc = all(r["drate"]["rgb_calc_matches"] for r in rows)
    L.append("2. **동작점**: 모든 환경 렌더가 유효(RGB∈[0,1]·NaN 없음, SAR raw 유한) → %s." % ("성함" if all(r["sound"] for r in rows) else "일부 깨짐"))
    L.append("3. **독립 대조**: RGB nbytes vs H·W·3·itemsize 계산값 일치=%s. 벽시계 vs process_time 도 같이 기록." % ("예" if okcalc else "아니오"))
    L.append("4. **사소한 설명 죽이기**: scene·DEM 생성은 1회성이라 per-frame 지연에서 뺐다(scene_gen_ms 따로). "
             "RGB 바이트가 화면크기(H·W)로 자명한 부분은 SAR raw I/Q(정보량 다름)와 함께 보여 구분.")
    for r in rows:
        la = r["latency"]
        L.append("   - %-7s scene_gen %.0f ms(1회) · RGB perf %.1f/cpu %.1f · SAR perf %.1f/cpu %.1f ms" %
                 (r["env"], la["scene_gen_ms"], la["rgb_ms"], la["rgb_cpu_ms"], la["sar_ms"], la["sar_cpu_ms"]))
    L.append("")
    L.append("## ④ 탐지정확도")
    if accuracy:
        L.append("| 환경 | 시정V[m] | 탐지율 | 위치RMSE[셀] |")
        L.append("|---|---|---|---|")
        for a in accuracy:
            L.append("| %s | %.0f | %.0f%% | %s |" % (a["env"], a["V"], a["detection_rate"],
                     ("%.2f" % a["loc_rmse_cells"]) if a["loc_rmse_cells"] == a["loc_rmse_cells"] else "—"))
    else:
        L.append("- 이 실행은 ①②③(오프라인·합성 DEM)만 쟀다. **탐지정확도는 숨은 truth 채점이 필요**하므로 "
                 "IV&V 평가기(`!독립검증`)가 소유한다 — 여기서 대충 만든 대리수를 정확도라 부르지 않는다(검사 4).")
    L.append("")
    L.append("## 정직 (한계)")
    L.append("- **임베디드 HW 아님**: 이 지연은 컨테이너 CPU 의 Python/numpy 값이다. 실 온보드(Jetson 등)와 다르다. 상대 비교로만 읽어라.")
    L.append("- fps 는 가정(명시). material·SAR 산란은 문헌 대표값(측정 아님) → [출처:조각]. 현장 validation 아님.")
    L.append("- land-cover 분류는 고도·경사 규칙(실 위성 land-cover 아님) — 이 표의 '환경'은 그 근사다.")
    return "\n".join(L) + "\n"


def demo(with_accuracy=False, lat=37.0966, lon=128.9456):
    """①②③ 를 다섯 환경에서 실측하고 보고서를 낸다. with_accuracy 면 IV&V 평가기로 ④ 도(실 DEM·망 필요)."""
    import datetime
    REPO = os.path.dirname(HERE); mem = os.path.join(REPO, "public_agent_memory"); os.makedirs(mem, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    rows = measure_all()
    accuracy = None
    if with_accuracy:
        accuracy = _measure_accuracy(lat, lon)
    md = render_md(rows, accuracy)
    rel = "public_agent_memory/measure_%s.md" % ts
    open(os.path.join(REPO, rel), "w", encoding="utf-8").write(md)
    for r in rows:
        la = r["latency"]; d = r["drate"]
        print("%-7s mpp=%.0f 피처=%d RGB=%.1fms SAR=%.1fms rawSAR=%.0fKB 동작점=%s" %
              (r["env"], r["world"]["mpp_m"], r["world"]["n_features"], la["rgb_ms"], la["sar_ms"],
               d["sar_raw_frame_B"] / 1024.0, "O" if r["sound"] else "X"))
    print("산출물:", rel)
    return rows, accuracy


def _measure_accuracy(lat, lon):
    """④ 탐지정확도 — IV&V 평가기(숨은 truth). 실 DEM 을 쓰므로 망이 필요하다(선택)."""
    sys.path.insert(0, os.path.join(HERE, "ivv"))
    import harness as H
    out = []
    for env, wx in ENVIRONMENTS:
        scn = dict(seed=hash(env) & 0xffff, lat=lat, lon=lon, V=wx["V"], illum=wx["illum"], n_target=2, sensors=["RGB", "SAR", "IMU"])
        m, _ = H.run_one(scn, budget=30)
        out.append(dict(env=env, V=wx["V"], detection_rate=m["detection_rate"], loc_rmse_cells=m["loc_rmse_cells"]))
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--accuracy", action="store_true", help="④ 탐지정확도까지(실 DEM·망 필요)")
    a, _ = ap.parse_known_args()
    demo(with_accuracy=a.accuracy)
