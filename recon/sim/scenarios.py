"""시나리오 30개. 각 항목: 세계 · 고장 · 시간 · 방법 · 대응 설명(detect→isolate→degrade→recover/stop)."""
from world import World


def base_world(seed, rough=0.04, rocks=6, ruins=True, size=30.0):
    w = World(size=size, seed=seed)
    w.rough(rough, 1.5)
    w.rough(rough * 0.25, 0.25)
    rng = w.rng
    for _ in range(rocks):
        w.rock(rng.uniform(8, 27), rng.uniform(3, 27), rng.uniform(0.25, 0.5), rng.uniform(0.15, 0.35))
    if ruins:                                         # 폐건물 잔해: LIO 가 붙잡을 수직 구조
        w.box(14, 20, 20, 20.3, 1.2); w.box(14, 20, 14.3, 25, 1.2); w.box(22, 6, 22.3, 11, 0.9); w.box(22, 6, 26, 6.3, 0.9)
    w.fence(1.0)
    return w


def W(fn):
    return fn


def flat(seed):
    w = World(seed=seed); w.rough(0.01, 2.0); w.box(18, 12, 18.4, 18, 1.0); w.box(10, 24, 16, 24.4, 1.0); w.fence(); return w


def uneven(seed):
    w = base_world(seed, rough=0.12, rocks=10); return w


def obstacles(seed):
    w = base_world(seed, rough=0.03, rocks=0)
    for x, y in ((8, 15), (10, 13), (10, 17.5), (13, 15.5), (16, 12), (16, 18.5), (19, 15)):
        w.rock(x, y, 0.45, 0.35)
    w.box(11.5, 9, 12, 12, 0.8); w.box(11.5, 18.5, 12, 21, 0.8); return w


def loose(seed):
    w = base_world(seed, rough=0.04, rocks=3)
    w.soil(9, 10, 16, 20, slip=0.25, chi=0.60, kind=3); w.notes.append("모래 구역 x 9-16 m: 슬립 0.25, 요 효율 0.60"); return w


def slippery(seed):
    w = base_world(seed, rough=0.03, rocks=2)
    w.soil(7, 8, 20, 22, slip=0.35, chi=0.55, kind=4); w.notes.append("진흙 구역: 슬립 0.35, 요 효율 0.55"); return w


def unknown(seed):
    w = base_world(seed, rough=0.06, rocks=8)
    w.box(6, 4, 6.3, 12, 1.0); w.box(6, 18, 6.3, 27, 1.0); w.box(9, 22, 13, 22.3, 1.0)
    w.hill(24, 22, 3.0, 0.8); w.ditch(17, 2, 17.8, 8, 0.5); return w


def open_field(seed):
    w = World(seed=seed); w.rough(0.03, 3.0); w.fence(); w.box(26, 26, 27, 27, 1.0); return w


def steep(seed):
    w = base_world(seed, rough=0.03, rocks=2)
    w.hill(14, 15, 2.2, 1.35); w.notes.append("원뿔 언덕 경사 약 31° (한계 25°)"); return w


def ditch(seed):
    w = base_world(seed, rough=0.03, rocks=2)
    w.ditch(11, 6, 11.9, 24, 0.5); w.box(11, 13.5, 11.9, 16.5, -0.02, kind=0)   # 가운데 다리(메운 곳)
    w.h[w.mask_rect(11, 13.5, 11.9, 16.5)] = 0.0
    w.notes.append("폭 0.9 m 깊이 0.5 m 도랑, 가운데 3 m 만 건널 수 있다"); return w


def narrow(seed):
    w = base_world(seed, rough=0.02, rocks=0, ruins=False)
    w.box(12, 1, 12.4, 14.4, 1.0); w.box(12, 15.6, 12.4, 29, 1.0)          # 폭 1.2 m 틈 (0.9 m 는 통과 못 함 — 측정, 보고서 §6)
    w.notes.append("벽의 폭 1.2 m 틈 (로버 전폭 0.44 m)"); return w


