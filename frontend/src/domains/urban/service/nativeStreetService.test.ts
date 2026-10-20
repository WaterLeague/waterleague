import { expect, test } from 'vitest';
import type { CityTile } from '../../city/entity/city';
import { nativeStreets } from './nativeStreetService';
import { streetActorRoutes, streetPath } from './streetLifeService';
import { streetGeometry } from './streetGeometryService';
import { nativeUrbanTileDto } from '../dto/nativeUrbanDto';
const id = (layer: string) => `ngii:${layer}:${'a'.repeat(64)}`;
const ring: [number, number][] = [
  [0, 0],
  [60, 0],
  [60, 10],
  [0, 10],
  [0, 0],
];
test('원 보도 내부 경로와 공개 양방향 도로의 사람·차량 경로를 주차장 없이 유지', () => {
  const common = {
    districtId: '11200',
    center: [30, 5] as [number, number],
    geometryEligibility: 'GEOMETRY_ONLY',
    sourceAreaM2: null,
    sourceLengthM: 60,
    candidateId: null,
    allowedMask: 0,
  };
  const tile: CityTile = {
    schemaVersion: 2,
    id: '0_0',
    buildings: [],
    nativeFeatures: [
      {
        ...common,
        id: id('N1L_A0020000'),
        role: 'ROAD_CENTERLINE',
        geometry: {
          type: 'LineString',
          coordinates: [
            [0, 5],
            [60, 5],
          ],
        },
        trafficDirection: 'BIDIRECTIONAL',
      },
      {
        ...common,
        id: id('N1L_A0020000').replace(/a$/, 'b'),
        role: 'ROAD_CENTERLINE',
        geometry: {
          type: 'LineString',
          coordinates: [
            [0, 8],
            [60, 8],
          ],
        },
        trafficDirection: 'UNKNOWN',
      },
    ],
    urban: {
      schemaVersion: 1,
      id: '0_0',
      parkingLots: [],
      crosswalks: [],
      walkPaths: [
        {
          id: id('N1A_A0033320') + ':walk:0',
          sourceObjectId: id('N1A_A0033320'),
          districtId: '11200',
          coordinates: [
            [1, 2],
            [59, 2],
          ],
        },
      ],
    },
  };
  const before = structuredClone(tile),
    roads = nativeStreets([tile]);
  const routes = roads.flatMap((road) => streetActorRoutes(streetPath(road)));
  expect(routes.map((route) => route.walking).sort()).toEqual([false, true]);
  expect(routes.find((route) => route.walking)?.path.road.coordinates).toEqual([
    [1, 2],
    [59, 2],
  ]);
  expect(tile).toEqual(before);
});
test('교량 원 면은 지면과 분리하고 횡단보도 표시는 줄무늬 원 면만 사용', () => {
  const bridge = {
    id: id('N1A_A0070000'),
    class: 'BRIDGE_AREA',
    districtId: '11200',
    widthM: 0,
    widthSource: 'NOT_CONFIRMED' as const,
    walk: false,
    motor: false,
    oneway: 0,
    sidewalk: '',
    bridge: true,
    coordinates: ring,
    nativeSourceRole: 'BRIDGE_AREA',
    nativePolygons: [[ring]],
  };
  const data = streetGeometry([bridge], null, true);
  expect(
    Math.max(...Array.from(data.positions).filter((_, index) => index % 3 === 1))
  ).toBeGreaterThan(5);
  const marking = {
    ...bridge,
    id: id('N1A_A0043325'),
    bridge: false,
    nativeSourceRole: 'CROSSWALK_AREA',
    nativeMarkingPolygons: [[ring]],
  };
  expect(streetGeometry([marking], null, false).positions.length).toBe(0);
  expect(streetGeometry([marking], null, true).positions.length).toBeGreaterThan(0);
});
test('주차 칸 제공·지원하지 않는 보행 원형 대응과 중복 식별자를 거부', () => {
  const tile = {
    schemaVersion: 1,
    id: '0_0',
    crosswalks: [],
    parkingLots: [],
    walkPaths: [
      {
        id: 'unbound',
        sourceObjectId: id('N1A_A0033320'),
        districtId: '11200',
        coordinates: [
          [1, 2],
          [59, 2],
        ],
      },
    ],
  };
  expect(nativeUrbanTileDto.safeParse(tile).success).toBe(false);
  tile.walkPaths[0].id = id('N1A_A0033320') + ':walk:0';
  expect(nativeUrbanTileDto.safeParse(tile).success).toBe(true);
  tile.walkPaths.push({ ...tile.walkPaths[0] });
  expect(nativeUrbanTileDto.safeParse(tile).success).toBe(false);
});
