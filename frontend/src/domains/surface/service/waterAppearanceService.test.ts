import { expect, it } from 'vitest';
import type { LiveRainfall } from '../../rainfall/entity/liveRainfall';
import { observedWind, waterWeather } from './waterAppearanceService';
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
it('관측 북풍·남풍의 지리 방향과 결측·비정상 풍향의 이동 중지', () => {
  expect(observedWind(3, 0)[1]).toBeCloseTo(3);
  expect(observedWind(3, 180)[1]).toBeCloseTo(-3);
  for (const direction of [null, undefined, -1, 360, NaN, Infinity])
    expect(observedWind(3, direction)).toEqual([0, 0]);
  for (const speed of [null, undefined, 0, -1, NaN, Infinity])
    expect(observedWind(speed, 90)).toEqual([0, 0]);
});
it('풍향 결측에도 유효한 풍속을 보존하고 무풍·오래된 풍속을 구분', () => {
  const station = {
    districtId: '1',
    observedAt: new Date(now).toISOString(),
    windSpeedMs: 2.5,
    windDirectionDeg: null,
    oneMinuteMm: 0,
  };
  const read = (changes = {}) =>
    waterWeather({ districts: [{ ...station, ...changes }] } as LiveRainfall, '1', now);
  expect(read()).toEqual({ wind: [0, 0], rain: 0, windSpeed: 2.5 });
  expect(read({ windSpeedMs: 0 })).toEqual({ wind: [0, 0], rain: 0, windSpeed: 0 });
  for (const windSpeedMs of [null, -1, NaN, Infinity])
    expect(read({ windSpeedMs })).toEqual({ wind: [0, 0], rain: 0 });
  expect(read({ observedAt: new Date(now - 300001).toISOString() })).toEqual({
    wind: [0, 0],
    rain: 0,
  });
});
it('반대 풍향이 상쇄되어도 실제 풍속의 평균 강도를 보존', () => {
  const value = {
    districts: [0, 180].map((windDirectionDeg) => ({
      districtId: String(windDirectionDeg),
      observedAt: new Date(now).toISOString(),
      windSpeedMs: 3,
      windDirectionDeg,
      oneMinuteMm: 0,
    })),
  } as LiveRainfall;
  const current = waterWeather(value, '', now);
  expect(Math.hypot(...current.wind)).toBeCloseTo(0);
  expect(current.windSpeed).toBe(3);
});
