import { expect, test } from 'vitest';
import { pavementGeometry } from './pavementGeometryService';
import { placementFootprint } from './facilityGeometryService';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import type { Terrain } from '../../terrain/entity/terrain';

test('도로 투수포장 면적 보존과 경사면 부착·얕은 침수 아래 표시', () => {
  const terrain: Terrain = {
    width: 3,
    height: 3,
    origin: [0, 20],
    spacing: [10, -10],
    heights: new Float32Array([0, 12, 0, 0, 0, 10, 5, 0, 0]),
    cover: new Uint8Array(9),
    districts: new Uint8Array(9),
    districtIds: [],
  };
  const cell = {
    coordinates: [
      [1, 19],
      [19, 19],
      [19, 17],
      [1, 17],
      [1, 19],
    ] as [number, number][],
    areaM2: 36,
    heightM: 0,
  };
  const footprint = placementFootprint(cell, {
    cellId: 'ROAD',
    facilityType: 'PERMEABLE_PAVEMENT',
    areaM2: 20,
  });
  const geometry = pavementGeometry(footprint, terrain);
  const positions = geometry.surface.getAttribute('position');
  let area = 0;
  for (let i = 0; i < positions.count; i += 3) {
    const triangle = [i, i + 1, i + 2].map(
      (index) => [positions.getX(index), -positions.getZ(index)] as const
    );
    const height = [i, i + 1, i + 2].reduce((n, index) => n + positions.getY(index), 0) / 3;
    const center: [number, number] = [
      triangle.reduce((n, p) => n + p[0], 0) / 3,
      triangle.reduce((n, p) => n + p[1], 0) / 3,
    ];
    expect(height - terrainMeshHeight(terrain, center)).toBeCloseTo(0.014, 5);
    expect(height).toBeLessThan(terrainMeshHeight(terrain, center) + 0.016);
    const [a, b, c] = triangle;
    area += Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2;
  }
  expect(area).toBeCloseTo(20, 4);
  Object.values(geometry).forEach((g) => g.dispose());
});
