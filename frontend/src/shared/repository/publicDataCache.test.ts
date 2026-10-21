import { afterEach, expect, test, vi } from 'vitest';
afterEach(() => vi.unstubAllGlobals());
const sha = async (s: string) =>
  [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))]
    .map((n) => n.toString(16).padStart(2, '0'))
    .join('');
test('교량 원본 결속 묶음의 32MiB 초과 예산 허용과 64MiB 상한 유지', async () => {
  vi.resetModules();
  vi.stubGlobal('caches', undefined);
  const fetcher = vi.fn(async () => new Response('{}'));
  vi.stubGlobal('fetch', fetcher);
  const { readPublicData } = await import('./publicDataCache');
  const signal = new AbortController().signal,
    hash = await sha('{}');
  expect(await readPublicData('/data/bridges.json', hash, 64000000, signal)).toEqual({});
  await expect(
    readPublicData('/data/bridges.json', hash, 64 * 1024 * 1024 + 1, signal)
  ).rejects.toThrow();
  expect(fetcher).toHaveBeenCalledOnce();
});
test('공개 해시 파일은 기기 저장소 재사용, 손상된 캐시는 원본 재검증', async () => {
  vi.resetModules();
  const entries = new Map<string, Response>();
  let putResolve: () => void = () => {};
  const saved = new Promise<void>((resolve) => (putResolve = resolve));
  const cache = {
    match: vi.fn(async (k: string) => entries.get(k)?.clone()),
    keys: vi.fn(async () => []),
    delete: vi.fn(async (k: string) => entries.delete(k)),
    put: vi.fn(async (k: string, v: Response) => {
      entries.set(k, v);
      putResolve();
    }),
  };
  vi.stubGlobal('caches', { open: async () => cache });
  const fetcher = vi.fn(async () => new Response('{"ok":true}'));
  vi.stubGlobal('fetch', fetcher);
  const { readPublicData } = await import('./publicDataCache');
  const hash = await sha('{"ok":true}'),
    signal = new AbortController().signal;
  expect(await readPublicData('/data/test.json', hash, 50, signal)).toEqual({ ok: true });
  await saved;
  expect(await readPublicData('/data/test.json', hash, 50, signal)).toEqual({ ok: true });
  expect(fetcher).toHaveBeenCalledTimes(1);
  entries.set('/data/test.json?sha256=' + hash, new Response('{"ok":false}'));
  expect(await readPublicData('/data/test.json', hash, 50, signal)).toEqual({ ok: true });
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(cache.delete).toHaveBeenCalled();
});
test('인증 API·다른 출처·경로 이탈·해시 불일치는 저장 차단', async () => {
  vi.resetModules();
  const put = vi.fn();
  vi.stubGlobal('caches', { open: async () => ({ match: async () => undefined, put }) });
  const fetcher = vi.fn(async () => new Response('{}'));
  vi.stubGlobal('fetch', fetcher);
  const { readPublicData } = await import('./publicDataCache');
  const signal = new AbortController().signal;
  for (const path of ['/api/me', 'https://example.com/data/x.json', '/data/../secret.json'])
    await expect(readPublicData(path, 'a'.repeat(64), 30, signal)).rejects.toThrow();
  expect(fetcher).not.toHaveBeenCalled();
  await expect(readPublicData('/data/x.json', 'a'.repeat(64), 30, signal)).rejects.toThrow();
  expect(put).not.toHaveBeenCalled();
});

test('압축 공개 타일은 해제한 원문 해시 검사와 해제 크기 상한 적용', async () => {
  vi.resetModules();
  vi.stubGlobal('caches', undefined);
  const raw = JSON.stringify({ buildings: ['원형 도형'] });
  const compressed = async (text: string) =>
    new Response(
      new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))
    ).arrayBuffer();
  const packed = await compressed(raw);
  const fetcher = vi.fn(async () => new Response(packed));
  vi.stubGlobal('fetch', fetcher);
  const { readPublicData } = await import('./publicDataCache');
  const signal = new AbortController().signal;
  expect(await readPublicData('/data/tile.json.gz', await sha(raw), 200, signal)).toEqual(
    JSON.parse(raw)
  );
  await expect(readPublicData('/data/tile.json.gz', 'a'.repeat(64), 200, signal)).rejects.toThrow();
  const bomb = await compressed(JSON.stringify({ value: 'x'.repeat(100000) }));
  fetcher.mockImplementation(async () => new Response(bomb));
  await expect(readPublicData('/data/tile.json.gz', await sha(raw), 200, signal)).rejects.toThrow();
});

