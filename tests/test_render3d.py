# -*- coding: utf-8 -*-
"""render3d -- scene format, two camera models, fog, SAR bridge, pipeline and wiring. Runs without a browser.

What it holds in place (each with the reason it can break):
  - The SAR camera reimplementation lands exactly where the real sar/camera.py draws (vv A). If this breaks, every
    'SAR vs three.js' comparison is meaningless.
  - A north-up plan is not mirrored (the first render was mirrored left/right: three.js puts +x on the left when viewed from the front).
  - The fog override strings are really in the HTML (removing them breaks agreement with SAR fog, silently).
  - Without a browser, the output says 'matplotlib 대체' (a fallback reported as photoreal is a false green).
  - Wiring: dispatch, bot tool lists, deploy paths, requirements, IV&V hook.
Run: python3 tests/test_render3d.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ["SE_RENDER3D_NO_BROWSER"] = "1"

fails = []


def ok(cond, label):
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


from render3d import scene as S, camera as C, fog as FOG, layout as LY, sar_bridge as B, html as HT, pipeline, vv  # noqa: E402
from render3d import discord_cmd as DC  # noqa: E402

# ---- Scene format
bad = S.new("x", "west")
bad["boxes"].append({"id": "a", "type": "nope", "x0": 1, "y0": 1, "x1": 0, "y1": 2, "h": 1})
e = S.check(bad)
ok(any("y_axis" in x for x in e) and any("unknown type" in x for x in e) and any("x1<=x0" in x for x in e),
   "check 가 y_axis·타입·뒤집힌 상자를 잡는다")
ex = LY.examples()
ok({"hongdae/F1", "hongdae/F2", "hongdae/F3", "hongdae/B1", "store_module/asis", "store_module/tobe"} <= set(ex), "예제 6개 층")
ok(all(S.check(LY.to_scene(L)) == [] for L in ex.values()), "예제 전부 유효한 장면으로 바뀐다")

# ---- Camera: mirroring check
v = {"pos": [0, 0, 1.6], "target": [0, 10, 1.6], "fov": 60}
u_c, v_c = C.pinhole_pixel(v, (0, 10, 1.6), 800, 500, "north")
ok(abs(u_c - 400) < 1e-6 and abs(v_c - 250) < 1e-6, "정면 점은 화면 중심")
u_e, _ = C.pinhole_pixel(v, (3, 10, 1.6), 800, 500, "north")
ok(u_e > 400, "북쪽을 보면 동쪽(+x)은 화면 오른쪽 -- 평면도가 뒤집히지 않는다")
u_s, _ = C.pinhole_pixel({"pos": [0, 0, 1.6], "target": [0, 10, 1.6], "fov": 60}, (3, 10, 1.6), 800, 500, "south")
ok(u_s < 400, "y=남 장면에서 남쪽을 보면 동쪽은 왼쪽 (DEM 좌표계)")
cam = {"x": 0.0, "y": 0.0, "z": 50.0, "heading_deg": 90.0, "pitch_deg": -20.0, "fov_deg": 72.0}
vw = C.sar_to_view(cam, 220, 140)
side = []
for q in ((5.0, 100.0, 0.0), (-5.0, 100.0, 0.0)):
    ps, pp = C.sar_pixel(cam, q, 220, 140), C.pinhole_pixel(vw, q, 220, 140, "south")
    side.append((ps[0] > 109.5, pp[0] > 110))
ok(side[0][0] == side[0][1] and side[1][0] == side[1][1] and side[0][0] != side[1][0],
   "SAR 식과 핀홀이 좌우를 같게 본다 (남쪽을 보면 동쪽이 왼쪽 -- y=남 DEM)")

# ---- V&V (no browser)
a = vv.check_sar_impl()
ok(a["판정"] == "PASS" and a["_num"]["found"] == 5, "A: SAR 재구현 == sar/camera.py 실제 출력 (%s)" % a["측정"])
b = vv.check_sar_vs_pinhole()
ok(b["판정"] == "측정" and b["_num"]["du"] > 5 and abs(b["_num"]["centre_du"]) <= 0.5 + 1e-9,
   "B: 두 모델 차이는 0 이 아니고, 중심선 차이는 픽셀중심 규약(0.5 px) 뿐 (%s)" % b["측정"][:60])
c = vv.check_fog_models()
ok(abs(FOG.T_beer_lambert(FOG.beta_from_visibility(200), 200) - 0.02) < 1e-4, "Koschmieder: V 에서 투과율 2% (3.912 = −ln 0.02 반올림)")
ok(abs(FOG.T_three_default(FOG.rho_matching_visibility(200), 200) - 0.02) < 1e-4, "같은 V 로 맞춘 three.js 기본 안개도 V 에서 2%")
ok(c["_num"]["max_abs_dT"] > 0.3, "그런데 그 사이 거리에선 |ΔT|>0.3 벌어진다 -- 덮어쓰기가 필요한 이유")
ok(vv.check_heightfield()["판정"] == "PASS", "E: 하이트필드 정점 == DEM·sar 샘플러")
ok(vv.check_area()["판정"] == "PASS", "F: 면적 합 == 외곽")
d = vv.run_all(browser=False)
ok(not any(r["판정"] == "PASS" and r["id"] == "D" for r in d), "브라우저를 안 쓰면 D 는 PASS 로 안 나온다")

# ---- HTML
with tempfile.TemporaryDirectory() as t:
    sc = LY.to_scene(ex["hongdae/F1"])
    hp = HT.write(sc, Path(t) / "a.html")
    txt = Path(hp).read_text(encoding="utf-8")
    ok("three@0.170.0/build/three.module.js" in txt, "three.js 0.170.0 고정")
    ok("exp( - fogDensity * vFogDepth )" in txt and "length( mvPosition.xyz )" in txt, "Beer-Lambert·광선거리 안개 셰이더가 들어 있다")
    ok('"y_axis":"north"' in txt and "window.__done = true" in txt, "장면 데이터와 완료 신호")

# ---- SAR bridge
dem, mpp, frames, feats, sdb = B.synthetic_mission()
ms = B.mission_scene(dem, mpp, frames, V_m=400.0, features=feats, scenedb=sdb)
ok(S.check(ms) == [], "IV&V 장면이 유효")
kinds = [m["kind"] for m in ms["markers"]]
ok("uav" in kinds and "truth" in kinds and "detect" in kinds, "UAV·truth·SUT 탐지 마커")
ok(ms["fog"]["views"] == ["onboard"] and abs(ms["fog"]["beta"] - 3.912 / 400) < 1e-12, "안개는 탑재 카메라에만, β=3.912/V")
ok("onboard" in ms["views"] and ms["meta"]["onboard_sar_cam"]["fov_deg"] == 72.0, "탑재 카메라 시점 = RGB 카메라(sar/camera.py) 파라미터")
ok(all("color" in p for p in ms["props"]), "피처 색 = SceneDB MATERIAL rgb (같은 재질)")
ok("colors" in ms["heightfield"], "지면 색 = SceneDB ground_rgb")

# ---- Pipeline (browser off -> must say fallback)
with tempfile.TemporaryDirectory() as t:
    r = pipeline.run(LY.to_scene(ex["hongdae/F2"]), t, "f2", views=["aerial"])
    ok(Path(r["plan"]).is_file() and Path(r["views"]["aerial"]["png"]).is_file() and Path(r["html"]).is_file(), "평면·3D·HTML 파일")
    ok(r["views"]["aerial"]["backend"] == pipeline.FALLBACK, "브라우저 없으면 백엔드가 'matplotlib 대체(비실사)'로 적힌다")
    ok(abs(sum(r["area"].values()) - 26.0 * 14.6) < 0.05, "면적표 합 == 26.0×14.6")

    class _Ref:
        dem, mpp, AGL, V = dem, mpp, 90.0, 400.0
    buf = io.StringIO()
    with redirect_stdout(buf):
        outs = B.render_mission(_Ref(), frames, t, "ivv", repo=None)
    ok(len(outs) == 3 and all(Path(p).is_file() for p in outs) and "render3d 백엔드" in buf.getvalue(), "IV&V 훅: 지도+조감+탑재 3장")

# ---- Mission animation (UAV flight + live policy log). The spec is 10 Hz / 1 Hz / event / 20 s decision -- an update rate, not a bandwidth
from render3d import mission_anim as MA  # noqa: E402
spec_ = dict(MA.default_spec(V=6000.0), budget_min=2)
sc_, su_ = MA.build(spec_, B.synthetic_dem(96, seed=2), speed=20)
A_ = sc_["anim"]
ok(len(A_["states"]) == int(2 * 60 * A_["state_hz"]) and A_["state_hz"] == 10 and A_["report_hz"] == 1 and A_["decision_s"] == 20.0,
   "10 Hz 상태 %d개 = 2분×10 Hz · 1 Hz 보고 · 결정 20 s" % len(A_["states"]))
ok(abs(su_["rates_measured"]["state_hz"] - 10.0) < 0.2 and abs(su_["rates_measured"]["report_hz"] - 1.0) < 0.1, "버스에서 잰 주기 == 스펙 (%s)" % su_["rates_measured"])
ok(len(A_["decisions"]) == 6 and all(("→ %s" % d[1]) in d[2] for d in A_["decisions"]), "결정 로그 6개, 근거 문장이 실제 상태와 같은 변수로 만들어졌다 (→ 상태)")
ok(all(len(s) == 11 and s[10] == spec_["agl"] for s in A_["states"][:50]), "상태 줄에 AGL 이 실린다 (해발과 따로)")
ok(any(p["kind"] == "person" for p in sc_["props"]) and S.check(sc_) == [], "사람 소품 · 장면 검사 통과 (%s)" % S.check(sc_)[:2])
with tempfile.TemporaryDirectory() as t:
    hp_ = Path(t) / "m.html"; HT.write(sc_, hp_); h_ = hp_.read_text(encoding="utf-8")
    ok("ANIM_RUN" in h_ and "b.visible = mode !== 'onboard'" in h_ and "__animDone" in h_, "애니 HTML: 재생 루프 · 탑재 시점에서 truth 숨김 · 끝 신호")
sut_src = (REPO / "sar/ivv/sut.py").read_text(encoding="utf-8")
ok("render3d" not in sut_src and "reference" not in sut_src.split('"""')[2], "SUT 는 결정 근거를 내도 참조세계·render3d 를 안 읽는다")
import relay  # noqa: E402
ok(relay.산출물꼴.search("산출물: public_agent_memory/render3d/mission_hill_1.webm").group(1).endswith(".webm")
   and relay.산출물꼴.search("public_agent_memory/render3d/mission_hill_1.html") is not None, "봇이 영상(webm)·HTML 을 붙인다")
