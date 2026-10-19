import { afterEach, expect, test, vi } from 'vitest';
afterEach(() => vi.unstubAllGlobals());
const sha = async (s: string) =>
  [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))]
    .map((n) => n.toString(16).padStart(2, '0'))
    .join('');
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
