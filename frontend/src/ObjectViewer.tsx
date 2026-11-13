import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Component, useEffect, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Camera, RotateCcw } from 'lucide-react';
import { download, type ObjectResult } from './types';

type Methods = { reset: () => void; turn: (x: number, y: number) => void; snapshot: () => void };
class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <p className="viewer-message">3D graphics unavailable. Download the GLB to view it in another application.</p> : this.props.children; }
}

function Scene({ result, automatic, onManual, onReady, onReadout, onError, methods }: { result: ObjectResult; automatic: boolean; onManual: () => void; onReady: (value: boolean) => void; onReadout: (value: string) => void; onError: (value: string) => void; methods: MutableRefObject<Methods | null> }) {
  const { gl, scene, camera, size } = useThree();
  const [model, setModel] = useState<THREE.Group | null>(null);
  const controls = useRef<OrbitControls | null>(null);
  const frames = useRef(0);
  useEffect(() => {
    const abort = new AbortController(); let active = true; let group: THREE.Group | null = null;
    onReady(false);
    fetch(result.assets.object_model, { signal: abort.signal }).then(async response => {
      if (!response.ok) throw new Error('The model could not be loaded.');
      return new GLTFLoader().parseAsync(await response.arrayBuffer(), '');
    }).then(gltf => {
      group = new THREE.Group(); group.add(gltf.scene); group.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(group), dimension = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
      const longest = Math.max(dimension.x, dimension.y, dimension.z);
      if (!Number.isFinite(longest) || longest <= 0) throw new Error('This model has no visible geometry.');
      const scale = 2.4 / longest; group.scale.setScalar(scale); group.position.copy(center).multiplyScalar(-scale);
      if (active) { setModel(group); onReady(true); }
      else dispose(group);
    }).catch(error => { if (active && error.name !== 'AbortError') onError(error.message); });
    return () => { active = false; abort.abort(); if (group) dispose(group); onReady(false); };
  }, [result.job_id, result.assets.object_model, onError, onReady]);
  useEffect(() => {
    const orbit = new OrbitControls(camera, gl.domElement);
    orbit.enablePan = false; orbit.enableDamping = false; orbit.minDistance = 1.5; orbit.maxDistance = 12;
    orbit.minPolarAngle = .05; orbit.maxPolarAngle = Math.PI - .05; orbit.autoRotateSpeed = 1;
    orbit.addEventListener('start', onManual); controls.current = orbit;
    const initialDistance = Math.max(4.8, 3.6 / Math.max(.35, size.width / size.height));
    const reset = () => { camera.position.set(0, 0, initialDistance); orbit.target.set(0, 0, 0); orbit.update(); };
    reset();
    methods.current = {
      reset,
      turn: (x, y) => {
        const spherical = new THREE.Spherical().setFromVector3(camera.position.clone().sub(orbit.target));
        spherical.theta += THREE.MathUtils.degToRad(x); spherical.phi = THREE.MathUtils.clamp(spherical.phi + THREE.MathUtils.degToRad(y), .05, Math.PI - .05);
        camera.position.copy(new THREE.Vector3().setFromSpherical(spherical).add(orbit.target)); orbit.update();
      },
      snapshot: () => { gl.render(scene, camera); gl.domElement.toBlob(blob => { if (blob) download(blob, 'object-360-view.png'); else onError('Still export failed.'); }, 'image/png'); },
    };
    return () => { orbit.dispose(); controls.current = null; methods.current = null; };
  }, [camera, gl, scene, size.width, size.height, onManual, onError, methods]);
  useFrame((_, delta) => {
    if (controls.current) {
      controls.current.autoRotate = automatic; controls.current.update(delta);
      if (++frames.current % 6 === 0) onReadout(`${Math.round((THREE.MathUtils.radToDeg(controls.current.getAzimuthalAngle()) + 360) % 360) % 360}° around`);
    }
  });
  return <><ambientLight intensity={1.6} /><directionalLight position={[3, 5, 4]} intensity={2.5} /><directionalLight position={[-3, 2, -3]} intensity={1.5} />{model && <primitive object={model} />}</>;
}

function dispose(group: THREE.Object3D) {
  const textures = new Set<THREE.Texture>();
  group.traverse(object => {
    const mesh = object as THREE.Mesh;
    mesh.geometry?.dispose();
    if (mesh.material) for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      for (const value of Object.values(material)) if (value instanceof THREE.Texture) textures.add(value);
      material.dispose();
    }
    if ((object as THREE.SkinnedMesh).isSkinnedMesh) (object as THREE.SkinnedMesh).skeleton?.dispose();
  });
  textures.forEach(texture => texture.dispose());
}

export default function ObjectViewer({ result, onError }: { result: ObjectResult; onError: (message: string) => void }) {
  const [automatic, setAutomatic] = useState(false), [ready, setReady] = useState(false), [readout, setReadout] = useState('0° around');
  const methods = useRef<Methods | null>(null);
  // State setter identity is stable; the scene controls must not reset on each readout update.
  const onManual = useRef(() => setAutomatic(false)).current;
  return <div className="object-viewer">
    <div className="object-canvas" data-testid="object-stage" tabIndex={0} aria-label="3D object. Drag to orbit around the person. Arrow keys rotate; Home resets."
      onPointerDownCapture={event => event.currentTarget.focus()}
      onKeyDown={event => { const angles: Record<string, [number, number]> = { ArrowLeft: [-15, 0], ArrowRight: [15, 0], ArrowUp: [0, -15], ArrowDown: [0, 15] }; if (event.key === 'Home' || angles[event.key]) { event.preventDefault(); setAutomatic(false); if (event.key === 'Home') methods.current?.reset(); else methods.current?.turn(...angles[event.key]); } }}>
      <Boundary><Canvas camera={{ fov: 40, position: [0, 0, 5], near: .01, far: 100 }} gl={{ preserveDrawingBuffer: true, antialias: true }} dpr={[1, 1.5]}><Scene result={result} automatic={automatic} onManual={onManual} onReady={setReady} onReadout={setReadout} onError={onError} methods={methods} /></Canvas></Boundary>
      <output className="panorama-heading" data-testid="object-heading">{readout}</output>
    </div>
    <div className="object-viewer-toolbar"><span>{ready ? 'Drag to orbit · scroll or pinch to zoom' : 'Loading 3D model…'}</span><button className="icon-button" aria-label="Reset object camera" disabled={!ready} onClick={() => { setAutomatic(false); methods.current?.reset(); }}><RotateCcw size={16} /></button><button className="icon-button" aria-label="Save object still" disabled={!ready} onClick={() => methods.current?.snapshot()}><Camera size={16} /></button></div>
    <label className="consent-field"><input type="checkbox" role="switch" aria-label="Auto rotate object" checked={automatic} onChange={e => setAutomatic(e.target.checked)} disabled={!ready} />Auto rotate</label>
  </div>;
}
