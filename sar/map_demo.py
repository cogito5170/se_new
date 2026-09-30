#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SAR (a) 데모: 실제 지도(정사영상 스탠드인) + 실제 탐지기(YuNet DNN) + 실제 정책코어(C, ctypes).

흐름(가짜 곡선 없음, 매 스텝 실제 픽셀에 탐지기를 돌린다):
  운용자 red spot ─▶ prior ─▶ [C policy_core.pc_policy_step 로 다음 셀 선택]
    ─▶ UAV footprint 크롭 ─▶ [cv2 YuNet 로 실제 얼굴/사람 탐지] ─▶ 탐지/미탐
    ─▶ [C pc_belief_update 베이즈 갱신] ─▶ 반복 ─▶ belief 수렴 ─▶ Discord 탐지 카드

정직: policy·belief 는 논문이 측정한 그 policy_core.c(ctypes, sar_core.c 껍데기)를 그대로 쓴다.
관측(탐지 여부·위치)은 명목 곡선이 아니라 YuNet 이 실제 이미지 크롭에서 낸 실측이다.
한계: 지상 사진을 수색구역 스탠드인으로, 얼굴탐지를 '사람 있음' 대리로 쓴다(도달 가능한 실 모델).
실기 SAR 은 항공+열화상 프레임에 SAR-학습 탐지기를 쓴다 -- 파이프라인(탐지→p_useful→belief)은 동일.
"""
import ctypes, os, sys
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
for _c in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
           "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
    if os.path.exists(_c):
        fm.fontManager.addfont(_c)
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c).get_name(); break
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
IMG = os.path.join(HERE, "assets", "zidane.jpg")   # 실제 사람 3인 분산 -> 수색 의미
YUNET = os.path.join(HERE, "models", "yunet.onnx")

# ── 실제 정책 코어 (C, ctypes) ─────────────────────────────────────────────
lib = ctypes.CDLL(os.path.join(HERE, "libsarcore.so"))
f32 = np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags="C_CONTIGUOUS")
lib.sar_grid_w.restype = ctypes.c_int; lib.sar_grid_h.restype = ctypes.c_int
lib.sar_set_rmax.argtypes = [ctypes.c_float]
lib.sar_next.argtypes = [f32, ctypes.c_float, ctypes.c_float,
                         ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float),
                         ctypes.POINTER(ctypes.c_int)]
lib.sar_update.argtypes = [f32, ctypes.c_float, ctypes.c_float, ctypes.c_int,
                           ctypes.c_float, ctypes.c_float]
lib.sar_argmax.argtypes = [f32, ctypes.POINTER(ctypes.c_float),
                           ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float)]
lib.sar_entropy.argtypes = [f32]; lib.sar_entropy.restype = ctypes.c_float
GW, GH = lib.sar_grid_w(), lib.sar_grid_h()
R_MAX_CELLS = 3.0                     # 데모 관측 반경(셀). planning·footprint 일치.
lib.sar_set_rmax(ctypes.c_float(R_MAX_CELLS))

def policy_next(bel):
    tx, ty = ctypes.c_float(), ctypes.c_float(); nl = ctypes.c_int()
    lib.sar_next(bel, ctypes.c_float(VEH[0]), ctypes.c_float(VEH[1]),
                 ctypes.byref(tx), ctypes.byref(ty), ctypes.byref(nl))
    return tx.value, ty.value, nl.value
def belief_update(bel, atx, aty, det, mx, my):
    lib.sar_update(bel, ctypes.c_float(atx), ctypes.c_float(aty), ctypes.c_int(det),
                   ctypes.c_float(mx), ctypes.c_float(my))
def belief_argmax(bel):
    ax, ay, ap = ctypes.c_float(), ctypes.c_float(), ctypes.c_float()
    lib.sar_argmax(bel, ctypes.byref(ax), ctypes.byref(ay), ctypes.byref(ap))
    return ax.value, ay.value, ap.value

# ── 실제 탐지기 (YuNet DNN) ────────────────────────────────────────────────
det = cv2.FaceDetectorYN_create(YUNET, "", (320, 320), score_threshold=0.5)
def detect(img_bgr):
    """이미지에서 실제 얼굴(=사람) 탐지. 반환 [(cx,cy,score),...] (픽셀)."""
    h, w = img_bgr.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(img_bgr)
    out = []
    if faces is not None:
        for f in faces:
            x, y, bw, bh = f[:4]; out.append((x + bw / 2, y + bh / 2, float(f[-1])))
    return out

# ── georeference: 이미지 ↔ 격자 ↔ 실좌표(데모) ─────────────────────────────
img = cv2.imread(IMG)
if img is None: sys.exit("image load failed: " + IMG)
IH, IW = img.shape[:2]
CELL_M = 5.0                           # sar_core.c 와 동일
AREA_M = GW * CELL_M                    # 24*5 = 120 m 정사각(가로 기준)
def px_of_cell(cx, cy):                 # 셀 중심 -> 픽셀
    return ((cx + 0.5) / GW * IW, (cy + 0.5) / GH * IH)
def cell_of_px(px, py):
    return (px / IW * GW - 0.5, py / IH * GH - 0.5)
# 데모 georeference(라벨용): 중심 좌표 임의, 셀->위경도 근사
LAT0, LON0 = 37.5665, 126.9780          # 데모 중심(서울시청 근처) -- 라벨 표기용
def latlon_of_cell(cx, cy):
    dm_x = (cx - GW / 2) * CELL_M; dm_y = (cy - GH / 2) * CELL_M
    dlat = -dm_y / 111320.0
    dlon = dm_x / (111320.0 * np.cos(np.radians(LAT0)))
    return LAT0 + dlat, LON0 + dlon

# ── 지상 진실: 전체 이미지에 탐지기 1회 -> 실제 사람(얼굴) 셀 ───────────────
truth = detect(img)                     # [(px,py,score)]
truth_cells = [cell_of_px(px, py) + (s,) for (px, py, s) in truth]
print("실제 탐지기(YuNet)로 찾은 사람(얼굴): %d" % len(truth))
for (cx, cy, s) in truth_cells:
    la, lo = latlon_of_cell(cx, cy)
    print("  survivor @ cell(%.1f,%.1f)  (%.5f,%.5f)  score=%.2f" % (cx, cy, la, lo, s))

# ── red spot(운용자 표시) = 사람들 대략 중심에서 살짝 벗어난 곳 -> 수색 필요 ──
tc = np.array([[c[0], c[1]] for c in truth_cells])
red = (float(tc[:, 0].mean()) - 4.0, float(tc[:, 1].mean()) + 4.0)  # 중심서 오프셋
S_PRIOR = 5.0

# prior blob (numpy) : red spot 가우시안 + floor. C 코어와 같은 꼴.
bel = np.zeros(GW * GH, dtype=np.float32)
for gy in range(GH):
    for gx in range(GW):
        d2 = (gx - red[0]) ** 2 + (gy - red[1]) ** 2
        bel[gy * GW + gx] = np.exp(-d2 / (2 * S_PRIOR ** 2)) + 0.01
bel /= bel.sum()
H0 = lib.sar_entropy(bel)

# ── 탐색 루프 ──────────────────────────────────────────────────────────────
VEH = [2.0, 2.0]                        # 시작(좌상)
BUDGET = 45
FOOT_PX = int(R_MAX_CELLS / GW * IW)     # footprint 반경(px)
traj = [tuple(VEH)]
events = []                              # (step, cell, score, thumb, latlon)
confirmed = []                           # 확정된 survivor 셀
for step in range(BUDGET):
    tx, ty, nl = policy_next(bel)
    VEH = [tx, ty]; traj.append((tx, ty))
    # UAV footprint 크롭 -> 실제 탐지기
    px, py = px_of_cell(tx, ty)
    x0, y0 = int(max(0, px - FOOT_PX)), int(max(0, py - FOOT_PX))
    x1, y1 = int(min(IW, px + FOOT_PX)), int(min(IH, py + FOOT_PX))
    crop = img[y0:y1, x0:x1]
    dets = detect(crop) if crop.size else []
    # footprint 내 탐지 중 '새로운 survivor'(진실 근처 & 아직 미확정)를 고른다.
    new_hit = None
    for (dx, dy, s) in dets:                           # 크롭 좌표 -> 이미지 -> 셀
        gcx, gcy = cell_of_px(x0 + dx, y0 + dy)
        if (gcx - tx) ** 2 + (gcy - ty) ** 2 <= R_MAX_CELLS ** 2 \
           and any((gcx - t[0]) ** 2 + (gcy - t[1]) ** 2 <= 4.0 for t in truth_cells) \
           and all((gcx - c[0]) ** 2 + (gcy - c[1]) ** 2 > 4.0 for c in confirmed):
            new_hit = (gcx, gcy, s, x0 + dx, y0 + dy); break
    if new_hit is not None:
        gcx, gcy, s, ipx, ipy = new_hit
        belief_update(bel, tx, ty, 1, gcx, gcy)        # 새 탐지 -> 베이즈 수렴
        confirmed.append((gcx, gcy))
        th = img[max(0, int(ipy) - 60):int(ipy) + 60, max(0, int(ipx) - 50):int(ipx) + 50].copy()
        la, lo = latlon_of_cell(gcx, gcy)
        events.append((step, (gcx, gcy), s, th, (la, lo)))
        print("  [step %2d] 탐지! survivor @ cell(%.1f,%.1f) (%.5f,%.5f) score=%.2f"
              % (step, gcx, gcy, la, lo, s))
    else:
        belief_update(bel, tx, ty, 0, 0.0, 0.0)        # 미탐(또는 이미 찾은 것 재탐지) -> footprint 감쇠
    # 찾은 survivor 는 '항상' 억제한다 -> belief 가 그 위로 재수렴하지 않고 다른 생존자로 탐색 계속.
    # 단일표적 belief 는 탐지 시 붕괴(엔트로피->0)한다; 순차 다표적 SAR 은 found-suppression 이 필요.
    if confirmed:
        for gy in range(GH):
            for gx in range(GW):
                for (cx, cy) in confirmed:
                    if (gx - cx) ** 2 + (gy - cy) ** 2 <= 4.0:
                        bel[gy * GW + gx] *= 0.001; break
        bel /= bel.sum()
    if len(confirmed) >= len(truth_cells):
        print("  모든 survivor 확정 (step %d)" % step); break
Hf = lib.sar_entropy(bel)
print("탐색 종료: 확정 %d/%d, 스텝 %d, 엔트로피 %.2f->%.2f" %
      (len(confirmed), len(truth_cells), len(traj) - 1, H0, Hf))

# ── 그림 1: 수색구역(실이미지) + 격자·red spot·진실·궤적·footprint ─────────
rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
fig, axes = plt.subplots(1, 2, figsize=(15, 5.2))
ax = axes[0]; ax.imshow(rgb); ax.set_title("Search area (real orthophoto stand-in) + real YuNet detections", fontsize=10)
for gx in range(GW + 1): ax.axvline(gx / GW * IW, color="w", lw=0.3, alpha=0.35)
for gy in range(GH + 1): ax.axhline(gy / GH * IH, color="w", lw=0.3, alpha=0.35)
rpx = px_of_cell(*red); ax.plot(*rpx, "o", ms=16, mfc="none", mec="red", mew=2.5); ax.annotate("red spot", rpx, color="red", fontsize=9, xytext=(rpx[0]+8, rpx[1]-8))
for (cx, cy, s) in truth_cells:
    p = px_of_cell(cx, cy); ax.add_patch(Circle(p, 26, fill=False, ec="lime", lw=2))
tp = np.array([px_of_cell(c[0], c[1]) for c in traj])
ax.plot(tp[:, 0], tp[:, 1], "-o", color="cyan", ms=3, lw=1.2, alpha=0.9)
ax.plot(tp[0, 0], tp[0, 1], "s", color="yellow", ms=8); ax.annotate("start", tp[0], color="yellow", fontsize=8)
for (st, cell, s, th, ll) in events:
    p = px_of_cell(*cell); ax.add_patch(Circle(p, 34, fill=False, ec="orange", lw=2.5))
ax.set_xlim(0, IW); ax.set_ylim(IH, 0); ax.axis("off")

ax = axes[1]
bg = bel.reshape(GH, GW)
im2 = ax.imshow(bg, cmap="inferno", origin="upper"); ax.set_title("Belief b(x) after search (C policy_core)", fontsize=10)
ax.plot(red[0], red[1], "o", ms=12, mfc="none", mec="red", mew=2)
for (cx, cy, s) in truth_cells: ax.plot(cx, cy, "x", color="lime", ms=9, mew=2)
tpc = np.array(traj); ax.plot(tpc[:, 0], tpc[:, 1], "-o", color="cyan", ms=2, lw=1, alpha=0.8)
axb = belief_argmax(bel); ax.plot(axb[0], axb[1], "+", color="white", ms=14, mew=2)
plt.colorbar(im2, ax=ax, fraction=0.046); ax.set_xlabel("green x = true survivors · red = operator tip · white + = belief peak", fontsize=8)
fig.suptitle("SAR: map+red spot -> active search -> real detection -> belief  (policy=C policy_core via ctypes, detector=cv2 YuNet)", fontsize=11)
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(os.path.join(OUT, "sar_demo.png"), dpi=110); plt.close(fig)
print("saved:", os.path.join(OUT, "sar_demo.png"))

# ── Discord 탐지 카드(수신기가 채널에 게시할 것) ──────────────────────────
if events:
    n = len(events)
    fig, axs = plt.subplots(1, n, figsize=(3.4 * n, 3.8)); axs = np.atleast_1d(axs)
    for a, (st, cell, s, th, (la, lo)) in zip(axs, events):
        a.imshow(cv2.cvtColor(th, cv2.COLOR_BGR2RGB)); a.axis("off")
        a.set_title("POSSIBLE SURVIVOR\n(%.5f, %.5f)\nconf=%.2f  t=step %d\nsensor=EO(YuNet)"
                    % (la, lo, s, st), fontsize=8, color="darkred")
    fig.suptitle("[Discord 수신기] UAV 다운링크 탐지 카드", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.9])
    fig.savefig(os.path.join(OUT, "discord_card.png"), dpi=110); plt.close(fig)
    print("saved:", os.path.join(OUT, "discord_card.png"))
