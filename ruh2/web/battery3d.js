/* battery3d.js — RuH2-P1 cell + RuH2-BMS board, true dimensions from spec.py (1 unit = 1 cm).
   makeBatteryScene(THREE, renderer, SPEC, root, {interactive}) -> {scene, cam, setState(o), setExplode(u), setCutaway(b), render(), callouts}
   Callouts: labels in two side columns with leader lines, sorted by screen y, never on top of the parts. */
function makeBatteryScene(THREE, renderer, SPEC, root, opts = {}) {
  const C = SPEC.CELL, V = SPEC.VESSEL;
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(30, 16 / 9, 0.5, 400);
  if (THREE.RoomEnvironment) {
    const pm = new THREE.PMREMGenerator(renderer);
    scene.environment = pm.fromScene(new THREE.RoomEnvironment(), 0.04).texture;
  }
  scene.background = new THREE.Color(opts.bg || 0x1a1f26);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.localClippingEnabled = true;
  scene.add(new THREE.HemisphereLight(0xdfe9ff, 0x2a2622, 0.35));
  const key = new THREE.DirectionalLight(0xfff4e6, 1.25); key.position.set(18, 30, 22); key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, { left: -30, right: 30, top: 30, bottom: -30, near: 1, far: 90 }); key.shadow.bias = -0.0004;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xbcd3ff, 0.35); fill.position.set(-20, 12, -10); scene.add(fill);

  /* ---------- procedural textures ---------- */
  function tex(w, h, draw, rep) {
    const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d"), w, h);
    const t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding; t.anisotropy = 8;
    if (rep) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep[0], rep[1]); }
    return t;
  }
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const brushed = tex(512, 512, (g, w, h) => { g.fillStyle = "#8c9096"; g.fillRect(0, 0, w, h); for (let i = 0; i < 2600; i++) { const v = 120 + rnd() * 70 | 0; g.strokeStyle = `rgba(${v},${v + 3},${v + 8},.35)`; g.beginPath(); const y = rnd() * h; g.moveTo(0, y); g.lineTo(w, y + (rnd() - 0.5) * 2); g.stroke(); } }, [1, 3]);
  const brushedRough = tex(256, 256, (g, w, h) => { g.fillStyle = "#6a6a6a"; g.fillRect(0, 0, w, h); for (let i = 0; i < 1400; i++) { const v = 60 + rnd() * 120 | 0; g.strokeStyle = `rgb(${v},${v},${v})`; g.beginPath(); const y = rnd() * h; g.moveTo(0, y); g.lineTo(w, y); g.stroke(); } }, [1, 3]);
  const niTex = tex(256, 256, (g, w, h) => { g.fillStyle = "#2f4a36"; g.fillRect(0, 0, w, h); for (let i = 0; i < 9000; i++) { const v = rnd(); g.fillStyle = v > .5 ? "rgba(90,140,100,.5)" : "rgba(20,30,24,.6)"; g.fillRect(rnd() * w, rnd() * h, 2, 2); } });
  const gdeTex = tex(256, 256, (g, w, h) => { g.fillStyle = "#15171b"; g.fillRect(0, 0, w, h); for (let i = 0; i < 7000; i++) { const v = 25 + rnd() * 40 | 0; g.fillStyle = `rgb(${v},${v},${v + 4})`; g.fillRect(rnd() * w, rnd() * h, 1.5, 1.5); } });
  const sepTex = tex(256, 256, (g, w, h) => { g.fillStyle = "#e9e6dc"; g.fillRect(0, 0, w, h); g.strokeStyle = "rgba(160,150,130,.35)"; for (let i = 0; i < 500; i++) { g.beginPath(); g.moveTo(rnd() * w, rnd() * h); g.quadraticCurveTo(rnd() * w, rnd() * h, rnd() * w, rnd() * h); g.stroke(); } });
  const meshTex = tex(128, 128, (g, w, h) => { g.clearRect(0, 0, w, h); g.strokeStyle = "#c7ccd3"; g.lineWidth = 3; for (let i = 0; i <= w; i += 16) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, h); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(w, i); g.stroke(); } }, [6, 6]);
  const matTex = tex(512, 512, (g, w, h) => { g.fillStyle = "#1f3a33"; g.fillRect(0, 0, w, h); g.strokeStyle = "rgba(255,255,255,.06)"; for (let i = 0; i < w; i += 32) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, h); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(w, i); g.stroke(); } }, [4, 3]);

  const std = (c, o = {}) => new THREE.MeshStandardMaterial(Object.assign({ color: c, roughness: 0.5, metalness: 0.0 }, o));
  const MT = {
    steel: std(0xc9ced4, { map: brushed, roughnessMap: brushedRough, metalness: 1.0, roughness: 0.38, side: THREE.DoubleSide }),
    steelIn: std(0x9aa0a8, { metalness: 0.9, roughness: 0.5, side: THREE.BackSide }),
    cutFace: std(0xd8dde2, { metalness: 0.8, roughness: 0.25 }),
    bolt: std(0xb8bec6, { metalness: 1, roughness: 0.3 }),
    brass: std(0xc9a14a, { metalness: 1, roughness: 0.3 }),
    ptfe: std(0xf2f2ee, { roughness: 0.7 }),
    epdm: std(0x1b1b1b, { roughness: 0.9 }),
    ni: std(0x6b8f72, { map: niTex, roughness: 0.8, metalness: 0.2 }),
    gde: std(0x2a2c30, { map: gdeTex, roughness: 0.65, metalness: 0.35 }),
    sep: std(0xefece2, { map: sepTex, roughness: 0.95 }),
    screen: std(0xd0d5dc, { map: meshTex, alphaMap: meshTex, transparent: true, metalness: 0.9, roughness: 0.35, side: THREE.DoubleSide }),
    niTab: std(0xb9bdc2, { metalness: 1, roughness: 0.35 }),
    pcb: std(0x0f4d34, { roughness: 0.55 }),
    ic: std(0x151618, { roughness: 0.45 }),
    wireR: std(0xb3261e, { roughness: 0.45 }), wireK: std(0x18191b, { roughness: 0.45 }), wireB: std(0x1f5fbf, { roughness: 0.45 }),
    bench: std(0x2a2f36, { map: matTex, roughness: 0.92 }),
    alu: std(0x9ea5ae, { metalness: 0.9, roughness: 0.4 }),
  };
  function mesh(g, m, parent = scene, cast = true) { const o = new THREE.Mesh(g, m); o.castShadow = cast; o.receiveShadow = true; parent.add(o); return o; }

  /* ---------- bench ---------- */
  const bench = mesh(new THREE.BoxGeometry(80, 1.2, 50), MT.bench, scene, false); bench.position.set(4, -0.6, 0);

  /* ---------- vessel (axis along x) ---------- */
  const R_o = V.od_mm / 20, R_i = V.id_mm / 20, L = V.inner_len_mm / 10;
  const vessel = new THREE.Group(); scene.add(vessel); vessel.rotation.z = Math.PI / 2; vessel.rotation.x = 0;
  const cutPlanes = [new THREE.Plane(new THREE.Vector3(0, 0, -1), 0), new THREE.Plane(new THREE.Vector3(0, -1, 0), 0)];
  // tube as open cylinder; cutaway = remove the front-top quadrant with theta range
  let tubeO, tubeI, cutA, cutB;
  function buildTube(cut) {
    [tubeO, tubeI, cutA, cutB].forEach(o => o && vessel.remove(o));
    const th0 = cut ? Math.PI * 0.5 : 0, thL = cut ? Math.PI * 1.5 : Math.PI * 2;
    const go = new THREE.CylinderGeometry(R_o, R_o, L, 96, 1, true, th0, thL); go.rotateZ(Math.PI / 2);
    const gi = new THREE.CylinderGeometry(R_i, R_i, L, 96, 1, true, th0, thL); gi.rotateZ(Math.PI / 2);
    tubeO = mesh(go, MT.steel, vessel); tubeI = mesh(gi, MT.steelIn, vessel);
    if (cut) {   // wall cut faces: removed quadrant is theta in [0, pi/2) -> y>=0, z>=0
      cutA = mesh(new THREE.PlaneGeometry(L, R_o - R_i), MT.cutFace, vessel); cutA.rotation.x = -Math.PI / 2; cutA.position.set(0, 0, (R_o + R_i) / 2);
      cutB = mesh(new THREE.PlaneGeometry(L, R_o - R_i), MT.cutFace, vessel); cutB.position.set(0, (R_o + R_i) / 2, 0);
    }
  }
  // flanges + bolts
  const flangeR = R_o + 1.6, flangeT = 1.2;
  const fl = [];
  for (const sx of [-1, 1]) {
    const g = new THREE.Group(); vessel.add(g); g.position.x = sx * (L / 2 + flangeT / 2);
    const disk = mesh(new THREE.CylinderGeometry(flangeR, flangeR, flangeT, 72), MT.steel, g); disk.rotation.z = Math.PI / 2;
    const oring = mesh(new THREE.TorusGeometry(R_i + 0.3, 0.12, 12, 64), MT.epdm, g); oring.rotation.y = Math.PI / 2; oring.position.x = -sx * flangeT / 2;
    for (let k = 0; k < 6; k++) {
      const a = k * Math.PI / 3 + Math.PI / 6, r = R_o + 0.95;
      const bh = mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.42, 6), MT.bolt, g); bh.rotation.z = Math.PI / 2; bh.position.set(sx * (flangeT / 2 + 0.21), r * Math.cos(a), r * Math.sin(a));
      const sh = mesh(new THREE.CylinderGeometry(0.3, 0.3, flangeT + 1.2, 16), MT.bolt, g); sh.rotation.z = Math.PI / 2; sh.position.set(0, r * Math.cos(a), r * Math.sin(a));
    }
    fl.push(g);
  }
  // feedthroughs on +x flange
  const ftPos = [];
  for (const z of [-1.7, 1.7]) {
    const f = mesh(new THREE.CylinderGeometry(0.55, 0.55, 1.4, 6), MT.bolt, fl[1]); f.rotation.z = Math.PI / 2; f.position.set(flangeT / 2 + 0.7, 0, z);
    const p = mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.5, 24), MT.ptfe, fl[1]); p.rotation.z = Math.PI / 2; p.position.set(flangeT / 2 + 1.6, 0, z);
    const rod = mesh(new THREE.CylinderGeometry(0.15, 0.15, 2.4, 16), MT.niTab, fl[1]); rod.rotation.z = Math.PI / 2; rod.position.set(flangeT / 2 + 2.2, 0, z);
    ftPos.push(rod);
  }
  // top port: nipple -> tee -> transducer (up), gauge (+z), relief (-z) ; needle valve on tee x
  const port = new THREE.Group(); vessel.add(port); port.position.set(L / 2 + 1.2, 0, 0); port.rotation.z = -Math.PI / 2;
  const nip = mesh(new THREE.CylinderGeometry(0.55, 0.55, 2.2, 24), MT.bolt, port); nip.position.y = 1.1;
  const tee = mesh(new THREE.BoxGeometry(1.8, 1.8, 1.8), MT.bolt, port); tee.position.y = 3.0;
  const tr = mesh(new THREE.CylinderGeometry(0.9, 0.9, 3.4, 32), std(0x2b2f35, { metalness: 0.6, roughness: 0.35 }), port); tr.position.y = 5.6;
  const trCap = mesh(new THREE.CylinderGeometry(0.6, 0.9, 0.9, 32), std(0x111214, { roughness: 0.6 }), port); trCap.position.y = 7.7;
  const gArm = mesh(new THREE.CylinderGeometry(0.45, 0.45, 1.8, 16), MT.bolt, port); gArm.rotation.x = Math.PI / 2; gArm.position.set(0, 3.0, 1.8);
  const gauge = new THREE.Group(); port.add(gauge); gauge.position.set(0, 3.0, 3.2);
  mesh(new THREE.CylinderGeometry(2.1, 2.1, 1.0, 64), MT.bolt, gauge).rotation.x = Math.PI / 2;
  const dialC = document.createElement("canvas"); dialC.width = dialC.height = 512;
  const dialT = new THREE.CanvasTexture(dialC); dialT.encoding = THREE.sRGBEncoding; dialT.anisotropy = 8;
  const dial = mesh(new THREE.CircleGeometry(1.9, 64), new THREE.MeshStandardMaterial({ map: dialT, roughness: 0.25, metalness: 0 }), gauge, false); dial.position.z = 0.51;
  const glass = mesh(new THREE.CircleGeometry(1.95, 64), new THREE.MeshPhysicalMaterial({ transparent: true, opacity: 0.12, roughness: 0.02, clearcoat: 1, color: 0xffffff }), gauge, false); glass.position.z = 0.56;
  function drawDial(p) {
    const g = dialC.getContext("2d"); g.fillStyle = "#f4f2ea"; g.fillRect(0, 0, 512, 512);
    g.translate(256, 256); const a0 = -Math.PI * 1.25, span = Math.PI * 1.5, pmax = 10;
    g.lineWidth = 26; g.strokeStyle = "#2f9a57"; g.beginPath(); g.arc(0, 0, 200, a0, a0 + span * 5 / pmax); g.stroke();
    g.strokeStyle = "#e0a526"; g.beginPath(); g.arc(0, 0, 200, a0 + span * 5 / pmax, a0 + span * 6 / pmax); g.stroke();
    g.strokeStyle = "#c73535"; g.beginPath(); g.arc(0, 0, 200, a0 + span * 6 / pmax, a0 + span); g.stroke();
    g.fillStyle = "#111"; g.font = "bold 44px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
    for (let k = 0; k <= 10; k += 2) { const a = a0 + span * k / pmax; g.fillText(String(k), 150 * Math.cos(a), 150 * Math.sin(a)); }
    g.lineWidth = 4; g.strokeStyle = "#111"; for (let k = 0; k <= 20; k++) { const a = a0 + span * k / 20; g.beginPath(); g.moveTo(185 * Math.cos(a), 185 * Math.sin(a)); g.lineTo(215 * Math.cos(a), 215 * Math.sin(a)); g.stroke(); }
    g.font = "bold 34px sans-serif"; g.fillText("bar abs · H₂", 0, 95); g.font = "bold 50px monospace"; g.fillText(p.toFixed(2), 0, 160);
    const a = a0 + span * Math.min(p, pmax) / pmax; g.strokeStyle = "#b3261e"; g.lineWidth = 10; g.beginPath(); g.moveTo(-20 * Math.cos(a), -20 * Math.sin(a)); g.lineTo(175 * Math.cos(a), 175 * Math.sin(a)); g.stroke();
    g.fillStyle = "#222"; g.beginPath(); g.arc(0, 0, 18, 0, 7); g.fill(); g.setTransform(1, 0, 0, 1, 0, 0); dialT.needsUpdate = true;
  }
  const rArm = mesh(new THREE.CylinderGeometry(0.45, 0.45, 1.6, 16), MT.bolt, port); rArm.rotation.x = Math.PI / 2; rArm.position.set(0, 3.0, -1.7);
  const relief = mesh(new THREE.CylinderGeometry(0.75, 0.6, 2.6, 24), MT.brass, port); relief.rotation.x = Math.PI / 2; relief.position.set(0, 3.0, -3.6);
  const reliefCap = mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.6, 6), MT.brass, port); reliefCap.rotation.x = Math.PI / 2; reliefCap.position.set(0, 3.0, -5.1);
  const nArm = mesh(new THREE.CylinderGeometry(0.45, 0.45, 1.6, 16), MT.bolt, port); nArm.rotation.z = Math.PI / 2; nArm.position.set(-1.7, 3.0, 0);
  const needle = mesh(new THREE.CylinderGeometry(0.7, 0.7, 1.8, 24), MT.brass, port); needle.rotation.z = Math.PI / 2; needle.position.set(-3.2, 3.0, 0);
  const knob = mesh(new THREE.CylinderGeometry(0.9, 0.9, 0.5, 24), std(0x2a2a2a, { roughness: 0.6 }), port); knob.position.set(-3.2, 4.3, 0);
  // NTC on wall
  const ntc = mesh(new THREE.BoxGeometry(1.2, 0.3, 0.8), std(0x2255aa, { roughness: 0.6 }), vessel); ntc.position.set(-L / 4, -0.2, R_o + 0.1);

  /* ---------- electrode stack ---------- */
  const stack = new THREE.Group(); vessel.add(stack); stack.position.x = -L / 2 + 3.2;
  const rD = C.disc_od_mm / 20, rH = C.disc_id_mm / 20, mm = 0.1;
  const layerDefs = [["screen", C.screen_thk_mm, MT.screen, "가스 스크린"], ["gde", C.gde_thk_mm, MT.gde, "Ru/C 수소 전극"], ["sep", C.sep_thk_mm, MT.sep, "분리막"],
                     ["ni", C.ni_thk_mm, MT.ni, "Ni(OH)₂ 전극"], ["sep", C.sep_thk_mm, MT.sep, "분리막"], ["gde", C.gde_thk_mm, MT.gde, "Ru/C 수소 전극"]];
  const layers = [];
  let x = -V.stack_h_mm * mm / 2;
  for (let u = 0; u < C.n_units; u++) for (const [k, t, m, nm] of layerDefs) {
    const th = Math.max(t * mm, 0.02);
    const g = new THREE.CylinderGeometry(rD, rD, th, 72); g.rotateZ(Math.PI / 2);
    const o = mesh(g, m, stack); o.position.x = x + th / 2; o.userData = { x0: x + th / 2, u, k, nm }; layers.push(o); x += th;
  }
  const endL = mesh(new THREE.CylinderGeometry(rD + 0.1, rD + 0.1, 0.5, 72), MT.ptfe, stack); endL.rotation.z = Math.PI / 2; endL.position.x = -V.stack_h_mm * mm / 2 - 0.25;
  const endR = mesh(new THREE.CylinderGeometry(rD + 0.1, rD + 0.1, 0.5, 72), MT.ptfe, stack); endR.rotation.z = Math.PI / 2; endR.position.x = V.stack_h_mm * mm / 2 + 0.25;
  const rod = mesh(new THREE.CylinderGeometry(rH * 0.8, rH * 0.8, 3.0, 24), MT.ptfe, stack); rod.rotation.z = Math.PI / 2; rod.position.x = -1.2;
  const tabs = [];
  for (const [zz, m] of [[1, MT.niTab], [-1, MT.niTab]]) { const tb = mesh(new THREE.BoxGeometry(L - 3.0, 0.05, 0.4), m, stack); tb.position.set((L - 3.0) / 2 + 0.3, 0, zz * 1.7); tabs.push(tb); }
  // H2 molecules in free volume
  const NMAX = 900, h2Geo = new THREE.SphereGeometry(0.07, 8, 6);
  const h2Mesh = new THREE.InstancedMesh(h2Geo, new THREE.MeshBasicMaterial({ color: 0x7fc4ff }), NMAX); vessel.add(h2Mesh);
  const h2P = [], dummy = new THREE.Object3D();
  for (let i = 0; i < NMAX; i++) {
    let px, pr, pa;
    do { px = (rnd() - 0.5) * (L - 0.4); } while (Math.abs(px - (-L / 2 + 3.2)) < V.stack_h_mm * mm / 2 + 0.7);
    pr = Math.sqrt(rnd()) * (R_i - 0.2); pa = rnd() * Math.PI * 2;
    h2P.push([px, pr, pa, rnd() * 10]);
  }

  /* ---------- BMS board ---------- */
  const bms = new THREE.Group(); scene.add(bms); bms.position.set(20, 0.1, 2); bms.rotation.y = -0.18;
  const pcbC = document.createElement("canvas"); pcbC.width = 1000; pcbC.height = 800;
  const pcbT = new THREE.CanvasTexture(pcbC); pcbT.encoding = THREE.sRGBEncoding; pcbT.anisotropy = 8;
  (function () { const g = pcbC.getContext("2d"); g.fillStyle = "#0f4d34"; g.fillRect(0, 0, 1000, 800);
    g.strokeStyle = "#1f7a52"; g.lineWidth = 6; for (let i = 0; i < 60; i++) { g.beginPath(); let a = rnd() * 1000, b = rnd() * 800; g.moveTo(a, b); a += (rnd() - .5) * 300; g.lineTo(a, b); b += (rnd() - .5) * 200; g.lineTo(a, b); g.stroke(); }
    g.setLineDash([14, 10]); g.strokeStyle = "rgba(255,255,255,.55)"; g.lineWidth = 3; g.strokeRect(20, 20, 300, 280); g.strokeRect(20, 320, 420, 460); g.strokeRect(460, 20, 360, 460); g.strokeRect(460, 500, 360, 280); g.strokeRect(840, 20, 140, 760);
    g.setLineDash([]); g.fillStyle = "#e8efe9"; g.font = "bold 30px sans-serif";
    g.fillText("POWER 12V", 40, 60); g.fillText("LINEAR STAGE", 40, 360); g.fillText("ANALOG AFE", 480, 60); g.fillText("MCU", 480, 540); g.fillText("ISO", 860, 60);
    g.font = "bold 34px sans-serif"; g.fillText("RuH2-BMS rev A", 480, 760); pcbT.needsUpdate = true; })();
  const pw = 10, pd = 8;
  const board = mesh(new THREE.BoxGeometry(pw, 0.16, pd), [MT.pcb, MT.pcb, std(0xffffff, { map: pcbT, roughness: 0.55 }), MT.pcb, MT.pcb, MT.pcb], bms); board.position.y = 0.9;
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) { const s = mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.8, 12), MT.brass, bms); s.position.set(sx * (pw / 2 - 0.4), 0.4, sz * (pd / 2 - 0.4)); }
  const bx = (w, h, d, m, x_, z_) => { const o = mesh(new THREE.BoxGeometry(w, h, d), m, bms); o.position.set(x_ - pw / 2, 0.98 + h / 2, z_ - pd / 2); return o; };
  const mcu = bx(1.2, 0.16, 1.2, MT.ic, 6.4, 6.0);
  const afe1 = bx(0.5, 0.12, 0.4, MT.ic, 5.6, 1.6), afe2 = bx(0.5, 0.12, 0.4, MT.ic, 6.6, 1.6), afe3 = bx(0.5, 0.12, 0.4, MT.ic, 7.6, 1.6);
  const shunt = bx(0.64, 0.12, 0.32, std(0x333333, { metalness: 0.4 }), 3.0, 4.2);
  const heat = new THREE.Group(); bms.add(heat); heat.position.set(1.8 - pw / 2, 1.0, 5.4 - pd / 2);
  for (let k = 0; k < 9; k++) mesh(new THREE.BoxGeometry(0.08, 1.4, 2.0), MT.alu, heat).position.set(-0.7 + k * 0.18, 0.7, 0);
  mesh(new THREE.BoxGeometry(1.7, 0.2, 2.0), MT.alu, heat).position.y = 0.1;
  const iso = bx(0.8, 0.14, 0.6, MT.ic, 9.0, 3.0);
  const usb = bx(0.9, 0.35, 0.8, MT.bolt, 9.6, 5.4);
  const buck = bx(0.5, 0.12, 0.5, MT.ic, 1.4, 1.2);
  const ind = bx(0.6, 0.35, 0.6, std(0x3a3a3a), 2.4, 1.2);
  const term = bx(1.4, 0.8, 0.9, std(0x2e7d32), 0.9, 4.0);
  const jcon = bx(0.8, 0.5, 2.2, std(0xeeeeee, { roughness: 0.6 }), 4.8, 7.2);
  const leds = [0, 1, 2].map(k => { const l = bx(0.18, 0.1, 0.12, new THREE.MeshStandardMaterial({ color: 0x111111, emissive: [0x22ff66, 0xffaa00, 0xff2222][k], emissiveIntensity: 0 }), 8.0 + k * 0.4, 7.4); return l; });
  for (let k = 0; k < 18; k++) bx(0.12, 0.06, 0.06, std(k % 3 ? 0xb07b40 : 0x303030), 4.6 + (k % 6) * 0.35, 3.0 + Math.floor(k / 6) * 0.3);

  /* ---------- cables ---------- */
  function cable(pts, m, r = 0.16) { const c = new THREE.CatmullRomCurve3(pts.map(p => new THREE.Vector3(...p))); return mesh(new THREE.TubeGeometry(c, 120, r, 12), m); }
  vessel.position.set(0, L / 2 + flangeT, 0);
  scene.updateMatrixWorld(true);
  const wp = (o, d = [0, 0, 0]) => { const v = new THREE.Vector3(...d); o.localToWorld(v); return [v.x, v.y, v.z]; };
  const fA = wp(ftPos[0], [0, 1.2, 0]), fB = wp(ftPos[1], [0, 1.2, 0]), trT = wp(trCap, [0, 0.45, 0]), ntcW = wp(ntc);
  const bx0 = 20 - 5, bz0 = 2;
  cable([fA, [fA[0], fA[1] + 3, fA[2]], [8, fA[1] + 1, fA[2] + 2], [bx0 + 0.4, 3, bz0 + 2.4], [bx0 + 0.9, 1.3, bz0 + 1.0]], MT.wireR);
  cable([fB, [fB[0], fB[1] + 3.5, fB[2]], [9, fB[1] + 0.5, fB[2] + 1], [bx0 + 0.4, 3, bz0 + 1.6], [bx0 + 0.9, 1.3, bz0 + 0.1]], MT.wireK);
  cable([trT, [trT[0], trT[1] + 2.5, trT[2]], [10, trT[1] - 2, -2], [bx0 + 5, 3, bz0 + 3.6], [bx0 + 5.0, 1.35, bz0 + 3.2]], MT.wireB, 0.1);
  cable([ntcW, [ntcW[0], ntcW[1], ntcW[2] + 3], [8, 0.6, 8], [bx0 + 4.4, 0.6, bz0 + 4.2], [bx0 + 4.4, 1.2, bz0 + 3.4]], std(0xeeeeee), 0.07);

  /* ---------- laptop with dashboard ---------- */
  const lap = new THREE.Group(); scene.add(lap); lap.position.set(40, 0, -18); lap.rotation.y = -0.6;
  mesh(new THREE.BoxGeometry(32, 1.2, 22), MT.alu, lap).position.y = 0.6;
  const lid = new THREE.Group(); lap.add(lid); lid.position.set(0, 1.2, -11); lid.rotation.x = -0.25;
  mesh(new THREE.BoxGeometry(32, 21, 0.7), MT.alu, lid).position.set(0, 10.5, -0.35);
  const scrC = document.createElement("canvas"); scrC.width = 1280; scrC.height = 800;
  const scrT = new THREE.CanvasTexture(scrC); scrT.encoding = THREE.sRGBEncoding;
  const scr = mesh(new THREE.PlaneGeometry(30, 18.75), new THREE.MeshBasicMaterial({ map: scrT }), lid, false); scr.position.set(0, 10.6, 0.02);
  cable([[20 + 4.8, 1.2, 3.5 - 0.6], [28, 0.5, 0], [33, 0.6, -8], [36, 1.2, -12]], std(0x303030), 0.12);

  /* ---------- callouts ---------- */
  const tubeAnchor = new THREE.Object3D(); vessel.add(tubeAnchor); tubeAnchor.position.set(-L / 3, -R_o * 0.5, R_o * 0.87);
  const PARTS = [
    { obj: tr, name: "압력 트랜스듀서", sub: "0–10 bar abs · SOC 게이지" },
    { obj: gauge, name: "기계식 압력계", sub: "이중 확인용" },
    { obj: relief, name: "릴리프 밸브", sub: `${V.p_relief_bar} bar 설정` },
    { obj: needle, name: "니들 밸브", sub: "H₂ 예충전 · 퍼지" },
    { obj: fl[1], name: "볼트 플랜지 (윗덮개)", sub: "6×M6 A4-70 · EPDM O-ring" },
    { obj: tubeAnchor, name: "316L 압력용기", sub: `Ø${V.od_mm}×${V.wall_mm} · 설계 ${V.p_design_bar} bar` },
    { obj: stack, name: "전극 스택 (4 unit)", sub: `Ø${C.disc_od_mm} mm · ${V.stack_h_mm.toFixed(1)} mm`, off: [0, -0.8, 0] },
    { obj: ntc, name: "NTC (용기 벽)", sub: "10k B3950" },
    { obj: ftPos[0], name: "전극 피드스루 ×2", sub: "PTFE 실링 Ni 로드 Ø3" },
    { obj: heat, name: "선형 전력단 + 방열판", sub: "CC 충·방전 ±2 A" },
    { obj: shunt, name: "10 mΩ 션트 + INA240A2", sub: "1.6 mA/LSB" },
    { obj: mcu, name: "STM32G474RE", sub: "ADC · DAC · 비교기" },
    { obj: iso, name: "USB 절연 ADuM3160", sub: "PC 링크" },
    { obj: leds[0], name: "하드웨어 인터록 LED", sub: "래치 · 수동 리셋" },
    { obj: scr, name: "모니터링 PC", sub: "V·I·p·SOC·T·EIS" },
  ];
  const svgNS = "http://www.w3.org/2000/svg";
  const cl = document.createElement("div"); cl.className = "co-root"; root.appendChild(cl);
  const svg = document.createElementNS(svgNS, "svg"); svg.setAttribute("class", "co-svg"); cl.appendChild(svg);
  PARTS.forEach(p => {
    p.el = document.createElement("div"); p.el.className = "co-lab"; p.el.innerHTML = `<b>${p.name}</b><span>${p.sub}</span>`; cl.appendChild(p.el);
    p.line = document.createElementNS(svgNS, "path"); p.line.setAttribute("class", "co-line"); svg.appendChild(p.line);
    p.dot = document.createElementNS(svgNS, "circle"); p.dot.setAttribute("r", "3.5"); p.dot.setAttribute("class", "co-dot"); svg.appendChild(p.dot);
    if (opts.onPick) { p.el.style.pointerEvents = "auto"; p.el.style.cursor = "pointer"; p.el.addEventListener("click", () => opts.onPick(p)); }
  });
  let showCallouts = true, calloutFilter = null;
  const tv = new THREE.Vector3();
  function layoutCallouts(W, H) {
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W); svg.setAttribute("height", H);
    const vis = [];
    PARTS.forEach(p => {
      p.obj.getWorldPosition(tv); if (p.off) { tv.x += p.off[0]; tv.y += p.off[1]; tv.z += p.off[2]; }
      tv.project(cam);
      const ok = showCallouts && (!calloutFilter || calloutFilter(p)) && tv.z < 1 && Math.abs(tv.x) < 0.98 && Math.abs(tv.y) < 0.98;
      p.sx = (tv.x + 1) / 2 * W; p.sy = (1 - tv.y) / 2 * H;
      p.el.style.display = ok ? "" : "none"; p.line.style.display = p.dot.style.display = ok ? "" : "none";
      if (ok) vis.push(p);
    });
    const colW = Math.min(230, W * 0.2), top = opts.calloutTop || 70, gap = 44;
    const leftSet = vis.filter(p => p.sx < W * 0.5).sort((a, b) => a.sy - b.sy);
    const rightSet = vis.filter(p => p.sx >= W * 0.5).sort((a, b) => a.sy - b.sy);
    for (const [set, side] of [[leftSet, "L"], [rightSet, "R"]]) {
      let y = top;
      const n = set.length, avail = H - top - (opts.calloutBottom || 40);
      const step = Math.max(gap, Math.min(80, avail / Math.max(n, 1)));
      set.forEach((p, i) => {
        const ty = Math.max(y, Math.min(p.sy - 16, top + avail - (n - i) * step)); y = ty + step;
        const x0 = side === "L" ? 14 + (opts.leftInset || 0) : W - colW - 14 - (opts.rightInset || 0);
        if (side === "R" && opts.rightInset) p.el.style.maxWidth = colW + "px";
        p.el.style.left = x0 + "px"; p.el.style.top = ty + "px"; p.el.style.width = colW + "px"; p.el.style.textAlign = side === "L" ? "left" : "right";
        const ax = side === "L" ? x0 + colW + 4 : x0 - 4, ay = ty + 14;
        const mx = side === "L" ? ax + 18 : ax - 18;
        p.line.setAttribute("d", `M${ax},${ay} L${mx},${ay} L${p.sx},${p.sy}`);
        p.dot.setAttribute("cx", p.sx); p.dot.setAttribute("cy", p.sy);
      });
    }
  }

  /* ---------- state -> visuals ---------- */
  let cut = true; buildTube(true);
  let state = { p: V.p_precharge_bar_abs, V: 1.3, I: 0, s: 0, T: 25, mode: "rest", A_ru: 1 };
  let clock = 0;
  function setState(o) { Object.assign(state, o); }
  function setExplode(u) {
    layers.forEach(o => { o.position.x = o.userData.x0 * (1 + 4.5 * u) + (o.userData.u - 1.5) * 0.9 * u; });
    endL.position.x = (-V.stack_h_mm * mm / 2 - 0.25) * (1 + 4.5 * u) - 1.4 * u; endR.position.x = (V.stack_h_mm * mm / 2 + 0.25) * (1 + 4.5 * u) + 1.4 * u;
  }
  function setCutaway(b) { if (b !== cut) { cut = b; buildTube(b); } }
  function drawScreen(extra) {
    const g = scrC.getContext("2d"), W = 1280, H = 800; g.fillStyle = "#0f141b"; g.fillRect(0, 0, W, H);
    g.fillStyle = "#e8eef5"; g.font = "bold 44px sans-serif"; g.fillText("RuH2-P1  ·  BMS", 40, 70);
    const md = { charge: ["충전 CC", "#3987e5"], discharge: ["방전 CC", "#eb6834"], rest: ["휴지", "#8fa0b3"], trip: ["차단(래치)", "#e66767"] }[state.mode] || ["-", "#888"];
    g.fillStyle = md[1]; g.fillText(md[0], 900, 70);
    const rows = [["Voltage", state.V.toFixed(3) + " V"], ["Current", (state.I >= 0 ? "+" : "") + state.I.toFixed(2) + " A"], ["H₂ pressure", state.p.toFixed(2) + " bar"], ["SOC (압력)", (Math.max(0, state.soc_p ?? state.s) * 100).toFixed(1) + " %"], ["Temperature", state.T.toFixed(1) + " °C"], ["Ru activity", (state.A_ru * 100).toFixed(0) + " %"]];
    g.font = "36px sans-serif";
    rows.forEach(([a, b], i) => { g.fillStyle = "#8fa0b3"; g.fillText(a, 40, 150 + i * 62); g.fillStyle = "#e8eef5"; g.fillText(b, 330, 150 + i * 62); });
    g.fillStyle = "#1c2632"; g.fillRect(40, 540, 520, 30); g.fillStyle = "#3fb877"; g.fillRect(40, 540, 520 * Math.min(1, Math.max(0, state.soc_p ?? state.s)), 30);
    if (extra) extra(g, W, H);
    scrT.needsUpdate = true;
  }
  function animate(dt) {
    clock += dt;
    // H2 molecules: count ~ moles of H2
    const nVis = Math.min(NMAX, Math.round(60 + (state.p - 0.0) * 170));
    for (let i = 0; i < NMAX; i++) {
      const [px, pr, pa, ph] = h2P[i];
      const on = i < nVis;
      const a = pa + clock * (0.3 + (i % 7) * 0.05), jx = Math.sin(clock * 1.7 + ph) * 0.3;
      dummy.position.set(px + jx, pr * Math.cos(a), pr * Math.sin(a));
      dummy.scale.setScalar(on ? 1 : 0.0001); dummy.updateMatrix(); h2Mesh.setMatrixAt(i, dummy.matrix);
    }
    h2Mesh.instanceMatrix.needsUpdate = true;
    leds[0].material.emissiveIntensity = state.mode === "trip" ? 0 : 1.4;
    leds[1].material.emissiveIntensity = state.mode === "charge" || state.mode === "discharge" ? (Math.sin(clock * 6) > 0 ? 1.4 : 0.2) : 0;
    leds[2].material.emissiveIntensity = state.mode === "trip" ? 1.6 : 0;
    MT.gde.color.setRGB(0.16 + 0.25 * (1 - state.A_ru), 0.17 + 0.1 * (1 - state.A_ru), 0.19);
    drawDial(state.p);
  }
  function render(W, H) { renderer.render(scene, cam); layoutCallouts(W, H); }
  drawDial(1.0); drawScreen();
  return { scene, cam, setState, setExplode, setCutaway, animate, render, drawScreen, layoutCallouts, PARTS,
           setCallouts: (b, f) => { showCallouts = b; calloutFilter = f || null; }, setInset: (px, lpx = 0) => { opts.rightInset = px; opts.leftInset = lpx; }, vessel, stack, bms, lap, R_o, L };
}
if (typeof module !== "undefined") module.exports = { makeBatteryScene };
