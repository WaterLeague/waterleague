import { expect, test, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
const requests: string[] = [];
vi.mock('../src/shared/repository/publicDataCache', () => ({
  readPublicData: async (url: string, hash: string, bytes: number) => {
    requests.push(url);
    const stored = readFileSync('public' + url),
      raw = url.endsWith('.gz') ? gunzipSync(stored) : stored;
    expect(createHash('sha256').update(raw).digest('hex')).toBe(hash);
    expect(raw.length).toBeLessThanOrEqual(bytes);
    return JSON.parse(raw.toString());
  },
}));
import { loadCityOverview } from '../src/domains/city/repository/cityOverviewRepository';
import { CITY_HASH } from '../src/domains/city/repository/cityRepository';
test('선택 구별 건물만 내려받고 전체 축소도 및 다른 구 요청 제외', async () => {
  const value = await loadCityOverview(100, CITY_HASH, new AbortController().signal, [
    '11110',
    '11680',
  ]);
  expect(value.buildings.length).toBeGreaterThan(0);
  expect(new Set(value.buildings.map((b) => value.districts[b[5]]))).toEqual(
    new Set(['11110', '11680'])
  );
  expect(requests).toEqual([
    '/data/seoul-overview-v1/index.json',
    '/data/seoul-overview-v1/districts/11110/100.json.gz',
    '/data/seoul-overview-v1/districts/11680/100.json.gz',
  ]);
  expect(
    await loadCityOverview(100, CITY_HASH, new AbortController().signal, ['11680', '11110'])
  ).toBe(value);
  expect(requests.length).toBe(3);
});
test('서울 전체 확대 자료 381499개를 누락 없이 읽고 재사용', async () => {
  const index = JSON.parse(readFileSync('public/data/seoul-overview-v1/index.json', 'utf8'));
  const expected = JSON.parse(
    gunzipSync(readFileSync('public/data/seoul-overview-v1/25.json.gz')).toString()
  ).buildings;
  const value = await loadCityOverview(
    25,
    CITY_HASH,
    new AbortController().signal,
    index.districts
  );
  expect(value.buildings).toEqual(expected);
  expect(value.buildings).toHaveLength(381499);
  const requestCount = requests.length;
  expect(await loadCityOverview(25, CITY_HASH, new AbortController().signal)).toBe(value);
  expect(requests).toHaveLength(requestCount);
});

import {
  competitionCity,
  scopeCityTile,
  scopeTopography,
} from '../src/domains/city/service/competitionMapService';
import { mapScope, scopeIntersects } from '../src/shared/service/mapScope';
import type { City, CityTile } from '../src/domains/city/entity/city';
test('원 서울 자료 보존 및 선택 구 바깥의 상세 타일과 요소 제외', () => {
  const city = JSON.parse(readFileSync('public/data/seoul-native-v1/city.json', 'utf8')) as City;
  const selected = competitionCity(city, ['11680', '11710']);
  const scope = mapScope(selected.districts);
  expect(selected.districts.map((d) => d.id).sort()).toEqual(['11680', '11710']);
  expect(selected.tiles.length).toBeLessThan(city.tiles.length / 2);
  expect(selected.tiles.every((t) => scopeIntersects(t.bounds, scope))).toBe(true);
  expect(city.districts.length).toBe(25);
  expect(
    competitionCity(
      city,
      city.districts.map((d) => d.id)
    )
  ).toBe(city);
  const tile = {
    buildings: [{ districtId: '11110' }, { districtId: '11680' }],
    nativeFeatures: [],
    urban: { crosswalks: [], walkPaths: [], parkingLots: [] },
  } as unknown as CityTile;
  expect(scopeCityTile(tile, scope).buildings.map((b) => b.districtId)).toEqual(['11680']);
  expect(tile.buildings.length).toBe(2);
});
test('경계 타일에서도 대회 외 지명과 지형지물 형상 제외', () => {
  const scope = mapScope([
    {
      id: '11680',
      polygons: [
        [
          [
            [0, 0],
            [10, 0],
            [10, 10],
            [0, 10],
            [0, 0],
          ],
        ],
      ],
    },
  ]);
  const tile = {
    id: '0_0',
    points: [
      [
        0,
        'p',
        [
          [5, 5],
          [20, 20],
        ],
        '지명',
      ],
    ],
    lines: [
      [
        0,
        'l',
        [
          [
            [-10, 5],
            [20, 5],
          ],
        ],
        null,
      ],
    ],
    areas: [],
  } as Parameters<typeof scopeTopography>[0];
  const selected = scopeTopography(tile, scope);
  expect(selected.points[0][2]).toEqual([[5, 5]]);
  expect(selected.lines[0][2]).toEqual([
    [
      [0, 5],
      [10, 5],
    ],
  ]);
  expect(tile.points[0][2]).toHaveLength(2);
});
