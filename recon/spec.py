"""RECON-R1: autonomous information / reconnaissance data-collection rover.
Single source of truth for the BOM, drawings, simulator, 3D model and report.
Every part is a real, currently-sold product; numbers marked [DS] are datasheet values
(to be verified in hw/bom_verified.json), [A] are design assumptions.
"""
import math

PARTS = {
    "compute":  dict(name="NVIDIA Jetson Orin Nano Super Developer Kit (8 GB)", role="SLAM/LIO, mapping, policy, logging",
                     power_W=(7, 25), iface="Ethernet(LiDAR), CSI(camera), USB3, M.2 NVMe", mass_g=176),
    "mcu":      dict(name="STM32H753ZI (ST NUCLEO-H753ZI; H743ZI2 is NRND)", role="motor PID, encoder capture, IMU, watchdog, E-stop logic, fw decision kernel host",
                     power_W=(0.5, 1.0), iface="4x quadrature timers, SPI(IMU), FDCAN, USB-CDC/UART to Jetson", mass_g=60),
    "lidar":    dict(name="Livox Mid-360", role="3D geometry (primary)", rate="200,000 pts/s, 10 Hz frame",
                     fov="360 x 59 deg", range_m=(0.1, 40), noise_cm=2.0, power_W=6.5, mass_g=265, iface="100BASE-TX Ethernet, PTP/PPS",
                     imu="built-in ICM40609 @200 Hz"),
    "imu":      dict(name="TDK InvenSense ICM-42688-P (SparkFun/Adafruit breakout)", role="high-rate yaw rate, tilt, slip detection on MCU",
                     rate_Hz=1000, gyro_noise_dps_rtHz=0.0028, accel_noise_ug_rtHz=70, iface="SPI", power_W=0.003),
    "camera":   dict(name="Raspberry Pi Camera Module v2 (Sony IMX219), CSI", role="live view, map colorisation, texture/quality cue",
                     res="3280x2464 (use 1280x720@30)", power_W=0.25, iface="MIPI CSI-2 (15->22 pin cable for Orin Nano devkit)"),
    "motor":    dict(name="Pololu 37D 50:1 metal gearmotor 24V with 64 CPR encoder (x4)", role="skid-steer drive",
                     rated_V=24, noload_rpm_24V=200, stall_A_24V=3.0, stall_Nm_24V=2.1,  # stall torque [A] (datasheet check pending)
                      encoder_cpr_motor=64, gear=50, mass_g=215),
    "driver":   dict(name="Cytron MDD20A dual 20 A motor driver (x2)", role="PWM H-bridge", V=(6, 30), I_cont_A=20),
    "battery":  dict(name="4S Li-ion 14.4 V 10 Ah pack (e.g. 18650 4S4P with BMS)", role="main power",
                     V_nom=14.4, V_max=16.8, V_min=12.0, Ah=10.0, mass_g=900),
    "gnss":     dict(name="u-blox ZED-F9P (SparkFun GPS-RTK2) + L1/L2 antenna", role="EXTENSION: outdoor absolute pose, PPS time",
                     rate_Hz=10, acc_m_rtk=0.01, acc_m_single=1.5, power_W=0.4, iface="UART/USB + PPS"),
    "storage":  dict(name="NVMe M.2 2280 SSD 512 GB", role="raw + compressed logs"),
    "jetson_feed": dict(name="Direct pack feed to Jetson DC jack (9-20 V input): 5 A fuse + ideal-diode (LTC4359) + 470 uF hold-up + LC filter",
                     role="compute rail; no DC-DC needed because pack 12.0-16.8 V is inside 9-20 V"),
    "dcdc_5":   dict(name="Pololu D36V50F5 5V 5.5A step-down", role="MCU, IMU, encoders, fans (camera is powered by the Jetson over CSI)"),
    "estop":    dict(name="Latching mushroom E-stop + 30 A automotive relay / contactor, 433 MHz wireless kill (secondary)",
                     role="cut motor power; logic stays alive to log"),
    "fuse":     dict(name="ATO blade fuses: 30 A main, 15 A per motor driver, 5 A compute, 3 A sensors"),
    "chassis":  dict(name="2020 aluminium extrusion frame + 3 mm aluminium deck, 4x 120 mm pneumatic/rubber wheels",
                     dims_mm=(450, 350, 150), wheel_d_mm=120, wheel_w_mm=40, wheelbase_mm=300, track_mm=400, mast_h_mm=420),  # track 330->400: 바퀴가 몸체 밖
}

