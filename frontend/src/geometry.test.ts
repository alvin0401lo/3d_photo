import { describe, it, expect } from 'vitest';
import { photoDistance, photoGeometry, sample, validateGrid } from './geometry';

const grid = { data: new Float32Array([0, 0.25, 0.75, 1]), width: 2, height: 2 };

describe('photo geometry and asset validation', () => {
  it('samples asymmetric depth with top-left row origin and bilinear interpolation', () => {
    expect(sample(grid, 0, 0)).toBe(0);
    expect(sample(grid, 1, 1)).toBe(1);
    expect(sample(grid, 0.5, 0.5)).toBe(0.5);
    expect(sample(grid, -5, 5)).toBe(0.75);
  });
  it('keeps the reference perspective projection identical at any depth strength', () => {
    const distance = photoDistance(1.6, 1.8);
    const geometry = photoGeometry(grid, 1.6, 0.8, 1, distance);
    const positions = geometry.getAttribute('position');
    expect(positions.getZ(0)).toBeLessThan(0);
    expect(positions.getZ(3)).toBeGreaterThan(0);
    for (let index = 0; index < positions.count; index++) {
      const projection = distance / (distance - positions.getZ(index));
      expect(positions.getX(index) * projection).toBeCloseTo(index % 2 ? 1.6 : -1.6, 5);
      expect(positions.getY(index) * projection).toBeCloseTo(index < 2 ? 1 : -1, 5);
    }
    geometry.dispose();
  });
  it('returns a flat, aspect-correct photo at zero strength', () => {
    const geometry = photoGeometry(grid, 2, 0, 2, 4);
    const positions = geometry.getAttribute('position');
    for (let index = 0; index < positions.count; index++) expect(Math.abs(positions.getZ(index))).toBe(0);
    expect(positions.getX(0)).toBe(-2);
    expect(positions.getY(0)).toBe(1);
    geometry.dispose();
  });
  it('fits portrait and landscape into different viewport aspects', () => {
    expect(photoDistance(2, 1)).toBeGreaterThan(photoDistance(1, 1));
    expect(photoDistance(1, 0.5)).toBeGreaterThan(photoDistance(1, 2));
  });
  it('rejects truncated, nonfinite and out-of-range browser assets', () => {
    expect(() => validateGrid(new ArrayBuffer(4), 2, 2)).toThrow();
    expect(() => validateGrid(new Float32Array([0, NaN, 0, 1]).buffer, 2, 2)).toThrow();
    expect(() => validateGrid(new Float32Array([0, 2, 0, 1]).buffer, 2, 2)).toThrow();
    expect(validateGrid(grid.data.buffer, 2, 2).data[3]).toBe(1);
  });
});