ok(relay.산출물꼴.search("산출물: public_agent_memory/mission/dmz_onboard.mp4").group(1).endswith(".mp4"), "봇이 mp4 영상을 붙인다")

# ---- Fixed command
ok(DC.run("!렌더") == DC.HELP and DC.run("!렌더기 x") is None and DC.run("오늘 날씨 어때") is None, "도움말 · 붙여 쓴 말 · 딴 말")
got = []
fake = lambda argv, log, what: (got.append(argv), "ack")[1]
DC.run("!렌더 검증", runner=fake); DC.run("!렌더 홍대 2층", runner=fake); DC.run("!렌더 sar 케이스", runner=fake, allow_write=False)
ok(got[0][-2:] == ["render3d", "vv"] and "hongdae/F2" in got[1] and got[2][-1] == "--case", "하위 명령 → argv (공개 채널도 됨)")
ok(isinstance(DC._LOG, Path), "_LOG 는 Path")
got.clear()
DC.run("!렌더 영상", runner=fake); DC.run("!렌더 영상 협곡 V=300", runner=fake); DC.run("!렌더 3d비교 나무", runner=fake)
ok(got[0][-2:] == ["anim", "--video"] and got[1][-3:] == ["--canyon", "--V", "300"] and got[2][-2:] == ["--set", "trees"], "!렌더 영상 [협곡] [V=] · !렌더 3d비교 [단위|협곡|나무|전부]")
ok("모르는 하위 명령" in DC.run("!렌더 뭐지", runner=fake), "모르는 하위 명령은 도움말과 함께 답한다")

