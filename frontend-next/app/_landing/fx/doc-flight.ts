/**
 * The camera-through-floating-orders fly-through between the hero and the
 * advocate-search scene. Dynamically imported (three is ~150 KB gzipped and
 * nothing above the fold needs it), only when motion is allowed and WebGL
 * exists. Renders on demand: a frame per progress change plus a short idle
 * drift while the flight is on screen, nothing at all otherwise.
 */
import * as THREE from "three";

type Flight = { setProgress: (p: number) => void; setActive: (on: boolean) => void; dispose: () => void };

const PAPER = "#FFFFFF";
const INK = "rgba(20,32,44,";

function sheetTexture(seed: number, size: number) {
  const c = document.createElement("canvas");
  c.width = size;
  c.height = Math.round(size * 1.414);
  const g = c.getContext("2d")!;
  const s = size / 512;
  g.fillStyle = PAPER;
  g.fillRect(0, 0, c.width, c.height);
  // paper speckle
  for (let i = 0; i < 900 * s; i++) {
    g.fillStyle = `${INK}${(Math.random() * 0.05).toFixed(3)})`;
    g.fillRect(Math.random() * c.width, Math.random() * c.height, 1.2 * s, 1.2 * s);
  }
  g.fillStyle = `${INK}0.75)`;
  g.textAlign = "center";
  g.font = `${600} ${15 * s}px "IBM Plex Mono", monospace`;
  g.fillText("IN THE HIGH COURT FOR THE STATE OF TELANGANA", c.width / 2, 58 * s);
  g.font = `${13 * s}px "IBM Plex Mono", monospace`;
  g.fillStyle = `${INK}0.55)`;
  g.fillText(["W.P. No. ____ of 2026", "C.R.P. No. ____ of 2025", "CAUSE LIST", "O.S. No. ____ of 2024"][seed % 4], c.width / 2, 84 * s);
  g.textAlign = "left";
  let y = 130 * s;
  const rnd = (n: number) => ((Math.sin(seed * 91.7 + n * 13.1) + 1) / 2);
  for (let i = 0; i < 26; i++) {
    const w = (0.55 + rnd(i) * 0.33) * (c.width - 96 * s);
    g.fillStyle = `${INK}${0.16 + rnd(i + 40) * 0.1})`;
    g.fillRect(48 * s, y, w, 5 * s);
    y += i % 6 === 5 ? 26 * s : 17 * s;
  }
  if (seed % 3 === 0) {
    // seal-red stamp
    g.strokeStyle = "rgba(168,58,44,0.55)";
    g.lineWidth = 3 * s;
    g.beginPath();
    g.arc(c.width - 110 * s, c.height - 120 * s, 46 * s, 0, Math.PI * 2);
    g.stroke();
    g.font = `${11 * s}px "IBM Plex Mono", monospace`;
    g.fillStyle = "rgba(168,58,44,0.6)";
    g.textAlign = "center";
    g.fillText("CERTIFIED", c.width - 110 * s, c.height - 116 * s);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 2;
  return t;
}

export function createDocFlight(canvas: HTMLCanvasElement, { lite }: { lite: boolean }): Flight {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: !lite, powerPreference: "high-performance" });
  // Phones render below native resolution: the sheets are soft and in motion, and fill is the cost.
  renderer.setPixelRatio(lite ? 0.75 : Math.min(window.devicePixelRatio, 1.5));
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  // Match the landing page so distant sheets dissolve into paper, not black.
  const paper = getComputedStyle(canvas).getPropertyValue("--nb-paper").trim() || "#F8F6F0";
  scene.fog = new THREE.Fog(paper, 3, lite ? 16 : 22);
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 60);

  const COUNT = lite ? 10 : 36;
  const DEPTH = 30;
  const textures = Array.from({ length: lite ? 2 : 6 }, (_, i) => sheetTexture(i, lite ? 256 : 512));
  const geo = new THREE.PlaneGeometry(0.9, 1.27);
  const sheets: { mesh: THREE.Mesh; spin: number; bob: number }[] = [];
  for (let i = 0; i < COUNT; i++) {
    // Opaque: no blending or back-to-front sorting; the fog does the fading.
    const mat = new THREE.MeshBasicMaterial({ map: textures[i % textures.length], side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(geo, mat);
    // Keep a clear corridor down the middle so the camera flies *between* sheets.
    const angle = Math.random() * Math.PI * 2;
    const r = 1.1 + Math.random() * 1.9;
    mesh.position.set(Math.cos(angle) * r * 1.35, Math.sin(angle) * r * 0.85, -Math.random() * DEPTH + 2);
    mesh.rotation.set((Math.random() - 0.5) * 0.9, (Math.random() - 0.5) * 1.4, (Math.random() - 0.5) * 0.8);
    scene.add(mesh);
    sheets.push({ mesh, spin: (Math.random() - 0.5) * 0.25, bob: Math.random() * Math.PI * 2 });
  }

  let progress = 0;
  let active = false;
  let raf = 0;
  let last = performance.now();
  let t = 0;

  const resize = () => {
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  resize();
  window.addEventListener("resize", resize);

  const render = () => {
    // ease the camera so the flight starts slow, rushes, then settles
    const e = progress < 0.5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2;
    camera.position.set(Math.sin(e * 3.1) * 0.35, Math.cos(e * 2.3) * 0.18, 4 - e * (DEPTH - 2));
    camera.rotation.z = Math.sin(e * Math.PI) * 0.12;
    for (const s of sheets) {
      s.mesh.rotation.y += s.spin * 0.016;
      s.mesh.position.y += Math.sin(t + s.bob) * 0.0009;
    }
    renderer.render(scene, camera);
  };

  const loop = (now: number) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    t += dt;
    render();
    if (active) raf = requestAnimationFrame(loop);
  };

  return {
    setProgress(p) {
      progress = p;
      if (!active) render();
    },
    setActive(on) {
      if (on === active) return;
      active = on;
      cancelAnimationFrame(raf);
      if (on) {
        last = performance.now();
        raf = requestAnimationFrame(loop);
      }
    },
    dispose() {
      active = false;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      sheets.forEach((s) => (s.mesh.material as THREE.Material).dispose());
      textures.forEach((tx) => tx.dispose());
      geo.dispose();
      renderer.dispose();
    },
  };
}
