import { expect, test } from 'vitest';
import type { Terrain } from '../entity/terrain';
import { drapeTriangle, drapeSegment, terrainMeshHeight } from './terrainDrapeService';
import { surfaceGeometry } from '../../surface/service/surfaceGeometry';
import type { SurfaceFrame } from '../../surface/entity/surface';
import { floodSurfaceLift } from './surfaceDisplayService';

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
type Point = readonly [number, number];
const area = ([a, b, c]: readonly Point[]) =>
  Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2;
test('행·대각선·지형 외곽을 가로지르는 수면의 원 면적과 실제 삼각면 높이 보존', () => {
  const source: [Point, Point, Point] = [
    [-3, 23],
    [22, 15],
    [3, -4],
  ];
  const result: (readonly [Point, Point, Point])[] = [];
  drapeTriangle(source, terrain, (triangle) => result.push(triangle));
  expect(result.length).toBeGreaterThan(8);
  expect(result.reduce((sum, triangle) => sum + area(triangle), 0)).toBeCloseTo(area(source), 8);
  for (const triangle of result) {
    const middle: Point = [
      triangle.reduce((n, p) => n + p[0], 0) / 3,
      triangle.reduce((n, p) => n + p[1], 0) / 3,
    ];
    expect(triangle.reduce((n, p) => n + terrainMeshHeight(terrain, p), 0) / 3).toBeCloseTo(
      terrainMeshHeight(terrain, middle),
      8
    );
  }
  // 첫 셀 중심은 표시 삼각면의 6m이며 기존 양선형 보간의 3m와 다르다.
  expect(terrainMeshHeight(terrain, [5, 15])).toBe(6);
});
test('경계 측면도 지형 대각선과 일치하며 중간에서 지형을 뚫지 않음', () => {
  const segments = drapeSegment([-3, 23], [23, -3], terrain);
  expect(segments[0][0]).toEqual([-3, 23]);
  expect(segments.at(-1)![1]).toEqual([23, -3]);
  for (const [a, b] of segments) {
    const middle: Point = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    expect((terrainMeshHeight(terrain, a) + terrainMeshHeight(terrain, b)) / 2).toBeCloseTo(
      terrainMeshHeight(terrain, middle),
      8
    );
  }
});
test('얕은 계산 수심이 원 수심 그대로 지형 위에 남고 흐름·계산 프레임 불변', () => {
  const frame = {
    cells: [
      {
        triangleId: 0,
        vertices: [
          [0, 20],
          [20, 20],
          [0, 0],
        ],
        depthM: 0.05,
        speedMps: 0.4,
        flowDirection: [1, 0],
      },
    ],
  } as SurfaceFrame;
  const before = JSON.stringify(frame);
  const mesh = surfaceGeometry(frame, 'depth', terrain);
  let surfaceArea = 0;
  for (let i = 0; i < mesh.positions.length; i += 9) {
    if (mesh.faces[i / 3] !== 1) continue;
    const points: Point[] = [0, 3, 6].map((j) => [
      mesh.positions[i + j],
      -mesh.positions[i + j + 2],
    ]);
    surfaceArea += area(points);
    const center: Point = [
      points.reduce((n, p) => n + p[0], 0) / 3,
      points.reduce((n, p) => n + p[1], 0) / 3,
    ];
    const height = (mesh.positions[i + 1] + mesh.positions[i + 4] + mesh.positions[i + 7]) / 3;
    expect(height - terrainMeshHeight(terrain, center)).toBeCloseTo(floodSurfaceLift + 0.05, 5);
    expect(mesh.flows[(i / 3) * 2]).toBeCloseTo(0.4);
  }
  expect(surfaceArea).toBeCloseTo(200);
  expect(JSON.stringify(frame)).toBe(before);
});
