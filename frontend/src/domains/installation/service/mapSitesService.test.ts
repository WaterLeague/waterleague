import { expect, test } from 'vitest';
import { mapSiteQuery } from './mapSitesService';
import type { SiteQuery } from '../repository/installationRepository';

test('종류·지면·빈 위치·페이지 변경에도 지도 주변 후보 조회 범위 유지', () => {
  const query: SiteQuery = {
    districtId: '2410520',
    x: 125,
    y: 240,
    offset: 0,
    type: '',
    vacant: false,
    surface: '',
  };
  const before = JSON.stringify(query);
  expect(
    mapSiteQuery({ ...query, type: 'GREEN_ROOF', surface: 'ROADWAY', vacant: true, offset: 200 })
  ).toEqual(mapSiteQuery(query));
  expect(JSON.stringify(query)).toBe(before);
  expect(mapSiteQuery({ ...query, x: 126, districtId: '2410510' })).toEqual({
    ...query,
    x: 126,
    districtId: '2410510',
  });
});
