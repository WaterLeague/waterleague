import { expect, it } from 'vitest';
import type { LiveRainfall } from '../../rainfall/entity/liveRainfall';
import { waterWeather } from './waterAppearanceService';
const now = Date.parse('2026-10-19T06:00:00Z');
it('최신 선택 구의 기상 풍향을 이동 방향으로 변환하고 오래된 바람을 제외', () => {
  const value = {
    districts: [
      {
        districtId: '1',
        observedAt: new Date(now).toISOString(),
        windSpeedMs: 3,
        windDirectionDeg: 90,
        oneMinuteMm: 0.4,
      },
      {
        districtId: '2',
        observedAt: new Date(now - 300001).toISOString(),
        windSpeedMs: 100,
        windDirectionDeg: 180,
        oneMinuteMm: 10,
      },
    ],
  } as LiveRainfall;
  const current = waterWeather(value, '1', now);
  expect(current.wind[0]).toBeCloseTo(-3);
  expect(current.wind[1]).toBeCloseTo(0);
  expect(current.rain).toBe(0.4);
  expect(waterWeather(value, '2', now)).toEqual({ wind: [0, 0], rain: 0 });
});
it('무풍 코드·풍향 결측·관측 공백에서 임의 유향을 생성하지 않음', () => {
  const value = {
    districts: [
      {
        districtId: '1',
        observedAt: new Date(now).toISOString(),
        windSpeedMs: 3,
        windDirectionDeg: 360,
        oneMinuteMm: 0,
      },
    ],
  } as LiveRainfall;
  expect(waterWeather(value, '', now).wind).toEqual([0, 0]);
  expect(waterWeather(null, '', now)).toEqual({ wind: [0, 0], rain: 0 });
});
