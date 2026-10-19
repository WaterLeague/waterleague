import { expect, test } from 'vitest';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import type { SurfaceFrame } from '../../surface/entity/surface';
import { streetGeometry } from './streetGeometryService';
import { surfaceGeometry } from '../../surface/service/surfaceGeometry';
import { tracePositions } from '../../floodtrace/service/traceGeometryService';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';

const road: Street = {
  id: 'test-road',
  class: 'residential',
  districtId: '1',
  widthM: 8,
  widthSource: 'OSM_WIDTH_TAG',
  walk: false,
  motor: true,
  oneway: 1,
  sidewalk: 'both',
  bridge: false,
  coordinates: [
    [1, 5],
    [19, 15],
  ],
};
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
test.each([null, terrain])(
  '지형 굴곡과 관계없이 도로·인도·차선이 최소 계산 수면 및 과거 흔적보다 아래',
  (ground) => {
    const streets = streetGeometry([road], ground, true);
    for (let i = 0; i < streets.positions.length; i += 3) {
      const base = terrainMeshHeight(ground, [streets.positions[i], -streets.positions[i + 2]]);
      expect(streets.positions[i + 1] - base).toBeGreaterThan(0);
      expect(streets.positions[i + 1] - base).toBeLessThan(0.016);
    }
    const vertices: [[number, number], [number, number], [number, number]] = [
      [0, 0],
      [20, 0],
      [0, 20],
    ];
    const frame = {
      cells: [{ triangleId: 0, vertices, depthM: 0.00001, speedMps: 0, flowDirection: null }],
    } as SurfaceFrame;
    const water = surfaceGeometry(frame, 'depth', ground);
    for (let i = 0; i < water.positions.length; i += 3)
      if (water.faces[i / 3] === 1) {
        const base = terrainMeshHeight(ground, [water.positions[i], -water.positions[i + 2]]);
        expect(water.positions[i + 1] - base).toBeGreaterThan(0.0199);
        expect(water.depths[i / 3]).toBeCloseTo(0.00001, 8);
      }
    const traces = tracePositions([{ triangleVertices: vertices.flat() }], ground);
    for (let i = 0; i < traces.length; i += 3)
      expect(traces[i + 1] - terrainMeshHeight(ground, [traces[i], -traces[i + 2]])).toBeCloseTo(
        0.016,
        5
      );
  }
);
test('교량 표시 높이와 원 도로 좌표 유지', () => {
  const before = JSON.stringify(road),
    bridge = streetGeometry([{ ...road, bridge: true }], null, true);
  for (let i = 1; i < bridge.positions.length; i += 3)
    expect(bridge.positions[i]).toBeGreaterThanOrEqual(3);
  expect(JSON.stringify(road)).toBe(before);
});
