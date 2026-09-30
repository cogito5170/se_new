"""RECON-R1 (자율 정찰 로버) 정책 커널·시뮬 부품·도구 배선을 붙든다. LLM·디스코드·브라우저 없이 돈다.

붙드는 것 -- 이 작업 중 **실제로 난** 버그가 되살아나지 않게 (recon/knowledge.md §4):
  7. EKF 과신: 공분산이 작은 채로 좋은 LIO 를 NIS 게이트가 계속 버려 3.3 m 틀렸다
     -> 연속 3회 기각이면 발산으로 보고 공분산을 부풀려 받아들인다.
  8. 지형 위험의 벽 팽창: 1.2 m 틈이 계획상 막혔다 -> 계단은 높은 셀에만, 45° 넘는 기울기는 경사에서 뺀다.
 10. 배터리 귀환 guard 가 걸쇠가 아니었다 -> SAFE_RETURN 동안 +5 % 이력.
 11. 배터리 비율: 만충이 1.055 로 잘려 처음 7 Wh 동안 100 % -> 만충 = 정확히 1.0.
그리고: C 커널 결정 표(호스트 검사 21개), 결과 요약·답 도구, 봇 배선·배포 경로.
실행: python3 tests/test_recon.py
"""
from __future__ import annotations

import ast
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

뿌리 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(뿌리))
os.environ["RECON_OUT"] = tempfile.mkdtemp(prefix="recontest-")   # 빌드·산출물을 저장소 밖에
sys.path.insert(0, str(뿌리 / "recon" / "sim"))

import numpy as np  # noqa: E402

FAIL = []


def ok(c, what):
    print(("  통과  " if c else "  실패  ") + what)
    if not c:
        FAIL.append(what)


print("== C 결정 커널 (SE fw 커널 + profile_recon.c) ==")
r = subprocess.run([sys.executable, str(뿌리 / "recon" / "fw" / "host_test.py")], capture_output=True, text=True, timeout=300)
ok(r.returncode == 0 and "FAIL 없음" in r.stdout, f"호스트 결정 검사 전부 통과 ({r.stdout.count('pass')}개)")
from fwpolicy import Policy  # noqa: E402

N = dict(j_explore=(0.6, 5, 5), bat_need=0.10)
p = Policy()
a1 = p.step(**N, battery=0.17)["act"]                    # 0.17 < 0.10+0.08 -> 귀환 시작
a2 = p.step(**N, battery=0.21)["act"]                    # 걸쇠: 0.21 < 0.10+0.08+0.05 -> 계속 귀환
a3 = Policy().step(**N, battery=0.21)["act"]              # 처음부터 0.21 이면 귀환 아님
ok(a1 == "RETURN" and a2 == "RETURN" and a3 != "RETURN", f"배터리 귀환은 걸쇠 (시작 {a1} · 이어서 {a2} · 새로 {a3})")

print("\n== 배터리 비율 ==")
from rover import Battery  # noqa: E402
ok(abs(Battery(1.0).usable() - 1.0) < 1e-9, "만충 = 가용 비율 정확히 1.0 (첫 판은 1.055 를 잘라 처음 7 Wh 동안 100 %)")
b = Battery(1.0); b.draw(46.0, 3600 * 0.1)
ok(b.usable() < 1.0, "쓰면 바로 줄어든다")

print("\n== EKF 발산 감지 ==")
from estimation import Estimator  # noqa: E402
e = Estimator("proposed", 0.0, 0.0, 0.0)
e.P[:3, :3] = np.diag([1e-4, 1e-4, 1e-5])                 # 과신한 상태
C = np.diag([0.03 ** 2, 0.03 ** 2, math.radians(0.3) ** 2])
z = np.array([3.0, 0.0, 0.0])                             # 실제로는 3 m 떨어져 있다
for _ in range(3):
    e.update_lio(z, C, 0.1)
ok(abs(e.s[0] - 3.0) < 0.3 and e.resets >= 1, f"연속 기각 3회 뒤 받아들인다 (x={e.s[0]:.2f}, 재설정 {e.resets})")
e2 = Estimator("proposed", 0.0, 0.0, 0.0); e2.P[:3, :3] = np.diag([1e-4, 1e-4, 1e-5])
e2.update_lio(z, C, 0.1)
ok(abs(e2.s[0]) < 1e-6, "한 번 튄 값은 여전히 버린다 (게이트는 살아 있다)")