def deadend(seed):
    w = base_world(seed, rough=0.02, rocks=0, ruins=False)
    w.box(8, 12, 16, 12.3, 1.0); w.box(8, 18, 16, 18.3, 1.0); w.box(16, 12, 16.3, 18.3, 1.0)   # U 자 막다른 곳
    w.box(20, 3, 20.3, 27, 1.0); w.box(20, 14, 20.3, 16, 0.0)
    w.h[w.mask_rect(20, 14, 20.3, 16)] = 0.0
    return w


def dynamic(seed):
    w = base_world(seed, rough=0.03, rocks=2)
    w.dyn.append(dict(path=[(9, 9), (9, 22)], v=0.6, r=0.25, h=1.7, t0=10, t1=200))
    w.dyn.append(dict(path=[(15, 20), (15, 8)], v=0.5, r=0.25, h=1.7, t0=35, t1=200))
    return w


def canopy(seed):
    w = base_world(seed, rough=0.05, rocks=5)
    w.gnss_block[w.mask_rect(10, 5, 22, 25)] = True
    w.rough(0.0, 1.0)
    w.notes.append("x 10-22 m: 수관 아래 GNSS 음영"); return w


def comm_zone(seed):
    w = base_world(seed, rough=0.05, rocks=5)
    w.comm_shadow.append((15, 1, 29, 29, 2e4, 6.0))
    w.notes.append("x>15 m: 통신 음영 20 kbps, 지연 6 s"); return w


def comparison(seed):
    w = base_world(seed, rough=0.06, rocks=8)
    w.box(6, 4, 6.3, 11, 1.0); w.box(9, 22, 13, 22.3, 1.0); w.soil(18, 3, 25, 9, 0.25, 0.6, 3)
    w.hill(24, 22, 3.0, 0.7); return w


def revisit_world(seed):
    w = base_world(seed, rough=0.05, rocks=6)
    w.box(9, 5, 9.3, 25, 0.5)       # 낮은 담: 뒤쪽이 가려져 불확실도가 남는다
    return w


def demo(seed):
    w = unknown(seed)
    w.soil(18, 3, 24, 9, 0.25, 0.6, 3)
    w.dyn.append(dict(path=[(12, 8), (12, 20)], v=0.5, r=0.25, h=1.7, t0=60, t1=90))
    return w


S = {}


def sc(id, title, world, what, how, **kw):
    S[id] = dict(id=id, title=title, world=world, what=what, how=how, **kw)


# ---- TEST-01..08
sc("T01", "TEST-01 평지 주행", flat, "평평한 운동장, 벽 2개", "정상 탐사: J 최대 후보로 이동, 커버리지 92% 또는 후보 소진 시 귀환", t_max=150)
sc("T02", "TEST-02 요철 지형", uneven, "±12 cm 요철과 바위 10개", "지형 위험(기울기·계단)을 비용에 넣어 우회, 불확실한 셀은 재방문", t_max=180)
sc("T03", "TEST-03 장애물 회피", obstacles, "바위 7개 + 담 2개 사이 슬라럼", "전방 통로 위험 >0.6 → AVOID(후진 0.4 m+벌점+재계획), >0.92 → SAFE_STOP", t_max=150)
sc("T04", "TEST-04 무른 지반", loose, "모래(슬립 0.25, 요 효율 0.6)", "엔코더↔LIO 속도 차로 슬립 추정 → Q 팽창·감속, 슬립 >0.45 이면 회피", t_max=180)
sc("T05", "TEST-05 바퀴 슬립 지도 왜곡 비교", slippery, "진흙(슬립 0.35) — 필터 4종이 같은 원시데이터로 지도를 만든다",
   "F1 엔코더 · F2 +자이로 · F3 EKF+LIO · F4 제안(편향 상태+슬립 적응 Q+게이트)의 자세·지도 오차 비교", t_max=180, compare_filters=True)
