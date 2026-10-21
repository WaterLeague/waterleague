import { expect, test } from 'vitest';
import { clipLine, clipPolygons, mapScope, scopeContains, scopeIntersects } from './mapScope';
import { scopeTraceTile } from '../../domains/floodtrace/service/floodTraceService';
import { competitionStreets } from '../../domains/urban/service/competitionStreetService';
import type { Street } from '../../domains/urban/entity/urban';
const scope = mapScope([
  {
    id: '11110',
    polygons: [
      [
        [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
          [0, 0],
        ],
        [
          [4, 4],
          [4, 6],
          [6, 6],
          [6, 4],
          [4, 4],
        ],
      ],
    ],
  },
]);
test('선택 구 밖과 내부 구멍의 타일 요청 제외', () => {
  expect(scopeIntersects([12, 0, 20, 5], scope)).toBe(false);
  expect(scopeIntersects([4.5, 4.5, 5.5, 5.5], scope)).toBe(false);
  expect(scopeIntersects([9, 2, 12, 5], scope)).toBe(true);
  expect(scopeContains([5, 5], scope)).toBe(false);
});
test('경계와 구멍에서 표시 선과 면 절단 및 원본 보존', () => {
  const line: [number, number][] = [
    [-5, 5],
    [15, 5],
  ];
  expect(clipLine(line, scope)).toEqual([
    [
      [0, 5],
      [4, 5],
    ],
    [
      [6, 5],
      [10, 5],
    ],
  ]);
  expect(line).toEqual([
    [-5, 5],
    [15, 5],
  ]);
  expect(
    clipPolygons(
      [
        [
          [
            [9, 1],
            [12, 1],
            [12, 3],
            [9, 3],
            [9, 1],
          ],
        ],
      ],
      scope
    )
  ).toEqual([
    [
      [
        [9, 1],
        [10, 1],
        [10, 3],
        [9, 3],
        [9, 1],
      ],
    ],
  ]);
});
test('침수 흔적 경계 삼각형과 SVG 좌표를 같은 범위로 제한', () => {
  const tile = {
    eventId: 'seoul-20220808' as const,
    id: '0_0',
    path: 'M8,-1L12,-1L8,-3Z',
    triangleVertices: [8, 1, 12, 1, 8, 3],
  };
  const result = scopeTraceTile(tile, scope);
  expect(result.triangleVertices.length).toBe(12);
  for (let i = 0; i < result.triangleVertices.length; i += 2)
    expect(result.triangleVertices[i]).toBeLessThanOrEqual(10);
  expect(result.path).not.toContain('12,');
  expect(tile.triangleVertices).toEqual([8, 1, 12, 1, 8, 3]);
});
test('구를 가로지르는 이동 경로도 선택 구 밖으로 나가지 않음', () => {
  const road = {
    id: 'r',
    coordinates: [
      [-5, 2],
      [15, 2],
    ],
    nativeRailPaths: [
      [
        [-5, 2],
        [15, 2],
      ],
    ],
  } as Street;
  const result = competitionStreets([road], scope);
  expect(result[0].coordinates).toEqual([
    [0, 2],
    [10, 2],
  ]);
  expect(result[0].nativeRailPaths).toEqual([
    [
      [0, 2],
      [10, 2],
    ],
  ]);
  expect(road.coordinates).toEqual([
    [-5, 2],
    [15, 2],
  ]);
});

test('절단된 교량의 높이 보간과 구조 구간을 새 경로 거리로 정렬', () => {
  const road = {
    id: 'bridge',
    coordinates: [
      [-5, 2],
      [15, 2],
    ],
    elevationsM: [10, 30],
    nativeStructurePath: {
      coordinates: [
        [-5, 2],
        [15, 2],
      ],
      span: [3, 18],
      widthM: 8,
    },
  } as Street;
  const result = competitionStreets([road], scope)[0];
  expect(result.elevationsM).toEqual([15, 25]);
  expect(result.nativeStructurePath?.span).toEqual([0, 10]);
  expect(road.nativeStructurePath?.span).toEqual([3, 18]);
});
