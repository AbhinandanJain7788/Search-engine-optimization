// 3D agent network visualization using Three.js.
// Renders the orchestrator at center with sub-agents on an orbital ring.
// Exposes setAgentStatus / setActiveAgents / resetAgents for live updates.
import * as THREE from "three";

const VIZ = document.getElementById("viz");
const TOOLTIP = document.getElementById("vizTooltip");

const STATE = {
  scene: null,
  camera: null,
  renderer: null,
  raycaster: null,
  mouse: new THREE.Vector2(),
  nodes: new Map(),     // id -> { mesh, ring, glow, label, agent, theta }
  edges: [],
  group: null,
  hovered: null,
  active: new Set(),
  rotationSpeed: 0.0015,
  pulseTime: 0,
};

const STATUS_COLOR = {
  idle: 0x4a5a7a,
  start: 0x4a7cff,
  info: 0x4a7cff,
  active: 0x4a7cff,
  ok: 0x2d6a4f,
  warn: 0xd4740e,
  fail: 0xc53030,
  error: 0xc53030,
  done: 0xb8860b,
};

window.addEventListener("agents-loaded", (e) => {
  const agents = e.detail || [];
  initScene(agents);
});

function initScene(agents) {
  const width = VIZ.clientWidth;
  const height = VIZ.clientHeight;

  STATE.scene = new THREE.Scene();
  STATE.scene.fog = new THREE.Fog(0x080c16, 18, 70);

  STATE.camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 200);
  STATE.camera.position.set(0, 8, 22);
  STATE.camera.lookAt(0, 0, 0);

  STATE.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  STATE.renderer.setSize(width, height);
  STATE.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  STATE.renderer.setClearColor(0x000000, 0);
  VIZ.appendChild(STATE.renderer.domElement);

  STATE.raycaster = new THREE.Raycaster();

  // Ambient + key light + rim light
  STATE.scene.add(new THREE.AmbientLight(0x4a6a9a, 0.55));
  const key = new THREE.PointLight(0xfff2c8, 1.2, 60);
  key.position.set(8, 14, 10);
  STATE.scene.add(key);
  const rim = new THREE.PointLight(0x4a7cff, 0.9, 50);
  rim.position.set(-12, -6, 8);
  STATE.scene.add(rim);

  // Starfield backdrop
  addStars();

  // Orbital floor grid
  addGrid();

  STATE.group = new THREE.Group();
  STATE.scene.add(STATE.group);

  // Build orchestrator at center + sub-agents around
  const sub = agents.filter((a) => a.id !== "orchestrator");
  const orchestrator = agents.find((a) => a.id === "orchestrator") || sub.shift();

  if (orchestrator) addNode(orchestrator, new THREE.Vector3(0, 0, 0), 1.6, true);

  const radius = 9.5;
  sub.forEach((a, i) => {
    const theta = (i / sub.length) * Math.PI * 2;
    const x = Math.cos(theta) * radius;
    const z = Math.sin(theta) * radius;
    const y = ((i % 3) - 1) * 0.7;
    addNode(a, new THREE.Vector3(x, y, z), 0.7, false, theta);
  });

  // Edges from orchestrator to each agent
  const orch = STATE.nodes.get(orchestrator?.id);
  if (orch) {
    sub.forEach((a) => {
      const tgt = STATE.nodes.get(a.id);
      if (tgt) addEdge(orch.mesh.position, tgt.mesh.position, a.id);
    });
  }

  // Interaction
  VIZ.addEventListener("mousemove", onPointerMove);
  VIZ.addEventListener("mouseleave", () => {
    TOOLTIP.hidden = true;
    STATE.hovered = null;
  });
  window.addEventListener("resize", onResize);

  animate();
}

function addStars() {
  const count = 320;
  const geo = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const r = 35 + Math.random() * 30;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.cos(phi);
    positions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
  }
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const mat = new THREE.PointsMaterial({
    color: 0xa0b0d0,
    size: 0.06,
    transparent: true,
    opacity: 0.45,
  });
  STATE.scene.add(new THREE.Points(geo, mat));
}

function addGrid() {
  const grid = new THREE.PolarGridHelper(11, 8, 6, 64, 0x1e3a5f, 0x1a2540);
  grid.position.y = -2.4;
  grid.material.transparent = true;
  grid.material.opacity = 0.55;
  STATE.scene.add(grid);

  // Outer ring
  const ringGeo = new THREE.RingGeometry(11.4, 11.55, 96);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x4a7cff,
    transparent: true,
    opacity: 0.32,
    side: THREE.DoubleSide,
  });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.x = Math.PI / 2;
  ring.position.y = -2.39;
  STATE.scene.add(ring);
}

function addNode(agent, position, size, isCenter, theta = 0) {
  const color = new THREE.Color(agent.color || "#4a7cff");

  // Core sphere
  const geom = new THREE.IcosahedronGeometry(size, 1);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x1a2540,
    emissive: color,
    emissiveIntensity: 0.45,
    roughness: 0.3,
    metalness: 0.55,
    flatShading: true,
  });
  const mesh = new THREE.Mesh(geom, mat);
  mesh.position.copy(position);
  mesh.userData = { agent };
  STATE.group.add(mesh);

  // Soft glow halo (sprite-like ring)
  const glowGeo = new THREE.SphereGeometry(size * 1.6, 24, 24);
  const glowMat = new THREE.MeshBasicMaterial({
    color: color,
    transparent: true,
    opacity: 0.06,
  });
  const glow = new THREE.Mesh(glowGeo, glowMat);
  glow.position.copy(position);
  STATE.group.add(glow);

  // Orbital ring around node
  let ring = null;
  if (!isCenter) {
    const rg = new THREE.RingGeometry(size * 1.35, size * 1.42, 32);
    const rm = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.25,
      side: THREE.DoubleSide,
    });
    ring = new THREE.Mesh(rg, rm);
    ring.position.copy(position);
    ring.rotation.x = Math.PI * 0.45;
    STATE.group.add(ring);
  }

  // Text label
  const label = makeLabel(agent.label || agent.id, isCenter);
  label.position.copy(position).add(new THREE.Vector3(0, isCenter ? -2.4 : -1.2, 0));
  STATE.group.add(label);

  STATE.nodes.set(agent.id, {
    mesh, ring, glow, label, agent, theta, size, isCenter,
    statusColor: color.clone(),
    baseColor: color.clone(),
    status: "idle",
  });
}

