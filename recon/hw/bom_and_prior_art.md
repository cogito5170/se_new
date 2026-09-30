# RECON-R1 — BOM 검증과 선행연구 (2026-09-29)

**확인 수준에 대해.** 벤더와 데이터시트 사이트(pololu, livoxtech, docs.nvidia, cdn.sparkfun, u-blox, mouser, cytron, arxiv, crossref)는 이 환경에서 WebFetch 가 **EGRESS_BLOCKED** 로 막혔다. 그래서 BOM 수치는 **전부 검색 조각 `[조각]`** 이다. 데이터시트를 직접 읽은 것은 하나도 없다. 선행연구 중 일부는 raw.githubusercontent.com 에서 **공식 저장소 README 의 인용 블록을 직접 읽었다** — `[README]` 로 표시했다. 이것은 논문 본문을 읽은 것이 아니다.

## 1. BOM 요약 (가격은 2026-09-29 검색 조각 기준)

| key | 부품 | 수량 | 단가 USD (min / typ) | 판매처 | 확인 |
|---|---|---|---|---|---|
| compute | Jetson Orin Nano Super Dev Kit 8GB | 1 | 249 / 249 | NVIDIA MSRP | [조각] |
| mcu | NUCLEO-H743ZI2 → **H753ZI** | 1 | 28.15 / 40.81 | DigiKey | [조각] |
| lidar | Livox Mid-360 (단종) / Mid-360S | 1 | 749 / 979 | DJI Store 외 | [조각] |
| imu | ICM-42688-P (Mikroe 6DOF IMU 14 Click) | 1 | 26.95 | SparkFun | [조각] |
| camera | Pi Camera v2 IMX219 | 1 | 16.50 | PiShop | [조각] |
| motor | Pololu #4693 50:1 24V 64CPR | 4 | 60.95 | Pololu/TME | [조각] |
| driver | Cytron MDD20A | 2 | 38.50 | Cytron | [조각] |
| battery | 4S Li-ion 14.4V 10Ah | 1 | 240 | 소매 조각 | [조각] |
| gnss | SparkFun GPS-RTK2 + L1/L2 안테나 | 1 | 326.90 / 369.90 | SparkFun | [조각] |
| storage | NVMe 500GB (Crucial P3 Plus) | 1 | 156.77 (비정상적으로 높음, 재확인 필요) | Newegg | [조각] |
| dcdc_19 | 12→19V 5A boost | 1 | 15.57 | eBay | [조각] |
| dcdc_5 | Pololu D36V50F5 | 1 | 39.95 | Pololu | [조각] |
| estop | 433MHz 30A 무선 릴레이(만) | 1 | 21.71 | eBay | [조각] |
| fuse | ATO 퓨즈·홀더 | – | null | – | 미확인 |
| chassis | 120mm 바퀴(만) goBILDA Rhino | 4 | 9.99 | goBILDA | [조각] |

**합계(가격이 확인된 품목만): min $2,231 / typical $2,517.** GNSS 를 빼면 $1,904 / $2,147 이다.
합계에 **들어가지 않은 것**: 퓨즈·홀더, 버섯형 E-stop과 컨택터, 2020 익스트루전과 데크, 6mm D축 허브, 15→22pin CSI 케이블, 배선·커넥터·충전기, 배송·세금.

## 2. spec.py 에서 틀렸거나 고칠 것

