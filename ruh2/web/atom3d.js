/* atom3d.js — deterministic atomic-scale animation of the RuH2-P1 electrode reactions.
   Ru(0001)+H geometry: GPAW PBE relaxed (this work). Water/OH/Ni layers: schematic positions.
   API: const A = makeAtomScene(THREE, renderer, geom, overlayRoot); A.render(t); A.duration  */
function makeAtomScene(THREE, renderer, GEOM, root) {
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(34, 16 / 9, 0.1, 300);
  let envTex = null;
  if (THREE.RoomEnvironment) {
    const pm = new THREE.PMREMGenerator(renderer);
    envTex = pm.fromScene(new THREE.RoomEnvironment(), 0.04).texture;
    scene.environment = envTex;
  }
  scene.background = new THREE.Color(0x0e141c);
  scene.fog = new THREE.Fog(0x0e141c, 38, 70);
  scene.add(new THREE.HemisphereLight(0xcfe3ff, 0x1a1410, 0.55));
  const key = new THREE.DirectionalLight(0xffffff, 1.1); key.position.set(8, 16, 10); scene.add(key);
  const rim = new THREE.DirectionalLight(0x7fb4ff, 0.6); rim.position.set(-10, 6, -12); scene.add(rim);

  const SG = new THREE.SphereGeometry(1, 40, 28);
  const mat = (c, o = {}) => new THREE.MeshStandardMaterial(Object.assign({ color: c, roughness: 0.35, metalness: 0.0, envMapIntensity: 0.45 }, o));
  const M = {
    Ru: mat(0x7d8898, { metalness: 0.8, roughness: 0.34 }),
    RuSub: mat(0x55606e, { metalness: 0.7, roughness: 0.4 }),
    RuOx: mat(0x4a2a1e, { metalness: 0.2, roughness: 0.7 }),
    H: mat(0xe9eef5, { roughness: 0.25 }),
    Hads: mat(0x3d9bff, { emissive: 0x1a5cff, emissiveIntensity: 0.9, roughness: 0.2 }),
    O: mat(0xd11f1f, { roughness: 0.3 }),
    Ni2: mat(0x2f9a57, { metalness: 0.2, roughness: 0.4 }),
    Ni3: mat(0x1d1f24, { metalness: 0.5, roughness: 0.35 }),
    ONi: mat(0xc0282a, { roughness: 0.35 }),
  };
  const ball = (m, r, parent) => { const s = new THREE.Mesh(SG, m); s.scale.setScalar(r); (parent || scene).add(s); return s; };
  const bondG = new THREE.CylinderGeometry(1, 1, 1, 16);
  const bondM = mat(0xd9dde3, { roughness: 0.4 });
  function bond(parent) { const b = new THREE.Mesh(bondG, bondM); (parent || scene).add(b); return b; }
  const up = new THREE.Vector3(0, 1, 0), tmp = new THREE.Vector3();
  function setBond(b, p, q, r = 0.12) {
    tmp.subVectors(q, p); const L = tmp.length();
    b.visible = L > 0.05 && L < 1.35;
    b.position.copy(p).addScaledVector(tmp, 0.5); b.scale.set(r, L, r);
    b.quaternion.setFromUnitVectors(up, tmp.normalize());
  }
  // glow sprite for electrons
  const gc = document.createElement("canvas"); gc.width = gc.height = 128;
  const g = gc.getContext("2d"); const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, "rgba(255,245,170,1)"); gr.addColorStop(0.25, "rgba(255,210,80,.9)"); gr.addColorStop(1, "rgba(255,180,40,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  const glowTex = new THREE.CanvasTexture(gc);
  function electron() { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, depthWrite: false, transparent: true, blending: THREE.AdditiveBlending })); s.scale.setScalar(1.8); scene.add(s); return s; }

  /* ---------------- Ru slab from DFT ---------------- */
  const ru = new THREE.Group(); scene.add(ru);
  const atoms = GEOM.atoms, cell = GEOM.cell;
  const zTop = Math.max(...atoms.filter(a => a[0] === "Ru").map(a => a[3]));
  const HD = atoms.find(a => a[0] === "H");
  const toW = (x, y, z) => new THREE.Vector3(x, z - zTop, -y);
  const NX = 4, NY = 4, cx = (NX * cell[0][0] + NY * cell[1][0]) / 2, cy = (NY * cell[1][1]) / 2;
  const topAtoms = [];
  for (let i = 0; i < NX; i++) for (let j = 0; j < NY; j++) for (const a of atoms) {
    if (a[0] !== "Ru") continue;
    const x = a[1] + i * cell[0][0] + j * cell[1][0] - cx, y = a[2] + i * cell[0][1] + j * cell[1][1] - cy;
    const top = a[3] > zTop - 0.5;
    const s = ball(top ? M.Ru : M.RuSub, 0.98, ru); s.position.copy(toW(x, y, a[3]));
    if (top) topAtoms.push(s);
  }
  // fcc hollow sites near the centre (DFT H position + surface lattice vectors)
  const b1 = [2.706, 0], b2 = [1.353, 2.3435];
  const baseX = HD[1] + 2 * cell[0][0] + 2 * cell[1][0] - cx - 2 * b1[0] - 2 * b2[0];
  const baseY = HD[2] + 2 * cell[1][1] - cy - 2 * b2[1];
  const hH = HD[3] - zTop;                       // 1.07 A above top layer (DFT)
  const site = (i, j) => new THREE.Vector3(baseX + i * b1[0] + j * b2[0], hH, -(baseY + i * b1[1] + j * b2[1]));
  const S1 = site(1, 1), S2 = site(2, 1), S3 = site(1, 2), S4 = site(2, 2);

  /* ---------------- movable species ---------------- */
  function water() {
    const grp = { O: ball(M.O, 0.55), H1: ball(M.H, 0.33), H2: ball(M.H, 0.33), b1: bond(), b2: bond() };
    return grp;
  }
  const W1 = water(), W2 = water(), W3 = water(), W4 = water();
  const Hs = [ball(M.Hads, 0.46), ball(M.Hads, 0.46)];
  const e1 = electron(), e2 = electron();
  const OHads = [];                              // oxidation segment
  for (let k = 0; k < 6; k++) OHads.push({ O: ball(M.O, 0.6), H: ball(M.H, 0.33), b: bond() });
  const H2m = { a: ball(M.H, 0.38), b: ball(M.H, 0.38), bb: bond() };

  /* ---------------- Ni(OH)2 / NiOOH layered block (schematic) ---------------- */
  const ni = new THREE.Group(); scene.add(ni); ni.position.set(0, 0, 0);
  const niAtoms = [], protons = [], oNi = [];
  const aNi = 3.13, cNi = 4.7, NL = 3, NNI = 5;
  for (let L = 0; L < NL; L++) for (let i = 0; i < NNI; i++) for (let j = 0; j < NNI; j++) {
    const x = (i + 0.5 * j - (NNI - 1) * 0.75) * aNi, z = (j - (NNI - 1) / 2) * aNi * 0.866, y = L * cNi;
    const n = ball(M.Ni2, 0.55, ni); n.position.set(x, y, z); niAtoms.push(n);
    for (const s of [-1, 1]) {
      const o = ball(M.ONi, 0.38, ni); o.position.set(x + aNi * 0.5, y + s * 1.05, z + aNi * 0.29 * s); oNi.push(o);
      if (s === 1 && L < NL) { const h = ball(M.H, 0.24, ni); h.position.set(x + aNi * 0.5, y + 1.05 + 0.97, z + aNi * 0.29); h.userData.home = h.position.clone(); protons.push(h); }
    }
  }
  for (let L = 0; L < NL; L++) {
    const sh = new THREE.Mesh(new THREE.BoxGeometry(NNI * aNi * 1.25, 0.05, NNI * aNi * 0.95), new THREE.MeshBasicMaterial({ color: 0x5fd08a, transparent: true, opacity: 0.08, depthWrite: false }));
    sh.position.set(0, L * cNi, 0); ni.add(sh);
  }
  const niW = [water(), water(), water()];
  [...Object.values(niW[0]), ...Object.values(niW[1]), ...Object.values(niW[2])].forEach(o => ni.add(o));

  /* ---------------- helpers ---------------- */
  const clamp = x => Math.max(0, Math.min(1, x));
  const sm = x => { x = clamp(x); return x * x * (3 - 2 * x); };
  const seg = (t, a, b) => sm((t - a) / (b - a));
  const lerp = (a, b, u) => a.clone().lerp(b, u);
  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  function placeWater(w, O, dirH1, dirH2, vis = true) {
    w.O.position.copy(O); w.H1.position.copy(O).add(dirH1); w.H2.position.copy(O).add(dirH2);
    [w.O, w.H1, w.H2, w.b1, w.b2].forEach(m => m.visible = vis);
    if (vis) { setBond(w.b1, w.O.position, w.H1.position); setBond(w.b2, w.O.position, w.H2.position); }
  }
  const hideW = w => [w.O, w.H1, w.H2, w.b1, w.b2].forEach(m => m.visible = false);
  const dA = V(0.25, -0.92, 0.2).setLength(0.97), dB = V(0.78, 0.55, -0.2).setLength(0.97);

  /* ---------------- overlay DOM ---------------- */
  root.innerHTML = `
  <div class="ov-title"><div class="ov-k"></div><div class="ov-t"></div></div>
  <div class="ov-eq"></div>
  <div class="ov-cap"></div>
  <svg class="ov-dg" viewBox="0 0 300 170"></svg>
  <div class="ov-src">Ru(0001)+H*: GPAW PBE 이완 구조 (본 작업) · H₂O/OH⁻/Ni 층: 모식적 배치</div>`;
  const q = s => root.querySelector(s);
  const DG = q(".ov-dg");
  function drawDG(active, dGru, dGpt, warn) {
    // free-energy diagram H+ + e- -> H* -> 1/2 H2 at U=0 V vs RHE
    const y = v => 85 - v * 110, lvl = (x, v, c, w = 3) => `<line x1="${x}" x2="${x + 50}" y1="${y(v)}" y2="${y(v)}" stroke="${c}" stroke-width="${w}"/>`;
    const lab = (x, v, s, c) => `<text x="${x + 25}" y="${y(v) - 7}" fill="${c}" font-size="13" text-anchor="middle">${s}</text>`;
    DG.innerHTML = `<rect x="0" y="0" width="300" height="170" rx="8" fill="rgba(12,18,26,.82)" stroke="#2c3a4c"/>
      <text x="12" y="18" fill="#9fb3c8" font-size="13">ΔG (eV) · U = 0 V vs RHE</text>
      <line x1="30" x2="290" y1="${y(0)}" y2="${y(0)}" stroke="#2c3a4c" stroke-dasharray="3 3"/>
      ${lvl(30, 0, active === 0 ? "#ffd166" : "#7c8da0")}${lab(30, 0, "H2O + e−", "#c9d6e3")}
      ${lvl(125, dGru, active === 1 ? "#ffd166" : "#6fa8ff", 4)}${lab(125, dGru, "H* (Ru) " + dGru.toFixed(2), "#9cc3ff")}
      ${lvl(125, dGpt, "#b58cff", 2)}<text x="185" y="${y(dGpt) + 4}" fill="#b58cff" font-size="11">Pt ${dGpt.toFixed(2)}</text>
      ${lvl(230, 0, active === 2 ? "#ffd166" : "#7c8da0")}${lab(230, 0, "½ H2", "#c9d6e3")}
      <line x1="80" x2="125" y1="${y(0)}" y2="${y(dGru)}" stroke="#7c8da0" stroke-dasharray="2 3"/>
      <line x1="175" x2="230" y1="${y(dGru)}" y2="${y(0)}" stroke="#7c8da0" stroke-dasharray="2 3"/>
      <text x="12" y="160" fill="${warn ? "#ff8a7a" : "#8193a6"}" font-size="11">${warn ? "E > 0.4 V: OH*·RuOx가 H* 자리 차단" : "Ru는 Pt보다 H를 강하게 잡음 (DFT ±0.1 eV)"}</text>`;
  }
  const DGRU = -0.37, DGPT = -0.21;
  function fmt(x) {
    const sub = {"₀":"0","₁":"1","₂":"2","₃":"3","₄":"4","ₓ":"x"}, sup = {"⁻":"−","⁺":"+","²":"2","³":"3"};
    return x.replace(/[₀₁₂₃₄ₓ]+/g, m => "<sub>" + [...m].map(c => sub[c]).join("") + "</sub>")
            .replace(/[⁻⁺²³]+/g, m => "<sup>" + [...m].map(c => sup[c]).join("") + "</sup>");
  }

  const SEGS = [
    [0, 3.5, "개요", "Ru(0001) 수소 전극 — DFT 이완 구조", "", "Ni–H₂ 배터리 음극(수소 전극)의 Ru 표면. 은색 = 표면 Ru, 회색 = 하부 층."],
    [3.5, 10, "충전 · HER ①", "Volmer 단계", "H₂O + e⁻ + * → H* + OH⁻", "전자가 표면으로 올라오고, 물의 O–H 결합이 끊어져 H가 fcc hollow 자리에 흡착(높이 1.07 Å, DFT)."],
    [10, 16, "충전 · HER ②", "Volmer 단계 (두 번째)", "H₂O + e⁻ + * → H* + OH⁻", "알칼리에서는 물 해리가 느린 단계가 될 수 있다. OH⁻는 전해질로 떠난다."],
    [16, 23, "충전 · HER ③", "Tafel 재결합과 탈착", "2 H* → H₂ + 2*", "두 H*가 bridge 자리를 넘어 만나 H₂(0.74 Å)가 되어 떠난다. 셀 압력이 올라가는 이유."],
    [23, 29, "방전 · HOR ①", "H₂ 해리 흡착 (Tafel 역반응)", "H₂ + 2* → 2 H*", "저장된 H₂가 Ru 표면에서 두 개의 H*로 쪼개진다."],
    [29, 37, "방전 · HOR ②", "Volmer 역반응", "H* + OH⁻ → H₂O + e⁻ + *", "OH⁻가 H*를 가져가 물이 되고, 전자는 금속을 통해 외부 회로로 나간다."],
    [37, 45, "고장 모드", "Ru 산화 — 보호가 필요한 이유", "Ru + OH⁻ → Ru–OH* + e⁻ → RuOₓ", "H₂ 결핍·역전으로 전위가 0.4 V vs RHE를 넘으면 OH*와 산화물이 H 자리를 막는다 [문헌]."],
    [45, 54, "충전 · 양극", "Ni(OH)₂ → NiOOH", "Ni(OH)₂ + OH⁻ → NiOOH + H₂O + e⁻", "층 사이의 양성자가 빠져나가 물이 되고 Ni²⁺(녹색)가 Ni³⁺(검정)로 산화된다."],
    [54, 62, "방전 · 양극", "NiOOH → Ni(OH)₂", "NiOOH + H₂O + e⁻ → Ni(OH)₂ + OH⁻", "양성자가 층으로 돌아오며 Ni가 다시 환원된다. 모식도(원자 위치 비실측)."],
    [62, 66, "전지 반응", "RuH2-P1 셀 전체", "NiOOH + ½ H₂ ⇌ Ni(OH)₂    E° ≈ 1.32 V", "충전하면 H₂ 압력이 오르고 방전하면 내려간다. 그래서 압력계가 곧 SOC 게이지다."],
  ];
  const duration = 66;

  function camRu(t) {
    const a = 0.35 + 0.18 * Math.sin(t * 0.07), r = 16 - 3.5 * seg(t, 3, 8) + 3 * seg(t, 36, 40), el = 0.72;
    const tx = S1.x + 1.4, tz = S1.z - 0.8;
    cam.position.set(tx + r * Math.cos(el) * Math.sin(a), 1 + r * Math.sin(el), tz + r * Math.cos(el) * Math.cos(a));
    cam.lookAt(tx, 1.4, tz);
  }
  function camNi(t) {
    const a = 0.9 + 0.1 * Math.sin(t * 0.1);
    cam.position.set(27 * Math.sin(a), 15, 27 * Math.cos(a)); cam.lookAt(0, 4.2, 0);
  }

  function render(t) {
    const segi = SEGS.findIndex(s => t >= s[0] && t < s[1]); const S = SEGS[segi < 0 ? SEGS.length - 1 : segi];
    const inNi = t >= 45 && t < 62;
    ru.visible = !inNi; ni.visible = inNi;
    [W1, W2, W3, W4].forEach(hideW); niW.forEach(hideW);
    Hs.forEach(h => h.visible = false); e1.visible = e2.visible = false;
    [H2m.a, H2m.b, H2m.bb].forEach(m => m.visible = false);
    OHads.forEach(o => [o.O, o.H, o.b].forEach(m => m.visible = false));
    topAtoms.forEach(a => a.material = M.Ru);
    let active = -1, warn = false;
    if (!inNi) {
      camRu(t);
      // --- Volmer 1 (3.5-10) and 2 (10-16)
      for (const [w, st, a0, ex, hi] of [[W1, S1, 3.5, e1, 0], [W2, S2, 10, e2, 1]]) {
        if (t < a0) continue;
        const u1 = seg(t, a0, a0 + 2.4), u2 = seg(t, a0 + 2.6, a0 + 4.2), u3 = seg(t, a0 + 4.2, a0 + 6);
        if (t < 23) {
          const Oap = lerp(st.clone().add(V(-3, 7, 2)), st.clone().add(V(0.3, 2.05, 0.2)), u1);
          const Hd = lerp(Oap.clone().add(dA), st.clone(), u2);
          const Oaway = Oap.clone().add(V(-1.8 * u3, 6 * u3, 1.5 * u3));
          if (u3 < 0.98) {
            w.O.position.copy(Oaway); w.H2.position.copy(Oaway).add(dB); w.H1.position.copy(u2 > 0 ? Hd : Oap.clone().add(dA));
            [w.O, w.H1, w.H2, w.b2].forEach(m => m.visible = true); setBond(w.b2, w.O.position, w.H2.position);
            w.b1.visible = u2 < 0.35; if (w.b1.visible) setBond(w.b1, w.O.position, w.H1.position, 0.12 * (1 - u2 * 2));
            if (u2 >= 0.35) { w.H1.visible = false; Hs[hi].visible = true; Hs[hi].position.copy(Hd); }
          } else { Hs[hi].visible = true; Hs[hi].position.copy(st); }
          // electron rises from the metal to the site
          if (u1 > 0.3 && u2 < 1) { ex.visible = true; ex.position.copy(lerp(st.clone().add(V(0, -4.5, 0)), st.clone().add(V(0, 0.2, 0)), seg(t, a0 + 1, a0 + 3))); }
          active = u2 >= 1 ? 1 : 0;
        }
      }
      // --- Tafel (16-23): H* migrate, combine, desorb
      if (t >= 16 && t < 23) {
        const mid = S1.clone().add(S2).multiplyScalar(0.5);
        const u = seg(t, 16, 19), v = seg(t, 19, 22.5);
        const pa = lerp(S1, mid.clone().add(V(-0.37, 0.25, 0)), u), pb = lerp(S2, mid.clone().add(V(0.37, 0.25, 0)), u);
        const lift = V(0, 8 * v, 0);
        Hs[0].visible = Hs[1].visible = v < 0.05;
        Hs[0].position.copy(pa); Hs[1].position.copy(pb);
        if (u > 0.9) { [H2m.a, H2m.b, H2m.bb].forEach(m => m.visible = true); H2m.a.position.copy(pa.clone().add(lift)); H2m.b.position.copy(pb.clone().add(lift)); setBond(H2m.bb, H2m.a.position, H2m.b.position); }
        active = v > 0.1 ? 2 : 1;
      }
      // --- HOR (23-37)
      if (t >= 23 && t < 37) {
        const u = seg(t, 23, 26.5), v = seg(t, 26.5, 28.5);
        const mid = S3.clone().add(S4).multiplyScalar(0.5);
        const c0 = mid.clone().add(V(0, 8 * (1 - u) + 1.2, 0));
        const half = V(0.37, 0, 0);
        const pa = lerp(c0.clone().sub(half), S3, v), pb = lerp(c0.clone().add(half), S4, v);
        const sites = [pa, pb];
        for (const [k, w, st, ex, a0] of [[0, W3, S3, e1, 29], [1, W4, S4, e2, 31]]) {
          const g1 = seg(t, a0, a0 + 2.2), g2 = seg(t, a0 + 2.2, a0 + 3.4), g3 = seg(t, a0 + 3.4, a0 + 5.5);
          let hp = sites[k];
          if (t >= a0) {
            const O = lerp(st.clone().add(V(2.5, 6, -2)), st.clone().add(V(0.2, 1.95, 0.1)), g1).add(V(1.2 * g3, 6 * g3, -1 * g3));
            hp = lerp(st, O.clone().add(dA), g2).add(V(1.2 * g3, 6 * g3, -1 * g3));
            if (g2 > 0) hp = O.clone().add(dA.clone().multiplyScalar(g2 > 0.99 ? 1 : 1)).lerp(lerp(st, O.clone().add(dA), g2), 1 - g2);
            w.O.position.copy(O); w.H2.position.copy(O).add(dB);
            [w.O, w.H2, w.b2].forEach(m => m.visible = g3 < 0.97); setBond(w.b2, w.O.position, w.H2.position);
            if (g2 > 0.6) { w.H1.visible = g3 < 0.97; w.H1.position.copy(O).add(dA); w.b1.visible = w.H1.visible; setBond(w.b1, w.O.position, w.H1.position); }
            if (g2 > 0.2 && g3 < 1) { ex.visible = true; ex.position.copy(lerp(st.clone().add(V(0, 0.3, 0)), st.clone().add(V(0, -5, 0)), seg(t, a0 + 2.4, a0 + 4.6))); }
          }
          const showH = t < a0 + 2.2 + 1.3;
          Hs[k].visible = showH && !(t >= a0 + 2.2 + 1.2); Hs[k].position.copy(t < a0 ? hp : st);
          if (t < 26.5 + 0.1 && u < 1) Hs[k].visible = false;
        }
        if (v < 0.95) { [H2m.a, H2m.b, H2m.bb].forEach(m => m.visible = true); H2m.a.position.copy(pa); H2m.b.position.copy(pb); setBond(H2m.bb, pa, pb); }
        else { Hs[0].visible = Hs[0].visible || t < 29 + 3.4; Hs[1].visible = Hs[1].visible || t < 31 + 3.4; }
        active = t < 28.5 ? 2 : (t < 34 ? 1 : 0);
      }
      // --- oxidation (37-45)
      if (t >= 37 && t < 45) {
        warn = true;
        const n = Math.floor(seg(t, 38, 43) * OHads.length + 0.001);
        const tops = [topAtoms[21], topAtoms[22], topAtoms[25], topAtoms[26], topAtoms[37], topAtoms[38]].filter(Boolean);
        OHads.forEach((o, k) => {
          if (k >= n || !tops[k]) return;
          const base = tops[k].position; o.O.position.set(base.x, base.y + 2.05, base.z); o.H.position.set(base.x + 0.3, base.y + 2.95, base.z);
          [o.O, o.H, o.b].forEach(m => m.visible = true); setBond(o.b, o.O.position, o.H.position);
          if (t > 41 + k * 0.4) tops[k].material = M.RuOx;
        });
      }
    } else {
      camNi(t);
      const charge = t < 54, u = charge ? seg(t, 46, 52.5) : 1 - seg(t, 55, 61);
      niAtoms.forEach((n, k) => { n.material = (u > (k % 7) / 7 + 0.05) ? M.Ni3 : M.Ni2; });
      protons.forEach((h, k) => {
        const f = clamp(u * 1.3 - (k % 5) * 0.06);
        h.visible = f < 0.98;
        h.position.copy(h.userData.home).add(V(0.4 * f, 6 * f, 0.6 * f));
      });
      niW.forEach((w, k) => {
        const O = V(-4 + 4 * k, 3 * 4.7 + 2.5 + Math.sin(t + k) * 0.3, 3 - k * 2);
        placeWater(w, O, dA, dB, true);
      });
      active = -1;
    }
    if (t >= 62) { camRu(t); }
    // overlay
    q(".ov-k").innerHTML = fmt(S[2]); q(".ov-t").innerHTML = fmt(S[3]); q(".ov-eq").innerHTML = fmt(S[4]); q(".ov-cap").innerHTML = fmt(S[5]);
    DG.style.visibility = inNi ? "hidden" : "visible";
    drawDG(active, DGRU, DGPT, warn);
    renderer.render(scene, cam);
  }
  return { render, duration, scene, cam, segments: SEGS };
}
if (typeof module !== "undefined") module.exports = { makeAtomScene };