print("\n== 벽 팽창: 1.2 m 틈이 계획상 열려 있어야 한다 ==")
from mapping import ElevationMap  # noqa: E402
from planning import Planner  # noqa: E402
m = ElevationMap(30.0)
m.var[:, :] = 0.01 ** 2; m.h[:, :] = 0.0
i0, i1 = int(12.0 / m.res), int(12.4 / m.res)
m.h[i0:i1, :] = 1.0                                        # 벽
m.h[i0:i1, int(14.4 / m.res):int(15.6 / m.res)] = 0.0      # 1.2 m 틈
pl = Planner(m, (1, 1, 29, 29)); pl.update(8.0, 15.0)
ok(np.isfinite(pl.dist[pl.ci(16.0, 15.0)]), "벽 너머(16,15)에 경로가 있다")
m.h[i0:i1, int(14.55 / m.res):int(15.45 / m.res)] = 1.0; m.h[i0:i1, int(14.6 / m.res):int(15.4 / m.res)] = 0.0
pl2 = Planner(m, (1, 1, 29, 29)); pl2.update(8.0, 15.0)
ok(np.isfinite(pl2.dist[pl2.ci(16.0, 15.0)]), "깨끗한 지도에서는 0.8 m 틈도 계획상 열린다 -- 시뮬의 0.9 m 불통은 계획 여유 탓이 아니다(벽 번짐 + 전방 위험)")

print("\n== 결과 요약 · 답 도구 ==")
from recon import answer  # noqa: E402
s = answer.부르기("요약")
ok("실측 아님" in s and "기준선" in s and "통로" in s, "요약에 출처(실측 아님)·기준선·통로가 있다")
ok("표준편차" in answer.부르기("기준선"), "기준선 답이 과장하지 않는다 (제안 vs 무작위는 표준편차 안팎)")
ok(len(answer._s()["scenarios"]) == 30, "시나리오 30개가 요약에 있다")
ok("F09" in answer.부르기("시나리오", "F09"), "시나리오 ID 로 묻는다")

print("\n== 배선 ==")
src = (뿌리 / "bot_tools.py").read_text(encoding="utf-8")
tree = ast.parse(src)
names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
ok({"recon_rover", "recon_make"} <= names, "bot_tools 에 recon_rover · recon_make")
for f in ("discord_bot_server.py", "main_public.py"):
    t = (뿌리 / f).read_text(encoding="utf-8")
    ok(t.count("recon_rover") >= 2 and t.count("recon_make") >= 2, f"{f}: 임포트 + 도구 목록")
wf = (뿌리 / ".github/workflows/deploy-oracle.yml").read_text(encoding="utf-8")
ok('"recon/**"' in wf, "배포 경로 recon/**")
ok("inbox/recon/" in (뿌리 / ".gitignore").read_text(encoding="utf-8"), "산출물 자리는 무시된다")
# 2026-09-30: 기억 노트는 git 에 남기지 않는다(.gitignore) -- 체크아웃(CI)에는 없고 봇이 도는 기계에만 있다.
# 그래서 "6개 있다" 는 이제 여기서 못 잰다. 있으면(그 기계) 머리말 꼴을 보고, git 이 안 받는다는 것을 본다.
mem = list((뿌리 / "public_agent_memory").glob("20260929-1350*_*.md"))
ok(all(x.read_text(encoding="utf-8").startswith("---\ntopic:") for x in mem), f"RAG 노트 {len(mem)}개 -- 있으면 머리말 형식")
import subprocess  # noqa: E402
ok(subprocess.run(["git", "check-ignore", "-q", "public_agent_memory/20260929-135000_x.md"], cwd=뿌리).returncode == 0,
   "기억 노트는 git 에 안 남는다(대화 · 기록물은 기계에만)")

print(f"\n{'실패 ' + str(len(FAIL)) if FAIL else '전부 통과'}")
sys.exit(1 if FAIL else 0)