| 부품 | spec.py | 확인값 | 조치 |
|---|---|---|---|
| lidar | noise_cm=2.0 | ≤2 cm @10 m, **≤3 cm @0.2 m** (1σ) | 거리에 따라 달라지는 잡음 모델로 바꾼다 |
| lidar | POWER peak 8 W | 정상 동작 6.5 W, **0 °C 이하 자가발열 시 최대 14 W** | 저온 운용이면 peak 를 14 W 로 잡는다 |
| lidar | range 0.1–40 m | 40 m 는 **10 % 반사율** 조건. 80 %에서는 70 m | 조건을 명시한다 |
| lidar | 제품 | DJI Store 에 **discontinued** 로 표시 | Mid-360S 로 바꾼다 |
| motor | 200 rpm / 3 A @24 V | **일치**(Pololu #4693) | – |
| motor | 14.4 V 로 구동 | 선형 환산하면 ~120 rpm, 스톨 ~1.8 A, 토크 ~13.8 kg·cm(데이터시트의 60 %) | POWER peak 173 W 는 과대하다(~104 W). 등판 여유는 60 % 토크로 다시 계산한다 |
| motor | mass 215 g | 미확인. TME 총중량 223 g 은 포장 포함일 수 있다 | – |
| compute | "15 W mode (12, 25)" | 모드는 7 / 15 / 25 W / **MAXN SUPER**. peak 25 W 는 25W 모드의 값이다 | 모드를 하나로 정해 표를 맞춘다 |
| compute | 19 V buck-boost 레일 | DC 잭 입력이 **9–20 V**(최대 3 A, 공급 어댑터 19 V)이고 캐리어 예산은 45 W | 4S(12–16.8 V)를 직결할 수 있다. 레일을 둔다면 16.8 V < 19 V 이므로 **boost 만으로 충분**하다 |
| mcu | NUCLEO-H743ZI2 | **NRND/Obsolete** | NUCLEO-H753ZI 로 바꾼다(코드 무수정) |
| gnss | power 0.2 W | 보드 68–130 mA → 3.3 V 기준 **0.22–0.43 W**, 여기에 안테나 LNA 가 더해진다 | 값을 올린다 |
| gnss | acc_single 1.5 m | 데이터시트 판에 따라 1.5 m 또는 2.0 m CEP | 미해결 |
| gnss | 안테나 L1/L2 | ANN-MB-00 은 SparkFun 에서 단종. **ANN-MB5 는 L1/L5 라 호환되지 않는다** | L1/L2 안테나를 명시한다 |
| camera | CSI | devkit 은 **22-pin**, Pi Cam v2 는 15-pin | 변환 케이블을 BOM 에 넣는다 |
| camera | 0.25 W | 피크 300 mA(전압 조건 미확인) | 과소일 수 있다 |
| imu | SparkFun breakout | SparkFun 브랜드 ICM-42688-P 보드는 검색에서 찾지 못했다(Mikroe Click 만 있음) | 보드명을 고친다 |
| battery | BMS | 예시로 찾은 Tenergy 팩은 6 A PCB 다 | BMS 연속전류가 모터 피크를 감당하는지 확인한다 |
| chassis | 120 mm 바퀴 | goBILDA 바퀴는 14/32 mm 보어다 | 6 mm D축 허브를 추가한다 |
| estop | 433 MHz 킬 | 소비자용 릴레이라 신호를 잃어도 차단되지 않는다 | '보조'로만 쓴다 |

## 3. 부품별 대안 (가격 null = 미확인)

| 부품 | 대안 | 트레이드오프 |
|---|---|---|
| compute | Orin NX 16GB 또는 RPi 5 | NX: 성능·메모리가 오르고 비싸다. RPi 5: 싸지만 CUDA 가 없어 cupy 고도맵을 못 쓴다 |
| mcu | NUCLEO-H753ZI $40.81 | ST 공식 대체품 |
| lidar | Mid-360S $799+ | 치수·질량·전력이 같다. 80 % 반사율에서 100 m, 간섭 내성이 좋아진다 |
| imu | Mid-360 내장 ICM40609 | $0. 대신 MCU 쪽 1 kHz 슬립 경로가 사라진다 |
| camera | Pi Camera Module 3 | AF·HDR. Orin 에서의 드라이버 지원은 미검증 |
| motor | Pololu #4753 (12 V 판) | 4S 전압에 맞는 권선이라 정격 속도·토크를 다 쓴다. 전류는 커진다 |
| driver | Cytron MDD10A | 스톨이 ≤3 A 라 10 A 로 충분하다 |
| battery | 4S LiFePO4 | 안전하고 수명이 길다. 무게가 늘고 전압이 낮다 |
| gnss | 제거(실내·숲) | $370 을 아낀다. 절대좌표와 PPS 를 잃는다 |
| dcdc_19 | 직결 + TVS·LC 필터 | 부품이 줄고 효율이 오른다. 모터 서지 대책이 필수다 |
| dcdc_5 | D36V28F5 3.2 A | 5 V 부하가 3 A 미만이면 충분하다 |
| chassis | goBILDA 킷 | 조립 시간이 준다. Strafer 는 메카넘이다($499.99) |

## 4. 선행연구

| 주제 | 문헌 | ID | 확인 |
|---|---|---|---|
| 프런티어 탐사 | Yamauchi, "A frontier-based approach for autonomous exploration", CIRA 1997, pp.146–151 | DOI 10.1109/CIRA.1997.613851 | [조각] |
| 정보이득 탐사 | Stachniss, Grisetti, Burgard, "Information Gain-based Exploration Using RBPF", RSS 2005 | DOI 10.15607/RSS.2005.I.009 | [조각] |
| NBV 탐사 | Bircher et al., "Receding horizon next-best-view planner for 3D exploration", ICRA 2016, pp.1462–1468 | DOI 10.1109/ICRA.2016.7487281 | [README](ethz-asl/nbvplanner) + [조각] |
| 고도맵(불확실성) | Fankhauser et al., "Robot-Centric Elevation Mapping with Uncertainty Estimates", CLAWAR 2014 | DOI 10.3929/ethz-a-010173654 | [README] |
| 고도맵 | Fankhauser, Bloesch, Hutter, "Probabilistic Terrain Mapping for Mobile Robots with Uncertain Localization", RA-L 3(4) 2018 | DOI 10.1109/LRA.2018.2849506 | [README] |
| GPU 고도맵 | Miki et al., "Elevation Mapping for Locomotion and Navigation using GPU", IROS 2022 | arXiv 2204.12876 | [README] |
| LIO | Xu et al., "FAST-LIO2", IEEE T-RO 2022 | arXiv 2107.06829 | [조각] (README 는 제목만 있음) |
| LIO | Shan et al., "LIO-SAM", IROS 2020, pp.5135–5142 | arXiv 2007.00258 | [README] + [조각] |
| GNSS-VIO | Cao, Lu, Shen, "GVINS" | arXiv 2103.07899 (게재지 미확인) | [README] |
| 3D 점유맵 | Hornung et al., "OctoMap", Auton. Robots 34:189–206, 2013 | DOI 10.1007/s10514-012-9321-0 | [조각] |
| TSDF/ESDF | Oleynikova et al., "Voxblox", IROS 2017 | arXiv 1611.03631 | [README] + [조각] |
| SubT 탐사 | Dang et al., "Graph-based subterranean exploration path planning…" (GBPlanner), JFR 37(8):1363–1388, 2020 | DOI 미확인 | [README] |
| SubT 탐사 | Cao, Zhu, Choset, Zhang, "TARE", RSS 2021 | DOI 10.15607/RSS.2021.XVII.018 | [README] + [조각] |
| SubT 시스템 | Tranzatto et al., "CERBERUS in the DARPA SubT Challenge", Sci. Robot. 2022 / "Team CERBERUS Wins…" | DOI 10.1126/scirobotics.abp9742 / arXiv 2207.04914 | [조각] |
| 스키드 슬립 | Yi et al., "Kinematic Modeling and Analysis of Skid-Steered Mobile Robots…", IEEE T-RO 2009 | DOI 10.1109/TRO.2009.2026506 | [조각] |
| 스키드 슬립 | Yi et al., "IMU-based localization and slip estimation for skid-steered mobile robots", IROS 2007 | DOI 미확인 | [조각] |
| 스키드 운동학 | Mandow et al., "Experimental kinematics for wheeled skid-steer mobile robots", 2007 | DOI 미확인 | [조각] (다른 논문의 참고문헌으로만 봤다) |

찾아본 질의(일부):
1. `Yamauchi 1997 "A frontier-based approach for autonomous exploration" CIRA DOI`
2. `Stachniss Grisetti Burgard 2005 information gain-based exploration using Rao-Blackwellized particle filters RSS`
3. `FAST-LIO2 Fast Direct LiDAR-Inertial Odometry arXiv 2107.06829 IEEE T-RO 2022 DOI`
4. `TARE hierarchical framework exploring complex 3D environments RSS 2021 DOI … ; Miki elevation mapping GPU arXiv 2204.12876`
5. `skid-steer mobile robot slip estimation kinematic model ICR paper Mandow 2007 Yi 2009 IMU slip`
6. `CERBERUS DARPA Subterranean Challenge winning team arXiv 2022 Tranzatto field robotics`
7. raw.githubusercontent.com README 11개: FAST_LIO, elevation_mapping(_cupy), voxblox, octomap, tare_planner, gbplanner_ros, LIO-SAM, GVINS, nbvplanner, livox_ros_driver2

## 5. 검증하지 못한 것

- **데이터시트 본문은 하나도 읽지 못했다.** 모든 사양이 검색 조각 수준이다.
- 가격이 없는 품목: 퓨즈·홀더, 버섯형 E-stop, 30 A 컨택터, 2020 익스트루전·데크, 6 mm 허브, CSI 변환 케이블, 12 V 모터 판, MDD10A, D36V28F5, Orin NX, Pi Cam 3, LiFePO4 팩, 256 GB SSD.
- 확인하지 못한 수치:
  - MCU 전력과 질량(spec 의 60 g)
  - 모터 순질량(215 g)
  - ICM40609 잡음 사양
  - Pi Cam v2 소비전력 조건
  - ZED-F9P 단독측위 정확도 1.5 m 와 2.0 m 중 어느 쪽인지
  - Orin Nano devkit NVMe 슬롯의 PCIe 세대
  - 12 V 모터(#4753)의 스톨 전류
- 가격 신뢰도:
  - NVMe 500GB 가 $157 로 나왔다. 조각이 과거 값이거나 이상치일 수 있어 벤더 페이지에서 다시 확인해야 한다.
  - Mid-360 의 $749 는 제3자 블로그 조각이다.
- 선행연구:
  - Mandow 2007 과 Yi 2007 의 DOI, GBPlanner JFR 의 DOI, GVINS 게재지를 확인하지 못했다.
  - 스키드 슬립은 2007–2009 이후 문헌(학습 기반, MI-UKF 등)을 **아직 조사하지 않았다.**
  - "가장 가까운 선행연구"도 아직 확정하지 않았다. 탐사 + 불확실성 고도맵 + 소형 스키드 로버를 조합한 시스템 논문을 찾는 검색은 하지 않았다.
