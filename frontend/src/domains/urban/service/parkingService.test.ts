import { expect, test } from 'vitest';
import type { Street } from '../entity/urban';
import type { ParkingLot, ParkingData } from '../entity/parking';
import type { SharedSite, SharedInstallation } from '../../installation/entity/installation';
import {
  parkingOutsideFacilities,
  parkingTrafficPaths,
  parkingDisplayRoads,
  visibleParkingLots,
} from './parkingService';
import { movingPosition, streetPath } from './streetLifeService';
import { parkingGeometry } from './parkingGeometryService';
import { streetAtFace } from './streetGeometryService';
import { createFloodField } from './floodFieldService';
import type { TraceTile } from '../../floodtrace/entity/floodTrace';
import type { SurfaceFrame } from '../../surface/entity/surface';
const road: Street = {
  id: 'way/1:0',
  class: 'service',
  districtId: '1',
  widthM: 5,
  widthSource: 'DISPLAY_ASSUMPTION',
  walk: false,
  motor: true,
  oneway: 1,
  sidewalk: 'no',
  bridge: false,
  coordinates: [
    [-100, 0],
    [100, 0],
  ],
};
const lot: ParkingLot = {
  id: 'way/2',
  surfacePolygons: [],
  supports: [],
  polygons: [
    [
      [
        [0, 0],
        [40, 0],
        [40, 30],
        [0, 30],
        [0, 0],
      ],
      [
        [10, 10],
        [10, 20],
        [20, 20],
        [20, 10],
        [10, 10],
      ],
    ],
  ],
  bounds: [0, 0, 40, 30],
  slots: [
    {
      center: [5, 5],
      corners: [
        [3.75, 2.5],
        [6.25, 2.5],
        [6.25, 7.5],
        [3.75, 7.5],
        [3.75, 2.5],
      ],
      angle: 0,
      seed: 0.2,
    },
  ],
};
lot.surfacePolygons = lot.polygons;
test('차로 수 기반 교량 표시 폭은 원 도로·폭 태그·지상 도로를 변경하지 않음', () => {
  const original = { ...road, bridge: true, widthM: 16 };
  const parking = {
    lots: [],
    routes: [],
    displayRoadWidths: [{ id: road.id, lanes: 3, widthM: 10.5 }],
  };
  expect(parkingDisplayRoads([original], parking)[0].widthM).toBe(10.5);
  expect(original.widthM).toBe(16);
  expect(
    parkingDisplayRoads([{ ...original, widthSource: 'OSM_WIDTH_TAG' }], parking)[0].widthM
  ).toBe(16);
  expect(parkingDisplayRoads([road], parking)[0]).toBe(road);
});
test('주차장 통로 차량 제외와 경계 밖 이동·일방통행·원본 좌표 유지', () => {
  const original = JSON.stringify(road),
    path = streetPath(road);
  const rule: ParkingData['routes'][number] = {
    id: road.id,
    reason: 'PUBLIC_PARKING_BOUNDARY',
    parts: [
      [
        [-100, 0],
        [-25, 0],
      ],
      [
        [25, 0],
        [100, 0],
      ],
    ],
  };
  const routes = new Map([[road.id, rule]]);
  const paths = parkingTrafficPaths(path, routes);
  expect(paths).toHaveLength(2);
  for (const route of paths) {
    expect(route.road.oneway).toBe(1);
    for (const t of [0, 1, 10, 100, 10000])
      expect(Math.abs(movingPosition(route, t, 0.5, false).x)).toBeGreaterThanOrEqual(25);
  }
  expect(
    parkingTrafficPaths(
      path,
      new Map([[road.id, { ...rule, reason: 'OSM_PARKING_AISLE', parts: [] }]])
    )
  ).toEqual([]);
  expect(parkingTrafficPaths(streetPath({ ...road, bridge: true }), routes)[0].road.bridge).toBe(
    true
  );
  expect(parkingTrafficPaths(path, new Map())[0]).toBe(path);
  expect(JSON.stringify(road)).toBe(original);
});
test('주차장 구멍·면적 유지와 포장·주차선의 침수 아래 높이', () => {
  const mesh = parkingGeometry([lot], null),
    p = mesh.surface.attributes.position.array;
  let area = 0;
  for (let i = 0; i < p.length; i += 9) {
    area +=
      Math.abs(
        (p[i + 3] - p[i]) * (p[i + 8] - p[i + 2]) - (p[i + 6] - p[i]) * (p[i + 5] - p[i + 2])
      ) / 2;
    expect(p[i + 1]).toBeCloseTo(0.006);
  }
  expect(area).toBeCloseTo(1100);
  const lines = mesh.markings.attributes.position.array;
  for (let i = 1; i < lines.length; i += 3) expect(lines[i]).toBeCloseTo(0.01);
  mesh.surface.dispose();
  mesh.markings.dispose();
  mesh.hit.dispose();
});
test('주차장 선택 면은 잘린 포장 대신 원 경계와 구멍·주차장별 매핑 유지', () => {
  const mesh = parkingGeometry([{ ...lot, surfacePolygons: [] }, lot], null);
  const positions = mesh.hit.attributes.position.array;
  let area = 0;
  for (let i = 0; i < positions.length; i += 9) {
    area +=
      Math.abs(
        (positions[i + 3] - positions[i]) * (positions[i + 8] - positions[i + 2]) -
          (positions[i + 6] - positions[i]) * (positions[i + 5] - positions[i + 2])
      ) / 2;
    expect(positions[i + 1]).toBeCloseTo(0.013);
  }
  expect(area).toBeCloseTo(2200);
  expect(streetAtFace(mesh.hitEnds, 0)).toBe(0);
  expect(streetAtFace(mesh.hitEnds, mesh.hitEnds[0] - 1)).toBe(0);
  expect(streetAtFace(mesh.hitEnds, mesh.hitEnds[0])).toBe(1);
  expect(streetAtFace(mesh.hitEnds, mesh.hitEnds[1])).toBe(-1);
  mesh.surface.dispose();
  mesh.markings.dispose();
  mesh.hit.dispose();
});
test('화면 주변만 표시하고 빗물정원과 겹친 주차 칸 제외·투수포장 주차 유지', () => {
  expect(visibleParkingLots([lot], [5, 5], 50)).toEqual([lot]);
  expect(visibleParkingLots([lot], [2000, 2000], 50)).toEqual([]);
  const site = {
    districtId: '1',
    cellId: 'p',
    kind: 'GROUND',
    areaM2: 100,
    polygons: [
      [
        [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
          [0, 0],
        ],
      ],
    ],
  } as SharedSite;
  const installation = { facilityType: 'RAIN_GARDEN', areaM2: 100 } as SharedInstallation;
  expect(
    parkingOutsideFacilities([lot], [site], new Map([['1:p', installation]]))[0].slots
  ).toHaveLength(0);
  expect(
    parkingOutsideFacilities(
      [lot],
      [site],
      new Map([['1:p', { ...installation, facilityType: 'PERMEABLE_PAVEMENT' }]])
    )
  ).toEqual([lot]);
  expect(lot.slots).toHaveLength(1);
});
test('정차 차량 침수 접촉은 주간 과거 흔적 제외·재해 기록 포함·원 수심 유지', () => {
  const trace = { triangleVertices: [0, 0, 20, 0, 0, 20] } as TraceTile;
  expect(createFloodField([], [trace], false).contact([5, 5])).toBeNull();
  expect(createFloodField([], [trace], true).contact([5, 5])).toMatchObject({
    kind: 'record',
    depth: null,
  });
  const frame = {
    cells: [
      {
        vertices: [
          [0, 0],
          [20, 0],
          [0, 20],
        ],
        depthM: 0.7,
        speedMps: 0.2,
      },
    ],
  } as SurfaceFrame;
  expect(createFloodField([frame], [trace], true).contact([5, 5])).toMatchObject({
    kind: 'calculated',
    depth: 0.7,
    speed: 0.2,
  });
  expect(createFloodField([frame], [], true).contact([30, 30])).toBeNull();
});
