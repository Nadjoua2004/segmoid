"use client";

import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { StatusBadge, type StatusKey } from "@/components/bio";

interface HologramModel3DProps {
  astronautId?: string;
  missionDay?: number;
  status: StatusKey;
  heartRate?: number | null;
  spo2?: number | null;
  sleepHours?: number | null;
  radiationMsv?: number | null;
  bpSys?: number | null;
  bpDia?: number | null;
  coreTempC?: number | null;
  bloodGlucose?: number | null;
  hrvRmssd?: number | null;
  moodScore?: number | null;
}

type BodyHotspotId = "brain" | "heart" | "lungs" | "metabolic";

interface BodyHotspotDef {
  id: BodyHotspotId;
  title: string;
  localPos: [number, number, number];
  side: "left" | "right";
  cardTopPct: number;
}

const BODY_HOTSPOTS: BodyHotspotDef[] = [
  { id: "brain", title: "NEURO / SLEEP", localPos: [0, 1.32, 0.08], side: "left", cardTopPct: 10 },
  { id: "heart", title: "HEART / CARDIO", localPos: [0.06, 0.52, 0.14], side: "right", cardTopPct: 26 },
  { id: "lungs", title: "LUNGS / O₂", localPos: [-0.11, 0.56, 0.12], side: "left", cardTopPct: 44 },
  { id: "metabolic", title: "RADIATION / METABOLIC", localPos: [0, -0.05, 0.13], side: "right", cardTopPct: 62 },
];

const STATUS_HEX: Record<StatusKey, number> = {
  NORMAL: 0x10e89a,
  MEDIUM: 0xfbbf24,
  CRITICAL: 0xfb7185,
  UNCLASSIFIED: 0x60a5fa,
  NODATA: 0x10e89a,
};

function createGlowTexture(): THREE.CanvasTexture | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.25, "rgba(210,255,235,0.85)");
  grad.addColorStop(0.55, "rgba(16,232,154,0.28)");
  grad.addColorStop(1, "rgba(16,232,154,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 64, 64);
  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  return tex;
}

function smoothBell(value: number, min: number, peak: number, max: number): number {
  if (value <= min || value >= max) return 0;
  const t =
    value < peak
      ? (value - min) / Math.max(peak - min, 1e-5)
      : (max - value) / Math.max(max - peak, 1e-5);
  return t * t * (3 - 2 * t);
}

/**
 * Adds athletic muscular volume to the thighs (quads/hamstrings) and calves
 * in normalized human space (y in [-1.39, 1.39]) while keeping the inner-leg gap clean.
 */
function sculptLegMuscles(root: THREE.Object3D): void {
  root.updateMatrixWorld(true);
  const v = new THREE.Vector3();
  const n = new THREE.Vector3();
  const invWorld = new THREE.Matrix4();
  const normalMat = new THREE.Matrix3();

  root.traverse((obj) => {
    if (!(obj as THREE.Mesh).isMesh) return;
    const mesh = obj as THREE.Mesh;
    const geo = mesh.geometry;
    if (!geo) return;

    geo.computeVertexNormals();
    const posAttr = geo.getAttribute("position");
    const normAttr = geo.getAttribute("normal");
    if (!posAttr || !normAttr) return;

    invWorld.copy(mesh.matrixWorld).invert();
    normalMat.getNormalMatrix(mesh.matrixWorld);

    for (let i = 0; i < posAttr.count; i++) {
      v.set(posAttr.getX(i), posAttr.getY(i), posAttr.getZ(i)).applyMatrix4(mesh.matrixWorld);

      // Only affect leg region (below pelvis, above ankles)
      if (v.y > -0.02 || v.y < -1.22) continue;

      n.set(normAttr.getX(i), normAttr.getY(i), normAttr.getZ(i))
        .applyMatrix3(normalMat)
        .normalize();

      const horizLen = Math.hypot(n.x, n.z);
      if (horizLen < 1e-4) continue;
      const nx = n.x / horizLen;
      const nz = n.z / horizLen;

      // Subtle athletic tone for thighs and calves (human-base already has natural form)
      const thigh = smoothBell(v.y, -0.72, -0.36, -0.02) * 0.009;
      const calf = smoothBell(v.y, -1.26, -1.0, -0.72) * 0.006;
      const bulk = thigh + calf;
      if (bulk <= 0) continue;

      // Guard inner thigh / midline so left & right legs never intersect
      const absX = Math.abs(v.x);
      const isInward = v.x * nx < 0;
      const midlineGuard = isInward
        ? Math.min(1, Math.max(0, (absX - 0.035) / 0.085))
        : 1;

      const offset = bulk * midlineGuard;
      v.x += nx * offset;
      v.z += nz * offset * 1.12;

      v.applyMatrix4(invWorld);
      posAttr.setXYZ(i, v.x, v.y, v.z);
    }

    posAttr.needsUpdate = true;
    geo.computeVertexNormals();
    geo.computeBoundingBox();
    geo.computeBoundingSphere();
  });
}