# ---------------- mechanical ----------------
MECH = dict(
    L=0.45, W=0.35, H_body=0.15, ground_clear=0.041,   # 37D 모터 하단이 지상고를 정한다(60 -> 41 mm)
    wheel_r=0.060, wheelbase=0.30, track=0.40,
    lidar_h=0.60, lidar_x=0.05,          # LiDAR optical centre height above ground / forward offset
    lidar_inverted=True,                 # Mid-360 FOV -7..+52 deg upright -> -52..+7 inverted [설계 결정]
    lidar_fov_deg=(-52.0, 7.0),
    cam_h=0.35, cam_x=0.21, cam_pitch_deg=-10,
    imu_x=0.0, imu_y=0.0,
    mass_kg=7.5,                         # [A] frame 2.2 + motors 0.86 + battery 0.9 + electronics 1.2 + LiDAR 0.27 + wheels 1.2 + misc
    cog_h=0.16,                          # [A]
    max_slope_deg=None, tip_margin=None,
)
MECH["roll_over_deg"] = math.degrees(math.atan((MECH["track"] / 2) / MECH["cog_h"]))      # 옆 전복
MECH["pitch_over_deg"] = math.degrees(math.atan((MECH["wheelbase"] / 2) / MECH["cog_h"]))  # 앞뒤 전복 (더 작다)
MECH["max_slope_deg"] = min(MECH["roll_over_deg"], MECH["pitch_over_deg"])                 # 정적 전복 한계
MECH["tip_margin"] = MECH["max_slope_deg"] - 25.0                                          # 정책 한계 25° 대비 여유
MECH["lidar_blind_r_upright"] = MECH["lidar_h"] / math.tan(math.radians(7.0))
MECH["lidar_blind_r_inverted"] = MECH["lidar_h"] / math.tan(math.radians(52.0))
MECH["slope_limit_deg"] = 25.0          # [A] 동적 여유: 정적 전복각의 약 55 %, 정책 tilt=1 기준

# ---------------- drive ----------------
m = PARTS["motor"]
V_BAT = PARTS["battery"]["V_nom"]
rpm_out = m["noload_rpm_24V"] * V_BAT / m["rated_V"]                    # [A] linear with voltage
DRIVE = dict(
    v_noload=rpm_out / 60 * 2 * math.pi * MECH["wheel_r"],              # m/s
    v_cmd_max=0.5,                                                        # m/s mapping speed limit [A]
    w_cmd_max=1.0,                                                        # rad/s
    ticks_per_rev=m["encoder_cpr_motor"] * m["gear"],                     # quadrature 64 CPR counts both edges -> 3200/rev
)
DRIVE["dist_per_tick_mm"] = 2 * math.pi * MECH["wheel_r"] * 1000 / DRIVE["ticks_per_rev"]

# ---------------- power budget (W) ----------------
POWER = {  # (average, peak)
    "Jetson Orin Nano Super (15 W mode; 25 W mode peak)": (12.0, 25.0),
    "Livox Mid-360": (6.5, 14.0),   # peak = self-heating below 0 C
    "STM32H753 + IMU + camera(Jetson CSI)": (1.5, 2.0),
    "Motors x4 (cruise 0.3 m/s, rough)": (24.0, 4 * m["stall_A_24V"] * V_BAT / m["rated_V"] * V_BAT),  # stall I scales with V
    "Motor drivers, fans, relay": (2.0, 4.0),
    "GNSS (extension)": (0.4, 0.6),
}
P_AVG = sum(a for a, _ in POWER.values())
P_PEAK = sum(p for _, p in POWER.values())
E_WH = PARTS["battery"]["V_nom"] * PARTS["battery"]["Ah"] * 0.85         # usable (85 %)
RUNTIME_H = E_WH / P_AVG
I_PEAK = P_PEAK / PARTS["battery"]["V_min"]

# ---------------- data rates ----------------
DATA = dict(
    lidar_Bps=200_000 * 26,          # Livox custom point: x,y,z int32 + reflectivity u8 + tag u8 + line ... ~26 B incl. header share [A]
    imu_Bps=1000 * 32,
    enc_Bps=100 * 24,
    cam_Bps=1280 * 720 * 1.5 * 30 / 20,   # H.264 ~ 20:1 [A]
    gnss_Bps=10 * 100,
)
DATA["raw_Bps"] = sum(v for k, v in DATA.items() if k.endswith("_Bps"))

# ---------------- map ----------------
MAP = dict(cell=0.10, size_m=40.0, max_obs_range=12.0, var_min=0.0004, var_init=1.0)

if __name__ == "__main__":
    import json
    print(json.dumps(dict(MECH=MECH, DRIVE=DRIVE, POWER=POWER, P_AVG=P_AVG, P_PEAK=P_PEAK, E_WH=E_WH,
                          RUNTIME_H=RUNTIME_H, I_PEAK=I_PEAK, DATA=DATA), indent=1, default=str))
