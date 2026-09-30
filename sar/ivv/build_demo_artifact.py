#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""demo_run.json → 자기완결 HTML 애니메이션(폐루프 UAV 정책 제어 콘솔). 실제 시뮬 데이터 임베드."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
import sys as _sys
_inp = _sys.argv[1] if len(_sys.argv) > 1 else os.path.join(HERE, "demo_run.json")
data = json.load(open(_inp))
DATA = json.dumps(data, separators=(",", ":"))

HTML = r"""<title>SAR UAV 정책 콘솔</title>
<style>
:root{
  --bg:#eef1f5; --panel:#ffffff; --ink:#18202e; --muted:#586474; --line:#d3dae4;
  --accent:#0e7490; --uav:#1d4ed8; --live:#15803d; --decoy:#b45309; --crit:#b91c1c; --relo:#7c3aed;
  --grid:rgba(20,30,45,.06);
}
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
  color-scheme:dark;
  --bg:#0b0f16; --panel:#141b26; --ink:#e6edf6; --muted:#93a1b3; --line:#25303f;
  --accent:#22d3ee; --uav:#60a5fa; --live:#34d399; --decoy:#f59e0b; --crit:#f87171; --relo:#a78bfa;
  --grid:rgba(230,237,246,.06);
}}
:root[data-theme="dark"]{
  color-scheme:dark;
  --bg:#0b0f16; --panel:#141b26; --ink:#e6edf6; --muted:#93a1b3; --line:#25303f;
  --accent:#22d3ee; --uav:#60a5fa; --live:#34d399; --decoy:#f59e0b; --crit:#f87171; --relo:#a78bfa;
  --grid:rgba(230,237,246,.06);
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);margin:0;
  font-family:"IBM Plex Sans",-apple-system,system-ui,sans-serif;line-height:1.4}
.wrap{max-width:1100px;margin:0 auto;padding-block:18px;padding-left:16px;padding-right:16px}
h1{font-size:17px;margin:0;letter-spacing:.2px;font-weight:600}
.sub{color:var(--muted);font-size:12.5px;margin:2px 0 14px}
.mono{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,monospace;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:16px}
@media (max-width:760px){.grid{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
canvas{width:100%;height:auto;display:block;border-radius:8px;background:#000}
.legend{display:flex;flex-wrap:wrap;gap:10px 16px;font-size:11.5px;color:var(--muted);margin-top:9px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.act{font-family:"IBM Plex Mono",monospace;font-size:26px;font-weight:600;letter-spacing:.5px}
.actrow{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
.tstamp{color:var(--muted);font-size:12px}
.phase{font-size:13px;margin:8px 0 12px;min-height:34px;color:var(--ink)}
.rows{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:12.5px;align-items:center}
.rows .k{color:var(--muted)}
.rows .v{font-family:"IBM Plex Mono",monospace;text-align:right}
.bar{height:8px;border-radius:5px;background:var(--line);overflow:hidden}
.bar>span{display:block;height:100%;border-radius:5px}
.sens{display:flex;gap:6px;margin-top:4px;flex-wrap:wrap}
.chip{font-family:"IBM Plex Mono",monospace;font-size:10.5px;padding:3px 7px;border-radius:6px;border:1px solid var(--line);color:var(--muted)}
.chip.on{color:#fff;border-color:transparent}
.controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:14px}
button{font:inherit;font-size:12.5px;padding:7px 12px;border-radius:8px;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);cursor:pointer}
button.primary{background:var(--accent);color:#04121a;border-color:transparent;font-weight:600}
button[aria-pressed="true"]{background:var(--accent);color:#04121a;border-color:transparent}
input[type=range]{flex:1;min-width:120px;accent-color:var(--accent)}
.note{font-size:11px;color:var(--muted);margin-top:12px}
.badge{display:inline-block;font-size:10.5px;padding:2px 7px;border-radius:20px;border:1px solid var(--line);color:var(--muted)}
</style>

<div class="wrap">
  <h1>SAR UAV — 정책 제어 폐루프</h1>
  <div class="sub">실측 지리산 지형 · 실제 C 결정 executive(<span class="mono">fw/</span>, ctypes)가 참조세계(<span class="mono">sar/</span>) 안에서 관측만 받아 UAV 제어 <span id="mode3d"></span>· <span class="badge">L2 verification · 현장 아님</span></div>

  <div class="grid">
    <div class="card">
      <canvas id="cv" width="520" height="520" aria-label="임무 지도"></canvas>
      <div class="legend">
        <span><i style="background:var(--uav)"></i>UAV·경로</span>
        <span><i style="background:var(--live)"></i>생존자(liveness 있음)</span>
        <span><i style="background:var(--decoy)"></i>decoy(생체징후 없음)</span>
        <span><i style="background:var(--crit)"></i>장애물</span>
        <span><i style="background:var(--accent);opacity:.5"></i>센서 FOV</span>
        <span>◍ 확인된 belief</span>
        <span>밝은 칸 = 탐색 완료</span>
      </div>
    </div>

    <div class="card">
      <div class="actrow"><span class="act" id="act">SEARCH</span><span class="tstamp mono" id="clock">t 000 / 000</span></div>
      <div class="phase" id="phase">—</div>
      <div class="rows">
        <span class="k">배터리</span><span class="v"><span id="battv">100%</span><span class="bar" style="margin-top:3px"><span id="batt" style="width:100%;background:var(--live)"></span></span></span>
        <span class="k">커버리지</span><span class="v" id="cov">0.0%</span>
        <span class="k">belief 신뢰(target_conf)</span><span class="v" id="tconf">0.00</span>
        <span class="k">운동 일관성 NIS</span><span class="v" id="nis">0.0</span>
        <span class="k" id="losk" hidden>가시선(3D 지형)</span><span class="v" id="losv" hidden>—</span>
        <span class="k">확인 상태</span><span class="v" id="confirmed">—</span>
        <span class="k">IMU / GNSS</span><span class="v" id="imu">OK</span>
      </div>
      <div style="font-size:12px;color:var(--muted);margin:12px 0 4px">센서 (present · 건강)</div>
      <div class="sens" id="sens"></div>
      <div class="controls">
        <button class="primary" id="play">⏸ 일시정지</button>
        <button data-spd="1" aria-pressed="true">1×</button>
        <button data-spd="2" aria-pressed="false">2×</button>
        <button data-spd="4" aria-pressed="false">4×</button>
        <button data-spd="0.3" aria-pressed="false">느리게(≈10분)</button>
      </div>
      <input type="range" id="scrub" min="0" max="1" value="0" step="1" aria-label="재생 위치">
      <div class="note" id="summary"></div>
    </div>
  </div>
  <div class="note">배선: <span class="mono">reference.observe</span> → <span class="mono">fw_bridge_step</span>(진짜 C 결정) → Action → 항법 → 관측 ↺. 정책 규칙: 건강가중 융합 · 시간확인 N=2 · CMPC≥2 · liveness 요구 · NIS 게이트 24 · 안전이 효용 위. 세계상태(배터리·충돌·센서고장·IMU)는 임무처럼 대본으로 넣어 FDIR·안전 층을 발화시켰다.</div>
</div>

<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<script>
const D = __DATA__;
const GW=D.GW, GH=D.GH, F=D.frames, N=F.length;
const ACTC={SEARCH:'--accent',APPROACH:'--uav',INSPECT:'--live',RETURN:'--decoy',EMERGENCY:'--crit',AVOID:'--crit',RELOCALIZE:'--relo',NONE:'--muted'};
const SENS=['RGB','THERMAL','LIDAR','SAR','AUDIO'];
const cv=document.getElementById('cv'), cx=cv.getContext('2d');
const cssv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function terrCol(v){ // muted earth ramp
  const a=[46,64,66], b=[120,132,110], c=[196,184,150];
  const mix=(p,q,t)=>Math.round(p+(q-p)*t);
  let r,g,bl; if(v<0.5){const t=v/0.5; r=mix(a[0],b[0],t);g=mix(a[1],b[1],t);bl=mix(a[2],b[2],t);}
  else{const t=(v-0.5)/0.5; r=mix(b[0],c[0],t);g=mix(b[1],c[1],t);bl=mix(b[2],c[2],t);}
  return `rgb(${r},${g},${bl})`;
}
const dem=D.dem, DR=dem.length, DC=dem[0].length;
function draw(i){
  const W=cv.width,H=cv.height, sx=W/GW, sy=H/GH;
  // terrain
  const cw=W/DC, ch=H/DR;
  for(let r=0;r<DR;r++)for(let c=0;c<DC;c++){cx.fillStyle=terrCol(dem[r][c]);cx.fillRect(c*cw,r*ch,cw+1,ch+1);}
  // coverage (union up to frame i): recompute lightly from veh trail radius3
  cx.fillStyle='rgba(255,255,255,.06)';
  // grid
  cx.strokeStyle=cssv('--grid');cx.lineWidth=1;
  for(let g=0;g<=GW;g++){cx.beginPath();cx.moveTo(g*sx,0);cx.lineTo(g*sx,H);cx.stroke();}
  for(let g=0;g<=GH;g++){cx.beginPath();cx.moveTo(0,g*sy);cx.lineTo(W,g*sy);cx.stroke();}
  const P=(p)=>[p[0]*sx+sx/2, p[1]*sy+sy/2];
  const fr0=F[i], vp=P(fr0.veh), RFOV=5;
  // sensor FOV footprint
  cx.fillStyle=cssv('--accent');cx.globalAlpha=.09;cx.beginPath();cx.arc(vp[0],vp[1],RFOV*sx,0,7);cx.fill();cx.globalAlpha=1;
  cx.strokeStyle=cssv('--accent');cx.globalAlpha=.25;cx.lineWidth=1;cx.beginPath();cx.arc(vp[0],vp[1],RFOV*sx,0,7);cx.stroke();cx.globalAlpha=1;
  // obstacle
  const ob=P(D.obstacle); cx.strokeStyle=cssv('--crit');cx.lineWidth=3;
  cx.beginPath();cx.moveTo(ob[0]-8,ob[1]-8);cx.lineTo(ob[0]+8,ob[1]+8);cx.moveTo(ob[0]+8,ob[1]-8);cx.lineTo(ob[0]-8,ob[1]+8);cx.stroke();
  // home
  const hm=P(D.home); cx.fillStyle=cssv('--muted');cx.font='12px IBM Plex Mono';cx.fillText('⌂',hm[0]-5,hm[1]+4);
  // trail
  cx.strokeStyle=cssv('--uav');cx.lineWidth=2;cx.globalAlpha=.7;cx.beginPath();
  for(let k=0;k<=i;k++){const p=P(F[k].veh);k===0?cx.moveTo(p[0],p[1]):cx.lineTo(p[0],p[1]);}
  cx.stroke();cx.globalAlpha=1;
  // decoy
  const dc=P(D.decoys[0]); const ddC=Math.hypot(fr0.veh[0]-D.decoys[0][0],fr0.veh[1]-D.decoys[0][1]);
  if(ddC<=RFOV){cx.strokeStyle=cssv('--decoy');cx.globalAlpha=.6;cx.lineWidth=1.5;cx.setLineDash([4,4]);cx.beginPath();cx.moveTo(vp[0],vp[1]);cx.lineTo(dc[0],dc[1]);cx.stroke();cx.setLineDash([]);cx.globalAlpha=1;}
  cx.fillStyle=cssv('--decoy');cx.beginPath();cx.arc(dc[0],dc[1],7,0,7);cx.fill();
  cx.font='10px IBM Plex Mono';cx.fillText('decoy',dc[0]+9,dc[1]+3);
  if(fr0.act==='APPROACH'&&ddC<4&&!fr0.belief[2]){cx.strokeStyle=cssv('--decoy');cx.lineWidth=2;cx.setLineDash([3,3]);cx.beginPath();cx.arc(dc[0],dc[1],14,0,7);cx.stroke();cx.setLineDash([]);cx.fillText('생체징후 없음 → 거부', dc[0]-30, dc[1]+26);}
  // target (pulsing) — 3D: 능선 뒤(los=0)면 흐리게 + '가림'
  const tg=P(D.targets[0]); const pulse=6+2.5*Math.sin(i/2);
  const dtC=Math.hypot(fr0.veh[0]-D.targets[0][0],fr0.veh[1]-D.targets[0][1]);
  const occT=(D.scene3d && fr0.los===0);
  if(dtC<=RFOV && !occT){cx.strokeStyle=cssv('--live');cx.globalAlpha=.6;cx.lineWidth=1.5;cx.beginPath();cx.moveTo(vp[0],vp[1]);cx.lineTo(tg[0],tg[1]);cx.stroke();cx.globalAlpha=1;}
  if(occT){cx.strokeStyle=cssv('--muted');cx.lineWidth=1.5;cx.beginPath();cx.arc(tg[0],tg[1],7,0,7);cx.stroke();
    cx.fillStyle=cssv('--muted');cx.font='10px IBM Plex Mono';cx.fillText('가림',tg[0]+9,tg[1]+3);}
  else{cx.fillStyle=cssv('--live');cx.beginPath();cx.arc(tg[0],tg[1],7,0,7);cx.fill();
    cx.strokeStyle=cssv('--live');cx.globalAlpha=.5;cx.lineWidth=2;cx.beginPath();cx.arc(tg[0],tg[1],pulse+4,0,7);cx.stroke();cx.globalAlpha=1;
    cx.fillStyle=cssv('--live');cx.font='10px IBM Plex Mono';cx.fillText('LIVE',tg[0]+9,tg[1]+3);}
  // belief ring if confirmed
  const fr=F[i];
  if(fr.belief[2]){const b=P(fr.belief);cx.strokeStyle=cssv('--live');cx.lineWidth=2.5;cx.beginPath();cx.arc(b[0],b[1],11,0,7);cx.stroke();}
  // UAV triangle (heading from prev)
  const p=P(fr.veh); let ang=0; if(i>0){const q=P(F[i-1].veh);ang=Math.atan2(p[1]-q[1],p[0]-q[0]);}
  cx.save();cx.translate(p[0],p[1]);cx.rotate(ang);cx.fillStyle=cssv('--uav');
  cx.beginPath();cx.moveTo(9,0);cx.lineTo(-6,5);cx.lineTo(-6,-5);cx.closePath();cx.fill();cx.restore();
}
function phaseText(fr){
  if(fr.act==='EMERGENCY') return '전력 임계 — 비상 귀환 (safety filter가 효용 위에서 override)';
  if(fr.act==='RETURN') return '저전력(<25%) — 자동 귀환 (FDIR 감독자)';
  if(fr.imu===0||fr.act==='RELOCALIZE') return 'IMU/GNSS 상실 — 재정렬, 전진 금지 (safety filter)';
  if(fr.health[2]<0.3) return 'LiDAR 고장 감지·격리 — 남은 센서로 융합 계속 (FDIR)';
  if(fr.act==='AVOID') return '충돌 위험 — 회피 (safety filter)';
  if(D.scene3d && fr.los===0) return '표적 능선 뒤 — 가시선 없음 (3D 지형 가림)';
  if(fr.belief[2]) return '생존자 확인 — liveness 있음, 접근·관측 (INSPECT)';
  const dc=D.decoys[0], near=Math.hypot(fr.veh[0]-dc[0],fr.veh[1]-dc[1])<4;
  if(fr.act==='APPROACH'&&near) return '후보 조사 중 — decoy는 생체징후(liveness) 없음 → 확인 거부';
  if(fr.act==='APPROACH') return '후보로 접근 (target_conf>0.5)';
  return '탐색 — 미탐색 구역 커버 중';
}
function render(i){
  const fr=F[i]; draw(i);
  const a=document.getElementById('act'); a.textContent=fr.act; a.style.color=cssv(ACTC[fr.act]||'--ink');
  document.getElementById('clock').textContent='t '+String(fr.t).padStart(3,'0')+' / '+String(N-1).padStart(3,'0');
  document.getElementById('phase').textContent=phaseText(fr);
  const bpct=Math.round(fr.battery*100);
  document.getElementById('battv').textContent=bpct+'%';
  const bb=document.getElementById('batt');bb.style.width=Math.max(0,bpct)+'%';
  bb.style.background=cssv(fr.battery<0.1?'--crit':fr.battery<0.25?'--decoy':'--live');
  document.getElementById('cov').textContent=fr.coverage.toFixed(1)+'%';
  document.getElementById('tconf').textContent=fr.belief[3].toFixed(2);
  document.getElementById('nis').textContent=fr.belief[4].toFixed(1);
  document.getElementById('confirmed').textContent=fr.belief[2]?'✓ 확인됨':'—';
  if(D.scene3d){const lv=document.getElementById('losv');lv.textContent=fr.los===0?'가림':'✓ 보임';lv.style.color=fr.los===0?cssv('--muted'):'var(--ink)';}
  document.getElementById('imu').textContent=fr.imu?'OK':'상실';
  document.getElementById('imu').style.color=fr.imu?'var(--ink)':cssv('--relo');
  const sc=document.getElementById('sens');sc.innerHTML='';
  SENS.forEach((s,k)=>{const c=document.createElement('span');c.className='chip'+(fr.present[k]?' on':'');
    const bad=fr.health[k]<0.3; c.textContent=s+(bad?'✕':'');
    if(fr.present[k]) c.style.background=cssv(bad?'--crit':'--accent');
    if(bad&&!fr.present[k]){c.style.color=cssv('--crit');c.style.borderColor=cssv('--crit');}
    sc.appendChild(c);});
  document.getElementById('scrub').value=i;
}
// summary
(function(){const h={};let conf=0,apprD=0;const dc=D.decoys[0];
  F.forEach(f=>{h[f.act]=(h[f.act]||0)+1;if(f.belief[2])conf++;if(f.act==='APPROACH'&&Math.hypot(f.veh[0]-dc[0],f.veh[1]-dc[1])<4)apprD++;});
  document.getElementById('summary').textContent='요약: 확인 '+conf+'스텝(모두 생존자, decoy 0) · decoy 조사 '+apprD+'스텝(확인 거부) · 행동 '+Object.entries(h).map(([k,v])=>k+':'+v).join(' ');
})();
let i=0, playing=true, spd=1, timer=null, base=900;
const scr=document.getElementById('scrub');scr.max=N-1;
function tick(){ if(!playing)return; i=(i+1)%N; render(i); schedule(); }
function schedule(){ clearTimeout(timer); timer=setTimeout(tick, base/spd); }
document.getElementById('play').onclick=e=>{playing=!playing;e.target.textContent=playing?'⏸ 일시정지':'▶ 재생';if(playing)schedule();};
document.querySelectorAll('[data-spd]').forEach(b=>b.onclick=()=>{spd=parseFloat(b.dataset.spd);
  document.querySelectorAll('[data-spd]').forEach(x=>x.setAttribute('aria-pressed', x===b));schedule();});
scr.oninput=e=>{i=+e.target.value;render(i);};
window.matchMedia('(prefers-color-scheme:dark)').addEventListener?.('change',()=>render(i));
if(D.scene3d){document.getElementById('mode3d').textContent='· 3D 지형 가시선 ';
  document.getElementById('losk').hidden=false;document.getElementById('losv').hidden=false;}
render(0); schedule();
</script>"""

base = "demo_artifact_3d" if data.get("scene3d") else "demo_artifact"
out = os.path.join(HERE, base + ".html")
open(out, "w").write(HTML.replace("__DATA__", DATA))
print("wrote", out, os.path.getsize(out), "bytes")