/**
 * True WebGL 3D floating, rotating anatomical human hologram powered by Three.js.
 * Loads the local Z-Anatomy `/body.glb` mesh via GLTFLoader + local DRACOLoader
 * and renders it with a custom Fresnel rim-glow + scanline holographic shader.
 */
export function HologramModel3D({
  astronautId,
  missionDay,
  status,
  heartRate,
  spo2,
  sleepHours,
  radiationMsv,
  bpSys,
  bpDia,
  coreTempC,
  bloodGlucose,
  hrvRmssd,
  moodScore,
}: HologramModel3DProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const angleRef = useRef<number>(0);
  const autoRotateRef = useRef<boolean>(true);
  const statusRef = useRef<StatusKey>(status);
  const dragRef = useRef<{ active: boolean; startX: number; startAngle: number }>({
    active: false,
    startX: 0,
    startAngle: 0,
  });
  const materialRef = useRef<THREE.ShaderMaterial | null>(null);
  const wireMatRef = useRef<THREE.LineBasicMaterial | null>(null);
  const nodeMatRef = useRef<THREE.PointsMaterial | null>(null);
  const ringMatRef = useRef<THREE.MeshBasicMaterial | null>(null);
  const particleMatRef = useRef<THREE.PointsMaterial | null>(null);
  const hotspotRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const svgLineRef = useRef<SVGLineElement | null>(null);
  const activePinRef = useRef<BodyHotspotId | null>(null);

  const [yawDeg, setYawDeg] = useState<number>(0);
  const [isAutoRotating, setIsAutoRotating] = useState<boolean>(true);
  const [isModelLoaded, setIsModelLoaded] = useState<boolean>(false);
  const [activePinId, setActivePinId] = useState<BodyHotspotId | null>(null);

  statusRef.current = status;
  autoRotateRef.current = isAutoRotating;
  activePinRef.current = activePinId;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (reduced) {
      setIsAutoRotating(false);
      autoRotateRef.current = false;
    }
  }, []);

  useEffect(() => {
    const hex = STATUS_HEX[status];
    if (materialRef.current) {
      materialRef.current.uniforms.uColor.value.setHex(hex);
    }
    if (wireMatRef.current) {
      wireMatRef.current.color.setHex(hex);
    }
    if (nodeMatRef.current) {
      nodeMatRef.current.color.setHex(hex);
    }
    if (ringMatRef.current) {
      ringMatRef.current.color.setHex(hex);
    }
    if (particleMatRef.current) {
      particleMatRef.current.color.setHex(hex);
    }
  }, [status]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;
    const width = Math.max(300, container.clientWidth);
    const height = Math.max(480, container.clientHeight);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, width / height, 0.1, 100);
    camera.position.set(0, 0.14, 5.55);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height);
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    const disposables: { dispose: () => void }[] = [];

    const glowTex = createGlowTexture();
    if (glowTex) disposables.push(glowTex);

    // Custom Holographic Fresnel Rim + Subtle Translucent Core Shader
    const holoMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.FrontSide,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: new THREE.Color(STATUS_HEX[statusRef.current]) },
      },
      vertexShader: `
        varying vec3 vNormalView;
        varying vec3 vViewDir;
        varying vec3 vWorldPos;
        void main() {
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          vNormalView = normalize(normalMatrix * normal);
          vViewDir = normalize(-mvPosition.xyz);
          vWorldPos = (modelMatrix * vec4(position, 1.0)).xyz;
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform vec3 uColor;
        varying vec3 vNormalView;
        varying vec3 vViewDir;
        varying vec3 vWorldPos;
        void main() {
          float ndotv = abs(dot(normalize(vNormalView), normalize(vViewDir)));
          float fresnel = pow(1.0 - ndotv, 2.1);
          float sweep = smoothstep(0.18, 0.0, abs(fract(vWorldPos.y * 0.24 - uTime * 0.18) - 0.5));
          float alpha = clamp(0.035 + fresnel * 0.68 + sweep * 0.12, 0.02, 0.86);
          vec3 col = mix(uColor, vec3(0.84, 1.0, 0.94), fresnel * 0.48 + sweep * 0.24);
          gl_FragColor = vec4(col, alpha);
        }
      `,
    });
    materialRef.current = holoMat;
    disposables.push(holoMat);

    // Glowing neural-wireframe network & luminous surface nodes
    const wireMat = new THREE.LineBasicMaterial({
      color: STATUS_HEX[statusRef.current],
      transparent: true,
      opacity: 0.24,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    wireMatRef.current = wireMat;
    disposables.push(wireMat);

    const nodeMat = new THREE.PointsMaterial({
      color: STATUS_HEX[statusRef.current],
      map: glowTex ?? undefined,
      size: 0.085,
      transparent: true,
      opacity: 0.88,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    nodeMatRef.current = nodeMat;
    disposables.push(nodeMat);

    // Floating human pivot
    const humanPivot = new THREE.Group();
    scene.add(humanPivot);

    // Load clean outer-skin human base mesh (/human-base.obj)
    const objLoader = new OBJLoader();
    objLoader.load(
      "/human-base.obj",
      (root) => {
        if (disposed) return;

        root.traverse((obj) => {
          if ((obj as THREE.Mesh).isMesh) {
            const mesh = obj as THREE.Mesh;
            // Hide MakeHuman rigging helper/joint cages so only the clean human shape renders
            if (mesh.name && mesh.name !== "body") {
              mesh.visible = false;
              return;
            }
            if (mesh.geometry) {
              mesh.geometry.computeVertexNormals();
              disposables.push(mesh.geometry);

              const wireGeo = new THREE.WireframeGeometry(mesh.geometry);
              disposables.push(wireGeo);
              const wireMesh = new THREE.LineSegments(wireGeo, wireMat);
              mesh.add(wireMesh);

              const posAttr = mesh.geometry.getAttribute("position");
              if (posAttr) {
                const nodeCoords: number[] = [];
                for (let i = 0; i < posAttr.count; i += 24) {
                  nodeCoords.push(posAttr.getX(i), posAttr.getY(i), posAttr.getZ(i));
                }
                const nodeGeo = new THREE.BufferGeometry();
                nodeGeo.setAttribute("position", new THREE.Float32BufferAttribute(nodeCoords, 3));
                disposables.push(nodeGeo);
                const nodePoints = new THREE.Points(nodeGeo, nodeMat);
                mesh.add(nodePoints);
              }
            }
            mesh.material = holoMat;
          }
        });

        // Normalize model to a taller, sleeker ~3.06-unit height and center at origin
        const box = new THREE.Box3().setFromObject(root);
        const size = new THREE.Vector3();
        const center = new THREE.Vector3();
        box.getSize(size);
        box.getCenter(center);

        const targetHeight = 3.06;
        const scale = targetHeight / Math.max(size.y, 0.001);
        const scaleXZ = scale * 0.95;
        const scaleY = scale * 1.05;
        root.scale.set(scaleXZ, scaleY, scaleXZ);
        root.position.set(-center.x * scaleXZ, -center.y * scaleY, -center.z * scaleXZ);

        humanPivot.add(root);
        setIsModelLoaded(true);
      },
      undefined,
      (err) => {
        console.error("Failed to load 3D human model:", err);
      }
    );

    // Upward hologram projection light cone from base
    const beamGeo = new THREE.CylinderGeometry(1.05, 0.42, 2.75, 48, 1, true);
    const beamMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uColor: holoMat.uniforms.uColor,
      },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        varying vec2 vUv;
        void main() {
          float vertFade = pow(1.0 - vUv.y, 1.9);
          float rays = 0.55 + 0.45 * sin(vUv.x * 62.8318);
          float alpha = vertFade * rays * 0.095;
          gl_FragColor = vec4(uColor, alpha);
        }
      `,
    });
    const beamMesh = new THREE.Mesh(beamGeo, beamMat);
    beamMesh.position.set(0, -0.05, 0);
    scene.add(beamMesh);
    disposables.push(beamGeo, beamMat);

    // 3D Orbital Scanner Rings below the floating human
    const ringMat = new THREE.MeshBasicMaterial({
      color: STATUS_HEX[statusRef.current],
      transparent: true,
      opacity: 0.48,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    });
    ringMatRef.current = ringMat;
    disposables.push(ringMat);

    const ringsGroup = new THREE.Group();
    ringsGroup.position.set(0, -1.62, 0);
    scene.add(ringsGroup);

    for (const [rIn, rOut] of [
      [0.88, 0.91],
      [0.64, 0.66],
      [0.40, 0.42],
    ]) {
      const rGeo = new THREE.RingGeometry(rIn, rOut, 64);
      disposables.push(rGeo);
      const rMesh = new THREE.Mesh(rGeo, ringMat);
      rMesh.rotation.x = -Math.PI / 2;
      ringsGroup.add(rMesh);
    }

    // Floating Rising Hologram Particles
    const pCount = 96;
    const pPositions = new Float32Array(pCount * 3);
    for (let i = 0; i < pCount; i++) {
      const a = Math.random() * Math.PI * 2;
      const rad = 0.45 + Math.random() * 0.78;
      pPositions[i * 3] = Math.cos(a) * rad;
      pPositions[i * 3 + 1] = -1.35 + Math.random() * 2.95;
      pPositions[i * 3 + 2] = Math.sin(a) * rad;
    }
    const pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute("position", new THREE.BufferAttribute(pPositions, 3));
    const pMat = new THREE.PointsMaterial({
      color: STATUS_HEX[statusRef.current],
      map: glowTex ?? undefined,
      size: 0.09,
      transparent: true,
      opacity: 0.72,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    particleMatRef.current = pMat;
    disposables.push(pGeo, pMat);
    const particles = new THREE.Points(pGeo, pMat);
    scene.add(particles);

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.max(280, Math.round(entry.contentRect.width));
        const h = Math.max(480, Math.round(entry.contentRect.height));
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      }
    });
    ro.observe(container);

    let frameId = 0;
    let last = performance.now();
    let uiTick = 0;

    const animate = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = now / 1000;

      holoMat.uniforms.uTime.value = t;

      if (autoRotateRef.current && !dragRef.current.active) {
        angleRef.current = (angleRef.current + dt * 0.52) % (Math.PI * 2);
      }

      // Floating levitation + smooth 360 rotation
      humanPivot.rotation.y = angleRef.current;
      humanPivot.position.y = Math.sin(t * 1.5) * 0.065 + 0.04;
      humanPivot.updateMatrixWorld();

      // Project 3D anatomical hotspots onto 2D stage coordinates
      const cw = container.clientWidth;
      const ch = container.clientHeight;
      const proj = new THREE.Vector3();
      for (const h of BODY_HOTSPOTS) {
        proj.set(h.localPos[0], h.localPos[1], h.localPos[2]);
        proj.applyMatrix4(humanPivot.matrixWorld).project(camera);
        const px = (proj.x * 0.5 + 0.5) * cw;
        const py = (-proj.y * 0.5 + 0.5) * ch;
        const btn = hotspotRefs.current[h.id];
        if (btn) {
          btn.style.transform = `translate3d(${px}px, ${py}px, 0) translate(-50%, -50%)`;
        }
        if (activePinRef.current === h.id && svgLineRef.current) {
          const cardAnchorX = h.side === "left" ? Math.min(156, cw * 0.34) : Math.max(cw - 156, cw * 0.66);
          const cardAnchorY = (h.cardTopPct / 100) * ch + 26;
          svgLineRef.current.setAttribute("x1", px.toFixed(1));
          svgLineRef.current.setAttribute("y1", py.toFixed(1));
          svgLineRef.current.setAttribute("x2", cardAnchorX.toFixed(1));
          svgLineRef.current.setAttribute("y2", cardAnchorY.toFixed(1));
        }
      }

      // Gentle drift on particles
      particles.rotation.y = -t * 0.14;
      const posAttr = pGeo.getAttribute("position") as THREE.BufferAttribute;
      for (let i = 0; i < pCount; i++) {
        let py = posAttr.getY(i) + dt * 0.18;
        if (py > 1.65) py = -1.35;
        posAttr.setY(i, py);
      }
      posAttr.needsUpdate = true;

      uiTick += dt;
      if (uiTick > 0.08) {
        uiTick = 0;
        const deg = Math.round(((angleRef.current * 180) / Math.PI) % 360);
        setYawDeg(deg < 0 ? deg + 360 : deg);
      }

      renderer.render(scene, camera);
      frameId = requestAnimationFrame(animate);
    };

    frameId = requestAnimationFrame(animate);

    return () => {
      disposed = true;
      cancelAnimationFrame(frameId);
      ro.disconnect();
      disposables.forEach((d) => d.dispose());
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = { active: true, startX: e.clientX, startAngle: angleRef.current };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.startX;
    angleRef.current = (dragRef.current.startAngle + dx * 0.012) % (Math.PI * 2);
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current.active) return;
    dragRef.current.active = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  };

  return (
    <section
      aria-label="3D Astronaut Biometric Hologram"
      className="relative flex min-h-[650px] flex-col justify-between overflow-hidden rounded-bio-lg border border-bio-border bg-transparent p-bio-4"
    >
      {/* Top HUD Bar */}
      <div className="relative z-10 flex items-center justify-between gap-bio-2">
        <div className="flex flex-col">
          <span className="font-mono text-bio-xs font-semibold uppercase tracking-wider text-bio-primary">
            Bio-Scan 3D
          </span>
          <span className="text-bio-xs text-bio-text-secondary">
            {astronautId ? `${astronautId}${missionDay ? ` · Sol ${missionDay}` : ""}` : "Awaiting telemetry"}
          </span>
        </div>
        <div className="flex items-center gap-bio-2">
          <StatusBadge status={status} />
          <button
            type="button"
            onClick={() => setIsAutoRotating((v) => !v)}
            aria-label={isAutoRotating ? "Pause 3D rotation" : "Resume 3D rotation"}
            title={isAutoRotating ? "Pause rotation" : "Auto-rotate"}
            className="bio-focus inline-flex h-8 items-center gap-bio-1 rounded-bio-sm border border-bio-border-control bg-transparent px-bio-2 font-mono text-bio-xs text-bio-text-secondary transition-colors hover:bg-bio-surface-hover hover:text-bio-text"
          >
            {isAutoRotating ? "Pause" : "Spin"}
          </button>
        </div>
      </div>

      {/* Central WebGL 3D Stage */}
      <div
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        title="Drag horizontally to rotate 3D model"
        className="relative my-bio-2 flex flex-1 cursor-grab select-none items-center justify-center active:cursor-grabbing"
      >
        <div ref={containerRef} className="h-[530px] w-full" />

        {!isModelLoaded && (
          <span className="pointer-events-none absolute font-mono text-bio-xs text-bio-primary">
            Loading 3D human anatomy…
          </span>
        )}

        {/* Interactive 3D Anatomical Hotspots + Leader Line + Rounded Callout Card */}
        {isModelLoaded && (
          <>
            {activePinId && (
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 z-10 h-full w-full"
              >
                <line
                  ref={svgLineRef}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="0"
                  stroke="#2DD4BF"
                  strokeWidth="1.5"
                  strokeDasharray="4 3"
                  strokeOpacity="0.85"
                />
              </svg>
            )}

            {BODY_HOTSPOTS.map((h) => {
              const isSelected = activePinId === h.id;
              return (
                <button
                  key={h.id}
                  ref={(el) => {
                    hotspotRefs.current[h.id] = el;
                  }}
                  type="button"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => setActivePinId((prev) => (prev === h.id ? null : h.id))}
                  aria-label={`Inspect ${h.title}`}
                  aria-expanded={isSelected}
                  title={`Click to ${isSelected ? "hide" : "inspect"} ${h.title}`}
                  style={{ left: 0, top: 0 }}
                  className="bio-focus absolute z-20 flex h-6 w-6 items-center justify-center rounded-full"
                >
                  <span
                    className={`absolute h-5 w-5 rounded-full transition-transform duration-200 ${
                      isSelected
                        ? "scale-125 bg-bio-primary/35 ring-2 ring-bio-primary"
                        : "animate-ping bg-bio-primary/30"
                    }`}
                  />
                  <span
                    className={`relative h-2.5 w-2.5 rounded-full border border-white/80 transition-colors ${
                      isSelected ? "bg-white shadow-[0_0_10px_#2DD4BF]" : "bg-bio-primary shadow-[0_0_8px_#10E89A]"
                    }`}
                  />
                </button>
              );
            })}

            {BODY_HOTSPOTS.map((h) => {
              if (activePinId !== h.id) return null;
              let primaryLine = "—";
              let secondaryLine = "";
              if (h.id === "brain") {
                primaryLine = sleepHours != null ? `${Number(sleepHours).toFixed(1)} h sleep` : "No sleep data";
                secondaryLine = moodScore != null ? `Mood ${moodScore}/5` : "Cognitive & rest";
              } else if (h.id === "heart") {
                primaryLine = heartRate != null ? `${Math.round(heartRate)} bpm` : "No HR data";
                secondaryLine =
                  bpSys != null && bpDia != null
                    ? `BP ${Math.round(bpSys)}/${Math.round(bpDia)}${hrvRmssd != null ? ` · HRV ${Math.round(hrvRmssd)} ms` : ""}`
                    : "Cardiovascular load";
              } else if (h.id === "lungs") {
                primaryLine = spo2 != null ? `SpO₂ ${Number(spo2).toFixed(1)}%` : "No SpO₂ data";
                secondaryLine = coreTempC != null ? `Core ${Number(coreTempC).toFixed(1)} °C` : "Oxygenation";
              } else {
                primaryLine = radiationMsv != null ? `${Number(radiationMsv).toFixed(2)} mSv` : "No dose data";
                secondaryLine = bloodGlucose != null ? `Glucose ${Math.round(bloodGlucose)} mg/dL` : "Exposure & metabolic";
              }

              return (
                <button
                  key={`card-${h.id}`}
                  type="button"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => setActivePinId(null)}
                  title="Click to collapse"
                  style={{ top: `${h.cardTopPct}%` }}
                  className={`bio-focus absolute z-20 max-w-[168px] rounded-xl border border-bio-primary/50 bg-bio-canvas/90 px-3 py-2 text-left shadow-[0_8px_24px_rgba(0,0,0,0.55)] backdrop-blur-md transition-all duration-200 hover:border-bio-primary ${
                    h.side === "left" ? "left-2" : "right-2 text-right"
                  }`}
                >
                  <div className="font-mono text-[10px] font-semibold tracking-wider text-bio-primary">
                    {h.title}
                  </div>
                  <div className="mt-0.5 font-mono text-bio-sm font-semibold text-bio-text">
                    {primaryLine}
                  </div>
                  <div className="mt-0.5 text-[11px] text-bio-text-secondary">
                    {secondaryLine}
                  </div>
                </button>
              );
            })}
          </>
        )}
      </div>

      {/* Bottom Interactive Hint */}
      <div className="relative z-10 flex items-center justify-between border-t border-bio-border pt-bio-2 font-mono text-[11px] text-bio-text-muted">
        <span>Drag to inspect 360°</span>
        <span className="text-bio-primary">YAW {yawDeg}°</span>
      </div>
    </section>
  );
}
