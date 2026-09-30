#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fw ctypes 브리지(libfw.so) + 런타임 확인창 설정을 검사(네트워크 불필요).

sar V&V 하네스가 쓰는 그 브리지를 직접 구동해, 외로운 센서는 확인 안 되고 코로보는 확인되며
확인창 N 이 실제로 먹는지 본다. gcc/make 없으면 건너뛴다(환경 한정)."""
from __future__ import annotations
import ctypes
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FW = os.path.join(REPO, "fw")
fails = []


def ok(cond, label):
    print(f"    {'OK  ' if cond else '실패'} {label}")
    if not cond:
        fails.append(label)


def _step(lib, h, ev, xs, ys, pres):
    cf = (ctypes.c_float * 5); ci = (ctypes.c_int * 5)
    health = [1.0] * 5
    px = ctypes.c_float(); py = ctypes.c_float(); conf = ctypes.c_int(); tc = ctypes.c_float()
    nis = ctypes.c_float()
    lib.fw_bridge_step(h, cf(*ev), cf(*xs), cf(*ys), ci(*pres), cf(*health),
                       ctypes.c_float(1.0), ctypes.c_float(0.0), ctypes.c_int(1), ctypes.c_int(1),
                       ctypes.c_float(0.0), ctypes.c_int(0), ctypes.c_float(0.0), ctypes.c_float(0.0),
                       ctypes.byref(px), ctypes.byref(py),
                       ctypes.byref(conf), ctypes.byref(tc), ctypes.byref(nis))
    return conf.value, tc.value


def test_bridge():
    if shutil.which("make") is None or (shutil.which("cc") is None and shutil.which("gcc") is None):
        print("    건너뜀: make/cc 없음(환경 한정)")
        return
    r = subprocess.run(["make", "-C", FW, "lib"], capture_output=True, text=True)
    ok(r.returncode == 0, "libfw.so 빌드")
    if r.returncode != 0:
        print(r.stdout + r.stderr); return
    lib = ctypes.CDLL(os.path.join(FW, "libfw.so"))
    lib.fw_bridge_new.restype = ctypes.c_void_p
    lib.fw_bridge_free.argtypes = [ctypes.c_void_p]
    lib.fw_bridge_set_confirm.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_float]
    fp = ctypes.POINTER(ctypes.c_float); ip = ctypes.POINTER(ctypes.c_int)
    lib.fw_bridge_step.argtypes = [ctypes.c_void_p, fp, fp, fp, ip, fp, ctypes.c_float,
                                   ctypes.c_float, ctypes.c_int, ctypes.c_int, ctypes.c_float,
                                   ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                   fp, fp, ip, fp, fp]
    lib.fw_bridge_step.restype = ctypes.c_int

    # 확인창 N=1: 외로운 Audio 는 신뢰 부족으로 확인 안 됨
    h = lib.fw_bridge_new(); lib.fw_bridge_set_confirm(h, 1, ctypes.c_float(0.6))
    c, tc = _step(lib, h, [0, 0, 0, 0, 0.9], [0, 0, 0, 0, 10], [0, 0, 0, 0, 10], [0, 0, 0, 0, 1])
    ok(c == 0 and tc < 0.6, "외로운 Audio(N=1)도 확인 안 됨(신뢰 %.3f)" % tc)
    lib.fw_bridge_free(h)

    # 확인창 N=1: RGB+Thermal 코로보는 한 스텝에 확인
    h = lib.fw_bridge_new(); lib.fw_bridge_set_confirm(h, 1, ctypes.c_float(0.6))
    c, tc = _step(lib, h, [0.9, 0.8, 0, 0, 0], [10, 10.2, 0, 0, 0], [10, 9.9, 0, 0, 0], [1, 1, 0, 0, 0])
    ok(c == 1 and tc >= 0.6, "RGB+Thermal 코로보(N=1)는 확인(신뢰 %.3f)" % tc)
    lib.fw_bridge_free(h)

    # 확인창 N=3: 같은 코로보라도 한 스텝만으론 확인 안 됨(시간창 실제로 먹는다)
    h = lib.fw_bridge_new(); lib.fw_bridge_set_confirm(h, 3, ctypes.c_float(0.6))
    c1, _ = _step(lib, h, [0.9, 0.8, 0, 0, 0], [10, 10.2, 0, 0, 0], [10, 9.9, 0, 0, 0], [1, 1, 0, 0, 0])
    ok(c1 == 0, "확인창 N=3: 한 스텝만으론 확인 안 됨")
    for _ in range(2):
        c3, _ = _step(lib, h, [0.9, 0.8, 0, 0, 0], [10, 10.2, 0, 0, 0], [10, 9.9, 0, 0, 0], [1, 1, 0, 0, 0])
    ok(c3 == 1, "확인창 N=3: 연속 3스텝이면 확인(런타임 설정 먹음)")
    lib.fw_bridge_free(h)
    subprocess.run(["make", "-C", FW, "clean"], capture_output=True, text=True)


if __name__ == "__main__":
    test_bridge()
    if fails:
        print("\n실패 %d개:" % len(fails))
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\nfw 브리지 검사 통과(외로운센서 억제·코로보 확인·확인창 런타임설정)")
