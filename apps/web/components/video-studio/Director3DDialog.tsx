"use client";

import { Box, Camera, CirclePlay, Cuboid, Download, LoaderCircle, Plus, Sparkles, Trash2, UserRound, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { DirectorAnchor, DirectorCamera, DirectorObject, DirectorScene } from "./types";

const DEFAULT_CAMERA: DirectorCamera = {
  position: { x: 6, y: 4, z: 8 },
  target: { x: 0, y: 1, z: 0 },
  focal_length: 35,
};

export const DEFAULT_DIRECTOR_SCENE: DirectorScene = {
  objects: [],
  camera: DEFAULT_CAMERA,
  background: "#edf2ff",
};

function vector(value: THREE.Vector3) {
  return { x: Number(value.x.toFixed(3)), y: Number(value.y.toFixed(3)), z: Number(value.z.toFixed(3)) };
}

function material(color: string) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.72, metalness: 0.05 });
}

function mannequin(value: DirectorObject): THREE.Group {
  const group = new THREE.Group();
  const body = material(value.color);
  const add = (geometry: THREE.BufferGeometry, x: number, y: number, z: number, rotationZ = 0) => {
    const mesh = new THREE.Mesh(geometry, body);
    mesh.position.set(x, y, z);
    mesh.rotation.z = rotationZ;
    mesh.castShadow = true;
    group.add(mesh);
  };
  add(new THREE.SphereGeometry(0.24, 18, 12), 0, 1.72, 0);
  add(new THREE.CapsuleGeometry(0.25, 0.62, 6, 12), 0, 1.12, 0);
  add(new THREE.CapsuleGeometry(0.09, 0.58, 5, 10), -0.38, 1.18, 0, -0.18);
  add(new THREE.CapsuleGeometry(0.09, 0.58, 5, 10), 0.38, 1.18, 0, 0.18);
  add(new THREE.CapsuleGeometry(0.11, 0.72, 5, 10), -0.16, 0.4, 0, 0.04);
  add(new THREE.CapsuleGeometry(0.11, 0.72, 5, 10), 0.16, 0.4, 0, -0.04);
  return group;
}

