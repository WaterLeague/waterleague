import { afterEach, expect, test, vi } from 'vitest';

afterEach(() => vi.unstubAllGlobals());

test('같은 공개 도로 타일 범위의 확대·축소는 요청과 형상을 재사용하며 다른 범위는 갱신', async () => {
  vi.resetModules();
  const files = import.meta.glob<string>('../../../../public/data/seoul-streets-v1/**/*.json', {
    query: '?raw',
    import: 'default',
  });
  const fetchMock = vi.fn(async (path: string) => {
    if (!path.startsWith('/data/seoul-streets-v1/')) throw new Error('검증 범위 밖 요청');
    const raw = await files['../../../../public' + path]();
    return new Response(raw);
  });
  vi.stubGlobal('fetch', fetchMock);
  const { loadStreets } = await import('./urbanRepository');
  const signal = new AbortController().signal;
  const first = await loadStreets([500, 500], 800, signal);
  const requests = fetchMock.mock.calls.length;
  expect(first.length).toBeGreaterThan(0);
  expect(await loadStreets([500, 500], 810, signal)).toBe(first);
  expect(fetchMock).toHaveBeenCalledTimes(requests);
  const moved = await loadStreets([6500, -4500], 800, signal);
  expect(moved).not.toBe(first);
  expect(moved.map((road) => road.id)).not.toEqual(first.map((road) => road.id));
  const afterMove = fetchMock.mock.calls.length;
  expect(await loadStreets([500, 500], 800, signal)).toBe(first);
  expect(fetchMock).toHaveBeenCalledTimes(afterMove);
});
