import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Component, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type MutableRefObject } from 'react';
import * as THREE from 'three';
import { photoDistance, photoGeometry, validateGrid, type DepthGrid } from './geometry';
import { download, type Project, type Settings } from './types';
import PanoramaViewer from './PanoramaViewer';

export type ViewerMethods = { snapshot: () => Promise<void>; glb: () => Promise<void>; video: (onProgress: (value: number) => void) => Promise<void>; cancelRecording: () => void; reset: () => void };
type Motion = { x: number; y: number; hoverX: number; hoverY: number; dragging: boolean; startX: number; startY: number; originX: number; originY: number };
export type Props = { project: Project; settings: Settings; mode: string; locked: boolean; controller: MutableRefObject<ViewerMethods | null>; onError: (message: string) => void; onReady: (ready: boolean) => void; onFps: (fps: number) => void; onZoom: (value: number) => void; onInteract: () => void };

class GraphicsBoundary extends Component<{ children: ReactNode; onError: (s: string) => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { this.props.onError(`3D graphics unavailable: ${error.message}. Original and depth downloads remain available.`); }
  render() { return this.state.failed ? <div className="viewer-message">3D is unavailable on this device. Use Original or Depth.</div> : this.props.children; }
}

function PhotoScene({ project, grid, settings, motion, controller, onReady, onFps }: Pick<Props, 'project' | 'settings' | 'controller' | 'onReady' | 'onFps'> & { grid: DepthGrid; motion: MutableRefObject<Motion> }) {
  const { gl, camera, scene, size } = useThree();
  const [texture, setTexture] = useState<THREE.Texture | null>(null);
  const meshRef = useRef<THREE.Mesh>(null);
  const recording = useRef<{ start: number; cancel: () => void } | null>(null);
  const stats = useRef({ frames: 0, start: performance.now(), total: 0 });
  const distance = photoDistance(project.width / project.height, Math.max(0.1, size.width / size.height));
  const geometry = useMemo(() => photoGeometry(grid, project.width / project.height, settings.strength, { draft: 64, balanced: 128, high: 256 }[settings.quality], distance), [grid, project.width, project.height, settings.strength, settings.quality, distance]);

  useLayoutEffect(() => {
    // Geometry is built along rays from this distance. Apply it immediately on mount/resize,
    // rather than easing from the previous viewport's calibration and cropping the reference photo.
    camera.position.set(0, 0, distance);
    camera.lookAt(0, 0, 0);
  }, [camera, distance]);

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => {
    let active = true;
    const tex = new THREE.TextureLoader().load(project.assets.image, loaded => {
      loaded.colorSpace = THREE.SRGBColorSpace;
      loaded.minFilter = THREE.LinearFilter;
      if (active) setTexture(loaded);
    });
    return () => { active = false; tex.dispose(); };
  }, [project.assets.image]);
  useEffect(() => {
    if (texture) onReady(true);
    return () => onReady(false);
  }, [texture, onReady]);

  useFrame((state, delta) => {
    const time = state.clock.elapsedTime;
    const recordingTime = recording.current ? (performance.now() - recording.current.start) / 1000 : null;
    const orbit = recordingTime !== null || settings.autoOrbit;
    const phase = recordingTime !== null ? recordingTime / 5 * Math.PI * 2 : time * 0.45;
    const x = orbit ? Math.sin(phase) : THREE.MathUtils.clamp(motion.current.x + motion.current.hoverX, -1, 1);
    const y = orbit ? Math.cos(phase) * 0.32 : THREE.MathUtils.clamp(motion.current.y + motion.current.hoverY, -1, 1);
    if (settings.autoOrbit && recordingTime === null) {
      // A manual drag can pick up at the current orbit angle without snapping back to the center.
      motion.current.x = x; motion.current.y = y;
    }
    const yaw = x * THREE.MathUtils.degToRad(20) * settings.motion;
    const pitch = y * THREE.MathUtils.degToRad(12) * settings.motion;
    const target = new THREE.Vector3(Math.sin(yaw) * Math.cos(pitch) * distance, Math.sin(pitch) * distance, Math.cos(yaw) * Math.cos(pitch) * distance);
    camera.position.lerp(target, Math.min(1, delta * 8));
    camera.lookAt(0, 0, 0);
    const perspective = camera as THREE.PerspectiveCamera;
    if (perspective.zoom !== settings.zoom) { perspective.zoom = settings.zoom; perspective.updateProjectionMatrix(); }
    const now = performance.now();
    stats.current.frames++;
    if (now - stats.current.start > 1200) {
      const fps = Math.round(stats.current.frames * 1000 / (now - stats.current.start));
      onFps(fps); stats.current.frames = 0; stats.current.start = now;
    }
  });

  useEffect(() => {
    let cleanupRecording: (() => void) | null = null;
    controller.current = {
      reset: () => { motion.current.x = 0; motion.current.y = 0; motion.current.hoverX = 0; motion.current.hoverY = 0; camera.position.set(0, 0, distance); camera.lookAt(0, 0, 0); },
      snapshot: async () => {
        gl.render(scene, camera);
        const blob = await new Promise<Blob>((resolve, reject) => gl.domElement.toBlob(value => value ? resolve(value) : reject(new Error('Could not capture this frame.')), 'image/png'));
        download(blob, `${project.name}-3d.png`);
      },
      glb: async () => {
        if (!meshRef.current || !texture) throw new Error('Wait for the photo to load.');
        const { GLTFExporter } = await import('three/examples/jsm/exporters/GLTFExporter.js');
        const mesh = meshRef.current.clone();
        mesh.userData = { representation: 'relative-depth-photo-mesh', note: 'Not a complete reconstructed scene; arbitrary units.', settings };
        const output = await new GLTFExporter().parseAsync(mesh, { binary: true });
        if (!(output instanceof ArrayBuffer)) throw new Error('GLB encoding failed.');
        download(new Blob([output], { type: 'model/gltf-binary' }), `${project.name}.glb`);
      },
      video: async onProgress => {
        if (recording.current) throw new Error('A recording is already running.');
        if (!window.MediaRecorder) throw new Error('Video recording is unavailable in this browser. Export a still or GLB.');
        const mime = ['video/webm;codecs=vp8', 'video/webm;codecs=vp9', 'video/webm', 'video/mp4'].find(value => MediaRecorder.isTypeSupported(value));
        if (!mime) throw new Error('This browser has no supported recording format. Try Chrome or Edge.');
        const output = document.createElement('canvas'); output.width = 1280; output.height = 720;
        const context = output.getContext('2d');
        if (!context || !output.captureStream) throw new Error('Canvas recording is unavailable.');
        const previousPixelRatio = gl.getPixelRatio();
        gl.setPixelRatio(1);
        const stream = output.captureStream(30);
        const recorder = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 6000000 });
        const chunks: Blob[] = [];
        await new Promise<void>((resolve, reject) => {
          let frame = 0, stopped = false, cancelled = false;
          let timer: ReturnType<typeof setTimeout>;
          const reset = () => { cancelAnimationFrame(frame); clearTimeout(timer); stream.getTracks().forEach(track => track.stop()); gl.setPixelRatio(previousPixelRatio); recording.current = null; cleanupRecording = null; };
          const stop = () => { if (!stopped) { stopped = true; if (recorder.state !== 'inactive') recorder.stop(); } };
          const cancel = () => { cancelled = true; stop(); };
          recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
          recorder.onerror = () => { reset(); reject(new Error('The browser could not encode this video. Try a still export.')); };
          recorder.onstop = () => {
            reset();
            if (cancelled) { reject(new Error('Recording cancelled.')); return; }
            const blob = new Blob(chunks, { type: mime });
            if (!blob.size) { reject(new Error('The recording was empty. Keep the tab visible and retry.')); return; }
            download(blob, `${project.name}-orbit.${mime.includes('mp4') ? 'mp4' : 'webm'}`);
            resolve();
          };
          recording.current = { start: performance.now(), cancel };
          cleanupRecording = cancel;
          const draw = () => {
            if (stopped) return;
            // R3F has already rendered the frame. Rendering again halves software-renderer throughput.
            context.fillStyle = '#111'; context.fillRect(0, 0, 1280, 720);
            const ratio = Math.min(1280 / gl.domElement.width, 720 / gl.domElement.height);
            const w = gl.domElement.width * ratio, h = gl.domElement.height * ratio;
            context.drawImage(gl.domElement, (1280 - w) / 2, (720 - h) / 2, w, h);
            onProgress(Math.min(100, (performance.now() - recording.current!.start) / 50));
            frame = requestAnimationFrame(draw);
          };
          recorder.start(100); draw(); timer = setTimeout(stop, 5000);
        });
      },
      cancelRecording: () => recording.current?.cancel(),
    };
    return () => { cleanupRecording?.(); controller.current = null; };
  }, [gl, camera, scene, project.name, settings, texture, distance, controller, motion]);

  return texture ? <mesh ref={meshRef} geometry={geometry}><meshBasicMaterial map={texture} side={THREE.DoubleSide} toneMapped={false} /></mesh> : null;
}

