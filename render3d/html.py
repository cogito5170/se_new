# -*- coding: utf-8 -*-
"""Scene -> a self-contained three.js HTML file. Open it in a browser to orbit around the scene, or headless.py
turns it into a PNG.

- PBR (MeshStandardMaterial) + RoomEnvironment reflections + soft shadows + ACES tone mapping.
- Fog: when scene.fog.model == "beer_lambert", the shader chunks are overridden **before any material is
  compiled**, so it matches the SAR camera (fog.py).
- three.js is pinned to 0.170.0. The default load is from the CDN. If three_base is given, it loads from
  there (headless.py passes it when it serves a local copy).
- URL query: ?view=<view name>|top&w=&h= . Controls: drag = orbit, scroll = zoom (loaded only when interactive).
"""
from __future__ import annotations

import json
from pathlib import Path

from render3d import fog as FOG
from render3d import scene as S
from render3d.visibility import TREE

THREE_VERSION = "0.170.0"
CDN = "https://cdn.jsdelivr.net/npm/three@%s/" % THREE_VERSION


def write(sc: dict, path, three_base: "str | None" = None, title: "str | None" = None) -> str:
    bad = S.check(sc)
    if bad:
        raise ValueError("invalid scene: " + "; ".join(bad[:5]))
    base = three_base or CDN
    html = (_TEMPLATE.replace("__TITLE__", (title or sc.get("name", "render3d")).replace("<", ""))
            .replace("__THREE__", base)
            .replace("__FOGV__", json.dumps(FOG.GLSL_FOG_VERTEX)).replace("__FOGF__", json.dumps(FOG.GLSL_FOG_FRAGMENT))
            .replace("__TREE__", json.dumps(TREE))
            .replace("/*__DATA__*/null", json.dumps(sc, ensure_ascii=False, separators=(",", ":"))))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(html, encoding="utf-8")
    return str(path)


_TEMPLATE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>html,body{margin:0;height:100%;background:#f4f1ea;overflow:hidden}canvas{display:block}
#hud{position:fixed;left:10px;top:8px;font:12px/1.4 "Noto Sans KR","WenQuanYi Zen Hei",sans-serif;color:#333;
background:#ffffffcc;padding:4px 8px;border-radius:6px}#hud select{font:inherit}</style>
<script>window.__err = null; window.__done = false;
addEventListener('error', e => { if (!window.__done) window.__err = String(e.message || (e.target && (e.target.src || e.target.href)) || 'load error'); }, true);
addEventListener('unhandledrejection', e => { window.__err = String(e.reason); });</script>
<script type="importmap">{"imports":{"three":"__THREE__build/three.module.js","three/addons/":"__THREE__examples/jsm/"}}</script>
</head><body><div id="hud"></div>
<script type="module">
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
const S = /*__DATA__*/null;
const TREE = __TREE__;
const P = new URLSearchParams(location.search);
const VIEW = P.get('view') || 'aerial', HEADLESS = P.has('headless');
const Wpx = +(P.get('w') || innerWidth || 1600), Hpx = +(P.get('h') || innerHeight || 1000);
const [BW, BD, BH] = S.bounds, NORTH = S.y_axis === 'north';
const CUT = VIEW !== 'top' && !(S.views[VIEW] && S.views[VIEW].pos[2] < BH * 0.9) && S.shell;   // aerial = cutaway
const BIG = Math.max(BW, BD);

// ---- Fog: Beer-Lambert + radial distance (render3d/fog.py). Must come before materials are compiled.
const FOG_ON = !!S.fog && (!S.fog.views || S.fog.views.includes(VIEW));   // Fog is sensor-view physics (the observer view gets none)
if (S.fog && (FOG_ON || S.anim) && (S.fog.model || 'beer_lambert') === 'beer_lambert') {   // anim: the fog is switched on/off with the camera, so override up front
  THREE.ShaderChunk.fog_vertex = __FOGV__;
  THREE.ShaderChunk.fog_fragment = __FOGF__;
}

let seed = 12345; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(HEADLESS ? 1 : Math.min(2, devicePixelRatio || 1)); renderer.setSize(Wpx, Hpx);
if (S.linear_output) { renderer.toneMapping = THREE.NoToneMapping; renderer.outputColorSpace = THREE.LinearSRGBColorSpace; }
else { renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.88; renderer.outputColorSpace = THREE.SRGBColorSpace; }
renderer.shadowMap.enabled = !S.linear_output; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const fogC = S.fog ? new THREE.Color().setRGB(...S.fog.color, THREE.LinearSRGBColorSpace) : null;
scene.background = S.linear_output ? new THREE.Color(0x000000) : (FOG_ON ? fogC.clone() : new THREE.Color(S.heightfield ? 0xbfd3e6 : 0xf4f1ea));
if (FOG_ON) scene.fog = new THREE.FogExp2(fogC, S.fog.beta);
if (!S.linear_output) {
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture; scene.environmentIntensity = 0.55;
}
const root = new THREE.Group(); root.scale.z = NORTH ? -1 : 1; scene.add(root);   // scene (x,y,z-up) -> three (X,Y-up,Z)
const T3 = (x, y, z) => new THREE.Vector3(x, z, NORTH ? -y : y);

function canvasTex(w, h, draw, rep = [1, 1]) {
  const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(...rep); t.anisotropy = 8; return t;
}
const M = {
  floor: new THREE.MeshStandardMaterial({ roughness: 0.38, map: canvasTex(1024, 1024, (g, w, h) => {
    g.fillStyle = '#e9e4da'; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 9000; i++) { const r = rnd() * 3.2 + 0.4; g.fillStyle = ['#cfc6b6', '#b9ae9b', '#f7f3ec', '#d8cfbf', '#a79c8a', '#f2d98a'][Math.floor(rnd() * 6)];
      g.beginPath(); g.ellipse(rnd() * w, rnd() * h, r, r * (0.5 + rnd() * 0.6), rnd() * 3, 0, 7); g.fill(); }
  }, [BW / 4, BD / 4]) }),
  wall: new THREE.MeshStandardMaterial({ color: 0xefe7da, roughness: 0.9 }),
  wood: new THREE.MeshStandardMaterial({ roughness: 0.55, map: canvasTex(512, 512, (g, w, h) => {
    const grd = g.createLinearGradient(0, 0, w, 0); grd.addColorStop(0, '#d8b98f'); grd.addColorStop(1, '#caa678'); g.fillStyle = grd; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 160; i++) { g.strokeStyle = `rgba(120,80,40,${0.04 + rnd() * 0.08})`; g.lineWidth = 1 + rnd() * 2.5; const y = rnd() * h; g.beginPath(); g.moveTo(0, y);
      for (let x = 0; x <= w; x += 32) g.lineTo(x, y + Math.sin(x / 60 + i) * 4); g.stroke(); }
  }) }),
  white: new THREE.MeshStandardMaterial({ color: 0xfbfaf7, roughness: 0.45 }),
  yellow: new THREE.MeshStandardMaterial({ color: 0xfee500, roughness: 0.5 }),
  dark: new THREE.MeshStandardMaterial({ color: 0x2b2b2b, roughness: 0.6 }),
  column: new THREE.MeshStandardMaterial({ color: 0xece8e0, roughness: 0.7 }),
  glass: new THREE.MeshPhysicalMaterial({ color: 0xcfe8f2, roughness: 0.05, transparent: true, opacity: 0.18 }),
  steel: new THREE.MeshStandardMaterial({ color: 0xbfc4c8, roughness: 0.25, metalness: 0.9 }),
  stock: new THREE.MeshStandardMaterial({ color: 0xd9d4cb, roughness: 0.9 }),
  belt: new THREE.MeshStandardMaterial({ color: 0x2f6fb0, roughness: 0.6 }),
};
const mediaTex = canvasTex(2048, 700, (g, w, h) => {
  const grd = g.createLinearGradient(0, 0, w, h); grd.addColorStop(0, '#7fd3ff'); grd.addColorStop(.5, '#ffe36e'); grd.addColorStop(1, '#ff9fb6'); g.fillStyle = grd; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 26; i++) { g.fillStyle = 'rgba(255,255,255,0.55)'; const x = rnd() * w, y = rnd() * h * .7; for (let k = 0; k < 4; k++) { g.beginPath(); g.arc(x + k * 38, y + (k % 2) * 10, 40 + rnd() * 20, 0, 7); g.fill(); } }
});
M.media = new THREE.MeshStandardMaterial({ map: mediaTex, emissive: 0xffffff, emissiveMap: mediaTex, emissiveIntensity: 0.9 });
const pm = [0xffd6e0, 0xffe7a3, 0xbfe3ff, 0xc9f2d0, 0xe3d4ff, 0xffc9a6, 0xfff3c4, 0xf9b8b8, 0xd2c1a8, 0xfee500, 0xff8c69].map(c => new THREE.MeshStandardMaterial({ color: c, roughness: 0.75 }));
const plushM = [0xc8813b, 0xffb6c1, 0xfee500, 0xf5f0e6, 0x9b6b43, 0xffffff, 0xa7d8f0].map(c => new THREE.MeshStandardMaterial({ color: c, roughness: 0.95 }));

