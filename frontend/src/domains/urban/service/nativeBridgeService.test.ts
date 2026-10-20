import { expect, test } from 'vitest';
import { nativeBridgeHeight, nativeBridgeProfileHeight } from './nativeBridgeService';
import { nativeStreets } from './nativeStreetService';
import { streetGeometry, streetHeight } from './streetGeometryService';
import type { NativeBridgeGroup, NativeBridgeProfile } from '../dto/nativeBridgeDto';
import type { Terrain } from '../../terrain/entity/terrain';
import {
  BufferAttribute,
  BufferGeometry,
  DoubleSide,
  Mesh,
  MeshBasicMaterial,
  Raycaster,
  Vector3,
} from 'three';
const ring = (a: number, b: number): [number, number][] => [
  [a, -5],
  [b, -5],
  [b, 5],
  [a, 5],
  [a, -5],
];
const id = (c: string) => 'ngii:N1A_A0070000:' + c.repeat(64);
const group: NativeBridgeGroup = {
  id: id('a'),
  role: 'BRIDGE_AREA',
  sourceIds: [id('a'), id('b')],
  sourceFids: [1, 2],
  bounds: [0, -5, 100, 5],
  polygons: [[ring(0, 50)], [ring(50, 100)]],
  profiles: [
    {
      roadIds: ['ngii:N1L_A0020000:' + 'c'.repeat(64) + ':part:0'],
      coordinates: [
        [-100, 0],
        [0, 0],
        [100, 0],
        [200, 0],
      ],
      span: [100, 200],
      polygons: [[ring(-100, 0)], [ring(100, 200)]],
      displayWidthM: 10,
    },
  ],
};
const profile: NativeBridgeProfile = { ...group.profiles[0], deckPolygons: group.polygons };
const terrain: Terrain = {
  width: 4,
  height: 2,
  origin: [-100, -10],
  spacing: [100, 100],
  districtIds: [],
  heights: new Float32Array([10, 12, 14, 16, 10, 12, 14, 16]),
  districts: new Uint8Array(8),
  cover: new Uint8Array(8),
};
test('인접 상판 조각·접속부·이동체가 같은 높이를 사용하고 지면으로 연속 접속', () => {
  const roads = nativeStreets([], [group]),
    deck = nativeBridgeHeight(terrain, group.polygons);
  const mesh = streetGeometry(roads, terrain, true);
  const at = (x: number) => nativeBridgeProfileHeight(terrain, [x, 0], profile);
  expect(at(-100)).toBeCloseTo(10);
  expect(at(200)).toBeCloseTo(16);
  expect(at(0)).toBeCloseTo(deck);
  expect(at(100)).toBeCloseTo(deck);
  expect(Math.abs(at(-0.001) - at(0.001))).toBeLessThan(0.001);
  expect(Math.abs(at(99.999) - at(100.001))).toBeLessThan(0.001);
  for (const x of [0, 50, 100]) {
    const ys = [];
    for (let i = 0; i < mesh.positions.length; i += 3)
      if (Math.abs(mesh.positions[i] - x) < 0.001) ys.push(mesh.positions[i + 1]);
    expect(ys.some((y) => Math.abs(y - deck - 0.016) < 0.0001)).toBe(true);
    expect(
      streetHeight(terrain, [x, 0], { ...roads[0], nativeBridgeProfiles: [profile] })
    ).toBeCloseTo(deck + 0.016);
  }
  // 접속부 삼각면을 촘촘히 나눠 차량 높이와 그려진 도로면의 오차를 제한한다.
  const approach = streetGeometry([roads[1]], terrain, true);
  let checked = 0;
  for (let i = 0; i < approach.positions.length; i += 9) {
    const values = [0, 3, 6].map((j) => [
      approach.positions[i + j],
      approach.positions[i + j + 1],
      -approach.positions[i + j + 2],
    ]);
    if (values.some((p) => Math.abs(p[1] - streetHeight(terrain, [p[0], p[2]], roads[1])) > 0.001))
      continue;
    const center = values.reduce(
      (a, p) => [a[0] + p[0] / 3, a[1] + p[1] / 3, a[2] + p[2] / 3],
      [0, 0, 0]
    );
    expect(
      Math.abs(center[1] - streetHeight(terrain, [center[0], center[2]], roads[1]))
    ).toBeLessThan(0.04);
    checked++;
  }
  expect(checked).toBeGreaterThan(100);
});
test('원 도로 식별자가 없는 하부 교차 도로는 상판 높이로 올리지 않음', () => {
  const before = structuredClone(group),
    roads = nativeStreets([], [group]);
  expect(roads[0].nativeBridgeGroupPolygons).toBe(group.polygons);
  expect(group).toEqual(before);
  expect(
    streetHeight(null, [50, 0], { ...roads[0], bridge: false, nativeBridgeProfiles: undefined })
  ).toBeCloseTo(0.004);
});
test('철교 선로는 원 철도 경로를 따라 접속부와 상판 위에 연속 생성', () => {
  const railGroup: NativeBridgeGroup = {
    ...group,
    names: ['시험 철교'],
    kinds: ['철교'],
    profiles: group.profiles.map((p) => ({
      ...p,
      rail: true,
      roadIds: p.roadIds.map((id) => id.replace('A0020000', 'A0150000')),
    })),
  };
  const roads = nativeStreets([], [railGroup]);
  expect(roads[1].nativeRailPaths).toEqual([group.profiles[0].coordinates]);
  const mesh = streetGeometry([roads[1]], null, true);
  const middle: number[] = [];
  for (let i = 0; i < mesh.positions.length; i += 3)
    if (mesh.positions[i] > 20 && mesh.positions[i] < 80) middle.push(mesh.positions[i + 1]);
  expect(middle.length).toBeGreaterThan(0);
  expect(Math.max(...middle)).toBeGreaterThan(6.6);
  expect(Math.min(...middle)).toBeGreaterThan(6.4);
  const geometry = new BufferGeometry().setAttribute(
    'position',
    new BufferAttribute(mesh.positions, 3)
  );
  const material = new MeshBasicMaterial({ side: DoubleSide });
  const model = new Mesh(geometry, material);
  const hits = new Raycaster(new Vector3(50, 20, -0.7175), new Vector3(0, -1, 0)).intersectObject(
    model
  );
  expect(hits[0].point.y).toBeGreaterThan(6.7);
  geometry.dispose();
  material.dispose();
});
test('교량 보행자는 원 보도 상판에 서고 지상 보도에는 교량 높이를 적용하지 않음', () => {
  const sidewalk: [number, number][][][] = [
    [
      [
        [0, 1],
        [100, 1],
        [100, 3],
        [0, 3],
        [0, 1],
      ],
    ],
  ];
  const g: NativeBridgeGroup = {
    ...group,
    sidewalks: [
      {
        sourceId: 'ngii:N1A_A0033320:' + 'd'.repeat(64),
        polygons: sidewalk,
        paths: [
          [
            [1, 2],
            [99, 2],
          ],
        ],
      },
    ],
  };
  const roads = nativeStreets([], [g]);
  const walk = roads.find((r) => r.walk)!;
  expect(streetHeight(null, [50, 2], walk)).toBeCloseTo(6.64);
  expect(streetHeight(null, [50, 4], walk)).toBeCloseTo(0.004);
  const surface = roads.find((r) => r.nativeSourceRole === 'SIDEWALK_AREA')!;
  const mesh = streetGeometry([surface], null, true);
  expect(Math.max(...Array.from(mesh.positions).filter((_, i) => i % 3 === 1))).toBeCloseTo(6.64);
});
test('반포대교 상층과 잠수교 하층을 같은 평면으로 합치지 않음', () => {
  const upper = nativeStreets([], [{ ...group, names: ['반포대교'] }]);
  const lower = nativeStreets([], [{ ...group, names: ['잠수교'] }]);
  expect(streetHeight(null, [50, 0], upper[1]) - streetHeight(null, [50, 0], lower[1])).toBeCloseTo(
    7
  );
});