export default function Viewer(props: Props) {
  return props.mode === 'panorama' && props.project.panorama ? <PanoramaViewer {...props} /> : <PhotoViewer {...props} />;
}

function PhotoViewer(props: Props) {
  const { project, mode, settings, onError, onZoom } = props;
  const [grid, setGrid] = useState<DepthGrid | null>(null);
  const [gridError, setGridError] = useState('');
  const motion = useRef<Motion>({ x: 0, y: 0, hoverX: 0, hoverY: 0, dragging: false, startX: 0, startY: 0, originX: 0, originY: 0 });
  useEffect(() => {
    const abort = new AbortController();
    setGrid(null); setGridError('');
    if (project.depth) {
      const depth = project.depth;
      fetch(depth.assets.grid, { signal: abort.signal }).then(async response => { if (!response.ok) throw new Error('Depth could not be loaded. Regenerate this result.'); return response.arrayBuffer(); }).then(buffer => setGrid(validateGrid(buffer, depth.grid_width, depth.grid_height))).catch(error => { if (error.name !== 'AbortError') { setGridError(error.message); onError(error.message); } });
    }
    return () => abort.abort();
  }, [project.depth?.job_id, onError]);

  return <div className="photo-stage" data-testid="photo-stage" tabIndex={mode === '3d' ? 0 : -1} style={{ touchAction: mode === '3d' ? 'none' : 'pan-y' }} aria-label="Interactive 3D photo. Drag to rotate and hold the angle. Arrow keys adjust it; Home resets the camera."
    onPointerDownCapture={event => {
      if (mode !== '3d' || props.locked || !project.depth || event.button !== 0 || !event.isPrimary) return;
      props.onInteract();
      event.preventDefault(); event.currentTarget.focus();
      Object.assign(motion.current, { dragging: true, startX: event.clientX, startY: event.clientY, originX: motion.current.x, originY: motion.current.y, hoverX: 0, hoverY: 0 });
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerUpCapture={event => { motion.current.dragging = false; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
    onPointerCancel={() => { motion.current.dragging = false; }}
    onLostPointerCapture={() => { motion.current.dragging = false; }}
    onPointerMoveCapture={event => {
      if (mode !== '3d' || props.locked) return;
      const rect = event.currentTarget.getBoundingClientRect();
      if (motion.current.dragging) {
        motion.current.x = THREE.MathUtils.clamp(motion.current.originX + (event.clientX - motion.current.startX) / rect.width * 3, -1, 1);
        motion.current.y = THREE.MathUtils.clamp(motion.current.originY - (event.clientY - motion.current.startY) / rect.height * 3, -1, 1);
      } else if (event.pointerType === 'mouse') {
        motion.current.hoverX = ((event.clientX - rect.left) / rect.width * 2 - 1) * .08;
        motion.current.hoverY = -((event.clientY - rect.top) / rect.height * 2 - 1) * .08;
      }
    }}
    onPointerLeave={() => { motion.current.hoverX = 0; motion.current.hoverY = 0; }}
    onWheel={event => { if (mode === '3d' && !props.locked && event.ctrlKey) { event.preventDefault(); onZoom(Math.max(0.7, Math.min(2, settings.zoom - event.deltaY * 0.001))); } }}
    onKeyDown={event => {
      if (mode !== '3d' || props.locked) return;
      const keys: Record<string, () => void> = { ArrowLeft: () => { motion.current.x = Math.max(-1, motion.current.x - 0.2); }, ArrowRight: () => { motion.current.x = Math.min(1, motion.current.x + 0.2); }, ArrowUp: () => { motion.current.y = Math.min(1, motion.current.y + 0.2); }, ArrowDown: () => { motion.current.y = Math.max(-1, motion.current.y - 0.2); }, Home: () => props.controller.current?.reset() };
      if (keys[event.key]) { event.preventDefault(); props.onInteract(); motion.current.hoverX = 0; motion.current.hoverY = 0; keys[event.key](); }
    }}>
    {project.depth && grid && <div className="canvas-layer" style={{ visibility: mode === '3d' ? 'visible' : 'hidden' }}><GraphicsBoundary onError={onError}><Canvas camera={{ fov: 40, position: [0, 0, 6], near: 0.01, far: 100 }} dpr={[1, settings.quality === 'high' ? 2 : 1.5]} gl={{ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' }} onCreated={({ gl }) => { gl.setClearColor('#111111'); gl.domElement.addEventListener('webglcontextlost', () => onError('Graphics context lost. Reload the project or use Original.'), { once: true }); }}><PhotoScene {...props} grid={grid} motion={motion} /></Canvas></GraphicsBoundary></div>}
    {(mode !== '3d' || !project.depth) && <img className="stage-image" src={mode === 'depth' && project.depth ? project.depth.assets.preview : project.assets.image} alt={mode === 'depth' ? 'Relative depth map, light areas are nearer' : project.name} />}
    {mode === '3d' && project.depth && !grid && <div className="viewer-message">{gridError || 'Loading depth scene…'}</div>}
  </div>;
}
