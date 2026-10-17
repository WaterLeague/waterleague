import { afterEach, expect, it, vi } from 'vitest';
import registryText from '../../../../public/data/maps.json?raw';
import legacyText from '../../../../public/data/seongsu.json?raw';
import topographyText from '../../../../public/data/seongsu-ngii-v2.json?raw';
import rainfallText from '../../../../public/data/rainfall-audit.json?raw';
import { loadCatalog } from './catalogRepository';
import { CatalogError } from '../exception/CatalogError';
const files: Record<string, string> = {
  ...Object.fromEntries(
    Object.entries(
      import.meta.glob<string>('../../../../public/data/seoul-osm-v1-*.json', {
        query: '?raw',
        import: 'default',
        eager: true,
      })
    ).map(([path, content]) => ['/data/' + path.split('/').at(-1), content])
  ),
  '/data/maps.json': registryText,
  '/data/seongsu.json': legacyText,
  '/data/seongsu-ngii-v2.json': topographyText,
  '/data/rainfall-audit.json': rainfallText,
};
const source = (path: string) => files[path];
afterEach(() => vi.unstubAllGlobals());
it('모든 모델을 해시가 검증된 자기 지도에 연결', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => new Response(source(path)))
  );
  const catalog = await loadCatalog(new AbortController().signal);
  expect(catalog.maps.slice(0, 2).map((entry) => entry.map.buildings.length)).toEqual([94, 246]);
  expect(catalog.maps).toHaveLength(27);
  expect(catalog.maps.slice(2).every((entry) => entry.map.buildings.length >= 8)).toBe(true);
  expect(catalog.maps.flatMap((entry) => entry.modelHashes)).toHaveLength(83);
});
it('지도 원문 변조를 조용히 다른 지도에 대체하지 않고 거부', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (path: string) =>
        new Response(source(path) + (path.endsWith('seongsu-ngii-v2.json') ? ' ' : ''))
    )
  );
  await expect(loadCatalog(new AbortController().signal)).rejects.toBeInstanceOf(CatalogError);
});
it('모델 하나가 여러 지도에 등록되면 거부', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => {
      const text = source(path);
      if (!path.endsWith('maps.json')) return new Response(text);
      const registry = JSON.parse(text);
      registry.maps[1].modelHashes.push(registry.maps[0].modelHashes[0]);
      return Response.json(registry);
    })
  );
  await expect(loadCatalog(new AbortController().signal)).rejects.toBeInstanceOf(CatalogError);
});
