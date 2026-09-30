"""SE fw 결정 커널 + RECON 프로파일 -> libfw_recon.so (호스트, ctypes 용) 와 freestanding 크기 측정.
저장소 fw/ 는 읽기만 한다. 결과물은 inbox/recon/build 에."""
from __future__ import annotations

import subprocess
from pathlib import Path

from recon import paths

KERNEL = ["blackboard.c", "estimator.c", "evidence.c", "bt.c", "event.c", "safety.c", "arbiter.c", "decision.c", "planner.c", "agent.c"]
FWD = paths.PKG / "fw"


def sources():
    return [str(paths.FW_KERNEL / k) for k in KERNEL]


def build(force: bool = False) -> Path:
    paths.ensure()
    srcs = [FWD / "recon_bridge.c", FWD / "profile_recon.c"]
    newest = max(p.stat().st_mtime for p in srcs + [Path(s) for s in sources()])
    if paths.LIB.exists() and not force and paths.LIB.stat().st_mtime >= newest:
        return paths.LIB
    cmd = ["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared", f"-I{paths.FW_KERNEL}", "-o", str(paths.LIB),
           *map(str, srcs), str(paths.FW_KERNEL / "profile_sar.c"), str(paths.FW_KERNEL / "profile_min.c"), *sources(), "-lm"]
    subprocess.run(cmd, check=True)
    return paths.LIB


def footprint() -> str:
    """-ffreestanding 로 커널 10 + recon 프로파일을 컴파일하고 size 를 돌려준다(호스트 x86 기준)."""
    d = paths.BUILD / "ft"
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gcc", "-std=c99", "-O2", "-ffreestanding", "-Wall", "-Wextra", "-Werror", f"-I{paths.FW_KERNEL}", "-c",
                    str(FWD / "profile_recon.c"), *sources()], cwd=d, check=True)
    r = subprocess.run("size -t *.o", shell=True, cwd=d, capture_output=True, text=True, check=True)
    return r.stdout


if __name__ == "__main__":
    print(build(force=True)); print(footprint())
