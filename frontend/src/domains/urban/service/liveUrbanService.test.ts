import { expect, it } from 'vitest';
import type { LivePlace } from '../entity/liveUrban';
import { freshReading, livePlaceAt, visibleLiveAreas } from './liveUrbanService';
import { advanceTravel } from './streetLifeService';
import { displayDensity } from './populationService';
const place: LivePlace = {
  id: 'POI001',
  name: '시험 장소',
  areaKm2: 1,
  bounds: [0, 0, 100, 100],
  polygons: [
    [
      [
        [0, 0],
        [100, 0],
        [100, 100],
        [0, 100],
        [0, 0],
      ],
      [
        [20, 20],
        [40, 20],
        [40, 40],
        [20, 40],
        [20, 20],
      ],
    ],
  ],
  population: null,
  traffic: null,
};
it('공식 경계 밖·도형 구멍 제외 및 중첩 장소의 중복 합산 방지', () => {
  expect(livePlaceAt([place], 150, 10)).toBeUndefined();
  expect(livePlaceAt([place], 30, 30)).toBeUndefined();
  expect(livePlaceAt([place], 10, 10)?.id).toBe('POI001');
  const small = { ...place, id: 'POI002', areaKm2: 0.2 };
  expect(livePlaceAt([place, small], 10, 10)?.id).toBe('POI002');
  expect(livePlaceAt([small, place], 10, 10)?.id).toBe('POI002');
});
it('현재 시야와 가까운 공개 장소 선택·확대 전 조회 생략', () => {
  expect(visibleLiveAreas([place], [50, 50], 1000)).toHaveLength(1);
  expect(visibleLiveAreas([place], [10000, 10000], 1000)).toHaveLength(0);
  expect(visibleLiveAreas([place], [50, 50], 8500)).toHaveLength(0);
});
it('자료 만료 경계와 미래 조회 시각 차단', () => {
  const reading = { retrievedAt: '2026-10-19T09:00:00Z', validUntil: '2026-10-19T09:05:00Z' };
  expect(freshReading(reading, Date.parse('2026-10-19T09:04:59Z'))).toBe(reading);
  expect(freshReading(reading, Date.parse('2026-10-19T09:05:00Z'))).toBeNull();
  expect(freshReading(reading, Date.parse('2026-10-19T08:50:00Z'))).toBeNull();
});
it('속도 변경 시 위치 연속 유지·0km/h 정지·숨긴 화면 이후 큰 이동 억제', () => {
  const start = { time: 100, distance: 500 };
  expect(advanceTravel(start, 100, 30)).toEqual(start);
  const moved = advanceTravel(start, 101, 10);
  expect(moved.distance).toBe(510);
  expect(advanceTravel(moved, 102, 0).distance).toBe(510);
  expect(advanceTravel(moved, 1001, 10).distance).toBe(530);
});
it('1km² 미만 공개 장소도 실제 면적에 비례하는 밀도 계산', () => {
  expect(displayDensity(1500, 0.1)).toBe(1);
  expect(displayDensity(15000, 1)).toBe(1);
});
