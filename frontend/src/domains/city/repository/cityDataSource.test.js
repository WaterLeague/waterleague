import { readFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
import { afterEach, expect, test, vi } from 'vitest';
import city from '../../../../public/data/seoul-native-v1/city.json';
const publicRoot = new URL('../../../../public', import.meta.url);
afterEach(() => vi.unstubAllGlobals());
test('백그라운드 지도 로더가 가장 큰 원 타일과 도시 요소를 누락 없이 검증', async () => {
  vi.resetModules();
  vi.stubGlobal('caches', undefined);
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path) => new Response(await readFile(new URL(publicRoot.href + path))))
  );
  const { loadCity, loadCityTile } = await import('./cityDataSource');
  const value = await loadCity(new AbortController().signal);
  expect(value.districts).toEqual(city.districts);
  const entry = value.tiles.reduce((a, b) => (a.bytes > b.bytes ? a : b));
  const tile = await loadCityTile(entry, new AbortController().signal);
  const raw = JSON.parse(
    gunzipSync(
      await readFile(new URL(publicRoot.href + '/data/seoul-native-v1/' + entry.file))
    ).toString()
  );
  const urban = JSON.parse(
    gunzipSync(
      await readFile(
        new URL(publicRoot.href + '/data/seoul-street-life-v1/tiles/' + entry.id + '.json.gz')
      )
    ).toString()
  );
  expect(tile).toEqual({ ...raw, urban });
});