# ---- Wiring
disp = (REPO / "dispatch.py").read_text(encoding="utf-8")
ok("from render3d import discord_cmd as 렌더" in disp and ", 렌더)" in disp.split("명령들 = (")[1].split("\n")[0], "dispatch 에 실렸다")
import dispatch  # noqa: E402
ok(dispatch.run("!렌더") is not None, "dispatch.run('!렌더') 이 답한다")
bt = (REPO / "bot_tools.py").read_text(encoding="utf-8")
fn = bt.split("def render_space")[1].split("\n@tool")[0]
ok('"""' in fn and "agent_context.is_blocked()" in fn and "_그림남기기(r[\"html\"])" in fn, "render_space: 독스트링·게스트 차단·첨부")
srv = (REPO / "discord_bot_server.py").read_text(encoding="utf-8")
pub = (REPO / "main_public.py").read_text(encoding="utf-8")
ok("render_space" in srv.split("ADMIN_TOOLS = [")[1].split("]")[0] and srv.count(" render_space,") >= 2, "관리 채널 도구")
ok("render_space" in pub.split("PUBLIC_TOOLS = [")[1].split("]")[0] and pub.count(" render_space,") >= 2, "공개 채널 도구")
dep = (REPO / ".github/workflows/deploy-oracle.yml").read_text(encoding="utf-8")
ok('"render3d/**"' in dep and "playwright install chromium" in dep, "배포: 경로 + chromium")
ok("playwright" in (REPO / "requirements.txt").read_text(encoding="utf-8"), "requirements 에 playwright")
hn = (REPO / "sar/ivv/harness.py").read_text(encoding="utf-8")
ok(hn.count("    _실사렌더(ref, frames, REPO, \"") == 2, "IV&V 데모·케이스 둘 다 render3d 훅")
ok((REPO / "paper/선행조사/실사렌더_VV_파이프라인.md").is_file(), "선행조사 노트")

# ---- CLI
o = subprocess.run([sys.executable, "-m", "render3d", "example", "--list"], cwd=str(REPO), capture_output=True, text=True, timeout=60)
ok(o.returncode == 0 and "hongdae/F3" in o.stdout, "python3 -m render3d example --list")

if fails:
    print("\nFAIL %d" % len(fails)); sys.exit(1)
print("\nrender3d: 장면·두 카메라·안개·SAR 다리·파이프라인·배선 -- 통과")
