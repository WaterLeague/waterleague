import { CityError } from '../../domains/city/exception/CityError';
const cacheName = 'waterleague-public-sha256-v1';
const maximumCacheBytes = 128 * 1024 * 1024;
let storedSizes: Map<string, number> | null = null;
let maintenance: Promise<void> = Promise.resolve();
async function digest(raw: ArrayBuffer) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))]
    .map((v) => v.toString(16).padStart(2, '0'))
    .join('');
}
export async function readPublicData(
  path: string,
  expected: string,
  maximum: number,
  signal: AbortSignal
): Promise<unknown> {
  if (
    !/^\/data\/[\w/.-]+\.json$/.test(path) ||
    path.includes('..') ||
    !/^[a-f0-9]{64}$/.test(expected)
  )
    throw new CityError('INVALID_DATA');
  signal.throwIfAborted();
  let cache: Cache | undefined;
  const key = `${path}?sha256=${expected}`;
  try {
    if (typeof caches !== 'undefined') cache = await caches.open(cacheName);
  } catch {
    /* 저장소가 차단된 기기도 메모리 조회는 계속한다. */
  }
  const cached = await cache?.match(key).catch(() => undefined);
  if (cached) {
    const raw = await cached.arrayBuffer();
    if (raw.byteLength <= maximum && (await digest(raw)) === expected) {
      signal.throwIfAborted();
      return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw));
    }
    await cache?.delete(key).catch(() => false);
  }
  const response = await fetch(path, { signal, credentials: 'same-origin' });
  if (!response.ok) throw new CityError('NETWORK');
  const raw = await response.arrayBuffer();
  if (raw.byteLength > maximum || (await digest(raw)) !== expected)
    throw new CityError('INVALID_DATA');
  signal.throwIfAborted();
  const value: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw));
  if (cache) {
    const storage = cache;
    // 인증 응답은 저장하지 않고 원본 해시로 고정한 공개 지도만 용량 상한 안에서 보관한다.
    maintenance = maintenance
      .then(async () => {
        if (!storedSizes) {
          storedSizes = new Map();
          for (const request of await storage.keys()) {
            const response = await storage.match(request);
            storedSizes.set(
              request.url,
              Number(response?.headers.get('Content-Length') ?? maximumCacheBytes)
            );
          }
        }
        const absolute = typeof location === 'undefined' ? key : new URL(key, location.origin).href;
        await storage.put(
          key,
          new Response(raw, {
            headers: {
              'Content-Type': 'application/json',
              'Content-Length': String(raw.byteLength),
            },
          })
        );
        storedSizes.delete(absolute);
        storedSizes.set(absolute, raw.byteLength);
        let bytes = [...storedSizes.values()].reduce((sum, n) => sum + n, 0);
        for (const [oldest, size] of storedSizes) {
          if (bytes <= maximumCacheBytes) break;
          await storage.delete(oldest);
          storedSizes.delete(oldest);
          bytes -= size;
        }
      })
      .catch(() => {});
  }
  return value;
}
