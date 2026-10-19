import { expect, test } from 'vitest';
import type { SurfaceFrame } from '../../surface/entity/surface';
import type { TraceTile } from '../../floodtrace/entity/floodTrace';
import type { Street } from '../entity/urban';
import {
  createFloodField,
  floodHazard,
  triangleIntersection,
  type FloodRoute,
  type FloodContact,
} from './floodFieldService';
import { floodMotion } from './floodMovementService';
import { streetPath } from './streetLifeService';

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
    [0, 0],
    [100, 0],
  ],
};
const frame = (depth = 0.2): SurfaceFrame => ({
  catalogSha256: 'a'.repeat(64),
  sourceSha256: 'b'.repeat(64),
  index: 0,
  timeSeconds: 0,
  wholeDomainStorageM3: 100 * depth,
  cells: [
    {
      triangleId: 0,
      vertices: [
        [40, -10],
        [60, -10],
        [50, 10],
      ],
      depthM: depth,
      speedMps: 0.5,
      flowDirection: [1, 0],
    },
  ],
});
const record: TraceTile = {
  eventId: 'seoul-20220808',
  id: 'test',
  path: '',
  triangleVertices: [40, -10, 60, -10, 50, 10],
};
const contact: FloodContact = { kind: 'calculated', depth: 0.2, speed: 0.5, hazard: 1 };
test('침수 음원은 정확한 삼각형 내부·가장 가까운 경계와 탐색 반경 사용', () => {
  const field = createFloodField([frame()], [], false);
  expect(field.nearest([50, 0], 1)?.distance).toBe(0);
  expect(field.nearest([50, -20], 15)?.point).toEqual([50, -10]);
  expect(field.nearest([50, -20], 9)).toBeNull();
  expect(createFloodField([frame(0)], [], false).nearest([50, 0], 50)).toBeNull();
});
test('주간 비교용 과거 침수에는 소리가 없고 재해 기록에는 원 수심을 생성하지 않음', () => {
  expect(createFloodField([], [record], false).nearest([50, 0], 10)).toBeNull();
  expect(createFloodField([], [record], true).nearest([50, 0], 10)?.contact.depth).toBeNull();
  expect(
    createFloodField([frame(0.5), frame(1)], [record], true).nearest([50, 0], 10)?.contact.depth
  ).toBe(1);
});
function route(from = 40, to = 60, value = contact): FloodRoute {
  const bands = [{ from, to, contact: value }];
  return { length: 100, bands, samples: bands };
}

test('얇은 삼각형·역방향 꼭짓점·구멍 구간의 선분 교차', () => {
  const triangle = [
    [50, -2],
    [50.001, -2],
    [50, 2],
  ] as const;
  expect(triangleIntersection([0, 0], [100, 0], triangle)).toEqual([0.5, 0.500005]);
  expect(triangleIntersection([0, 0], [100, 0], [triangle[2], triangle[1], triangle[0]])).toEqual([
    0.5, 0.500005,
  ]);
  expect(triangleIntersection([0, 5], [100, 5], triangle)).toBeNull();
  expect(
    triangleIntersection(
      [0, 0],
      [100, 0],
      [
        [1, 0],
        [2, 0],
        [3, 0],
      ]
    )
  ).toBeNull();
  const tile = {
    ...record,
    triangleVertices: [10, -10, 30, -10, 20, 10, 70, -10, 90, -10, 80, 10],
  };
  const field = createFloodField([], [tile], true);
  const result = field.route(streetPath(road), false, 1);
  expect(result.bands).toHaveLength(2);
  expect(result.bands.some((b) => b.from <= 50 && b.to >= 50)).toBe(false);
});

test('주간 비교 흔적 제외·재해 사건 흔적 포함·건조 계산 제외·교량 제외', () => {
  const path = streetPath(road);
  expect(createFloodField([], [record], false).route(path, false, 1).bands).toEqual([]);
  expect(createFloodField([], [record], true).route(path, false, 1).bands[0].contact).toEqual({
    kind: 'record',
    depth: null,
    speed: null,
    hazard: null,
  });
  expect(createFloodField([frame(0)], [], false).route(path, false, 1).bands).toEqual([]);
  expect(
    createFloodField([frame()], [record], true).route(
      streetPath({ ...road, bridge: true }),
      false,
      1
    ).bands
  ).toEqual([]);
});

test('실제 차선·보행 위치별 교차 및 동일 자료의 인덱스 재사용', () => {
  const source = frame(),
    path = streetPath(road),
    field = createFloodField([source], [], false);
  expect(createFloodField([source], [], false)).toBe(field);
  const car = field.route(path, false, 1),
    person = field.route(path, true, 1),
    reverse = field.route(path, false, -1);
  expect(field.route(path, false, 1)).toBe(car);
  expect(person.bands[0].from).toBeLessThan(car.bands[0].from);
  expect(reverse.bands[0].from).toBeGreaterThan(car.bands[0].from);
  expect(createFloodField([frame()], [], false).key).not.toBe(field.key);
});

