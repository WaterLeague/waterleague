import { expect, test } from 'vitest';
import type { SurfaceCatalog, SurfaceFrame } from '../entity/surface';
import { assertSurfaceBinding, surfaceBounds, surfaceFrameIndex } from './surfaceService';
import { surfaceGeometry, surfacePlanPaths } from './surfaceGeometry';
const catalog: SurfaceCatalog = {
  schemaVersion: 1,
  catalogSha256: 'a'.repeat(64),
  surfaceResultSha256: 'b'.repeat(64),
  classification: 'TEST_ONLY',
  startUtc: '2022-08-08T09:00:00Z',
  coordinateSystem: 'EPSG:5186',
  originProjected: [198128, 551989],
  verticalPlacement: 'TERRAIN_DRAPED_SCALAR_NOT_WATER_ELEVATION',
  triangleCount: 2,
  timesSeconds: [0, 1, 5.000000000000002],
  limitations: [],
};
const frame: SurfaceFrame = {
  catalogSha256: catalog.catalogSha256,
  sourceSha256: 'c'.repeat(64),
  index: 1,
  timeSeconds: 1,
  wholeDomainStorageM3: 0.5,
  cells: [
    {
      triangleId: 0,
      vertices: [
        [0, 0],
        [1, 0],
        [0, 1],
      ],
      depthM: 0.25,
      speedMps: 0.8,
    },
    {
      triangleId: 1,
      vertices: [
        [10, 10],
        [11, 10],
        [10, 11],
      ],
      depthM: 0,
      speedMps: 0,
    },
  ],
};
test('실제 저장 프레임만 선택하며 시계 반올림 외 외삽 금지', () => {
  expect(surfaceFrameIndex(catalog, '2022-08-08T09:00:02.500Z')).toBe(1);
  expect(surfaceFrameIndex(catalog, '2022-08-08T09:00:05Z')).toBe(2);
  expect(surfaceFrameIndex(catalog, '2022-08-08T09:00:05.001Z')).toBe(null);
  expect(surfaceFrameIndex(catalog, '2022-08-08T08:59:59Z')).toBe(null);
});
test('계산·시각·격자 연결이 다른 응답 거부', () => {
  expect(assertSurfaceBinding(catalog, frame, 1)).toBe(frame);
  expect(() =>
    assertSurfaceBinding(catalog, { ...frame, catalogSha256: 'd'.repeat(64) }, 1)
  ).toThrow();
  expect(() => assertSurfaceBinding(catalog, frame, 2)).toThrow();
  expect(() =>
    assertSurfaceBinding(catalog, { ...frame, cells: [{ ...frame.cells[0], triangleId: 2 }] }, 1)
  ).toThrow();
});
test('2D·3D 같은 젖은 격자와 좌표 표시, 원값과 수면 표고 불변', () => {
  const before = JSON.stringify(frame),
    geometry = surfaceGeometry(frame, 'depth', null);
  expect([...geometry.positions]).toEqual([
    0,
    expect.closeTo(0.4),
    expect.closeTo(0),
    1,
    expect.closeTo(0.4),
    expect.closeTo(0),
    0,
    expect.closeTo(0.4),
    -1,
  ]);
  const paths = surfacePlanPaths(frame, 'depth');
  expect(paths).toHaveLength(1);
  expect(paths[0].path).toBe('M0,0L1,0L0,-1Z');
  expect(surfacePlanPaths(frame, 'speed')[0].color).not.toBe(paths[0].color);
  expect(JSON.stringify(frame)).toBe(before);
});
test('화면 범위는 표시 선택에만 사용하고 서울 경계 내 제한', () => {
  const bounds = surfaceBounds({ center: [10, 20], distance: 50000 });
  expect(bounds).toEqual([-60000, -60000, 60000, 60000]);
});
