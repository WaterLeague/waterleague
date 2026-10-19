import { expect, it } from 'vitest';
import raw2022 from '../../../../public/data/water-weather-v2/seoul-20220808.json';
import raw2011 from '../../../../public/data/water-weather-v2/seoul-20110727.json';
import raw2010 from '../../../../public/data/water-weather-v2/seoul-20100921.json';
import { archivedWeatherDto } from '../dto/archivedWeatherDto';
import { archivedWindAt } from './archivedWeatherService';
import { observedWind } from '../../surface/service/waterAppearanceService';
const district = '2419953';
it('같은 구의 원 관측소 분 풍향·풍속과 시각 경계를 보존', () => {
  const value = archivedWeatherDto.parse(raw2022);
  expect(archivedWindAt(value, value.eventId, '2022-08-08T18:00:00+09:00', district)).toEqual({
    windSpeedMs: 1.5,
    windDirectionDeg: 225.3,
  });
  expect(archivedWindAt(value, value.eventId, '2022-08-08T18:30:59+09:00', district)).toEqual({
    windSpeedMs: 1.5,
    windDirectionDeg: 327.8,
  });
  for (const at of ['2022-08-08T17:59:59+09:00', '2022-08-08T23:59:00+09:00', 'invalid'])
    expect(archivedWindAt(value, value.eventId, at, district)).toBeUndefined();
  expect(archivedWindAt(value, 'seoul-20110727', value.start, district)).toBeUndefined();
  expect(archivedWindAt(value, value.eventId, value.start, 'unavailable')).toBeUndefined();
  expect(archivedWindAt(null, value.eventId, null, district)).toBeUndefined();
});
it('세 사건의 25개 구를 원문 해시로 연결하고 무풍·결측 방향을 생성하지 않음', () => {
  for (const raw of [raw2022, raw2011, raw2010]) {
    const value = archivedWeatherDto.parse(raw);
    expect(value.stations.flatMap((s) => s.districtIds)).toHaveLength(25);
    expect(value.stations.every((s) => s.sourceSha256.length === 64)).toBe(true);
  }
  const value = archivedWeatherDto.parse(raw2010);
  const wind = archivedWindAt(value, value.eventId, '2010-09-21T10:30:00+09:00', district)!;
  expect(wind).toEqual({ windSpeedMs: 0, windDirectionDeg: null });
  expect(observedWind(wind.windSpeedMs, wind.windDirectionDeg)).toEqual([0, 0]);
  expect(observedWind(5, null)).toEqual([0, 0]);
  expect(observedWind(2, 270)[0]).toBeCloseTo(2);
  expect(observedWind(2, 0)).toEqual([-0, 2]);
});
it('기간·샘플 수 불일치와 중복 구·무풍의 유향 입력 거부', () => {
  const value = archivedWeatherDto.parse(raw2022);
  expect(archivedWeatherDto.safeParse({ ...value, end: value.start }).success).toBe(false);
  expect(
    archivedWeatherDto.safeParse({ ...value, stations: [...value.stations, value.stations[0]] })
      .success
  ).toBe(false);
  value.stations[0].samples[0] = [0, 90];
  expect(archivedWeatherDto.safeParse(value).success).toBe(false);
});