test.each([
  [0.3, 1, 1],
  [0.5, 1, 2],
  [1.2, 0.5, 3],
  [2, 0.5, 4],
  [4, 1, 5],
  [4.001, 0, 6],
  [0.1, 2.01, 5],
  [0.31, 0, 2],
  [1, 1.01, 5],
])('AIDR 수심 %s·속력 %s의 독립 한계와 곱 한계 → H%s', (depth, speed, hazard) => {
  expect(floodHazard(depth, speed)).toBe(hazard);
});

test('3600배속 이동량도 얇은 침수 경계를 통과하지 않고 양 방향 정차', () => {
  const thin = route(50, 50.001);
  expect(floodMotion(thin, 10, 3600 * 9, 1, false, 9, 0)).toMatchObject({
    arc: 46,
    action: 'stopped',
    moving: false,
  });
  const reverse = floodMotion(thin, 90, 3600 * 9, -1, false, 9, 0);
  expect(reverse).toMatchObject({ action: 'stopped', moving: false });
  expect(reverse.arc).toBeCloseTo(54.001, 8);
  expect(floodMotion(thin, 10, 3600 * 9, 1, false, 9, 6).arc).toBe(40);
  expect(floodMotion(thin, 10, 3600 * 9, 1, false, 9, 100).arc).toBe(10);
});

test('실시간 통행 속력이 변해도 감속 곡선에서 위치 역행이나 점프 없음', () => {
  const source = route();
  const before = floodMotion(source, 10, 20, 1, false, 9, 0, 9);
  const paused = floodMotion(source, 10, 20, 1, false, 0, 0, 9);
  const after = floodMotion(source, 10, 21, 1, false, 1, 0, 9);
  expect(paused.arc).toBe(before.arc);
  expect(paused.moving).toBe(false);
  expect(after.arc).toBeGreaterThanOrEqual(before.arc);
  expect(after.arc - before.arc).toBeLessThanOrEqual(1);
});

test('건조 구간 보행자는 고배속·역방향에서도 침수 구간 진입 없이 되돌아감', () => {
  for (const home of [10, 90])
    for (const direction of [-1, 1])
      for (const travel of [0, 20, 60, 170, 3600]) {
        const response = floodMotion(route(), home, travel, direction, true, 1.3, 0);
        expect(response.arc < 40 || response.arc > 60).toBe(true);
        expect(response.arc).toBeGreaterThanOrEqual(0);
        expect(response.arc).toBeLessThanOrEqual(100);
      }
  expect(floodMotion(route(), 10, 40, 1, true, 1.3, 0)).toMatchObject({
    action: 'avoiding',
    direction: -1,
  });
});

test('노출 차량 정지·얕은 구간 보행자 대피·H4 이상 및 도로 전체 침수의 고립', () => {
  expect(floodMotion(route(), 45, 100, 1, false, 9, 0)).toMatchObject({
    arc: 45,
    action: 'exposed',
    moving: false,
  });
  expect(floodMotion(route(), 45, 2, 1, true, 1.3, 0)).toMatchObject({
    arc: 43,
    action: 'evacuating',
    direction: -1,
  });
  expect(floodMotion(route(), 45, 100, 1, true, 1.3, 0)).toMatchObject({
    arc: 39,
    action: 'avoiding',
    moving: false,
  });
  expect(
    floodMotion(route(40, 60, { ...contact, depth: 2, hazard: 4 }), 45, 100, 1, true, 1.3, 0).action
  ).toBe('stranded');
  expect(floodMotion(route(0, 100), 45, 100, 1, true, 1.3, 0).action).toBe('stranded');
});

test('이어진 침수 구간의 지역별 실제 위험도 보존 및 높은 위험도를 통과하는 대피 배제', () => {
  const source = route(20, 80, { ...contact, hazard: 4, depth: 2 });
  source.samples = [
    { from: 20, to: 40, contact: { ...contact, hazard: 4, depth: 2 } },
    { from: 40, to: 80, contact },
  ];
  const response = floodMotion(source, 45, 100, 1, true, 1.3, 0);
  expect(response).toMatchObject({ arc: 81, direction: 1, action: 'avoiding', contact });
});

test('일시정지·되감기 동일 입력 재현 및 주간 침수 해제 후 기존 위치에서 이동', () => {
  const source = route(),
    at = (seconds: number) => floodMotion(source, 10, seconds * 9, 1, false, 9, 0);
  const before = at(2);
  at(100);
  expect(at(2)).toEqual(before);
  const stopped = at(100);
  expect(
    floodMotion({ length: 100, bands: [], samples: [] }, stopped.arc, 0, 1, false, 9, 0).arc
  ).toBe(stopped.arc);
  expect(
    floodMotion({ length: 100, bands: [], samples: [] }, stopped.arc, 9, 1, false, 9, 0).arc
  ).toBe(stopped.arc + 9);
});
