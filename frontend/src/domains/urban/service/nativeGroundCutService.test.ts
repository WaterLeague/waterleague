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
