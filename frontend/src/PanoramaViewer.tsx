import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Component, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import * as THREE from 'three';
import { download } from './types';
import type { Props } from './Viewer';

type Angles = { yaw: number; pitch: number };
const clampPitch = (value: number) => Math.max(-89, Math.min(89, value));
const heading = (value: number) => ((value % 360) + 360) % 360;

class Boundary extends Component<{ children: ReactNode; onError: (s: string) => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onError('360° graphics could not start. Reload the page or download the panorama.'); }
  render() { return this.state.failed ? <div className="viewer-message">360° graphics unavailable. The panorama download is still available.</div> : this.props.children; }
}

function Scene({ angles, report, ...props }: Props & { angles: MutableRefObject<Angles>; report: (a: Angles) => void }) {
  const { gl, camera, scene } = useThree();
  const [texture, setTexture] = useState<THREE.Texture | null>(null);
  const stats = useRef({ start: performance.now(), frames: 0, report: 0 });
  // Bake the inversion into the geometry. A negative mesh transform also flips
  // WebGL's front-face test, leaving the sphere culled from inside.
  const geometry = useMemo(() => new THREE.SphereGeometry(50, 96, 64).scale(-1, 1, 1), []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const url = props.project.panorama!.assets.panorama;
  useEffect(() => {
    let active = true;
    const tex = new THREE.TextureLoader().load(url, loaded => {
      loaded.colorSpace = THREE.SRGBColorSpace;
      loaded.wrapS = THREE.RepeatWrapping;
      loaded.minFilter = THREE.LinearFilter;
      if (active) setTexture(loaded);
    }, undefined, () => props.onError('The panorama image could not be loaded. Try reopening this project.'));
    return () => { active = false; tex.dispose(); };
  }, [url, props.onError]);
  useEffect(() => { props.onReady(Boolean(texture)); return () => props.onReady(false); }, [texture, props.onReady]);
  useEffect(() => {
    props.controller.current = {
      reset: () => { angles.current = { yaw: 0, pitch: 0 }; report(angles.current); },
      snapshot: async () => {
        gl.render(scene, camera);
        const blob = await new Promise<Blob>((resolve, reject) => gl.domElement.toBlob(value => value ? resolve(value) : reject(new Error('Image export failed.')), 'image/png'));
        download(blob, `${props.project.name}-360-view.png`);
      },
      glb: async () => { throw new Error('A panorama is a spherical image. Download the panorama image instead.'); },
      video: async () => { throw new Error('Use the panorama image or a still export for this view.'); },
      cancelRecording: () => {},
    };
    return () => { props.controller.current = null; };
  }, [gl, scene, camera, props.controller, props.project.name, angles, report]);
  useFrame((_, delta) => {
    if (props.settings.autoOrbit) angles.current.yaw = heading(angles.current.yaw + delta * 8);
    const yaw = THREE.MathUtils.degToRad(angles.current.yaw), pitch = THREE.MathUtils.degToRad(angles.current.pitch);
    camera.position.set(0, 0, 0);
    camera.lookAt(Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), -Math.cos(yaw) * Math.cos(pitch));
    const perspective = camera as THREE.PerspectiveCamera;
    const fov = THREE.MathUtils.clamp(75 / props.settings.zoom, 35, 105);
    if (perspective.fov !== fov) { perspective.fov = fov; perspective.updateProjectionMatrix(); }
    stats.current.frames++;
    const now = performance.now();
    if (now - stats.current.report > 100) { report({ ...angles.current }); stats.current.report = now; }
    if (now - stats.current.start > 1000) {
      props.onFps(Math.round(stats.current.frames * 1000 / (now - stats.current.start)));
      stats.current.frames = 0; stats.current.start = now;
    }
  });
  return texture ? <mesh geometry={geometry} rotation={[0, -Math.PI / 2, 0]}><meshBasicMaterial map={texture} toneMapped={false} /></mesh> : null;
}

export default function PanoramaViewer(props: Props) {
  const angles = useRef<Angles>({ yaw: 0, pitch: 0 });
  const drag = useRef({ active: false, x: 0, y: 0, yaw: 0, pitch: 0 });
  const [readout, setReadout] = useState<Angles>(angles.current);
  return <div className="photo-stage panorama-stage" data-testid="panorama-stage" tabIndex={0} aria-label="360 degree environment. Drag to look all around. Arrow keys turn; Home resets."
    onPointerDownCapture={event => {
      if (props.locked || event.button !== 0 || !event.isPrimary) return;
      props.onInteract(); event.preventDefault(); event.currentTarget.focus();
      drag.current = { active: true, x: event.clientX, y: event.clientY, ...angles.current };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMoveCapture={event => {
      if (!drag.current.active || props.locked) return;
      const width = event.currentTarget.getBoundingClientRect().width;
      // One viewport-width swipe turns 180°. Horizontal motion has no angular limit.
      angles.current = { yaw: heading(drag.current.yaw - (event.clientX - drag.current.x) / width * 180), pitch: clampPitch(drag.current.pitch + (event.clientY - drag.current.y) / width * 180) };
    }}
    onPointerUpCapture={event => { drag.current.active = false; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
    onPointerCancel={() => { drag.current.active = false; }} onLostPointerCapture={() => { drag.current.active = false; }}
    onKeyDown={event => {
      if (props.locked || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home'].includes(event.key)) return;
      event.preventDefault(); props.onInteract();
      if (event.key === 'Home') props.controller.current?.reset();
      if (event.key === 'ArrowLeft') angles.current.yaw = heading(angles.current.yaw - 15);
      if (event.key === 'ArrowRight') angles.current.yaw = heading(angles.current.yaw + 15);
      if (event.key === 'ArrowUp') angles.current.pitch = clampPitch(angles.current.pitch + 15);
      if (event.key === 'ArrowDown') angles.current.pitch = clampPitch(angles.current.pitch - 15);
    }}>
    <Boundary onError={props.onError}><Canvas camera={{ fov: 75, position: [0, 0, 0], near: .1, far: 100 }} dpr={[1, 1.5]} gl={{ antialias: true, preserveDrawingBuffer: true }} onCreated={({ gl }) => { gl.domElement.addEventListener('webglcontextlost', () => props.onError('Graphics context lost. Reload this project.'), { once: true }); }}><Scene {...props} angles={angles} report={setReadout} /></Canvas></Boundary>
    <output className="panorama-heading" data-testid="panorama-heading" data-yaw={readout.yaw.toFixed(1)} data-pitch={readout.pitch.toFixed(1)}>{Math.round(readout.yaw) % 360}° around · {Math.round(readout.pitch)}° tilt</output>
  </div>;
}
