import { expect, it } from 'vitest';
import {
  isRaining,
  rainCondition,
  rainParticleSeeds,
  insideRainArea,
  type RainStation,
  type RainPolygons,
} from './rainEffectService';

const at = Date.parse('2026-10-17T12:00:00Z');
const station: RainStation = {
  districtId: 'gu',
  districtName: '검증 구',
  stationId: '1',
  stationName: '검증 관측소',
  observedAt: new Date(at).toISOString(),
  ageSeconds: 120,
  status: 'CURRENT',
  fifteenMinuteMm: 5,
  sixtyMinuteMm: 20,
  dayMm: 30,
  rainDetected: false,
  oneMinuteMm: 0,
  rainState: 'NO_RAIN_DETECTED',
};
it('과거 누적 강우와 결측·지연을 현재 비 효과로 사용하지 않음', () => {
  expect(isRaining(station, at + 120000)).toBe(false);
  const wet = { ...station, rainDetected: true, rainState: 'WET' as const };
  expect(isRaining(wet, at + 120000)).toBe(true);
  expect(isRaining(wet, at + 300001)).toBe(false);
  expect(isRaining(wet, at - 1)).toBe(false);
  expect(isRaining({ ...wet, observedAt: null }, at)).toBe(false);
  expect(isRaining({ ...wet, rainState: 'UNKNOWN' }, at)).toBe(false);
  expect(rainCondition(wet, at + 300001)).toBe('현재 강수 확인 불가');
});
it('비 입자는 구 경계 안이며 구멍과 카메라 범위 밖을 제외', () => {
  const polygons: RainPolygons = [
    [
      [
        [0, 0],
        [10, 0],
        [10, 10],
        [0, 10],
        [0, 0],
      ],
      [
        [3, 3],
        [7, 3],
        [7, 7],
        [3, 7],
        [3, 3],
      ],
    ],
  ];
  const seeds = rainParticleSeeds(polygons, [5, 5], 4, 240);
  expect(seeds).toHaveLength(240);
  expect(seeds.every(({ point }) => insideRainArea(point, polygons))).toBe(true);
  expect(seeds.every(({ point: [x, y] }) => x >= 1 && x <= 9 && y >= 1 && y <= 9)).toBe(true);
  expect(insideRainArea([5, 5], polygons)).toBe(false);
  expect(rainParticleSeeds(polygons, [100, 100], 5, 240)).toHaveLength(0);
});
