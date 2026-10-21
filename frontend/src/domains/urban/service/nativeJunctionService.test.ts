import { expect, test } from 'vitest';
import { connectNativeJunctions } from './nativeJunctionService';
import { streetGeometry } from './streetGeometryService';
import type { Street } from '../entity/urban';
const surface: [number, number][][][] = [
  [
    [
      [-100, -30],
      [100, -30],
      [100, 30],
      [-100, 30],
      [-100, -30],
    ],
  ],
];
const road = (id: string, coordinates: [number, number][], lanes = 4): Street => ({
  id,
  coordinates,
  lanes,
  class: 'road',
  districtId: '',
  widthM: lanes * 3.25,
  widthSource: 'DISPLAY_ASSUMPTION',
  walk: false,
  motor: true,
  oneway: 0,
  sidewalk: '',
  bridge: false,
  nativeSourceRole: 'ROAD_CENTERLINE',
  nativeLaneClipPolygons: surface,
  nativeLanePaths: [{ coordinates, lanes, widthM: lanes * 3.25, span: [0, 100] }],
});
test('큰 도로·작은 도로 접속 노드 내부에 직진 차선 중첩 없음', () => {
  const rows = connectNativeJunctions([
    road('west', [
      [-100, 0],
      [0, 0],
    ]),
    road('east', [
      [0, 0],
      [100, 0],
    ]),
    road(
      'north',
      [
        [0, 0],
        [0, 100],
      ],
      2
    ),
  ]);
  const data = streetGeometry(rows, null, true);
  expect(data.positions.length).toBeGreaterThan(0);
  for (let i = 0; i < data.positions.length; i += 9) {
    const x = (data.positions[i] + data.positions[i + 3] + data.positions[i + 6]) / 3,
      z = (data.positions[i + 2] + data.positions[i + 5] + data.positions[i + 8]) / 3;
    expect(Math.hypot(x, z)).toBeGreaterThan(7);
  }
});
test('서로 겹치기만 하는 입체 교차 선분은 접속 노드로 결합하지 않음', () => {
  const rows = connectNativeJunctions([
    road('upper', [
      [-100, 0],
      [100, 0],
    ]),
    road('lower', [
      [0, -100],
      [0, 100],
    ]),
  ]);
  expect(rows.every((r) => !r.nativeJunctionPolygons)).toBe(true);
});
