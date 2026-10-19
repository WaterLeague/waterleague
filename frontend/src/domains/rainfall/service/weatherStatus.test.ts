import { describe, it, expect } from 'vitest';
import { weatherStatus } from './weatherStatus';
import type { LiveRainfall } from '../entity/liveRainfall';
const now = Date.parse('2026-10-19T06:00:00Z');
const value = (state: string, age = 0) =>
  ({
    districts: Array.from({ length: 25 }, (_, i) => ({
      districtId: String(i),
      districtName: `구${i}`,
      stationName: `지점${i}`,
      rainState: state,
      rainObservedAt: new Date(now - age).toISOString(),
    })),
  }) as LiveRainfall;
describe('날씨 상태의 관측 공백 구분', () => {
  it('0mm나 결측·오래된 관측을 비 없음으로 표시하지 않는다', () => {
    expect(weatherStatus(null, '', now).kind).toBe('unknown');
    expect(weatherStatus(value('UNKNOWN'), '', now).kind).toBe('unknown');
    expect(weatherStatus(value('NO_RAIN_DETECTED', 300001), '', now).kind).toBe('unknown');
    expect(weatherStatus(value('NO_RAIN_DETECTED', -1), '', now).kind).toBe('unknown');
  });
  it('서울 전체 비 없음은 25개 구의 유효 감지 결과를 요구한다', () => {
    const v = value('NO_RAIN_DETECTED');
    expect(weatherStatus(v, '', now).kind).toBe('dry');
    v.districts[3].rainState = 'UNKNOWN';
    expect(weatherStatus(v, '', now).kind).toBe('unknown');
    expect(weatherStatus(v, '2', now).kind).toBe('dry');
  });
  it('유효한 비·눈 감지 지역을 선택 구 또는 전체 집계로 표시한다', () => {
    const v = value('UNKNOWN');
    v.districts[3].rainState = 'WET';
    expect(weatherStatus(v, '', now).label).toBe('1개 구 비');
    expect(weatherStatus(v, '3', now).label).toBe('비 오는 중');
    v.districts[3].rainState = 'SNOW';
    expect(weatherStatus(v, '3', now).kind).toBe('snow');
  });
});

it('감지 신호 결측에도 실제 관측된 분강우 0을 표시하고 지연·미래 관측은 제외', () => {
  const v = value('UNKNOWN');
  Object.assign(v.districts[0], { observedAt: new Date(now).toISOString(), oneMinuteMm: 0 });
  expect(weatherStatus(v, '0', now).amount).toBe('1분 강우 0 mm');
  expect(weatherStatus(v, '0', now).kind).toBe('unknown');
  v.districts[0].observedAt = new Date(now - 300001).toISOString();
  expect(weatherStatus(v, '0', now).amount).toBe('강우량 확인 불가');
  v.districts[0].observedAt = new Date(now + 1000).toISOString();
  expect(weatherStatus(v, '0', now).amount).toBe('강우량 확인 불가');
});
it('유효한 무강수 감지는 0으로 표시하고 비 감지 중 미확보량은 생성하지 않음', () => {
  expect(weatherStatus(value('NO_RAIN_DETECTED'), '0', now).amount).toBe('1분 강우 0 mm');
  expect(weatherStatus(value('WET'), '0', now).amount).toBe('강우량 확인 불가');
});