function makeLabel(text, big) {
  const canvas = document.createElement("canvas");
  const dpr = 2;
  const fontSize = big ? 30 : 22;
  canvas.width = 512 * dpr;
  canvas.height = 96 * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.fillStyle = big ? "#b8860b" : "#e6ecf5";
  ctx.font = `${big ? 700 : 600} ${fontSize}px Inter, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.shadowColor = "rgba(0,0,0,0.6)";
  ctx.shadowBlur = 6;
  ctx.fillText(text, 256, 48);

  const tex = new THREE.CanvasTexture(canvas);
  tex.minFilter = THREE.LinearFilter;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(big ? 4 : 3, big ? 0.75 : 0.55, 1);
  return sprite;
}

function addEdge(from, to, agentId) {
  const geom = new THREE.BufferGeometry().setFromPoints([from, to]);
  const mat = new THREE.LineBasicMaterial({
    color: 0x4a7cff,
    transparent: true,
    opacity: 0.13,
  });
  const line = new THREE.Line(geom, mat);
  STATE.group.add(line);
  STATE.edges.push({ line, agentId });
}

function onPointerMove(e) {
  const rect = VIZ.getBoundingClientRect();
  STATE.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  STATE.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  STATE.raycaster.setFromCamera(STATE.mouse, STATE.camera);
  const meshes = Array.from(STATE.nodes.values()).map((n) => n.mesh);
  const hits = STATE.raycaster.intersectObjects(meshes);
  if (hits.length) {
    const agent = hits[0].object.userData.agent;
    STATE.hovered = agent.id;
    TOOLTIP.hidden = false;
    TOOLTIP.style.left = `${e.clientX + 14}px`;
    TOOLTIP.style.top = `${e.clientY + 14}px`;
    TOOLTIP.innerHTML = `<div class="tt-label">${agent.label}</div>
      <div class="tt-desc">${agent.desc || ""}</div>`;
  } else {
    TOOLTIP.hidden = true;
    STATE.hovered = null;
  }
}

function onResize() {
  if (!STATE.renderer) return;
  const w = VIZ.clientWidth;
  const h = VIZ.clientHeight;
  STATE.camera.aspect = w / h;
  STATE.camera.updateProjectionMatrix();
  STATE.renderer.setSize(w, h);
}

function animate() {
  requestAnimationFrame(animate);
  STATE.pulseTime += 0.045;
  STATE.group.rotation.y += STATE.rotationSpeed;

  // Pulse active nodes
  STATE.nodes.forEach((n) => {
    const isActive = STATE.active.has(n.agent.id);
    const baseScale = 1;
    const pulse = isActive ? 1 + Math.sin(STATE.pulseTime * 2.6) * 0.12 : 1;
    n.mesh.scale.setScalar(baseScale * pulse);

    if (isActive) {
      n.glow.material.opacity = 0.22 + Math.sin(STATE.pulseTime * 2) * 0.08;
    } else {
      n.glow.material.opacity = 0.06;
    }

    if (n.ring) {
      n.ring.rotation.z += isActive ? 0.04 : 0.008;
    }

    n.label.material.opacity =
      STATE.hovered === n.agent.id || isActive ? 1 : 0.75;
  });

  // Brighten active edges
  STATE.edges.forEach((e) => {
    e.line.material.opacity = STATE.active.has(e.agentId) ? 0.6 : 0.13;
    e.line.material.color.setHex(
      STATE.active.has(e.agentId) ? 0x6294ff : 0x4a7cff
    );
  });

  // Subtle camera orbit when nothing hovered/active
  const targetY = STATE.active.size ? 7 : 8 + Math.sin(STATE.pulseTime * 0.2) * 0.5;
  STATE.camera.position.y += (targetY - STATE.camera.position.y) * 0.02;
  STATE.camera.lookAt(0, 0, 0);

  STATE.renderer.render(STATE.scene, STATE.camera);
}

// ---------- Public API ----------
export function setActiveAgents(ids) {
  STATE.active = new Set(ids);
}

export function setAgentStatus(agentId, status) {
  const n = STATE.nodes.get(agentId);
  if (!n) return;
  const color = STATUS_COLOR[status];
  if (color !== undefined) {
    n.mesh.material.emissive.setHex(color);
    if (n.ring) n.ring.material.color.setHex(color);
    n.glow.material.color.setHex(color);
  }
  n.status = status;

  if (status === "start" || status === "info" || status === "active") {
    STATE.active.add(agentId);
  } else if (status === "ok" || status === "fail" || status === "warn" || status === "error" || status === "done") {
    STATE.active.delete(agentId);
  }
}

export function resetAgents() {
  STATE.active.clear();
  STATE.nodes.forEach((n) => {
    n.mesh.material.emissive.copy(n.baseColor).multiplyScalar(0.45);
    n.glow.material.color.copy(n.baseColor);
    if (n.ring) n.ring.material.color.copy(n.baseColor);
    n.status = "idle";
  });
}
