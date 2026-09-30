"""ctypes 래퍼: libfw_recon.so (SE fw 커널 + profile_recon.c) 를 부른다."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
from recon import paths  # noqa: E402
import ctypes as C
from pathlib import Path

from recon import fwbuild  # noqa: E402
LIB = C.CDLL(str(fwbuild.build()))   # SE fw 커널 + profile_recon.c (없거나 낡았으면 짓는다)
ACTIONS = ["HOLD", "EXPLORE", "OBSERVE", "REVISIT", "RETURN", "AVOID", "RELOCALIZE", "SAFE_STOP", "EMERGENCY"]
SAFETY = ["NORMAL", "DEGRADED", "RETURN", "EMERGENCY"]
MODES = ["SURVEY", "INVESTIGATE", "RETURN", "RECOVERY", "EMERGENCY"]
SENS = ["LIDAR", "IMU", "ENC", "CAM", "GNSS"]
EV = ["NONE", "SENSOR_FAIL", "SENSOR_RECOVER", "COLLISION", "BATTERY_LOW", "TARGET", "MODE", "ACTUATOR_FAIL", "SENSOR_STALE"]


class ReconIn(C.Structure):
    _fields_ = [("cand", (C.c_float * 3) * 5), ("health", C.c_float * 5), ("battery", C.c_float),
                ("collision", C.c_float), ("pos_sigma", C.c_float), ("gps_valid", C.c_int),
                ("imu_valid", C.c_int), ("actuator_ok", C.c_int)]


class ReconOut(C.Structure):
    _fields_ = [(n, C.c_int) for n in ("bt", "arb", "act", "safety", "mode", "plan_ticks", "ev_mask", "ev_sensor_mask")]


LIB.recon_new.restype = C.c_void_p
LIB.recon_free.argtypes = [C.c_void_p]
LIB.recon_step.argtypes = [C.c_void_p, C.POINTER(ReconIn), C.POINTER(ReconOut)]
LIB.recon_step.restype = C.c_int
LIB.recon_sizeof_agent.restype = C.c_int


class Policy:
    def __init__(self):
        self.h = LIB.recon_new()

    def __del__(self):
        try:
            LIB.recon_free(self.h)
        except Exception:
            pass

    def step(self, *, j_explore=(0, 0, 0), j_revisit=(0, 0, 0), j_observe=(0, 0, 0), coverage=0.0, bat_need=0.0,
             storage=0.0, slip=0.0, link=0.0, tilt=0.0, health=(1, 1, 1, 1, 1), battery=1.0, collision=0.0,
             pos_sigma=0.05, gps_valid=True, imu_valid=True, actuator_ok=True):
        i = ReconIn()
        for k, v in enumerate([j_explore, j_revisit, j_observe, (coverage, bat_need, storage), (slip, link, tilt)]):
            for m in range(3):
                i.cand[k][m] = float(v[m])
        for k in range(5):
            i.health[k] = float(health[k])
        i.battery, i.collision, i.pos_sigma = battery, collision, pos_sigma
        i.gps_valid, i.imu_valid, i.actuator_ok = int(gps_valid), int(imu_valid), int(actuator_ok)
        o = ReconOut()
        LIB.recon_step(self.h, C.byref(i), C.byref(o))
        return dict(bt=ACTIONS[o.bt], arb=ACTIONS[o.arb], act=ACTIONS[o.act], safety=SAFETY[o.safety],
                    mode=MODES[o.mode], ticks=o.plan_ticks,
                    events=[EV[b] for b in range(9) if o.ev_mask >> b & 1],
                    failed=[SENS[b] for b in range(5) if o.ev_sensor_mask >> b & 1])
