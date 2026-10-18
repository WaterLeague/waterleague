import { expect, test } from 'vitest';
import type { SurfaceCatalog, SurfaceFrame } from '../entity/surface';
import {
  assertSurfaceBinding,
  surfaceBounds,
  surfaceFrameIndex,
  liveSurfaceFrameIndex,
} from './surfaceService';
import { surfaceGeometry, surfacePlanPaths } from './surfaceGeometry';
import {
  surfaceDirections,
  surfaceDirectionPaths,
  maximumDirectionGlyphs,
  arrowTriangles,
} from './surfaceDirections';
import { surfaceFrameDto, surfaceCatalogDto } from '../dto/surfaceDto';
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
test('현재 침수 표시에서 오래된 재해 프레임·미래 프레임 제외', () => {
  const start = Date.parse(catalog.startUtc);
  expect(liveSurfaceFrameIndex(catalog, start - 1)).toBeNull();
  expect(liveSurfaceFrameIndex(catalog, start + 2500)).toBe(1);
  expect(liveSurfaceFrameIndex(catalog, start + 5000)).toBe(2);
  expect(liveSurfaceFrameIndex(catalog, start + 305000)).toBe(2);
  expect(liveSurfaceFrameIndex(catalog, start + 305001)).toBeNull();
  expect(liveSurfaceFrameIndex(catalog, Date.parse('2026-10-18T09:00:00Z'))).toBeNull();
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

test('정지·건조·이전 기록 방향 제외와 비정규 방향 응답 거부', () => {
  expect(surfaceDirections(frame)).toEqual([]);
  const current = {
    ...catalog,
    schemaVersion: 2 as const,
    flowDirectionMethod: 'SOURCE_MOMENTUM_LOCAL_PROJECTION_JACOBIAN_V1' as const,
  };
  expect(surfaceCatalogDto.safeParse(current).success).toBe(true);
  expect(surfaceCatalogDto.safeParse({ ...current, flowDirectionMethod: undefined }).success).toBe(
    false
  );
  expect(() => assertSurfaceBinding(current, frame, 1)).toThrow();
  for (const value of [
    [0, 0],
    [2, 0],
    [Infinity, 0],
  ]) {
    expect(
      surfaceFrameDto.safeParse({ ...frame, cells: [{ ...frame.cells[0], flowDirection: value }] })
        .success
    ).toBe(false);
  }
  expect(
    surfaceFrameDto.safeParse({ ...frame, cells: [{ ...frame.cells[1], flowDirection: [1, 0] }] })
      .success
  ).toBe(false);
});

test('2D·3D 화살표의 동서남북 방향 일치와 원 속력 불변', () => {
  for (const direction of [
    [1, 0],
    [0, 1],
    [-1, 0],
    [0, -1],
  ] as [number, number][]) {
    const value: SurfaceFrame = {
      ...frame,
      cells: [{ ...frame.cells[0], flowDirection: direction }],
    };
    const before = JSON.stringify(value),
      arrows = surfaceDirections(value);
    expect(arrows).toHaveLength(1);
    const center = [1 / 3, 1 / 3],
      tip = arrows[0].points[5];
    expect(
      (tip[0] - center[0]) * direction[0] + (tip[1] - center[1]) * direction[1]
    ).toBeGreaterThan(0);
    expect(surfaceDirectionPaths(value)[0].path).toContain(`${tip[0]},${-tip[1]}`);
    const geometry = surfaceGeometry(value, 'speed', null);
    const expected = arrowTriangles.flat().flatMap((i) => {
      const p = arrows[0].points[i];
      return [p[0], 0.5, -p[1]];
    });
    expect([...geometry.positions.slice(9)]).toEqual(expected.map((v) => expect.closeTo(v, 6)));
    expect(surfaceGeometry(value, 'depth', null).positions.length).toBe(9);
    expect(JSON.stringify(value)).toBe(before);
  }
});

test('많은 격자는 공간별 원 방향을 선택하고 표시 상한 준수', () => {
  const cells = Array.from({ length: 8192 }, (_, i) => {
    const x = (i % 128) * 10,
      y = Math.floor(i / 128) * 10;
    return {
      ...frame.cells[0],
      triangleId: i,
      flowDirection: [1, 0] as [number, number],
      vertices: [
        [x, y],
        [x + 9, y],
        [x, y + 9],
      ] as [[number, number], [number, number], [number, number]],
    };
  });
  const arrows = surfaceDirections({ ...frame, cells });
  expect(arrows.length).toBeGreaterThan(100);
  expect(arrows.length).toBeLessThanOrEqual(maximumDirectionGlyphs);
  expect(surfaceDirections({ ...frame, cells: [...cells].reverse() })).toEqual(arrows);
});
