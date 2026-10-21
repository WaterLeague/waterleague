import { expect, it, vi, afterEach, beforeEach } from 'vitest';
import registryText from '../../../../public/data/seoul-native-v1/game.json?raw';
import city from '../../../../public/data/seoul-native-v1/city.json';
let loadCityPlayRegions: typeof import('../repository/cityDataSource').loadCityPlayRegions;
beforeEach(async () => {
  vi.resetModules();
  ({ loadCityPlayRegions } = await import('../repository/cityDataSource'));
});
import { cityPlayDto } from '../dto/cityPlayDto';
afterEach(() => vi.unstubAllGlobals());
it('서울의 모든 구를 각기 다른 플레이 모델과 연결', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(registryText))
  );
  const regions = await loadCityPlayRegions(new AbortController().signal);
  expect(regions.map((r) => r.districtId).sort()).toEqual(city.districts.map((d) => d.id).sort());
  expect(new Set(regions.flatMap((r) => r.modelHashes)).size).toBe(100);
  expect(regions.filter((r) => r.defaultRainfall)).toHaveLength(25);
  expect(regions.find((r) => r.districtName === '강서구')?.modelHashes).toHaveLength(4);
  for (const r of regions) expect(r.modelHashes).toContain(r.defaultModelHash);
});
it('변조된 플레이 목록과 중복 구역을 거부', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(registryText + ' '))
  );
  await expect(loadCityPlayRegions(new AbortController().signal)).rejects.toHaveProperty(
    'name',
    'CityError'
  );
  const copy = JSON.parse(registryText);
  copy.regions[1] = copy.regions[0];
  expect(cityPlayDto.safeParse(copy).success).toBe(false);
});
