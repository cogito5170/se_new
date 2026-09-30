"""RuH2-P1 (Ru 수소 전극 Ni-H2 배터리) 모델·도구 배선을 붙든다. LLM·디스코드 없이 돈다.

붙드는 것 -- 이 작업 중 **실제로 난** 두 버그가 되살아나지 않게:
  1. back-to-back 스택은 Ni 전극 하나가 Ru 전극 **두 장**을 본다. 첫 판 spec 은 한 장만 셌다
     (수소 전극 64.5 cm² · Ru 32 mg 로 틀림 -> 128.9 cm² · 64.5 mg). 도면 작업이 잡았다.
  2. 방전 말단에 Ni 공급 한계가 없어서 1.0 V 종지를 잡기 전에 셀이 역전됐다(웹 시뮬레이터가
     표준 사이클에서 '인터록 트립' 을 띄워 드러났다). 표준 사이클은 트립 없이 끝나야 한다.
그리고: 질량수지·닫힌 식(구현 검사), 산화 대책의 방향, JS 이식 일치, 도구·배포 배선.
실행: python3 tests/test_ruh2.py
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

뿌리 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(뿌리))
임시 = tempfile.mkdtemp(prefix="ruh2test-")
os.environ["RUH2_OUT"] = 임시                     # 산출물을 저장소 밖에 -- 검사는 재는 것이지 남기는 것이 아니다

import numpy as np  # noqa: E402

from ruh2 import analysis, spec  # noqa: E402
from ruh2 import model as N  # noqa: E402

FAIL = []


def ok(c, what):
    print(("  통과  " if c else "  실패  ") + what)
    if not c:
        FAIL.append(what)


print("== 사양 (버그 1) ==")
C, V = spec.CELL, spec.VESSEL
ok(abs(C["h2_area_cm2"] - 2 * C["n_units"] * C["face_area_cm2"]) < 1e-9, f"수소 전극 면적 = 2 x unit x 면 = {C['h2_area_cm2']:.1f} cm²")
ok(abs(C["ru_total_mg"] - 64.47) < 0.05, f"Ru 총량 {C['ru_total_mg']:.2f} mg")
ok(4.3 < V["p_full_bar_abs_25C"] < 4.7 and V["p_full_bar_abs_25C"] < spec.LIMITS["p_max_oper_bar_abs"], f"완충 압력 {V['p_full_bar_abs_25C']:.2f} bar < 운전 상한")
ok(V["p_trip_bar_abs"] < V["p_relief_bar"] < V["p_burst_disk_bar"] < V["p_design_bar"] < V["p_proof_bar"], "압력 안전 계층이 오름차순")
ok(V["allow_316L_MPa"] / V["hoop_stress_MPa_at_design"] > 4, f"후프응력 여유 x{V['allow_316L_MPa'] / V['hoop_stress_MPa_at_design']:.1f}")

print("\n== 표준 사이클 (버그 2) ==")
r = analysis.사이클()
ok(not r["trip"], "C/2 표준 사이클은 인터록 트립 없이 끝난다")
ok(r["V_min"] > 0.98, f"최저 전압 {r['V_min']:.3f} V -- 역전(-0.2 V) 없이 1.0 V 종지")
ok(0.70 < r["EE"] < 0.86 and 0.8 < r["CE"] < 0.95, f"효율 EE {r['EE']:.3f} · CE {r['CE']:.3f} 이 Ni-H2 범위")
ok(r["eta_h2_mV"] < 5, f"Ru 과전압 {r['eta_h2_mV']:.2f} mV -- 손실은 Ni·옴이 지배")

print("\n== 구현 검사 (같은 식이라 물리 검증은 아님) ==")
st = N.init()
rows, _ = N.run([("cc", 0.5, {"s_in": 1.1}), ("rest", 0, {"t": 3600}), ("cc", -0.5, {"V_min": 1.0})], st)
c = N.cols(rows)
n = np.array([N.n_from_p(p, T) for p, T in zip(c["p"], c["T"])])
dn = np.cumsum((c["I"] / (2 * N.F) - 2 * c["I"] * np.where(c["I"] > 0, c["f_oer"], 0) / (4 * N.F) - c["I_rev"] / (2 * N.F) - c["r_sd"] * N.P["Q_C"] / (2 * N.F)) * c["h"])
ok(np.max(np.abs((n - n[0]) - np.concatenate([[0], dn[:-1]]))) < 1e-9, "H2 질량수지")
slope = np.polyfit(c["s"], c["p"] * 298.15 / c["T"], 1)[0]
ok(abs(slope - V["dp_full_bar_25C"]) < 1e-6, f"압력-SOC 기울기 = 닫힌 식 {V['dp_full_bar_25C']:.3f} bar/Ah (정의상)")

print("\n== Ru 산화 대책의 방향 ==")
a0, e0, _ = analysis.고장(precharge=False, protect=False)
a1, e1, _ = analysis.고장(precharge=True, protect=False)
a2, _, how = analysis.고장(precharge=False, protect=True)
ok(a0 < 0.01 and e0 > 0.4, f"대책 없음: Ru {a0 * 100:.0f} % (H2 결핍으로 {e0:.2f} V)")
ok(a1 > 0.99 and e1 <= 0.4, "H2 예충전만으로 막는다")
ok(a2 > 0.99 and "0.9" in how, "HW 0.9 V 래치만으로 막는다")

print("\n== 분석 글 ==")
for k in ("사양", "사이클", "ru_pt", "산화대책", "자가방전대책", "실험설계", "지식"):
    t = analysis.부르기(k)
    ok(isinstance(t, str) and len(t) > 80 and "모르는 항목" not in t, f"{k}: {len(t)}자")
ok("실측 아님" in analysis.부르기("사이클"), "모델 출력임을 글에 적는다")
ok("모르는 항목" in analysis.부르기("없는것"), "모르는 항목은 모른다고 한다")

print("\n== JS 이식 일치 (브라우저 시뮬레이터 = 이 모델) ==")
node = shutil.which("node")
if node:
    B = dict(spec=dict(CELL=C, VESSEL=V, LIMITS=spec.LIMITS, BMS=spec.BMS), params=N.P)
    tmpj = Path(임시) / "b.json"; tmpj.write_text(json.dumps(B))
    js = f"""const {{makeNiH2}}=require({json.dumps(str(뿌리 / 'ruh2/web/nih2.js'))}); const B=require({json.dumps(str(tmpj))});
    const M=makeNiH2(B.spec,B.params); const r=M.run([["cc",0.5,{{s_in:1.1}}],["rest",0,{{t:3600}}],["cc",-0.5,{{V_min:1.0}}]],M.init());
    console.log(JSON.stringify(r.rows.map(x=>[x.V,x.p])))"""
    out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)
    d = max(max(abs(a[0] - b), abs(a[1] - q)) for a, b, q in zip(out, c["V"], c["p"]))
    ok(len(out) == len(c["V"]) and d < 1e-9, f"JS 와 Python: 행 {len(out)} · 최대 차 {d:.1e}")
else:
    print("  건너뜀  node 가 없다 -- JS 일치는 이 기계에서 못 봤다")

print("\n== 도면 한 장 (spec 에서 계산) ==")
env = dict(os.environ, RUH2_DRAW_OUT=str(Path(임시) / "dw"), MPLBACKEND="Agg")
p = subprocess.run([sys.executable, str(뿌리 / "ruh2/drawings/e001_block.py")], cwd=str(뿌리 / "ruh2/drawings"), capture_output=True, text=True, env=env)
ok(p.returncode == 0 and (Path(임시) / "dw" / "E-001_block.png").exists(), f"E-001 블록도 생성 {p.stderr[-200:] if p.returncode else ''}")

print("\n== 배선 ==")


def 목록(파일, 이름):
    t = ast.parse((뿌리 / 파일).read_text(encoding="utf-8"))
    for nd in ast.walk(t):
        if isinstance(nd, ast.Assign) and any(getattr(x, "id", "") == 이름 for x in nd.targets):
            return {e.id for e in nd.value.elts if isinstance(e, ast.Name)}
    return set()


for 파일, 이름 in (("discord_bot_server.py", "ADMIN_TOOLS"), ("main_public.py", "PUBLIC_TOOLS")):
    got = 목록(파일, 이름)
    ok({"ruh2_battery", "ruh2_make", "report_pdf"} <= got, f"{이름} 에 ruh2_battery · ruh2_make · report_pdf")
bt = (뿌리 / "bot_tools.py").read_text(encoding="utf-8")
ok(all(f"def {x}(" in bt for x in ("ruh2_battery", "ruh2_make", "report_pdf")), "bot_tools 에 도구 정의")
ok("start_new_session=True" in bt and "/proc/" in bt, "영상은 새 세션으로 띄우고, 좀비를 '렌더 중' 으로 읽지 않는다")
dep = (뿌리 / ".github/workflows/deploy-oracle.yml").read_text(encoding="utf-8")
ok('"ruh2/**"' in dep and '"reportkit/**"' in dep, "배포 경로에 ruh2/** · reportkit/**")
gi = (뿌리 / ".gitignore").read_text(encoding="utf-8")
ok("inbox/ruh2/" in gi and "inbox/reportkit/" in gi, "산출물 자리는 커밋되지 않는다")

shutil.rmtree(임시, ignore_errors=True)
print(f"\n{'실패 ' + str(len(FAIL)) if FAIL else '전부 통과'}")
sys.exit(1 if FAIL else 0)