test('진행 중인 공개 스트림 취소와 크기 초과 캐시의 폐기·복구', async () => {
  vi.resetModules();
  const cancel = vi.fn();
  vi.stubGlobal('caches', undefined);
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode('{'));
            },
            cancel,
          })
        )
    )
  );
  const { readPublicData } = await import('./publicDataCache');
  const controller = new AbortController();
  const pending = readPublicData('/data/x.json', await sha('{}'), 20, controller.signal);
  const rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  await new Promise((resolve) => setTimeout(resolve, 10));
  controller.abort();
  await rejected;
  expect(cancel).toHaveBeenCalledOnce();
  const remove = vi.fn(async () => true);
  vi.stubGlobal('caches', {
    open: async () => ({
      match: async () => new Response(' '.repeat(500)),
      delete: remove,
      keys: async () => [],
      put: vi.fn(),
    }),
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{}'))
  );
  expect(
    await readPublicData('/data/x.json', await sha('{}'), 20, new AbortController().signal)
  ).toEqual({});
  expect(remove).toHaveBeenCalledOnce();
});

test('이미 해제된 gzip 응답과 패킷 사이에 나뉜 압축 서명 보존', async () => {
  vi.resetModules();
  vi.stubGlobal('caches', undefined);
  const raw = '{"native":true}';
  const packed = new Uint8Array(
    await new Response(
      new Blob([raw]).stream().pipeThrough(new CompressionStream('gzip'))
    ).arrayBuffer()
  );
  const fetcher = vi.fn(async () => new Response(raw, { headers: { 'Content-Encoding': 'gzip' } }));
  vi.stubGlobal('fetch', fetcher);
  const { readPublicData } = await import('./publicDataCache');
  const signal = new AbortController().signal;
  expect(await readPublicData('/data/tile.json.gz', await sha(raw), 100, signal)).toEqual({
    native: true,
  });
  fetcher.mockImplementation(
    async () =>
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(packed.slice(0, 1));
            controller.enqueue(packed.slice(1));
            controller.close();
          },
        })
      )
  );
  expect(await readPublicData('/data/tile.json.gz', await sha(raw), 100, signal)).toEqual({
    native: true,
  });
});

test('손상된 압축 응답은 브라우저 내부 오류 대신 지도 무결성 오류 반환', async () => {
  vi.resetModules();
  vi.stubGlobal('caches', undefined);
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(new Uint8Array([31, 139, 8, 0])))
  );
  const { readPublicData } = await import('./publicDataCache');
  const { CityError } = await import('../../domains/city/exception/CityError');
  await expect(
    readPublicData('/data/tile.json.gz', await sha('{}'), 100, new AbortController().signal)
  ).rejects.toThrow(new CityError('INVALID_DATA'));
});

test('지도 전용 기기 캐시는 새 작업 스레드에서도 재사용하고 저장소 거부 시 조회 유지', async () => {
  vi.resetModules();
  const entries = new Map<string, Response>();
  let saved: () => void = () => {};
  const stored = new Promise<void>((resolve) => {
    saved = resolve;
  });
  const storage = {
    match: async (key: string) => entries.get(key)?.clone(),
    keys: async () => [],
    delete: async (key: string) => entries.delete(key),
    put: async (key: string, response: Response) => {
      entries.set(key, response);
      saved();
    },
  };
  const open = vi.fn(async () => storage);
  vi.stubGlobal('caches', { open });
  const fetcher = vi.fn(async () => new Response('{"map":1}'));
  vi.stubGlobal('fetch', fetcher);
  const hash = await sha('{"map":1}'),
    signal = new AbortController().signal;
  let source = await import('./publicDataCache');
  await source.readPublicData('/data/map.json', hash, 50, signal, 'city');
  await stored;
  vi.resetModules();
  source = await import('./publicDataCache');
  expect(await source.readPublicData('/data/map.json', hash, 50, signal, 'city')).toEqual({
    map: 1,
  });
  expect(fetcher).toHaveBeenCalledOnce();
  expect(open).toHaveBeenCalledWith('waterleague-city-sha256-v1');
  open.mockRejectedValue(new Error('저장소 차단'));
  expect(await source.readPublicData('/data/map.json', hash, 50, signal, 'city')).toEqual({
    map: 1,
  });
  expect(fetcher).toHaveBeenCalledTimes(2);
});