function object3d(value: DirectorObject): THREE.Object3D {
  if (value.shape === "mannequin") return mannequin(value);
  const geometry = value.shape === "sphere"
    ? new THREE.SphereGeometry(0.5, 24, 16)
    : value.shape === "cylinder"
      ? new THREE.CylinderGeometry(0.5, 0.5, 1, 24)
      : new THREE.BoxGeometry(1, 1, 1);
  const mesh = new THREE.Mesh(geometry, material(value.color));
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

export function Director3DDialog({
  open,
  isChinese,
  scene,
  anchors,
  onClose,
  onSceneChange,
  onAnchorsChange,
  onGenerate,
  onExport,
}: {
  open: boolean;
  isChinese: boolean;
  scene: DirectorScene;
  anchors: DirectorAnchor[];
  onClose: () => void;
  onSceneChange: (scene: DirectorScene) => void;
  onAnchorsChange: (anchors: DirectorAnchor[]) => void;
  onGenerate: (prompt: string) => Promise<DirectorScene>;
  onExport: (blob: Blob) => Promise<void>;
}) {
  const host = useRef<HTMLDivElement>(null);
  const renderer = useRef<THREE.WebGLRenderer | null>(null);
  const camera = useRef<THREE.PerspectiveCamera | null>(null);
  const controls = useRef<OrbitControls | null>(null);
  const [selectedId, setSelectedId] = useState(scene.objects[0]?.id || "");
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const selected = useMemo(() => scene.objects.find((item) => item.id === selectedId) || null, [scene.objects, selectedId]);

  useEffect(() => {
    if (!open || !host.current) return;
    const element = host.current;
    const stage = new THREE.Scene();
    stage.background = new THREE.Color(scene.background);
    const nextRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    nextRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    nextRenderer.shadowMap.enabled = true;
    element.replaceChildren(nextRenderer.domElement);
    const nextCamera = new THREE.PerspectiveCamera(50, 1, 0.05, 500);
    nextCamera.setFocalLength(scene.camera.focal_length);
    nextCamera.position.set(scene.camera.position.x, scene.camera.position.y, scene.camera.position.z);
    const nextControls = new OrbitControls(nextCamera, nextRenderer.domElement);
    nextControls.target.set(scene.camera.target.x, scene.camera.target.y, scene.camera.target.z);
    nextControls.enableDamping = true;
    nextControls.dampingFactor = 0.08;
    nextControls.update();
    const ambient = new THREE.HemisphereLight(0xffffff, 0x667085, 2.2);
    stage.add(ambient);
    const sun = new THREE.DirectionalLight(0xffffff, 3.2);
    sun.position.set(5, 9, 5);
    sun.castShadow = true;
    stage.add(sun);
    stage.add(new THREE.GridHelper(30, 30, 0xa7b3c7, 0xd8deea));
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.ShadowMaterial({ opacity: 0.12 }));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    stage.add(floor);
    for (const item of scene.objects) {
      const rendered = object3d(item);
      rendered.position.set(item.position.x, item.position.y, item.position.z);
      rendered.scale.set(item.scale.x, item.scale.y, item.scale.z);
      rendered.userData.directorObjectId = item.id;
      stage.add(rendered);
    }
    const resize = () => {
      const width = Math.max(1, element.clientWidth);
      const height = Math.max(1, element.clientHeight);
      nextRenderer.setSize(width, height, false);
      nextCamera.aspect = width / height;
      nextCamera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    let frame = 0;
    const draw = () => {
      nextControls.update();
      nextRenderer.render(stage, nextCamera);
      frame = requestAnimationFrame(draw);
    };
    draw();
    renderer.current = nextRenderer;
    camera.current = nextCamera;
    controls.current = nextControls;
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      nextControls.dispose();
      stage.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          for (const item of materials) item.dispose();
        }
      });
      nextRenderer.dispose();
      renderer.current = null;
      camera.current = null;
      controls.current = null;
    };
  }, [open, scene]);

  if (!open) return null;

  const readCamera = (): DirectorCamera => ({
    position: camera.current ? vector(camera.current.position) : scene.camera.position,
    target: controls.current ? vector(controls.current.target) : scene.camera.target,
    focal_length: camera.current ? Number(camera.current.getFocalLength().toFixed(1)) : scene.camera.focal_length,
  });
  const updateObject = (patch: Partial<DirectorObject>) => {
    if (!selected) return;
    onSceneChange({ ...scene, objects: scene.objects.map((item) => item.id === selected.id ? { ...item, ...patch } : item) });
  };
  const addObject = (shape: DirectorObject["shape"]) => {
    const value: DirectorObject = { id: crypto.randomUUID(), name: shape === "mannequin" ? (isChinese ? "人物" : "Person") : shape, shape, position: { x: 0, y: shape === "mannequin" ? 0 : 0.5, z: 0 }, scale: { x: 1, y: 1, z: 1 }, color: "#8b5cf6" };
    onSceneChange({ ...scene, objects: [...scene.objects, value] });
    setSelectedId(value.id);
  };
  const capture = () => onAnchorsChange([...anchors, { id: crypto.randomUUID(), name: `${isChinese ? "机位" : "Camera"} ${anchors.length + 1}`, camera: readCamera() }]);
  const close = () => {
    onSceneChange({ ...scene, camera: readCamera() });
    onClose();
  };
  const restore = (value: DirectorAnchor) => onSceneChange({ ...scene, camera: value.camera });
  const play = async () => {
    if (anchors.length === 0 || playing) return;
    setPlaying(true);
    for (const anchor of anchors) {
      onSceneChange({ ...scene, camera: anchor.camera });
      await new Promise((resolve) => window.setTimeout(resolve, 900));
    }
    setPlaying(false);
  };
  const generate = async () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    setError("");
    try {
      const next = await onGenerate(prompt.trim());
      onSceneChange(next);
      setSelectedId(next.objects[0]?.id || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Director generation failed");
    } finally {
      setGenerating(false);
    }
  };
  const exportFrame = async () => {
    const canvas = renderer.current?.domElement;
    if (!canvas) return;
    setExporting(true);
    try {
      const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob((value) => value ? resolve(value) : reject(new Error("Could not capture frame")), "image/png"));
      await onExport(blob);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[90] flex bg-[#141827]/50 p-5">
      <section role="dialog" aria-modal="true" aria-label={isChinese ? "3D 导演台" : "3D Director"} className="m-auto flex h-[min(900px,calc(100vh-40px))] w-[min(1480px,calc(100vw-40px))] flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
                <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#ebeef5] px-5"><div className="flex items-center gap-2"><Box className="size-5 text-[#8b5cf6]" /><h2 className="font-semibold">{isChinese ? "3D 导演台" : "3D Director"}</h2></div><div className="flex items-center gap-2"><button onClick={capture} className="inline-flex items-center gap-2 rounded-lg border border-[#dcdfe6] px-3 py-2 text-xs"><Camera className="size-4" />{isChinese ? "记录机位" : "Capture camera"}</button><button onClick={() => void play()} disabled={playing || anchors.length === 0} className="inline-flex items-center gap-2 rounded-lg border border-[#dcdfe6] px-3 py-2 text-xs disabled:opacity-40"><CirclePlay className="size-4" />{isChinese ? "预览运镜" : "Preview cameras"}</button><button onClick={() => void exportFrame()} disabled={exporting} className="inline-flex items-center gap-2 rounded-lg bg-[#8b5cf6] px-3 py-2 text-xs text-white"><Download className="size-4" />{isChinese ? "导出关键帧" : "Export frame"}</button><button onClick={close} className="rounded-lg p-2 text-[#909399] hover:bg-[#f5f7fa]"><X className="size-5" /></button></div></header>
        <div className="flex min-h-0 flex-1">
          <aside className="w-64 shrink-0 overflow-y-auto border-r border-[#ebeef5] p-3"><p className="px-2 py-2 text-xs font-semibold text-[#909399]">{isChinese ? "场景物体" : "Scene objects"}</p><div className="grid grid-cols-4 gap-1"><button onClick={() => addObject("cube")} title="Cube" className="rounded-lg p-2 hover:bg-[#f5f1ff]"><Cuboid className="m-auto size-4" /></button><button onClick={() => addObject("sphere")} title="Sphere" className="rounded-lg p-2 hover:bg-[#f5f1ff]">●</button><button onClick={() => addObject("cylinder")} title="Cylinder" className="rounded-lg p-2 hover:bg-[#f5f1ff]">◉</button><button onClick={() => addObject("mannequin")} title="Person" className="rounded-lg p-2 hover:bg-[#f5f1ff]"><UserRound className="m-auto size-4" /></button></div><div className="mt-3 space-y-1">{scene.objects.map((item) => <button key={item.id} onClick={() => setSelectedId(item.id)} className={`flex w-full items-center rounded-lg px-3 py-2 text-left text-xs ${selectedId === item.id ? "bg-[#f2eafe] text-[#7c3aed]" : "hover:bg-[#f5f7fa]"}`}><span className="min-w-0 flex-1 truncate">{item.name}</span></button>)}</div>{selected && <div className="mt-4 space-y-3 border-t border-[#ebeef5] pt-4"><input value={selected.name} onChange={(event) => updateObject({ name: event.target.value })} className="w-full rounded-lg border border-[#dcdfe6] px-2 py-1.5 text-xs" /><label className="block text-[11px] text-[#909399]">{isChinese ? "颜色" : "Color"}<input type="color" value={selected.color} onChange={(event) => updateObject({ color: event.target.value })} className="mt-1 h-8 w-full" /></label>{(["x", "y", "z"] as const).map((axis) => <label key={axis} className="grid grid-cols-[18px_1fr] items-center gap-2 text-[11px] uppercase text-[#909399]">{axis}<input type="number" step="0.1" value={selected.position[axis]} onChange={(event) => updateObject({ position: { ...selected.position, [axis]: Number(event.target.value) } })} className="rounded-lg border border-[#dcdfe6] px-2 py-1.5 text-xs text-[#303133]" /></label>)}<button onClick={() => { onSceneChange({ ...scene, objects: scene.objects.filter((item) => item.id !== selected.id) }); setSelectedId(""); }} className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-red-200 px-2 py-2 text-xs text-red-600"><Trash2 className="size-3.5" />{isChinese ? "删除物体" : "Delete object"}</button></div>}</aside>
          <div className="relative min-w-0 flex-1 bg-[#edf0f7]"><div ref={host} className="absolute inset-4 overflow-hidden rounded-2xl bg-[#edf2ff] shadow-inner" /><div className="absolute bottom-7 left-1/2 flex max-w-[80%] -translate-x-1/2 gap-2 overflow-x-auto rounded-2xl border border-white/60 bg-white/90 p-2 shadow-lg backdrop-blur">{anchors.map((anchor, index) => <button key={anchor.id} onClick={() => restore(anchor)} className="group flex shrink-0 items-center gap-2 rounded-xl bg-[#f5f1ff] px-3 py-2 text-xs text-[#7c3aed]"><span>{String(index + 1).padStart(2, "0")} · {anchor.name}</span><X onClick={(event) => { event.stopPropagation(); onAnchorsChange(anchors.filter((item) => item.id !== anchor.id)); }} className="size-3 opacity-50 group-hover:opacity-100" /></button>)}{anchors.length === 0 && <span className="px-3 py-2 text-xs text-[#909399]">{isChinese ? "调整镜头后记录机位" : "Frame the shot, then capture a camera"}</span>}</div></div>
          <aside className="w-80 shrink-0 overflow-y-auto border-l border-[#ebeef5] p-4"><div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-[#8b5cf6]" />{isChinese ? "AI 场景搭建" : "AI scene blocking"}</div><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={8} placeholder={isChinese ? "描述场景、人物位置、道具与镜头…" : "Describe the scene, blocking, props, and camera…"} className="mt-3 w-full resize-y rounded-xl border border-[#dcdfe6] p-3 text-xs leading-5 outline-none focus:border-[#8b5cf6]" /><button onClick={() => void generate()} disabled={generating || !prompt.trim()} className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#8b5cf6] px-3 py-2.5 text-xs font-medium text-white disabled:opacity-50">{generating ? <LoaderCircle className="size-4 animate-spin" /> : <Sparkles className="size-4" />}{isChinese ? "生成可编辑场景" : "Generate editable scene"}</button>{error && <p className="mt-2 text-xs text-red-600">{error}</p>}<div className="mt-6 space-y-3 border-t border-[#ebeef5] pt-4"><label className="block text-xs font-medium">{isChinese ? "背景" : "Background"}<input type="color" value={scene.background} onChange={(event) => onSceneChange({ ...scene, background: event.target.value })} className="mt-2 h-9 w-full" /></label><label className="block text-xs font-medium">{isChinese ? "焦距（毫米）" : "Focal length (mm)"}<input type="range" min={6} max={110} value={scene.camera.focal_length} onChange={(event) => onSceneChange({ ...scene, camera: { ...scene.camera, focal_length: Number(event.target.value) } })} className="mt-2 w-full" /><span className="text-[11px] text-[#909399]">{scene.camera.focal_length} mm</span></label><p className="text-[11px] leading-5 text-[#909399]">{isChinese ? "拖动旋转镜头，滚轮缩放，右键平移。场景、物体和机位都会随画布自动保存。" : "Drag to orbit, wheel to zoom, and right-drag to pan. Scene objects and cameras autosave with the canvas."}</p></div></aside>
        </div>
      </section>
    </div>
  );
}
