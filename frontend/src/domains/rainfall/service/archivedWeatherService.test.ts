import { expect, it } from 'vitest';
import raw from '../../../../public/data/water-weather-v1.json';
import { archivedWeatherDto } from '../dto/archivedWeatherDto';
import { archivedWindAt } from './archivedWeatherService';
it('재해 시각의 보관 풍속만 선택하고 원본 해시와 시간 해상도를 보존', () => {
  const value = archivedWeatherDto.parse(raw);
  expect(archivedWindAt(value, 'seoul-20220808', '2022-08-08T18:30:00+09:00')).toBe(3.945);
  expect(archivedWindAt(value, 'seoul-20220808', '2022-08-09T01:00:00+09:00')).toBeUndefined();
  expect(archivedWindAt(value, 'seoul-20110727', '2011-07-27T05:30:00+09:00')).toBe(2.6);
  expect(value.entries.find((e) => e.eventId === 'seoul-20110727')?.resolution).toBe('DAY');
  expect(archivedWindAt(null, 'seoul-20110727', null)).toBeUndefined();
});
