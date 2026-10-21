import { expect, test } from 'vitest';
import {
  connectBridgeDatums,
  nativeBridgeHeight,
  nativeBridgeProfileHeight,
} from './nativeBridgeService';
import { nativeStreets } from './nativeStreetService';
import {
  bridgeTransportBindings,
  bridgeAttachmentHeight,
  bridgeSurfaceSupports,
} from './nativeBridgeTransportService';
import { topographyGeometry } from '../../topography/service/topographyGeometryService';
import { topographyIndexDto } from '../../topography/dto/topographyDto';
import sourceIndex from '../../../../public/data/seoul-features-v1/index.json';
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
test('원 경로 길이의 미소 반올림 차이 때문에 섬 연결 끝점이 지면으로 꺼지지 않음', () => {
  const connected = {
    ...profile,
    coordinates: [
      [0, 0],
      [100, 0],
    ] as [number, number][],
    span: [0, 100 - 1e-12] as [number, number],
  };
  expect(nativeBridgeProfileHeight(terrain, [100, 0], connected)).toBeCloseTo(
    nativeBridgeHeight(terrain, group.polygons)
  );
});
test('육상 접속부의 조명은 경사면에 놓고 수면으로 연장된 표시 접속부는 지지로 쓰지 않음', () => {
  const point: [number, number] = [-50, 0];
  expect(bridgeSurfaceSupports([group], point, false)).toEqual([group]);
  expect(bridgeSurfaceSupports([group], point, true)).toEqual([]);
  expect(bridgeAttachmentHeight([group], terrain)(point)).toBeCloseTo(
    nativeBridgeProfileHeight(terrain, point, profile)
  );
});
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
test('철교 레일은 원 철도 레이어에서만 접속부·상판 높이로 연속 생성', () => {
  const railGroup: NativeBridgeGroup = {
    ...group,
    names: ['시험 철교'],
    kinds: ['철교'],
    profiles: group.profiles.map((p) => ({
      ...p,
      rail: true,
      sourceFids: [1],
      roadIds: p.roadIds.map((id) => id.replace('A0020000', 'A0150000')),
    })),
  };
  const roads = nativeStreets([], [railGroup]);
  expect(roads.every((road) => !road.nativeRailPaths)).toBe(true);
  const index = topographyIndexDto.parse(sourceIndex);
  const layer = index.layers.findIndex((l) => l.id === 'N1L_A0150000');
  const mesh = topographyGeometry(
    {
      schemaVersion: 1,
      id: '0_0',
      points: [],
      areas: [],
      lines: [[layer, 1, [group.profiles[0].coordinates], null]],
    },
    index.layers,
    null,
    false,
    true,
    bridgeTransportBindings([railGroup])
  );
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

test('접속 경로가 다음 상판 내부까지 겹쳐도 실제 상판 간격으로 같은 높이 연결', () => {
  const first: NativeBridgeGroup = {
    ...group,
    polygons: [[ring(0, 100)]],
    profiles: [{ ...group.profiles[0] }],
  };
  const second: NativeBridgeGroup = {
    ...group,
    id: id('d'),
    polygons: [[ring(150, 250)]],
    profiles: [
      {
        ...group.profiles[0],
        coordinates: [
          [50, 0],
          [150, 0],
          [250, 0],
          [350, 0],
        ],
        span: [100, 200],
      },
    ],
  };
  const joined = connectBridgeDatums([first, second]);
  const a = { ...joined[0].profiles[0], deckPolygons: first.polygons };
  const b = { ...joined[1].profiles[0], deckPolygons: second.polygons };
  expect(a.connections?.find((c) => c.side === 1)?.gapM).toBe(50);
  expect(b.connections?.find((c) => c.side === 0)?.gapM).toBe(50);
  for (const x of [100, 110, 125, 140, 150])
    expect(nativeBridgeProfileHeight(terrain, [x, 0], a)).toBeCloseTo(
      nativeBridgeProfileHeight(terrain, [x, 0], b)
    );
});

test('같은 이름이어도 원 도로 연결이 없는 구조의 높이 기준은 분리', () => {
  const first = { ...group, names: ['동명 교량'] };
  const second = {
    ...group,
    id: id('e'),
    names: ['동명 교량'],
    polygons: [[ring(200, 300)]],
    profiles: group.profiles.map((p) => ({ ...p, roadIds: ['other-road'] })),
  };
  const joined = connectBridgeDatums([first, second]);
  expect(joined[0].displayDatumPolygons).not.toBe(joined[1].displayDatumPolygons);
});

test('다른 원 도로의 끝점이 본선 접속부 중간에 합류하면 높이 연속', () => {
  const main = {
    ...group,
    profiles: [
      {
        ...group.profiles[0],
        coordinates: [
          [-100, 0],
          [-50, 0],
          [0, 0],
          [100, 0],
          [200, 0],
        ] as [number, number][],
      },
    ],
  };
  const branch = {
    ...group,
    id: id('f'),
    polygons: [
      [
        [
          [-55, 40],
          [-45, 40],
          [-45, 100],
          [-55, 100],
          [-55, 40],
        ],
      ],
    ] as [number, number][][][],
    profiles: [
      {
        ...group.profiles[0],
        roadIds: ['other-road'],
        coordinates: [
          [-50, 0],
          [-50, 40],
          [-50, 100],
          [-50, 150],
        ] as [number, number][],
        span: [40, 100] as [number, number],
      },
    ],
  };
  const [a, b] = connectBridgeDatums([main, branch]);
  expect(b.profiles[0].connections?.[0].endpointTarget).toBeDefined();
  for (const x of [-54, -50, -46]) {
    const at: [number, number] = [x, 0];
    expect(
      nativeBridgeProfileHeight(terrain, at, {
        ...b.profiles[0],
        deckPolygons: b.displayDatumPolygons!,
      })
    ).toBeCloseTo(
      nativeBridgeProfileHeight(terrain, at, {
        ...a.profiles[0],
        deckPolygons: a.displayDatumPolygons!,
      })
    );
  }
});
