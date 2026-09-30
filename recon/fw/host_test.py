"""RECON 프로파일 결정 표 검사 — 각 guard 가 의도한 행동을 내는가, 결정적인가."""
import sys; sys.path.insert(0, __file__.rsplit("/fw/", 1)[0] + "/sim")
from fwpolicy import Policy, LIB
F = []
def ok(c, w):
    print(("  pass  " if c else "  FAIL  ") + w); c or F.append(w)
N = dict(j_explore=(0.6, 5, 5), j_revisit=(0.3, 1, 1), j_observe=(0.2, 0, 0), bat_need=0.1, battery=0.9)
def run(**kw):
    p = Policy(); a = dict(N); a.update(kw); return p.step(**a)
ok(run()["act"] == "EXPLORE", "정상: J 최대 = EXPLORE")
ok(run(j_revisit=(0.8, 1, 1))["act"] == "REVISIT", "재방문 J 가 크면 REVISIT")
ok(run(j_observe=(0.9, 0, 0))["act"] == "OBSERVE", "관측 J 가 크면 OBSERVE")
ok(run(actuator_ok=False)["act"] == "EMERGENCY", "구동계 고장 -> EMERGENCY")
ok(run(battery=0.04)["act"] == "EMERGENCY", "배터리 4% -> EMERGENCY")
ok(run(battery=0.17)["act"] == "RETURN", "배터리 < 귀환필요+여유 -> RETURN")
ok(run(collision=0.7)["act"] == "AVOID", "전방 위험 0.7 -> AVOID")
ok(run(collision=0.95)["act"] == "SAFE_STOP", "전방 위험 0.95 -> SAFE_STOP")
ok(run(slip=0.6)["act"] == "AVOID", "슬립 0.6 -> AVOID")
ok(run(tilt=1.05)["act"] == "SAFE_STOP", "경사 한계 초과 -> SAFE_STOP")
ok(run(pos_sigma=0.5)["act"] == "RELOCALIZE", "자세 σ 0.5 m -> RELOCALIZE")
ok(run(pos_sigma=1.5)["act"] == "SAFE_STOP", "자세 σ 1.5 m -> SAFE_STOP")
ok(run(health=(0, 1, 1, 1, 1))["act"] == "RETURN", "LiDAR 사망 -> RETURN(추측항법)")
ok(run(health=(0, 0, 0, 1, 1), imu_valid=False)["act"] == "SAFE_STOP", "항법 수단 전부 사망 -> SAFE_STOP")
r = run(health=(1, 1, 0, 1, 1)); ok(r["act"] == "EXPLORE" and r["safety"] == "DEGRADED", "엔코더 고장 -> 계속 + DEGRADED")
ok(run(storage=0.99)["act"] == "RETURN", "저장소 99% -> RETURN")
ok(run(link=1.2)["act"] == "RETURN", "링크 36 s 끊김 -> RETURN")
ok(run(coverage=0.95)["act"] == "RETURN", "커버리지 95% -> RETURN(임무 완료)")
ok(run(j_explore=(0, 0, 0), j_revisit=(0, 0, 0), j_observe=(0, 0, 0))["act"] == "RETURN", "후보 없음 -> RETURN")
# 결정성
import random
random.seed(1); seq = [dict(battery=random.random(), collision=random.random(), slip=random.random() * .6,
                           pos_sigma=random.random() * .6, j_explore=(random.random(), 1, 1)) for _ in range(500)]
a, b = Policy(), Policy()
ra = [a.step(**{**N, **s})["act"] for s in seq]; rb = [b.step(**{**N, **s})["act"] for s in seq]
ok(ra == rb, "같은 입력 500 스텝 -> 같은 행동열")
p = Policy(); p.step(**N); r = p.step(**{**N, "health": (1, 1, 0, 1, 1)})
ok("SENSOR_FAIL" in r["events"] and r["failed"] == ["ENC"], "건강 엣지 -> SENSOR_FAIL(ENC) 이벤트")
print("sizeof(Agent) =", LIB.recon_sizeof_agent(), "B")
print("FAIL", len(F) if F else "없음"); sys.exit(1 if F else 0)
