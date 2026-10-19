import { expect, it } from 'vitest';
import { historicalWeather } from './historicalWeather';
import type { DisasterCatalog } from '../../disaster/entity/disaster';
const event = {
  regions: Array.from({ length: 25 }, (_, i) => ({
    districtId: String(i),
    stationName: `시험 관측소 ${i}`,
    depthsMm: [i === 0 ? 0.5 : 0, 0],
  })),
} as DisasterCatalog['events'][number];
it('전체는 구별 관측 범위, 이동한 구는 해당 관측 강우로 전환', () => {
  expect(historicalWeather(event, 0, '', '').amount).toBe('1분 강우 0–0.5 mm');
  expect(historicalWeather(event, 0, '', '').label).toBe('1개 구 비');
  expect(historicalWeather(event, 0, '0', '시험구').place).toBe('시험구');
  expect(historicalWeather(event, 0, '0', '시험구').amount).toBe('1분 강우 0.5 mm');
  expect(historicalWeather(event, 0, '1', '다른구').amount).toBe('1분 강우 0 mm');
  expect(historicalWeather(event, 1, '', '').kind).toBe('dry');
});
it('확보하지 않은 구와 기간 밖 관측을 무강우로 대체하지 않음', () => {
  expect(historicalWeather(event, 0, 'missing', '미확보구').kind).toBe('unknown');
  expect(historicalWeather(event, 2, '', '').amount).toBe('강우량 확인 불가');
  expect(historicalWeather(undefined, 0, '', '').kind).toBe('unknown');
  expect(historicalWeather({ ...event, regions: event.regions.slice(1) }, 1, '', '').kind).toBe(
    'unknown'
  );
});