const add = m => { m.castShadow = true; m.receiveShadow = true; root.add(m); return m; };
const box = (x0, y0, x1, y1, z0, z1, mat, r = 0) => {
  const g = r > 0 ? new RoundedBoxGeometry(x1 - x0, z1 - z0, y1 - y0, 2, r) : new THREE.BoxGeometry(x1 - x0, z1 - z0, y1 - y0);
  const m = new THREE.Mesh(g, mat); m.position.set((x0 + x1) / 2, (z0 + z1) / 2, (y0 + y1) / 2); return add(m);
};
function sign(text, x, y, z, w, h, rotY, bg = '#FEE500', fg = '#222') {
  const t = canvasTex(1024, Math.round(1024 * h / w), (g, cw, ch) => { g.fillStyle = bg; g.fillRect(0, 0, cw, ch); g.fillStyle = fg;
    g.font = `bold ${Math.round(ch * 0.55)}px "Noto Sans KR","WenQuanYi Zen Hei",sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, cw / 2, ch / 2 + 2); });
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: t, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: 0.15 }));
  m.position.set(x, z, y); m.rotation.y = rotY; if (NORTH) m.scale.x = -1; root.add(m); return m;
}
function products(x0, y0, x1, y1, z, kind = 'mix', density = 1) {
  const n = Math.floor((x1 - x0) * (y1 - y0) * 28 * density);
  for (let i = 0; i < n; i++) {
    const px = x0 + 0.06 + rnd() * (x1 - x0 - 0.12), py = y0 + 0.06 + rnd() * (y1 - y0 - 0.12);
    if (kind === 'plush' || (kind === 'mix' && rnd() < 0.35)) { const r = 0.07 + rnd() * 0.06; const m = new THREE.Mesh(new THREE.SphereGeometry(r, 14, 10), plushM[Math.floor(rnd() * plushM.length)]); m.scale.set(1, 0.9, 0.85); m.position.set(px, z + r * 0.9, py); add(m); }
    else { const bw = 0.06 + rnd() * 0.12, bh = 0.05 + rnd() * 0.18, bd = 0.05 + rnd() * 0.1; const m = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, bd), pm[Math.floor(rnd() * pm.length)]); m.position.set(px, z + bh / 2, py); m.rotation.y = (rnd() - .5) * .3; add(m); }
  }
}
function bearFigure(cx, cy, s, mat) {
  const g = new THREE.Group(), sp = (r, x, y, z, m = mat, sc = [1, 1, 1]) => { const o = new THREE.Mesh(new THREE.SphereGeometry(r * s, 36, 24), m); o.position.set(x * s, y * s, z * s); o.scale.set(...sc); o.castShadow = true; g.add(o); return o; };
  sp(0.5, 0, 0.55, 0, mat, [1, 1.1, 0.9]); sp(0.62, 0, 1.45, 0, mat, [1.05, 0.92, 0.95]); sp(0.17, -0.42, 1.95, 0); sp(0.17, 0.42, 1.95, 0);
  const eye = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.3 }); sp(0.045, -0.2, 1.5, -0.57, eye); sp(0.045, 0.2, 1.5, -0.57, eye);
  sp(0.16, 0, 1.33, -0.56, new THREE.MeshStandardMaterial({ color: 0xf6efe2, roughness: 0.9 }), [1.3, 0.8, 0.7]); sp(0.15, -0.52, 0.75, -0.1, mat, [1, 1.6, 1]); sp(0.15, 0.52, 0.75, -0.1, mat, [1, 1.6, 1]);
  g.position.set(cx, 0, cy); root.add(g); return g;
}
function person(x, y, color, h = 1.68, face = 0) {
  const g = new THREE.Group(), cloth = new THREE.MeshStandardMaterial({ color, roughness: 0.85 }), pants = new THREE.MeshStandardMaterial({ color: 0x3a4250, roughness: 0.9 });
  const l1 = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, h * 0.4, 4, 10), pants); l1.position.set(-0.09, h * 0.25, 0); const l2 = l1.clone(); l2.position.x = 0.09;
  const t = new THREE.Mesh(new THREE.CapsuleGeometry(0.17, h * 0.26, 6, 14), cloth); t.position.y = h * 0.62; t.scale.z = 0.7;
  const hd = new THREE.Mesh(new THREE.SphereGeometry(0.11, 20, 14), new THREE.MeshStandardMaterial({ color: 0xe8c7a8, roughness: 0.8 })); hd.position.y = h * 0.9;
  const hr = new THREE.Mesh(new THREE.SphereGeometry(0.115, 20, 14, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x2a1d15, roughness: 0.9 })); hr.position.y = h * 0.9 + 0.01;
  for (const m of [l1, l2, t, hd, hr]) { m.castShadow = true; g.add(m); } g.position.set(x, 0, y); g.rotation.y = face; root.add(g);
}

// ---------------- Interior shell
if (S.shell) {
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(BW, BD), M.floor); fl.rotation.x = -Math.PI / 2; fl.position.set(BW / 2, 0, BD / 2); fl.receiveShadow = true; root.add(fl);
  if (VIEW === 'aerial' || VIEW === 'top') { const gr = new THREE.Mesh(new THREE.PlaneGeometry(BW * 4, BD * 4), new THREE.MeshStandardMaterial({ color: 0xd9d6cf, roughness: 1 })); gr.rotation.x = -Math.PI / 2; gr.position.set(BW / 2, -0.02, BD / 2); gr.receiveShadow = true; root.add(gr); }
  const wallH = CUT ? 1.1 : (VIEW === 'top' ? 0.4 : BH);
  box(-0.25, 0, 0, BD, 0, wallH, M.wall); box(BW, 0, BW + 0.25, BD, 0, wallH, M.wall); box(-0.25, BD, BW + 0.25, BD + 0.25, 0, CUT ? 3.2 : wallH, M.wall);
  const doors = S.boxes.filter(b => b.type === 'door'); let segs = [[0, BW]];
  for (const d of doors) { const n = []; for (const [a, b] of segs) { if (d.x1 <= a || d.x0 >= b) n.push([a, b]); else { if (d.x0 > a) n.push([a, d.x0]); if (d.x1 < b) n.push([d.x1, b]); } } segs = n; }
  for (const [a, b] of segs) { box(a, -0.06, b, 0, 0, CUT ? 1.1 : BH, M.glass);
    if (!CUT) for (let x = a; x <= b + 0.01; x += (b - a) / Math.max(1, Math.round((b - a) / 2.5))) box(x - 0.03, -0.08, x + 0.03, 0.02, 0, BH, M.dark); }
  if (!CUT) for (const d of doors) { box(d.x0 - 0.05, -0.1, d.x0 + 0.05, 0.05, 0, 2.6, M.dark); box(d.x1 - 0.05, -0.1, d.x1 + 0.05, 0.05, 0, 2.6, M.dark); box(d.x0, -0.1, d.x1, 0.05, 2.6, BH, M.dark); }
  for (const [cx, cy] of S.columns) box(cx - 0.3, cy - 0.3, cx + 0.3, cy + 0.3, 0, CUT ? 3.0 : BH, M.column);
  if (!CUT && VIEW !== 'top') {
    const c = new THREE.Mesh(new THREE.PlaneGeometry(BW, BD), new THREE.MeshStandardMaterial({ color: 0xf2f0ec, roughness: 1 })); c.rotation.x = Math.PI / 2; c.position.set(BW / 2, BH, BD / 2); root.add(c);
    const lm = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xfff4e0, emissiveIntensity: 2.2 });
    for (let x = 2; x < BW; x += 3) for (let y = 1.5; y < BD; y += 3) { const l = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.02, 20), lm); l.position.set(x, BH - 0.01, y); root.add(l); }
  }
  for (let x = 3; x < BW; x += 6) for (let y = 3.5; y < BD; y += 7) { const p = new THREE.PointLight(0xfff1dc, 7, 9, 2); p.position.set(x, BH - 0.3, y); root.add(p); }
}

// ---------------- Fixtures
for (const i of S.boxes) {
  const vertical = (i.y1 - i.y0) > (i.x1 - i.x0), cx = (i.x0 + i.x1) / 2, cy = (i.y0 + i.y1) / 2;
  switch (i.type) {
    case 'wall_shelf': {
      box(i.x0, i.y0, i.x1, i.y1, 0, 0.12, M.dark);
      if (vertical) { const bx = i.x0 < BW / 2 ? i.x0 : i.x1 - 0.04; box(bx, i.y0, bx + 0.04, i.y1, 0, i.h, M.wood); }
      else { const by = i.y1 > BD - 1 ? i.y1 - 0.04 : i.y0; box(i.x0, by, i.x1, by + 0.04, 0, i.h, M.wood); }
      for (const z of [0.12, 0.55, 0.95, 1.35, 1.75].filter(z => z < i.h - 0.2)) { box(i.x0 + .02, i.y0 + .02, i.x1 - .02, i.y1 - .02, z, z + 0.03, M.white); products(i.x0 + .05, i.y0 + .05, i.x1 - .05, i.y1 - .05, z + .03, z > 1.2 ? 'plush' : 'mix', 1.1); }
      box(i.x0, i.y0, i.x1, i.y1, i.h - 0.04, i.h, M.wood); break; }
    case 'island': {
      box(i.x0 + .08, i.y0 + .08, i.x1 - .08, i.y1 - .08, 0, Math.max(0.05, i.h - 0.35), M.white, 0.04); box(i.x0, i.y0, i.x1, i.y1, Math.max(0.05, i.h - 0.35), Math.max(0.1, i.h - 0.3), M.wood, 0.02);
      products(i.x0 + .05, i.y0 + .05, i.x1 - .05, i.y1 - .05, Math.max(0.1, i.h - 0.3), 'mix', 1.0);
      const a = (i.x1 - i.x0) * .3, b = (i.y1 - i.y0) * .3; box(i.x0 + a, i.y0 + b, i.x1 - a, i.y1 - b, Math.max(0.1, i.h - 0.3), i.h, M.wood); products(i.x0 + a, i.y0 + b, i.x1 - a, i.y1 - b, i.h, 'plush', 1.3); break; }
    case 'gondola': {
      box(i.x0, i.y0, i.x1, i.y1, 0, 0.12, M.dark);
      if (vertical) box(cx - .02, i.y0, cx + .02, i.y1, 0, i.h, M.wood); else box(i.x0, cy - .02, i.x1, cy + .02, 0, i.h, M.wood);
      for (const z of [0.12, 0.6, 1.05, 1.5].filter(z => z < i.h - 0.1)) { box(i.x0, i.y0, i.x1, i.y1, z, z + .03, M.white); products(i.x0 + .04, i.y0 + .04, i.x1 - .04, i.y1 - .04, z + .03, 'mix', 1); } break; }
    case 'bin': box(i.x0, i.y0, i.x1, i.y1, 0, i.h - 0.25, M.yellow, 0.03); products(i.x0 + .03, i.y0 + .03, i.x1 - .03, i.y1 - .03, i.h - 0.25, 'mix', 2.2); break;
    case 'window': box(i.x0, i.y0, i.x1, i.y1, 0, i.h, M.white, 0.03); products(i.x0 + .2, i.y0 + .1, i.x1 - .2, i.y1 - .1, i.h, 'plush', 0.9); bearFigure(cx, cy, 0.45, plushM[0]); break;
    case 'checkout': {
      const cm = i.zone === 'cafe' ? M.wood : M.white;
      box(i.x0, i.y0, i.x1, i.y1, 0, i.h, cm, 0.04); box(i.x0 - .02, i.y0 - .02, i.x1 + .02, i.y1 + .02, i.h, i.h + .04, M.wood);
      const n = i.n || Math.max(1, Math.round((vertical ? i.y1 - i.y0 : i.x1 - i.x0) / 1.8));
      for (let k = 0; k < n; k++) { const t = (k + .5) / n, px = vertical ? cx : i.x0 + t * (i.x1 - i.x0), py = vertical ? i.y0 + t * (i.y1 - i.y0) : cy;
        const s = box(px - .18, py - .02, px + .18, py + .02, i.h + .15, i.h + .42, M.dark); s.rotation.y = vertical ? Math.PI / 2 : 0; box(px - .02, py - .02, px + .02, py + .02, i.h, i.h + .16, M.steel); }
      break; }
    case 'figure': bearFigure(cx, cy, 1.25, plushM[0]); { const b = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.05, 0.12, 48), M.yellow); b.position.set(cx, .06, cy); add(b); } break;
    case 'media': {
      box(i.x0, i.y0, i.x1, i.y1, 0.3, i.h, M.dark);
      const m = new THREE.Mesh(new THREE.PlaneGeometry((vertical ? i.y1 - i.y0 : i.x1 - i.x0) - 0.1, i.h - 0.4), M.media);
      if (vertical) { m.position.set(i.x1 + .01, (i.h + .3) / 2, cy); m.rotation.y = Math.PI / 2; } else { m.position.set(cx, (i.h + .3) / 2, i.y0 - .01); m.rotation.y = Math.PI; }
      if (NORTH) m.scale.x = -1; root.add(m); break; }
    case 'stock': box(i.x0, i.y0, i.x1, i.y1, 0, CUT ? 2.4 : i.h, M.stock); break;
    case 'block': box(i.x0, i.y0, i.x1, i.y1, 0, i.h || 1, new THREE.MeshStandardMaterial({ color: i.color ? new THREE.Color(...i.color) : 0xcccccc, roughness: .7 })); break;
    case 'kiosk': {
      const r = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.62, i.h, 40), M.white); r.position.set(cx, i.h / 2, cy); add(r);
      for (let k = 0; k < 4; k++) { const a = k * Math.PI / 2 + Math.PI / 4, s = new THREE.Mesh(new THREE.BoxGeometry(.42, .62, .03), M.media); s.position.set(cx + Math.sin(a) * .64, 1.35, cy + Math.cos(a) * .64); s.rotation.y = a; root.add(s); } break; }
    case 'room': {
      const t = 0.1, mid = cx, rm = new THREE.MeshStandardMaterial({ color: 0xffe9d6, roughness: 0.9 });
      box(i.x0, i.y0, i.x0 + t, i.y1, 0, i.h, rm); box(i.x1 - t, i.y0, i.x1, i.y1, 0, i.h, rm); box(i.x0, i.y0, mid - 1.1, i.y0 + t, 0, i.h, rm); box(mid + 1.1, i.y0, i.x1, i.y0 + t, 0, i.h, rm); box(mid - 1.1, i.y0, mid + 1.1, i.y0 + t, 2.2, i.h, rm); break; }
    case 'stair': {
      const mid = cx, n = 14, rise = Math.min(2.2, BH * 0.55), run = (i.y1 - i.y0) / n;
      for (let k = 0; k < n; k++) box(i.x0 + .05, i.y0 + k * run, mid - .05, i.y0 + (k + 1) * run, 0, (k + 1) * rise / n, M.white);
      box(mid + .05, i.y0 + .05, i.x1 - .05, i.y1 - .05, 0, .012, new THREE.MeshStandardMaterial({ color: 0x3a3a3a, roughness: 1 }));
      box(i.x0, i.y0, i.x0 + .03, i.y1, 0, 1.1, M.glass); box(i.x1 - .03, i.y0, i.x1, i.y1, 0, 1.1, M.glass); box(i.x0, i.y1 - .03, i.x1, i.y1, 0, 1.1, M.glass); break; }
    case 'elevator': box(i.x0, i.y0, i.x1, i.y1, 0, CUT ? 2.6 : BH, M.steel); box(i.x0 + .35, i.y0 - .02, i.x1 - .35, i.y0, 0, 2.2, M.dark); break;
    case 'tables': {
      const tm = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 });
      for (let yy = i.y0 + 0.9; yy < i.y1 - 0.5; yy += 1.7) for (let xx = i.x0 + 0.9; xx < i.x1 - 0.5; xx += 2.2) {
        const tp = new THREE.Mesh(new THREE.CylinderGeometry(.38, .38, .04, 32), tm); tp.position.set(xx, .74, yy); add(tp);
        const lg = new THREE.Mesh(new THREE.CylinderGeometry(.04, .04, .72, 12), M.steel); lg.position.set(xx, .36, yy); add(lg);
        for (const dx of [-.62, .62]) { const st = new THREE.Mesh(new THREE.CylinderGeometry(.2, .2, .05, 24), M.wood); st.position.set(xx + dx, .45, yy); add(st); box(xx + dx + (dx > 0 ? .14 : -.2), yy - .18, xx + dx + (dx > 0 ? .2 : -.14), yy + .18, .45, .85, M.wood); } }
      break; }
    case 'queue': if ((i.x1 - i.x0) < 3.5) { const xs = [i.x0 + .05, cx, i.x1 - .05];
      for (const x of xs) for (let y = i.y0 + .3; y <= i.y1 - .2; y += 1.0) { const p = new THREE.Mesh(new THREE.CylinderGeometry(.03, .03, .95, 12), M.steel); p.position.set(x, .475, y); add(p);
        if (y + 1.0 <= i.y1 - .2 && !(x === xs[1] && y < i.y0 + .6)) box(x - .01, y, x + .01, y + 1.0, .86, .91, M.belt); } } break;
  }
}
for (const s of (S.signs || [])) if (VIEW !== 'top') sign(...s);
const PC = [0xe57373, 0x64b5f6, 0x81c784, 0xffb74d, 0xba68c8, 0xf06292, 0x4db6ac, 0x7986cb, 0xa1887f, 0xffd54f, 0x90a4ae, 0x4fc3f7, 0xaed581, 0xff8a65, 0x9575cd];
(S.people || []).forEach((p, k) => person(p[0], p[1], PC[k % PC.length], 1.55 + rnd() * .25, rnd() * 6.28));

// ---------------- Terrain (SAR DEM heightfield)
if (S.heightfield) {
  const hf = S.heightfield, Z = hf.z, ny = Z.length, nx = Z[0].length;
  const xs = hf.xs || Array.from({ length: nx }, (_, i) => i * hf.mpp), ys = hf.ys || Array.from({ length: ny }, (_, j) => j * hf.mpp);
  const zmin = hf.zmin ?? Math.min(...Z.flat()), zmax = hf.zmax ?? Math.max(...Z.flat()), zr = Math.max(1e-6, zmax - zmin);
  const pos = new Float32Array(nx * ny * 3), col = new Float32Array(nx * ny * 3), idx = [];
  const pal = t => { const g = [0.34, 0.45, 0.24], f = [0.20, 0.33, 0.17], r = [0.46, 0.43, 0.39], s = [0.86, 0.88, 0.92];
    const mix = (a, b, u) => a.map((v, k) => v * (1 - u) + b[k] * u), cl = v => Math.min(1, Math.max(0, v));
    let c = mix(g, f, cl((t - .12) / .3)); c = mix(c, r, cl((t - .55) / .2)); return mix(c, s, cl((t - .82) / .12)); };   // sar/camera.py elevation-band palette
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) { const k = j * nx + i;
    pos.set([xs[i], Z[j][i], ys[j]], 3 * k); const c = hf.colors ? hf.colors[j][i] : pal((Z[j][i] - zmin) / zr); col.set(c, 3 * k); }
  for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) { const a = j * nx + i, b = a + 1, c = a + nx, d = c + 1; idx.push(a, c, b, b, c, d); }   // Local normal = +Y (three handles the mirroring)
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('color', new THREE.BufferAttribute(col, 3)); g.setIndex(idx); g.computeVertexNormals();
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, side: THREE.DoubleSide })); m.receiveShadow = true; m.castShadow = true; root.add(m);
}
// ---------------- SceneDB features (instanced; same material RGB as the SAR RGB view)
{
  const byK = {}; for (const p of (S.props || [])) (byK[p.kind] = byK[p.kind] || []).push(p);
  const dummy = new THREE.Object3D(), C = new THREE.Color();
  const inst = (geo, mat, list, place) => { const im = new THREE.InstancedMesh(geo, mat, list.length); list.forEach((p, k) => { place(p, dummy); dummy.updateMatrix(); im.setMatrixAt(k, dummy.matrix);
    const c = p.color || [0.5, 0.5, 0.5], v = 0.85 + rnd() * 0.3; im.setColorAt(k, C.setRGB(c[0] * v, c[1] * v, c[2] * v, THREE.SRGBColorSpace)); }); im.castShadow = im.receiveShadow = true; root.add(im); };
  const std = () => new THREE.MeshStandardMaterial({ roughness: 0.9 });
  // Tree geometry = render3d/visibility.TREE (single source). The same tree the numpy ray visibility measures.
  if (byK.tree) { inst(new THREE.ConeGeometry(TREE.cone_r, 1, TREE.segments), std(), byK.tree, (p, d) => { d.position.set(p.x, p.z + p.size * TREE.cone_c, p.y); d.scale.set(p.size, p.size * TREE.cone_h, p.size); d.rotation.set(0, 0, 0); });
    inst(new THREE.CylinderGeometry(TREE.trunk_r, TREE.trunk_r, 1, 16), new THREE.MeshStandardMaterial({ color: 0x5a3f2a }), byK.tree.map(p => ({ ...p, color: [0.35, 0.25, 0.17] })), (p, d) => { d.position.set(p.x, p.z + p.size * TREE.trunk_c, p.y); d.scale.set(p.size, p.size * TREE.trunk_h, p.size); }); }
  // Lying person: 0.5 x 1.7 m (visibility.PERSON). Centred 0.15 m above the ground, 0.25 m thick. yaw_deg = rotation from +x.
  if (byK.person) inst(new THREE.BoxGeometry(0.5, 0.25, 1.7), new THREE.MeshStandardMaterial({ roughness: 0.7 }), byK.person.map(p => ({ ...p, color: p.color || [0.85, 0.12, 0.10] })),
    (p, d) => { d.position.set(p.x, p.z + 0.15, p.y); d.scale.set(1, 1, 1); d.rotation.set(0, -(p.yaw_deg || 0) * Math.PI / 180, 0); });   // width axis = (cos yaw, sin yaw), same as the vv G mask plate
  if (byK.rock) inst(new THREE.DodecahedronGeometry(0.5, 0), std(), byK.rock, (p, d) => { d.position.set(p.x, p.z + p.size * 0.2, p.y); d.scale.set(p.size, p.size * 0.6, p.size * 0.8); d.rotation.set(0, rnd() * 6, 0); });
  if (byK.building) inst(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial({ roughness: 0.6 }), byK.building, (p, d) => { d.position.set(p.x, p.z + p.size * 0.35, p.y); d.scale.set(p.size, p.size * 0.7, p.size * 0.8); d.rotation.set(0, 0, 0); });
}
// ---------------- IV&V markers and paths (the viewer may see truth -- sar/ivv/viewer.py rule)
{
  const sc = Math.max(1, BIG / 150);
  for (const pth of (S.paths || [])) { if (pth.pts.length < 2) continue;
    const curve = new THREE.CatmullRomCurve3(pth.pts.map(p => new THREE.Vector3(p[0], p[2], p[1])));
    const col = pth.kind === 'uav_track' ? 0x00c8ff : 0x1e8449;
    const m = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.min(600, pth.pts.length * 8), (S.heightfield ? 0.5 : 0.04) * sc, 8, false), new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.5 })); root.add(m); }
  for (const mk of (S.markers || [])) {
    if (mk.kind === 'uav') { const g = new THREE.Group(), b = new THREE.Mesh(new THREE.BoxGeometry(2.4 * sc, 0.6 * sc, 2.4 * sc), new THREE.MeshStandardMaterial({ color: 0xe53935, metalness: .3, roughness: .4 })); g.add(b);
      for (const [dx, dz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) { const r = new THREE.Mesh(new THREE.CylinderGeometry(1.1 * sc, 1.1 * sc, 0.1 * sc, 20), M.dark); r.position.set(dx * 1.8 * sc, 0.4 * sc, dz * 1.8 * sc); g.add(r); }
      g.position.set(mk.x, mk.z, mk.y); g.traverse(o => o.castShadow = true); root.add(g); }
    else { const c = mk.kind === 'truth' ? 0xe53935 : (mk.kind === 'detect' ? 0x43a047 : 0xfee500);
      const s = new THREE.Mesh(mk.kind === 'detect' ? new THREE.ConeGeometry(1.4 * sc, 3 * sc, 16) : new THREE.SphereGeometry(1.2 * sc, 24, 16), new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: .35 }));
      s.position.set(mk.x, mk.z + (mk.kind === 'detect' ? 5 : 1.5) * sc, mk.y); if (mk.kind === 'detect') s.rotation.x = Math.PI; s.castShadow = true; root.add(s);
      const beam = new THREE.Mesh(new THREE.CylinderGeometry(.15 * sc, .15 * sc, 20 * sc, 8), new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: .45 })); beam.position.set(mk.x, mk.z + 10 * sc, mk.y); root.add(beam); }
  }
}

// ---------------- Lighting
scene.add(new THREE.HemisphereLight(0xfffaf0, 0xcdbd9c, S.heightfield ? 1.1 : 0.75));
const sun = new THREE.DirectionalLight(0xfff3e0, S.heightfield ? 2.6 : 2.2), ctr = T3(BW / 2, BD / 2, 0);
sun.position.copy(ctr).add(new THREE.Vector3(-0.25 * BIG, 0.75 * BIG + BH, 0.33 * BIG)); sun.target.position.copy(ctr);
sun.castShadow = !S.linear_output; sun.shadow.mapSize.set(4096, 4096);
Object.assign(sun.shadow.camera, { left: -0.75 * BIG, right: 0.75 * BIG, top: 0.75 * BIG, bottom: -0.75 * BIG, near: 0.1, far: 3 * BIG + BH * 3 });
sun.shadow.bias = -0.0004; sun.shadow.radius = 4; scene.add(sun, sun.target);

// ---------------- Camera
let cam;
const views = Object.keys(S.views || {});
if (VIEW === 'top') {
  const a = Wpx / Hpx, hh = BD / 2 + BIG * 0.03; cam = new THREE.OrthographicCamera(-hh * a, hh * a, hh, -hh, 0.1, 10 * BIG + BH * 10);
  cam.position.copy(T3(BW / 2, BD / 2, BH * 3 + 5 * BIG)); cam.up.set(0, 0, -1); cam.lookAt(T3(BW / 2, BD / 2, 0));
  // Up vector: north at the top of the image (north plan: +y up; DEM: +y=south down). The first version had this comment in the middle of the line
  // and commented out lookAt -- the top view looked in the wrong direction.
} else {
  // near plane: the first version used BIG/20000 (0.07 m for a 1.4 km terrain) -> at 1.1 km the depth resolution was ~1 m and a person
  // 0.15 m above the ground z-fought the terrain (vv G: 0.509 visible vs 1.0). views[].near can set it; default = scene size / 2000.
  const v = S.views[VIEW] || S.views[views[0]]; cam = new THREE.PerspectiveCamera(v.fov, Wpx / Hpx, v.near || Math.max(0.05, BIG / 2000), 50 * BIG + BH * 20);
  cam.position.copy(T3(...v.pos)); cam.lookAt(T3(...v.target));
}
// V&V: unlit planes (always facing the camera). pixel = transmittance x colour (linear output)
for (const q of (S.unlit_planes || [])) { const m = new THREE.Mesh(new THREE.PlaneGeometry(q.size, q.size), new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(...(q.color || [1, 1, 1]), THREE.LinearSRGBColorSpace), fog: true }));
  m.position.copy(T3(q.x, q.y, q.z)); m.lookAt(cam.position); scene.add(m); }

// V&V mask mode (vv G): target = white, everything else = black (or hidden). Visible fraction = white pixels with occluders / without.
if (S.mask) {
  const blk = new THREE.MeshBasicMaterial({ color: 0x000000 });
  root.traverse(o => { if (o.isMesh) { o.material = blk; if (o.isInstancedMesh) o.instanceColor = null; o.castShadow = o.receiveShadow = false; if (!S.mask.occluders) o.visible = false; } });
  scene.fog = null; scene.background = new THREE.Color(0x000000); scene.environment = null;
  const g = new THREE.Group(); g.position.set(S.mask.x, S.mask.z, S.mask.y); g.rotation.y = -(S.mask.yaw_deg || 0) * Math.PI / 180;
  const t = new THREE.Mesh(new THREE.PlaneGeometry(S.mask.w, S.mask.l), new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide }));
  t.rotation.x = -Math.PI / 2; g.add(t); root.add(g);
}
// ---------------- Mission animation (render3d/mission_anim.py): UAV flight + live log of the 10 Hz state / 1 Hz report / events / policy decisions
let ANIM_RUN = null;
if (S.anim) {
  const A = S.anim, ST = A.states, last = ST.length ? ST[ST.length - 1][0] : 0;
  const MODE0 = P.get('cam') || 'chase';
  const TOUR = MODE0 === 'tour';   // for the recording: chase -> onboard RGB -> aerial in turn
  let mode = TOUR ? 'chase' : MODE0, speed = +(P.get('speed') || A.speed || 20), playing = true, t0 = performance.now(), tpause = 0;
  // UAV (x3 exaggerated in chase/onboard, scene-scaled in the aerial view)
  const uav = new THREE.Group();
  uav.add(new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.25, 0.8), new THREE.MeshStandardMaterial({ color: 0xe53935, metalness: .3, roughness: .4 })));
  for (const [dx, dz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) { const r = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.04, 20), M.dark); r.position.set(dx * 0.6, 0.15, dz * 0.6); uav.add(r); }
  root.add(uav);
  const pts = ST.filter((s, i) => i % 10 === 0).map(s => new THREE.Vector3(s[1], s[3], s[2]));
  if (pts.length > 1) root.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x00a8e0 })));  // 1 px line: does not block the view at any distance
  const beacons = [];
  for (const [x, y, z] of (A.truth || [])) { const b = new THREE.Mesh(new THREE.CylinderGeometry(BIG / 900, BIG / 900, BIG / 25, 8), new THREE.MeshBasicMaterial({ color: 0xe53935, transparent: true, opacity: .5 }));
    b.position.set(x, z + BIG / 50, y); root.add(b); beacons.push(b); }
  // Panel (right side): 10 Hz gauges / 1 Hz report / event+decision log
  const css = document.createElement('style'); css.textContent = `#pan{position:fixed;right:0;top:0;bottom:0;width:36%;background:#0d1117e6;color:#dfe7f1;font:12px/1.45 "Noto Sans KR","WenQuanYi Zen Hei",monospace;padding:10px 12px;box-sizing:border-box;display:flex;flex-direction:column;gap:6px}
  #pan h4{margin:2px 0;font-size:12px;color:#8fb8ff;font-weight:700}#g{display:grid;grid-template-columns:1fr 1fr;gap:2px 10px}#g b{color:#fff}
  #rep{background:#161c26;padding:4px 6px;border-radius:4px;white-space:pre-wrap;min-height:34px}#log{flex:1;overflow:hidden;background:#161c26;padding:4px 6px;border-radius:4px;display:flex;flex-direction:column-reverse}
  .ev{color:#ffd166}.dc{color:#9be7a8}.mrc{color:#ff6b6b}.dt{color:#ff9f43}#bar{position:fixed;left:10px;bottom:10px;color:#fff;background:#000a;padding:4px 8px;border-radius:4px;font:12px sans-serif}
  #bar button{margin-right:4px}`;
  document.head.appendChild(css);
  const pan = document.createElement('div'); pan.id = 'pan';
  pan.innerHTML = `<h4>자율 정책 실시간 로그 — ${S.name}</h4><div style="color:#93a1b5">스펙: 기계상태 ${A.state_hz} Hz · 운용보고 ${A.report_hz} Hz · 이벤트 즉시 · SUT 결정 ${A.decision_s}s 마다 (10 Hz 는 갱신 주기, 대역폭 아님)</div>
  <h4>10 Hz 기계 상태</h4><div id=g></div><h4>1 Hz 운용 보고</h4><div id=rep></div><h4>이벤트 · 정책 결정 근거</h4><div id=log></div>`;
  document.body.appendChild(pan);
  const bar = document.createElement('div'); bar.id = 'bar';
  bar.innerHTML = `<button data-m=chase>추적</button><button data-m=onboard>탑재 RGB</button><button data-m=aerial>조감</button><button id=pp>일시정지</button> <span id=tt></span>`;
  document.body.appendChild(bar);
  bar.querySelectorAll('button[data-m]').forEach(b => b.onclick = () => { mode = b.dataset.m; });
  document.getElementById('pp').onclick = () => { playing = !playing; if (playing) t0 = performance.now() - tpause * 1000 / speed; document.getElementById('pp').textContent = playing ? '일시정지' : '재생'; };
  const G = document.getElementById('g'), REP = document.getElementById('rep'), LOG = document.getElementById('log'), TT = document.getElementById('tt');
  let ie = 0, id = 0, ir = 0;
  const lo = tt => { let a = 0, b = ST.length; while (a < b) { const m = (a + b) >> 1; if (ST[m][0] < tt) a = m + 1; else b = m; } return a; };
  const line = (cls, txt) => { const d = document.createElement('div'); d.className = cls; d.textContent = txt; LOG.prepend(d); while (LOG.childNodes.length > 60) LOG.removeChild(LOG.lastChild); };
  const fmt = t => 'T+' + t.toFixed(1).padStart(6, '0');
  const fogObj = FOG_ON || !S.fog ? scene.fog : new THREE.FogExp2(fogC, S.fog.beta);
  ANIM_RUN = () => {
    const ts = playing ? (performance.now() - t0) / 1000 * speed : tpause; if (playing) tpause = ts;
    const i = Math.min(ST.length - 1, Math.max(0, Math.floor(ts * A.state_hz)));
    const s = ST[i]; if (!s) return true;
    const [t, x, y, z, hd, pol, vis, sig, cov, vel, agl] = s;
    if (TOUR) mode = ts < 0.45 * last ? 'chase' : ts < 0.75 * last ? 'onboard' : 'aerial';
    uav.position.set(x, z, y); uav.rotation.y = -hd * Math.PI / 180;
    const k = mode === 'aerial' ? BIG / 150 : 3; uav.scale.set(k, k, k);
    const h = hd * Math.PI / 180;
    if (mode === 'chase') { cam.fov = 50; cam.position.copy(T3(x - 70 * Math.cos(h), y - 70 * Math.sin(h), z + 35)); cam.lookAt(T3(x + 60 * Math.cos(h), y + 60 * Math.sin(h), z - 30)); }
    else if (mode === 'onboard') { const p = (A.rgb_pitch_deg || -30) * Math.PI / 180; cam.fov = A.rgb_fov_v || 50;
      cam.position.copy(T3(x, y, z - 1)); cam.lookAt(T3(x + 100 * Math.cos(h) * Math.cos(p), y + 100 * Math.sin(h) * Math.cos(p), z - 1 + 100 * Math.sin(p))); }
    else { const v = S.views.aerial; cam.fov = v.fov; cam.position.copy(T3(...v.pos)); cam.lookAt(T3(...v.target)); }
    cam.near = mode === 'aerial' ? Math.max(0.5, BIG / 2000) : 0.5; cam.updateProjectionMatrix();
    uav.visible = mode !== 'onboard';
    for (const b of beacons) b.visible = mode !== 'onboard';   // truth beacons are for the observer view only -- not in the onboard (SUT) view
    scene.fog = (mode === 'onboard') ? fogObj : null;
    if (S.fog) scene.background = (mode === 'onboard') ? fogC.clone() : new THREE.Color(0xbfd3e6);
    // Receive rate = the number of state packets actually in the stream over the last 1 sim second (counted from the timestamps, not copied from the spec). Independent of the render frame rate.
    const hz = t >= 1 ? (i + 1 - lo(t - 1 + 1e-9)) / 1.0 : 0;
    G.innerHTML = `<span>시각 <b>${fmt(t)}</b></span><span>정책 <b style="color:${pol === 'MRC' ? '#ff6b6b' : pol === 'SEARCHING' ? '#9be7a8' : '#ffd166'}">${pol}</b></span>
      <span>위치 <b>${x.toFixed(0)}, ${y.toFixed(0)} m</b></span><span>고도 <b>${(agl ?? 0).toFixed(0)} m AGL</b> (해발 ${z.toFixed(0)})</span><span>속도 <b>${vel.toFixed(1)} m/s</b></span><span>방위 <b>${String(Math.round(((hd % 360) + 360) % 360)).padStart(3, '0')}°</b></span>
      <span>RGB vis <b>${vis.toFixed(2)}</b></span><span>IMU σ <b>${sig.toFixed(1)} m</b></span><span>커버리지 <b>${cov.toFixed(1)}%</b></span><span>수신 <b>${hz.toFixed(1)} Hz</b> (재생 ×${speed})</span>`;
    while (ir < A.reports.length && A.reports[ir][0] <= t) { REP.textContent = A.reports[ir][1]; ir++; }
    for (;;) {   // decisions and events in time order (a decision comes before an event at the same time -- the decision produces the event)
      const td = id < A.decisions.length ? A.decisions[id][0] : Infinity, te = ie < A.events.length ? A.events[ie][0] : Infinity;
      if (Math.min(td, te) > t) break;
      if (td <= te) { const d = A.decisions[id]; line(d[1] === 'MRC' ? 'mrc' : 'dc', `${fmt(d[0])} [결정 ${id + 1}] ${d[2]}`); line('', `         ${d[3]}`); id++; }
      else { const e = A.events[ie]; line(e[1] === 'MRC' ? 'mrc' : e[1] === 'DETECT' ? 'dt' : 'ev', `${fmt(e[0])} [${e[1]}] ${e[2]}`); ie++; }
    }
    TT.textContent = `${fmt(t)} / ${fmt(last)} · 시점 ${mode}`;
    return ts >= last;
  };
}
const hud = document.getElementById('hud');
if (S.anim) {
  hud.remove();
  window.__done = true;
  renderer.setAnimationLoop(() => { const end = ANIM_RUN(); renderer.render(scene, cam); if (end) window.__animDone = true; });
} else if (!HEADLESS) {
  hud.innerHTML = `<b>${S.name}</b> · 시점 <select id=vs>${views.concat(['top']).map(k => `<option ${k === VIEW ? 'selected' : ''}>${k}</option>`).join('')}</select>` + (S.fog ? ` · 안개 β=${S.fog.beta.toFixed(4)}/m (${S.fog.model || 'beer_lambert'})` : '');
  document.getElementById('vs').onchange = e => { P.set('view', e.target.value); location.search = P.toString(); };
  import('three/addons/controls/OrbitControls.js').then(({ OrbitControls }) => {
    const oc = new OrbitControls(cam, renderer.domElement); if (VIEW !== 'top' && S.views[VIEW]) oc.target.copy(T3(...S.views[VIEW].target)); oc.update();
    renderer.setAnimationLoop(() => { oc.update(); renderer.render(scene, cam); });
  });
} else hud.remove();
renderer.render(scene, cam);
window.__done = true;
</script></body></html>
"""