sc("T06", "TEST-06 미지 환경 탐사", unknown, "벽·언덕·도랑이 섞인 미지 구역", "정보이득−에너지−시간−위험 J 로 프런티어 선택, 도랑은 음장애로 회피", t_max=240)
sc("T07", "TEST-07 반복 관측", revisit_world, "낮은 담 뒤 가려진 구역", "관심구역(담 뒤 x 10-16 m)은 σ ≤ 2 cm 요구 — 한 번 본 뒤에도 남은 불확실도를 REVISIT·OBSERVE(정지 스캔 4 s)로 줄인다", t_max=220, aoi=(10, 5, 16, 25, 0.02))
sc("T08", "TEST-08 센서 열화(먼지)", uneven, "40 s 부터 LiDAR 잡음 4배·점 35% 손실·허공 반사",
   "되돌림 비율·허공 점으로 건강 산출 → DEGRADED(속도 ½)·측정분산 3배 → 회복 시 정상", t_max=180,
   faults=dict(lidar_degrade=(40, 110, 4.0)))
# ---- 고장 9
sc("F01", "고장: LiDAR 끊김", unknown, "60-80 s 이더넷 끊김 (프레임 없음)",
   "detect: 0.3 s 무프레임 → 건강 0 · isolate: 지도 갱신 중지 · degrade: 빵부스러기 길로 저속 귀환 · recover: 프레임 복귀 시 탐사 재개", t_max=180,
   faults=dict(lidar_drop=(60, 80)))
sc("F02", "고장: IMU 드리프트", uneven, "50 s 부터 자이로 편향 0.03°/s² 로 증가",
   "detect: EKF 편향 상태 >0.6°/s · isolate: 자이로 배제 → 엔코더 요율 · degrade: DEGRADED · recover: LIO 로 요 보정 유지", t_max=180,
   faults=dict(imu_drift=(50, 999, 0.03)))
sc("F03", "고장: 엔코더 고장", uneven, "40 s 에 좌전륜 엔코더 정지",
   "detect: 짝 바퀴 대비 <20% 1 s · isolate: 짝 바퀴로 대체(주행기록·PID 되먹임) · degrade: 속도 ½ · 계속", t_max=160,
   faults=dict(enc_fail=(40, 999, 0)))
sc("F04", "고장: 심한 슬립/빠짐", slippery, "진흙에서 헛돎", "detect: 엔코더 움직임·LIO 정지 → 슬립 >0.45 · AVOID 후진 · 진흙 구역 벌점 · 재계획", t_max=180)
sc("F05", "고장: 카메라 고장", uneven, "50 s 카메라 프레임 없음",
   "detect: 프레임 시각 · isolate: 영상 채널 배제 · degrade: 지도·정책은 LiDAR 로 계속, 실시간 영상 대신 지도 표시", t_max=150,
   faults=dict(cam_fail=(50, 999)))
sc("F06", "고장: GNSS 상실(수관)", canopy, "확장 센서 GNSS. 수관 아래에서 RTK 고정 상실",
   "detect: 고정 없음 · isolate: GNSS 갱신 중단 · degrade: LIO+엔코더+IMU 로 계속 · recover: 밖에서 재고정·게이트 통과 후 보정", t_max=200, gnss=True)
sc("F07", "고장: 통신 지연/끊김", comm_zone, "x>15 m 20 kbps·6 s 지연, 120-160 s 완전 두절",
   "degrade: 정보밀도 높은 지도 타일만 전송(영상 중단) · 30 s 두절 → RETURN(통신 복귀 지점) · 자율 루프는 온보드라 계속", t_max=200,
   faults=dict(comm_loss=(120, 160)))
sc("F08", "고장: 저장 공간 한계", uneven, "저장 용량 0.45 GB 로 축소(원시 5.3 MB/s)",
   "85% → DEGRADED(원시 점 로그 중단, 압축 지도만) · 98% → RETURN", t_max=160, storage_B=0.45e9)
