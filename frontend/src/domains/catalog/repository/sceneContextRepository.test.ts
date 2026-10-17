import { afterEach, expect, it, vi } from 'vitest';
import registry from '../../../../public/data/maps.json';
import base from '../../../../public/data/seoul-osm-v1-2410520.json';
import raw from '../../../../public/data/seoul-context-v1-2410520.json?raw';
import { mapDto } from '../dto/catalogDto';
import { toCandidateMap } from '../mapper/catalogMapper';
import { loadSceneContext } from './sceneContextRepository';
import { CatalogError } from '../exception/CatalogError';
const entry = registry.maps.find((m) => m.id === base.id)!;
const contextSource = { ...entry.context!, baseMapSha256: entry.sha256 };
const map = { ...toCandidateMap(mapDto.parse(base)), contextSource };
afterEach(() => vi.unstubAllGlobals());
it('주변 자료가 없는 기존 지도는 외부 요청 없이 유지', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  expect(
    await loadSceneContext(toCandidateMap(map.snapshot), new AbortController().signal)
  ).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});
it('변조되거나 다른 원점에 연결된 주변 자료 거부', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(raw))
  );
  await expect(
    loadSceneContext(
      { ...map, contextSource: { ...contextSource, sha256: '0'.repeat(64) } },
      new AbortController().signal
    )
  ).rejects.toBeInstanceOf(CatalogError);
  await expect(
    loadSceneContext(
      { ...map, snapshot: { ...map.snapshot, originProjected: [0, 0] } },
      new AbortController().signal
    )
  ).rejects.toBeInstanceOf(CatalogError);
});
it('선택 지역의 검증된 자료만 캐시하며 계산 지도 원문 유지', async () => {
  const fetch = vi.fn(async () => new Response(raw));
  vi.stubGlobal('fetch', fetch);
  const before = JSON.stringify(map.snapshot);
  const context = await loadSceneContext(map, new AbortController().signal);
  expect(context?.modelInput).toBe(false);
  expect(context?.features.filter((f) => f.kind === 'road')).toHaveLength(276);
  expect(context?.features.filter((f) => f.kind === 'green')).toHaveLength(8);
  expect(await loadSceneContext(map, new AbortController().signal)).toBe(context);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledWith(
    '/data/' + entry.context!.file,
    expect.objectContaining({ credentials: 'same-origin' })
  );
  expect(JSON.stringify(map.snapshot)).toBe(before);
});
