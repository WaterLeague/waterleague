import { expect, test } from 'vitest';
import { NativeGroundCuts } from './nativeGroundCutService';
import { withinBridge } from './nativeBridgeService';
import type { NativeBridgeGroup } from '../dto/nativeBridgeDto';
const rectangle = (x: number, y: number, w: number, h: number): [number, number][][][] => [
  [
    [
      [x, y],
      [x + w, y],
      [x + w, y + h],
      [x, y + h],
      [x, y],
    ],
  ],
];
test('같은 교차 좌표의 상부 원 객체만 제거하고 실제 하부 도로 보존', () => {
  const shape = rectangle(0, 0, 10, 10);
  const cuts = new NativeGroundCuts(
    [{ sourceSurfaceCuts: [{ sourceFids: [10], polygons: shape }] } as NativeBridgeGroup],
    []
  );
  expect(cuts.surface(shape, 'ROAD_AREA', 10)).toEqual([]);
  expect(cuts.surface(shape, 'ROAD_AREA', 11)).toEqual(shape);
  expect(cuts.contains([5, 5])).toBe(false);
});
test('수면 위 교량 구간의 원 지면 사본만 잘라내고 주변 도로와 구멍 보존', () => {
  const cuts = new NativeGroundCuts([
    { groundCutPolygons: rectangle(2, 2, 6, 6) } as NativeBridgeGroup,
  ]);
  const ground = cuts.surface(rectangle(0, 0, 10, 10));
  expect(withinBridge([5, 5], ground)).toBe(false);
  expect(withinBridge([1, 5], ground)).toBe(true);
  expect(
    cuts.line([
      [0, 5],
      [10, 5],
    ])
  ).toEqual([
    [
      [0, 5],
      [2, 5],
    ],
    [
      [8, 5],
      [10, 5],
    ],
  ]);
  expect(
    cuts.line([
      [0, 1],
      [10, 1],
    ])
  ).toEqual([
    [
      [0, 1],
      [10, 1],
    ],
  ]);
  expect(cuts.surface(rectangle(3, 3, 1, 1))).toEqual([]);
});

test('원 수면 경계로 교량 폭 밖의 사본도 제거하고 섬 구멍과 육상 도로 보존', () => {
  const water = rectangle(2, 2, 6, 6);
  water[0].push(rectangle(4, 4, 2, 2)[0][0]);
  const cuts = new NativeGroundCuts([], water);
  const ground = cuts.surface(rectangle(0, 0, 10, 10));
  expect(withinBridge([3, 5], ground)).toBe(false);
  expect(withinBridge([5, 5], ground)).toBe(true);
  expect(withinBridge([1, 5], ground)).toBe(true);
  expect(cuts.contains([3, 5])).toBe(true);
  expect(cuts.contains([5, 5])).toBe(false);
});

test('섬·육지의 같은 도로만 제거하고 철교 아래 도로와 실제 하부 횡단부 보존', () => {
  const island = rectangle(3, 3, 4, 4);
  const water = rectangle(0, 0, 10, 10);
  water[0].push(island[0][0]);
  const owned = rectangle(4, 0, 2, 10);
  owned[0].push(rectangle(4.2, 4.5, 1.6, 1)[0][0]);
  const group = {
    surfaceCuts: [{ roles: ['ROAD_AREA'], polygons: owned }],
    profiles: [],
  } as unknown as NativeBridgeGroup;
  const cuts = new NativeGroundCuts([group], water);
  const road = cuts.surface(rectangle(0, 0, 10, 10), 'ROAD_AREA');
  expect(withinBridge([5, 4], road)).toBe(false);
  expect(withinBridge([5, 5], road)).toBe(true);
  expect(withinBridge([3.5, 4], road)).toBe(true);
  expect(withinBridge([5, 4], cuts.surface(island, 'RAILWAY_AREA'))).toBe(true);
  expect(cuts.contains([5, 4])).toBe(false);
  expect(cuts.at([5, 4])).toEqual([group]);
  expect(cuts.at([5, 5])).toEqual([]);
  expect(
    cuts.line(
      [
        [5, 3],
        [5, 7],
      ],
      false,
      'ROAD_AREA'
    )
  ).toEqual([
    [
      [5, 4.5],
      [5, 5.5],
    ],
  ]);
});
