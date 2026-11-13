import * as THREE from 'three';

export type DepthGrid = { data: Float32Array; width: number; height: number };

export function sample(grid: DepthGrid, u: number, v: number): number {
  const x = Math.max(0, Math.min(grid.width - 1, u * (grid.width - 1)));
  const y = Math.max(0, Math.min(grid.height - 1, v * (grid.height - 1)));
  const x0 = Math.floor(x), y0 = Math.floor(y);
  const x1 = Math.min(x0 + 1, grid.width - 1), y1 = Math.min(y0 + 1, grid.height - 1);
  const a = x - x0, b = y - y0;
  return (1 - b) * ((1 - a) * grid.data[y0 * grid.width + x0] + a * grid.data[y0 * grid.width + x1]) + b * ((1 - a) * grid.data[y1 * grid.width + x0] + a * grid.data[y1 * grid.width + x1]);
}

export function photoDistance(aspect: number, viewportAspect: number) {
  return Math.max(1 / Math.tan(Math.PI / 9), aspect / (Math.tan(Math.PI / 9) * viewportAspect)) * 1.08;
}

export function photoGeometry(grid: DepthGrid, aspect: number, strength: number, segments: number, distance: number) {
  const geometry = new THREE.PlaneGeometry(2 * aspect, 2, segments, segments);
  const positions = geometry.getAttribute('position');
  const uv = geometry.getAttribute('uv');
  for (let index = 0; index < positions.count; index++) {
    // Grid rows run top-to-bottom; plane UVs run bottom-to-top.
    const z = (sample(grid, uv.getX(index), 1 - uv.getY(index)) - 0.5) * strength * 0.9;
    const rayScale = (distance - z) / distance;
    positions.setXYZ(index, positions.getX(index) * rayScale, positions.getY(index) * rayScale, z);
  }
  positions.needsUpdate = true;
  geometry.computeBoundingSphere();
  return geometry;
}

export function validateGrid(buffer: ArrayBuffer, width: number, height: number): DepthGrid {
  if (width < 2 || height < 2 || buffer.byteLength !== width * height * 4) throw new Error('The depth asset is incomplete. Regenerate depth.');
  const data = new Float32Array(buffer);
  if (data.some(value => !Number.isFinite(value) || value < 0 || value > 1)) throw new Error('The depth asset contains invalid values.');
  return { data, width, height };
}
