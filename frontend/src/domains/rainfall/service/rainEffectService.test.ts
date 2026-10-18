import { expect, it } from 'vitest';
import {
  isRaining,
  rainCondition,
  rainEvidenceLabel,
  rainParticleSeeds,
  rainSamplingWindow,
  rainVisualDensity,
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
  rainObservedAt: new Date(at).toISOString(),
  rainEvidence: 'AWS_RAIN_SENSOR',
  presentWeatherCode: null,
  temperatureC: 20,
  humidityPercent: 60,
  windSpeedMs: 0,
  pressureHpa: 1000,
};
it('구별 분 강수량이 증가하면 표현 밀도가 증가하고 표시 상한 유지', () => {
  expect(rainVisualDensity(0.1)).toBeGreaterThan(rainVisualDensity(null));
  expect(rainVisualDensity(1)).toBeGreaterThan(rainVisualDensity(0.1));
  expect(rainVisualDensity(2)).toBeGreaterThan(rainVisualDensity(1));
  expect(rainVisualDensity(1000)).toBe(1.6);
  expect(rainVisualDensity(Number.NaN)).toBe(rainVisualDensity(null));
});
it('과거 누적 강우와 결측·지연을 현재 비 효과로 사용하지 않음', () => {
  expect(isRaining(station, at + 120000)).toBe(false);
  const wet = { ...station, rainDetected: true, rainState: 'WET' as const };
  expect(isRaining(wet, at + 120000)).toBe(true);
  expect(isRaining(wet, at + 300001)).toBe(false);
  expect(isRaining(wet, at - 1)).toBe(false);
  expect(isRaining({ ...wet, rainObservedAt: null }, at)).toBe(false);
  expect(isRaining({ ...wet, rainState: 'UNKNOWN' }, at)).toBe(false);
  expect(rainCondition(wet, at + 300001)).toBe('현재 강수 확인 불가');
});
it('강수량 0이어도 현천의 비 감지를 표시하고 별도 관측 시각으로 만료', () => {
  const drizzle: RainStation = {
    ...station,
    rainState: 'WET',
    rainDetected: null,
    rainEvidence: 'AWS_PRESENT_WEATHER',
    presentWeatherCode: 51,
    observedAt: new Date(at - 600000).toISOString(),
  };
  expect(isRaining(drizzle, at + 120000)).toBe(true);
  expect(rainEvidenceLabel(drizzle)).toBe('현천 관측 · 코드 51');
  expect(isRaining(drizzle, at + 300001)).toBe(false);
  expect(isRaining({ ...drizzle, rainState: 'SNOW' }, at)).toBe(false);
  expect(rainCondition({ ...drizzle, rainState: 'SNOW' }, at)).toBe('최근 관측에서 눈 감지');
});
it('작은 확대·축소와 이동은 같은 비 입자 영역을 재사용', () => {
  const base = rainSamplingWindow([200100, 450100], 3000);
  expect(rainSamplingWindow([200130, 450070], 3200)).toEqual(base);
  expect(rainSamplingWindow([200100, 450100], 4200).scale).toBeGreaterThan(base.scale);
});
it('입자 영역은 확대 단계와 이동 경계에서도 카메라 범위를 포함', () => {
  for (const distance of [15, 255, 256, 257, 4095, 4096, 4097, 35000]) {
    for (const center of [
      [200100, 450100],
      [-1025, 1025],
      [2047, 2049],
    ] as [number, number][]) {
      const window = rainSamplingWindow(center, distance);
      expect(window.x - window.radius).toBeLessThanOrEqual(center[0] - distance);
      expect(window.x + window.radius).toBeGreaterThanOrEqual(center[0] + distance);
      expect(window.y - window.radius).toBeLessThanOrEqual(center[1] - distance);
      expect(window.y + window.radius).toBeGreaterThanOrEqual(center[1] + distance);
    }
  }
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
