import { expect, test } from 'vitest';
import { visibleTraceTiles } from './floodTraceService';
import { tracePositions } from './traceGeometryService';
import type { TraceEvent } from '../entity/floodTrace';

test('경계에 닿는 표시 타일 포함과 미확보 사건 제외', () => {
  const event = {
    tiles: [
      { id: '0_0', bounds: [0, 0, 4000, 4000] },
      { id: '1_0', bounds: [4000, 0, 8000, 4000] },
    ],
  } as TraceEvent;
  expect(
    visibleTraceTiles(event, { center: [3850, 2000], distance: 100 }).map((t) => t.id)
  ).toEqual(['0_0', '1_0']);
  expect(
    visibleTraceTiles(event, { center: [2000, 2000], distance: 100 }).map((t) => t.id)
  ).toEqual(['0_0']);
  expect(visibleTraceTiles(undefined, { center: [0, 0], distance: 30000 })).toEqual([]);
});

test('표시 지형에만 투영하고 수심 생성 없이 2D와 같은 평면 좌표 유지', () => {
  const positions = tracePositions([{ triangleVertices: [0, 90, 90, 90, 0, 0] }], {
    width: 2,
    height: 2,
    origin: [0, 90],
    spacing: [90, -90],
    districtIds: [],
    heights: new Float32Array([10, 30, 50, 70]),
    districts: new Uint8Array(4),
    cover: new Uint8Array(4),
  });
  expect(Array.from(positions)).toEqual([
    0,
    expect.closeTo(10.016),
    -90,
    90,
    expect.closeTo(30.016),
    -90,
    0,
    expect.closeTo(50.016),
    -0,
  ]);
});
