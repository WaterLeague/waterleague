import { expect, it } from 'vitest';
import { daylight, solarPosition } from './solarService';
it('서울 여름 정오의 남쪽 높은 태양·밤의 지평선 아래 태양 구분', () => {
  const noon = solarPosition(Date.parse('2022-08-08T12:30:00+09:00'));
  expect(noon.elevation).toBeGreaterThan(65);
  expect(noon.elevation).toBeLessThan(72);
  expect(noon.azimuth).toBeGreaterThan(170);
  expect(noon.azimuth).toBeLessThan(190);
  expect(noon.direction[2]).toBeGreaterThan(0);
  expect(solarPosition(Date.parse('2022-08-08T23:00:00+09:00')).elevation).toBeLessThan(-20);
});
it('동쪽 일출·서쪽 일몰과 실제 날짜별 계절 차이 유지', () => {
  const morning = solarPosition(Date.parse('2022-08-08T07:00:00+09:00'));
  const evening = solarPosition(Date.parse('2022-08-08T18:00:00+09:00'));
  expect(morning.direction[0]).toBeGreaterThan(0);
  expect(evening.direction[0]).toBeLessThan(0);
  const winter = solarPosition(Date.parse('2022-12-21T12:30:00+09:00'));
  expect(winter.elevation).toBeLessThan(31);
  expect(daylight(-6)).toBe(0);
  expect(daylight(10)).toBe(1);
});
