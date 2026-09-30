/* rover3d.js — RECON-R1 실물 치수 3D (1 unit = 1 cm, y 위, x 앞, z 왼쪽). SPEC 는 recon/spec.py 에서 온다.
   makeRoverScene(THREE, renderer, SPEC, root, opts) -> {scene, cam, render(W,H), setExplode(u), setFov(b), setCallouts(b), PARTS} */
function makeRoverScene(THREE, renderer, SPEC, root, opts = {}) {
  const M = SPEC.MECH, CM = 100;
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(30, 16 / 9, 1, 2000);
  if (THREE.RoomEnvironment) { const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromScene(new THREE.RoomEnvironment(), 0.04).texture; }
  scene.background = new THREE.Color(opts.bg || 0x1a1f26);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  scene.add(new THREE.HemisphereLight(0xdfe9ff, 0x3a3226, 0.45));
  const key = new THREE.DirectionalLight(0xfff4e6, 1.2); key.position.set(60, 120, 70); key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, { left: -80, right: 80, top: 80, bottom: -80, near: 10, far: 300 }); key.shadow.bias = -0.0005; scene.add(key);
  const fill = new THREE.DirectionalLight(0xbcd3ff, 0.35); fill.position.set(-60, 40, -50); scene.add(fill);
  let seed = 11; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  function tex(w, h, draw, rep) { const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d"), w, h);
    const t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding; t.anisotropy = 8; if (rep) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep[0], rep[1]); } return t; }
  const std = (c, o = {}) => new THREE.MeshStandardMaterial(Object.assign({ color: c, roughness: 0.5, metalness: 0 }, o));
  const brushed = tex(512, 512, (g, w, h) => { g.fillStyle = "#9aa0a7"; g.fillRect(0, 0, w, h); for (let i = 0; i < 2500; i++) { const v = 130 + rnd() * 60 | 0; g.strokeStyle = `rgba(${v},${v + 3},${v + 8},.35)`; g.beginPath(); const y = rnd() * h; g.moveTo(0, y); g.lineTo(w, y + (rnd() - .5) * 2); g.stroke(); } }, [2, 2]);
  const tread = tex(512, 128, (g, w, h) => { g.fillStyle = "#1b1b1c"; g.fillRect(0, 0, w, h); g.fillStyle = "#101011"; for (let i = 0; i < 24; i++) { const x = i * w / 24; g.beginPath(); g.moveTo(x, 0); g.lineTo(x + 10, 0); g.lineTo(x + 18, h / 2); g.lineTo(x + 10, h); g.lineTo(x, h); g.lineTo(x + 8, h / 2); g.fill(); } }, [1, 1]);
  const pcbT = (col, label, chips) => tex(512, 400, (g, w, h) => { g.fillStyle = col; g.fillRect(0, 0, w, h); g.strokeStyle = "rgba(255,215,120,.35)"; g.lineWidth = 2;
    for (let i = 0; i < 60; i++) { g.beginPath(); let x = rnd() * w, y = rnd() * h; g.moveTo(x, y); x += (rnd() - .5) * 200; g.lineTo(x, y); y += (rnd() - .5) * 150; g.lineTo(x, y); g.stroke(); }
    (chips || []).forEach(([x, y, a, b, c]) => { g.fillStyle = c || "#111"; g.fillRect(x * w, y * h, a * w, b * h); });
    g.fillStyle = "rgba(255,255,255,.85)"; g.font = "bold 34px sans-serif"; g.fillText(label, 16, h - 18); });
  const batT = tex(512, 256, (g, w, h) => { g.fillStyle = "#1d4f91"; g.fillRect(0, 0, w, h); g.fillStyle = "rgba(255,255,255,.9)"; g.font = "bold 40px sans-serif"; g.fillText("4S4P Li-ion 18650", 20, 70); g.font = "30px sans-serif"; g.fillText("14.4 V  10 Ah  144 Wh", 20, 120); g.fillText("BMS 20 A cont.", 20, 165); g.fillStyle = "#f2c12e"; g.fillRect(0, h - 26, w, 10); });
  const lidT = tex(512, 128, (g, w, h) => { g.fillStyle = "#1e2226"; g.fillRect(0, 0, w, h); const gr = g.createLinearGradient(0, 30, 0, 98); gr.addColorStop(0, "#0b0d10"); gr.addColorStop(.5, "#2a3440"); gr.addColorStop(1, "#0b0d10"); g.fillStyle = gr; g.fillRect(0, 34, w, 60); g.fillStyle = "#c8ccd0"; g.font = "bold 22px sans-serif"; g.fillText("LIVOX  MID-360", 170, 24); });
  const groundT = tex(512, 512, (g, w, h) => { g.fillStyle = "#6b604e"; g.fillRect(0, 0, w, h); for (let i = 0; i < 16000; i++) { const v = 70 + rnd() * 90 | 0; g.fillStyle = `rgba(${v},${v - 8},${v - 22},.8)`; const r = rnd() * 3; g.fillRect(rnd() * w, rnd() * h, r, r); } }, [6, 6]);
  const MT = { alu: std(0xb9bfc6, { map: brushed, metalness: 0.9, roughness: 0.38 }), ext: std(0xa9b0b8, { metalness: 0.85, roughness: 0.45 }),
    dark: std(0x23262b, { roughness: 0.6 }), tire: std(0x1c1c1d, { map: tread, roughness: 0.95 }), hub: std(0xd0a02a, { metalness: 0.8, roughness: 0.35 }),
    motor: std(0x8d949c, { metalness: 0.9, roughness: 0.3 }), gear: std(0xc7ccd1, { metalness: 0.9, roughness: 0.25 }), black: std(0x121314, { roughness: 0.5 }),
    red: std(0xc9261d, { roughness: 0.35 }), yellow: std(0xf1c40f, { roughness: 0.45 }), copper: std(0xb87333, { metalness: 1, roughness: 0.3 }),
    wireR: std(0xb3261e, { roughness: 0.45 }), wireK: std(0x18191b, { roughness: 0.45 }), wireB: std(0x1f5fbf, { roughness: 0.45 }), wireY: std(0xd8b41e, { roughness: 0.45 }),
    ground: std(0x6b604e, { map: groundT, roughness: 1 }), glass: std(0x0b1117, { metalness: 0.2, roughness: 0.08, transparent: true, opacity: 0.85 }),
    pc: new THREE.MeshPhysicalMaterial({ color: 0xdfe8ef, transparent: true, opacity: 0.16, roughness: 0.1, metalness: 0, side: THREE.DoubleSide }) };
  function mesh(g, m, parent = scene, cast = true) { const o = new THREE.Mesh(g, m); o.castShadow = cast; o.receiveShadow = true; parent.add(o); return o; }
  const box = (w, h, d, m, p, x, y, z) => { const o = mesh(new THREE.BoxGeometry(w, h, d), m, p); o.position.set(x, y, z); return o; };
  const cyl = (r1, r2, h, m, p, seg = 24) => mesh(new THREE.CylinderGeometry(r1, r2, h, seg), m, p);
  const ground = mesh(new THREE.PlaneGeometry(400, 400), MT.ground, scene, false); ground.rotation.x = -Math.PI / 2;

  const L = M.L * CM, W = M.W * CM, H = M.H_body * CM, gc = M.ground_clear * CM, R = M.wheel_r * CM, WB = M.wheelbase * CM, TR = M.track * CM;
  const y0 = gc, y1 = gc + H;                  // 몸체 바닥·윗면
  const G = { frame: new THREE.Group(), drive: new THREE.Group(), power: new THREE.Group(), comp: new THREE.Group(), sens: new THREE.Group(), safe: new THREE.Group() };
  Object.values(G).forEach(g => scene.add(g));
  /* 2020 프레임: 아래·위 사각 + 기둥 4 */
  const e = 2.0;
  for (const yy of [y0 + e / 2, y1 - e / 2]) {
    box(L, e, e, MT.ext, G.frame, 0, yy, W / 2 - e / 2); box(L, e, e, MT.ext, G.frame, 0, yy, -W / 2 + e / 2);
    box(e, e, W - 2 * e, MT.ext, G.frame, L / 2 - e / 2, yy, 0); box(e, e, W - 2 * e, MT.ext, G.frame, -L / 2 + e / 2, yy, 0);
  }
  for (const [x, z] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) box(e, H - 2 * e, e, MT.ext, G.frame, x * (L / 2 - e / 2), (y0 + y1) / 2, z * (W / 2 - e / 2));
  const lowDeck = box(L - 2 * e, 0.3, W - 2 * e, MT.alu, G.frame, 0, y0 + e + 0.15, 0);
  const topDeck = box(L, 0.3, W, MT.alu, G.frame, 0, y1 + 0.15, 0);
  for (const s of [1, -1]) { const p = box(L - 4, H - 4, 0.3, MT.pc, G.frame, 0, (y0 + y1) / 2, s * (W / 2 + 0.2)); p.castShadow = false; }
  /* 바퀴·모터 */
  const wheels = [];
  for (const [sx, sz] of [[1, 1], [-1, 1], [1, -1], [-1, -1]]) {
    const g = new THREE.Group(); G.drive.add(g); g.position.set(sx * WB / 2, R, sz * TR / 2);
    const t = cyl(R, R, 4, MT.tire, g, 40); t.rotation.x = Math.PI / 2;
    const rim = cyl(R * 0.62, R * 0.62, 4.2, MT.hub, g, 24); rim.rotation.x = Math.PI / 2;
    for (let k = 0; k < 5; k++) { const b = cyl(0.35, 0.35, 4.6, MT.gear, g, 8); b.rotation.x = Math.PI / 2; b.position.set(Math.cos(k * 1.2566) * R * 0.4, Math.sin(k * 1.2566) * R * 0.4, 0); }
    wheels.push(g);
    const mg = new THREE.Group(); G.drive.add(mg); mg.position.set(sx * WB / 2, R, sz * (W / 2 - 4.2));
    const gb = cyl(1.85, 1.85, 2.6, MT.gear, mg); gb.rotation.x = Math.PI / 2; gb.position.z = sz * 1.3;
    const mo = cyl(1.75, 1.75, 5.0, MT.motor, mg); mo.rotation.x = Math.PI / 2; mo.position.z = -sz * 2.5;
    const ec = cyl(1.6, 1.6, 1.6, MT.black, mg); ec.rotation.x = Math.PI / 2; ec.position.z = -sz * 5.8;
    const br = box(4.6, 0.3, 6, MT.alu, mg, 0, -2.0, 0);
    const sh = cyl(0.3, 0.3, 4.5, MT.gear, mg, 10); sh.rotation.x = Math.PI / 2; sh.position.z = sz * 4;
    if (sx === 1 && sz === 1) { G.motorFL = mg; }
  }
  /* 전원: 배터리·BMS·퓨즈·접촉기·DC-DC */
  const bat = box(22, 7.2, 14, [MT.dark, MT.dark, std(0xffffff, { map: batT }), MT.dark, MT.dark, MT.dark].map(m => m), G.power, -3, y0 + e + 0.3 + 3.6, 0);
  bat.material = [std(0x1d4f91), std(0x1d4f91), std(0xffffff, { map: batT }), std(0x1d4f91), std(0x1d4f91), std(0x1d4f91)];
  const xt = box(2.2, 1.2, 1.6, MT.yellow, G.power, 9, y0 + e + 1.2, 6);
  const drvT = pcbT("#b3261e", "MDD20A", [[.1, .1, .25, .2, "#222"], [.45, .1, .2, .2, "#222"], [.1, .5, .8, .15, "#0a5"]]);
  const drv = [box(8.4, 0.2, 6.2, std(0xffffff, { map: drvT }), G.power, 14, y0 + e + 1.0, 8), box(8.4, 0.2, 6.2, std(0xffffff, { map: drvT }), G.power, 14, y0 + e + 1.0, -8)];
  drv.forEach(d => { for (let k = 0; k < 4; k++) box(0.9, 1.4, 0.9, MT.black, d, -3 + k * 1.3, 0.8, -2.2); });
  const fuse = box(6, 2.2, 4, std(0x2b2f36), G.power, -16, y0 + e + 1.4, 9); for (let k = 0; k < 6; k++) box(0.6, 1.2, 1.4, [MT.red, MT.yellow, MT.wireB, std(0x7a3fb1), MT.red, std(0xe8e8e8)][k], fuse, -2.4 + k * 0.95, 1.4, 0);
  const cont = box(4, 4, 4, std(0x2a2a2d), G.power, -16, y0 + e + 2.3, -8); cyl(0.5, 0.5, 1, MT.copper, cont).position.set(-1, 2.3, 0); cyl(0.5, 0.5, 1, MT.copper, cont).position.set(1, 2.3, 0);
  const d5T = pcbT("#1a6b3a", "D36V50F5", [[.3, .2, .4, .4, "#222"]]);
  const dc5 = box(2.5, 0.2, 3.3, std(0xffffff, { map: d5T }), G.power, 3, y0 + e + 0.6, 10);
  const ideal = box(2.2, 0.2, 2.2, std(0xffffff, { map: pcbT("#1a3f6b", "LTC4359", [[.3, .3, .4, .3, "#222"]]) }), G.power, 3, y0 + e + 0.6, -10);
  const capy = cyl(0.8, 0.8, 2, std(0x20304a), ideal); capy.position.set(0, 1.1, 0.5);
  /* 계산: Jetson · Nucleo · IMU */
  const jT = pcbT("#0d2f25", "JETSON ORIN NANO", [[.05, .05, .9, .08, "#555"], [.1, .7, .15, .15, "#333"], [.35, .72, .15, .12, "#333"]]);
  const jet = box(10, 0.2, 7.9, std(0xffffff, { map: jT }), G.comp, -8, y1 + 1.2, 4);
  const hs = box(7, 2.2, 6.5, MT.dark, jet, 0, 1.3, 0); for (let k = 0; k < 13; k++) box(0.15, 1.6, 6.4, MT.alu, hs, -3.1 + k * 0.52, 1.5, 0);
  const fan = cyl(2.6, 2.6, 0.6, MT.black, hs, 24); fan.position.y = 2.6;
  for (let k = 0; k < 4; k++) box(0.5, 1.2, 2.4, std(0x888888), jet, -4 - 0.2 + (k % 2) * 0.0, 0.7, -2.5 + k * 1.4);
  for (const [px, pz] of [[-4.7, -3.6], [4.7, -3.6], [-4.7, 3.6], [4.7, 3.6]]) cyl(0.3, 0.3, 1.2, MT.alu, jet, 8).position.set(px, -0.6, pz);
  const nT = pcbT("#141414", "NUCLEO-H753ZI", [[.35, .3, .3, .3, "#333"], [.02, .1, .96, .05, "#666"], [.02, .85, .96, .05, "#666"]]);
  const nuc = box(13.4, 0.2, 7.0, std(0xffffff, { map: nT }), G.comp, 11, y1 + 1.0, 6);
  const imu = box(2.0, 0.2, 2.0, std(0xffffff, { map: pcbT("#6b1a6b", "ICM-42688", [[.35, .35, .3, .3, "#111"]]) }), G.comp, 0, y1 + 0.8, -6);
  /* 안전: E-stop · 무선 킬 */
  const esb = box(6, 4, 6, MT.yellow, G.safe, -18, y1 + 2.3, -9);
  const esm = cyl(2.4, 2.0, 1.6, MT.red, esb, 32); esm.position.y = 2.8; const esc = cyl(1, 1, 1.4, MT.red, esb, 16); esc.position.y = 2.1;
  const rxa = cyl(0.12, 0.12, 16, MT.black, G.safe, 8); rxa.position.set(-20, y1 + 8, 12);
  const rxb = box(3, 1.2, 2, MT.black, G.safe, -20, y1 + 0.8, 12);
  /* 센서: 마스트 · Mid-360(뒤집음) · 카메라 · GNSS */
  const lx = M.lidar_x * CM, lh = M.lidar_h * CM;
  const mastH = lh + 3.5 - y1;
  const mast = cyl(1.0, 1.0, mastH, MT.alu, G.sens, 16); mast.position.set(lx, y1 + mastH / 2, 0);
  const mbase = box(8, 0.5, 8, MT.alu, G.sens, lx, y1 + 0.5, 0);
  const mtop = box(9, 0.5, 9, MT.alu, G.sens, lx, lh + 3.5, 0);
  const lid = new THREE.Group(); G.sens.add(lid); lid.position.set(lx, lh, 0);
  const lbody = cyl(3.25, 3.25, 6.0, [std(0xffffff, { map: lidT, roughness: .4 }), MT.dark, MT.dark], lid, 48);
  lbody.material = [std(0xffffff, { map: lidT, roughness: .35, metalness: .3 }), std(0x2a2e33), std(0x0b0d10)];
  const dome = mesh(new THREE.SphereGeometry(3.2, 32, 12, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), MT.glass, lid); dome.position.y = -3.0; dome.scale.y = 0.35;
  const cab = new THREE.CatmullRomCurve3([[lx + 2.5, lh + 3.5, 0], [lx + 3, lh - 6, 0.5], [lx + 1.5, y1 + 10, 1.5], [lx - 6, y1 + 1, 4]].map(p => new THREE.Vector3(...p)));
  mesh(new THREE.TubeGeometry(cab, 60, 0.3, 8), MT.wireK, G.sens);
  const camG = new THREE.Group(); G.sens.add(camG); camG.position.set(M.cam_x * CM, M.cam_h * CM, 0); camG.rotation.z = M.cam_pitch_deg * Math.PI / 180;
  box(0.2, 2.5, 2.4, std(0xffffff, { map: pcbT("#0d4d2b", "IMX219", [[.35, .35, .3, .3, "#111"]]) }), camG, 0, 0, 0);
  const lens = cyl(0.45, 0.45, 0.7, MT.black, camG, 16); lens.rotation.z = Math.PI / 2; lens.position.x = 0.4;
  const cpost = box(1.0, M.cam_h * CM - y1, 1.0, MT.alu, G.sens, M.cam_x * CM - 0.6, (M.cam_h * CM + y1) / 2, 0);
  const garm = box(10, 0.4, 1.2, MT.alu, G.sens, lx - 5, lh + 3.9, -6); const gant = cyl(3.2, 3.2, 1.4, std(0xe8e8e8), G.sens, 32); gant.position.set(lx - 9, lh + 4.8, -6);
  const gnssB = box(4.3, 0.2, 4.3, std(0xffffff, { map: pcbT("#b3261e", "ZED-F9P", [[.3, .3, .4, .4, "#222"]]) }), G.sens, -14, y1 + 0.8, 3);
  /* 배선 몇 가닥 */
  const wire = (pts, m, r = 0.35) => mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map(p => new THREE.Vector3(...p))), 60, r, 8), m, G.power);
  wire([[9, y0 + e + 1.2, 6], [5, y0 + e + 3, 8], [-12, y0 + e + 2, 9], [-16, y0 + e + 1.4, 9]], MT.wireR, 0.45);
  wire([[-16, y0 + e + 2.3, -8], [0, y0 + e + 2, -9], [14, y0 + e + 1.0, -8]], MT.wireR, 0.45);
  wire([[-16, y0 + e + 2.3, -8], [0, y0 + e + 2, 9], [14, y0 + e + 1.0, 8]], MT.wireR, 0.45);
  for (const [sx, sz] of [[1, 1], [-1, 1], [1, -1], [-1, -1]]) wire([[14, y0 + e + 1.0, sz * 8], [sx * 8, y0 + e + 2, sz * 10], [sx * WB / 2, R + 1.5, sz * (W / 2 - 8)]], sz > 0 ? MT.wireK : MT.wireB, 0.25);
  wire([[3, y0 + e + 0.6, -10], [-2, y1 - 3, -8], [-8, y1 + 1, 0]], MT.wireY, 0.25);
  /* LiDAR 시야 쐐기 (뒤집힌 -52..+7°) */
  const fovG = new THREE.Group(); scene.add(fovG); fovG.visible = !!opts.fov;
  { const e0 = SPEC.MECH.lidar_fov_deg[0] * Math.PI / 180, e1 = SPEC.MECH.lidar_fov_deg[1] * Math.PI / 180, r = 180;
    const shape = new THREE.Shape(); shape.moveTo(0, 0); shape.lineTo(r * Math.cos(e0), r * Math.sin(e0)); shape.absarc(0, 0, r, e0, e1, false); shape.lineTo(0, 0);
    for (const s of [0, Math.PI]) { const f = mesh(new THREE.ShapeGeometry(shape, 24), new THREE.MeshBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.18, side: THREE.DoubleSide, depthWrite: false }), fovG, false); f.position.set(lx, lh, 0); f.rotation.y = s; }
    const ring = mesh(new THREE.RingGeometry(M.lidar_blind_r_inverted * CM - 0.6, M.lidar_blind_r_inverted * CM + 0.6, 64), new THREE.MeshBasicMaterial({ color: 0xff9d3c, side: THREE.DoubleSide }), fovG, false);
    ring.rotation.x = -Math.PI / 2; ring.position.set(lx, 0.2, 0); }
  /* CoG */
  const cog = mesh(new THREE.SphereGeometry(1.2, 16, 12), new THREE.MeshBasicMaterial({ color: 0xff00aa }), scene, false); cog.position.set(0, M.cog_h * CM, 0); cog.visible = !!opts.fov;

  /* ---------- callouts ---------- */
  const PARTS = [
    { obj: lid, name: "Livox Mid-360 (뒤집어 장착)", sub: "200k pt/s · -52..+7° · 사각 0.47 m" },
    { obj: mtop, name: "센서 마스트 Ø20 mm", sub: `LiDAR 광학중심 ${lh.toFixed(0)} cm` },
    { obj: gant, name: "GNSS 안테나 (확장)", sub: "ZED-F9P RTK · PPS" },
    { obj: camG, name: "카메라 IMX219", sub: "1280×720@30 · 피치 -10°" },
    { obj: hs, name: "Jetson Orin Nano Super", sub: "LIO · 지도 · J 계산 · 기록" },
    { obj: nuc, name: "NUCLEO-H753ZI", sub: "바퀴 PID · 엔코더 · fw 결정 커널" },
    { obj: imu, name: "IMU ICM-42688-P", sub: "1 kHz SPI · 슬립·기울기" },
    { obj: esm, name: "비상정지 버섯 스위치", sub: "모터 버스 하드웨어 차단" },
    { obj: rxa, name: "433 MHz 무선 킬", sub: "하트비트형 · 끊기면 정지" },
    { obj: bat, name: "4S4P Li-ion 10 Ah", sub: `${SPEC.E_WH.toFixed(0)} Wh 가용 · ${SPEC.RUNTIME_H.toFixed(1)} h` },
    { obj: cont, name: "접촉기 K1 (모터 버스)", sub: "E-stop·MCU·킬 직렬" },
    { obj: fuse, name: "퓨즈 블록 ATO", sub: "30/15/15/5/3/3 A" },
    { obj: drv[0], name: "모터 드라이버 MDD20A ×2", sub: "PWM + DIR · 20 A" },
    { obj: G.motorFL, name: "기어모터 37D 50:1 ×4", sub: "64 CPR → 3200 tick/rev" },
    { obj: wheels[0], name: `바퀴 Ø${20 * R} mm`, sub: `축거 ${WB} · 윤거 ${TR} cm` },
    { obj: ideal, name: "Jetson 직결 급전", sub: "5 A 퓨즈 · 이상다이오드 · 470 µF" },
  ];
  const svgNS = "http://www.w3.org/2000/svg";
  const cl = document.createElement("div"); cl.className = "co-root"; root.appendChild(cl);
  const svg = document.createElementNS(svgNS, "svg"); svg.setAttribute("class", "co-svg"); cl.appendChild(svg);
  PARTS.forEach(p => { p.el = document.createElement("div"); p.el.className = "co-lab"; p.el.innerHTML = `<b>${p.name}</b><span>${p.sub}</span>`; cl.appendChild(p.el);
    p.line = document.createElementNS(svgNS, "path"); p.line.setAttribute("class", "co-line"); svg.appendChild(p.line);
    p.dot = document.createElementNS(svgNS, "circle"); p.dot.setAttribute("r", "3.5"); p.dot.setAttribute("class", "co-dot"); svg.appendChild(p.dot); });
  let showCallouts = true; const tv = new THREE.Vector3();
  function layoutCallouts(W, H) {
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W); svg.setAttribute("height", H);
    const vis = [];
    PARTS.forEach(p => { p.obj.getWorldPosition(tv); tv.project(cam); const ok = showCallouts && tv.z < 1 && Math.abs(tv.x) < 0.98 && Math.abs(tv.y) < 0.98;
      p.sx = (tv.x + 1) / 2 * W; p.sy = (1 - tv.y) / 2 * H; p.el.style.display = ok ? "" : "none"; p.line.style.display = p.dot.style.display = ok ? "" : "none"; if (ok) vis.push(p); });
    const colW = Math.min(230, W * 0.21), top = opts.calloutTop || 60;
    const leftSet = vis.filter(p => p.sx < W * 0.5).sort((a, b) => a.sy - b.sy), rightSet = vis.filter(p => p.sx >= W * 0.5).sort((a, b) => a.sy - b.sy);
    for (const [set, side] of [[leftSet, "L"], [rightSet, "R"]]) {
      let y = top; const n = set.length, avail = H - top - 30; const step = Math.max(40, Math.min(80, avail / Math.max(n, 1)));
      set.forEach((p, i) => { const ty = Math.max(y, Math.min(p.sy - 16, top + avail - (n - i) * step)); y = ty + step;
        const x0 = side === "L" ? 12 : W - colW - 12;
        p.el.style.left = x0 + "px"; p.el.style.top = ty + "px"; p.el.style.width = colW + "px"; p.el.style.textAlign = side === "L" ? "left" : "right";
        const ax = side === "L" ? x0 + colW + 4 : x0 - 4, ay = ty + 14, mx = side === "L" ? ax + 18 : ax - 18;
        p.line.setAttribute("d", `M${ax},${ay} L${mx},${ay} L${p.sx},${p.sy}`); p.dot.setAttribute("cx", p.sx); p.dot.setAttribute("cy", p.sy); });
    }
  }
  const base = {}; Object.entries(G).forEach(([k, g]) => { if (g.position) base[k] = g.position.clone(); });
  function setExplode(u) { const off = { frame: [0, 0, 0], drive: [0, 0, 0], power: [0, 0.5 * u, 62 * u], comp: [0, 16 * u, 0], sens: [0, 30 * u, 0], safe: [0, 16 * u, -40 * u] };
    Object.entries(off).forEach(([k, o]) => { G[k].position.set(base[k].x + o[0], base[k].y + o[1], base[k].z + o[2]); });
    wheels.forEach((w, i) => { w.position.z = (i < 2 ? 1 : -1) * (TR / 2 + 14 * u); }); topDeck.position.y = y1 + 0.15 + 12 * u; }
  function render(W, H) { renderer.render(scene, cam); layoutCallouts(W, H); }
  return { scene, cam, render, setExplode, layoutCallouts, PARTS, setFov: b => { fovG.visible = b; cog.visible = b; }, setCallouts: b => { showCallouts = b; } };
}
if (typeof module !== "undefined") module.exports = { makeRoverScene };