sc("F09", "고장: 배터리 부족", unknown, "가용 배터리 9.5 %로 출발", "귀환 필요 에너지(경로 Dijkstra×1.5)+8% 여유 아래로 → RETURN · 5% → EMERGENCY",
   t_max=300, soc=0.23075)
# ---- 기준선 4 (같은 세계·같은 시드·같은 안전층)
sc("B01", "기준선: 고정 웨이포인트", comparison, "잔디깎이 경로 4 m 간격", "순서대로 방문, 막힌 점은 건너뜀", t_max=240, method="fixed", aoi=(18, 14, 27, 26, 0.02))
sc("B02", "기준선: 무작위", comparison, "도달 가능한 무작위 목표", "도착하면 새 무작위 목표", t_max=240, method="random", aoi=(18, 14, 27, 26, 0.02))
sc("B03", "기준선: 프런티어(Yamauchi)", comparison, "가장 가까운 프런티어", "경로 비용 최소 프런티어로", t_max=240, method="frontier", aoi=(18, 14, 27, 26, 0.02))
sc("B04", "제안: 정보이득 J + fw 정책", comparison, "J = IG − λE·E − λT·T − λR·R", "탐사·재방문·정지관측을 효용으로 중재, 안전층 동일", t_max=240, method="proposed", aoi=(18, 14, 27, 26, 0.02))
# ---- 정책 행동 9
sc("P01", "정책: 고불확실 재방문", revisit_world, "담 뒤 σ 큰 셀", "관심구역 σ≤2 cm 를 처음 지날 때 먼지(25-70 s)로 LiDAR 가 열화 → 남은 σ 를 회복 후 REVISIT·OBSERVE 로 줄인다", t_max=240, aoi=(10, 5, 16, 25, 0.02), faults=dict(lidar_degrade=(25, 70, 4.0)))
sc("P02", "정책: 비용 대비 정보 — 먼 곳 포기", open_field, "구석의 작은 미지 구역", "IG 보다 에너지·시간 비용이 크면 J≤0 → 가지 않고 귀환", t_max=200)
sc("P03", "정책: 급경사 위험", steep, "31° 언덕", "지도 기울기 >25° = 치명 비용 · 올라탄 경우 tilt>0.8 → AVOID, ≥1 → SAFE_STOP", t_max=180)
sc("P04", "정책: 음장애(도랑)", ditch, "폭 0.9 m·깊이 0.5 m 도랑", "지도에서 바닥보다 12 cm 낮은 셀 → 위험 0.95 → 다리 쪽으로 재계획", t_max=200)
sc("P05", "정책: 동적 장애물", dynamic, "사람 2명이 왕복", "전방 점 높이 → 위험 >0.92 SAFE_STOP, 지나가면 재개. 지도 변화 감지로 흔적 제거", t_max=180)
sc("P06", "정책: 좁은 통로", narrow, "1.2 m 틈 (0.9 m 에선 통과 못 함)", "몸체 반폭 팽창 후 통과 가능한 경로만 · 통로 안 감속", t_max=180)
sc("P07", "정책: 막다른 길 복구", deadend, "U 자 함정", "프런티어 소멸 → J 재계산으로 되돌아 나옴 · 전방 막힘 AVOID", t_max=200)
sc("P08", "정책: 비상 정지(E-stop)", uneven, "70 s 에 원격 킬 스위치", "릴레이가 모터 전원 차단(하드웨어) → actuator_ok=0 → EMERGENCY · 로그는 계속", t_max=120,
   faults=dict(estop=(70, 999)))
sc("P09", "종합 데모 임무", demo, "미지 구역 + 모래 + 사람 + 도랑", "탐사→관측→재방문→회피→귀환 전 과정 (관심구역 σ≤2 cm)", t_max=300, aoi=(14, 18, 22, 26, 0.02))
SCENARIOS = S
