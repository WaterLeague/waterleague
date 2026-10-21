import { CityError } from '../../domains/city/exception/CityError';
export type CacheNamespace = 'default' | 'topography' | 'city';
const cacheBuckets = {
  city: {
    name: 'waterleague-city-sha256-v1',
    maximum: 256 * 1024 * 1024,
    sizes: null as Map<string, number> | null,
    maintenance: Promise.resolve(),
  },
  default: {
    name: 'waterleague-public-sha256-v1',
    maximum: 128 * 1024 * 1024,
    sizes: null as Map<string, number> | null,
    maintenance: Promise.resolve(),
  },
  topography: {
    name: 'waterleague-topography-sha256-v1',
    maximum: 96 * 1024 * 1024,
    sizes: null as Map<string, number> | null,
    maintenance: Promise.resolve(),
  },
};
async function digest(raw: ArrayBuffer) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))]
    .map((v) => v.toString(16).padStart(2, '0'))
    .join('');
}
async function boundedResponse(
  response: Response,
  maximum: number,
  gzip: boolean,
  signal: AbortSignal
) {
  if (!response.body) throw new CityError('INVALID_DATA');
  let received = 0;
  const source = response.body
    .pipeThrough(
      new TransformStream<Uint8Array<ArrayBuffer>, Uint8Array<ArrayBuffer>>({
        transform(chunk, controller) {
          received += chunk.byteLength;
          if (received > maximum + 65536) throw new CityError('INVALID_DATA');
          controller.enqueue(chunk);
        },
      })
    )
    .getReader();
  const abort = () => {
    void source.cancel(signal.reason).catch(() => {});
  };
  signal.addEventListener('abort', abort, { once: true });
  let reader: ReadableStreamDefaultReader<Uint8Array<ArrayBuffer>> | undefined;
  try {
    const prefix: Uint8Array<ArrayBuffer>[] = [];
    const signature = new Uint8Array(2);
    let headerLength = 0;
    while (gzip && headerLength < 2) {
      signal.throwIfAborted();
      const next = await source.read();
      if (next.done) break;
      prefix.push(next.value);
      const length = Math.min(2 - headerLength, next.value.byteLength);
      signature.set(next.value.subarray(0, length), headerLength);
      headerLength += length;
    }
    signal.throwIfAborted();
    let body = new ReadableStream<Uint8Array<ArrayBuffer>>({
      start(controller) {
        for (const chunk of prefix) controller.enqueue(chunk);
      },
      async pull(controller) {
        try {
          const next = await source.read();
          if (next.done) controller.close();
          else controller.enqueue(next.value);
        } catch (error) {
          controller.error(error);
        }
      },
      cancel(reason) {
        return source.cancel(reason);
      },
    });
    // 전송 계층에서 이미 해제된 .gz 응답도 원문 해시로 검사한다.
    if (gzip && signature[0] === 0x1f && signature[1] === 0x8b)
      body = body.pipeThrough(new DecompressionStream('gzip'));
    reader = body.getReader();
    const parts: Uint8Array[] = [];
    let size = 0;
    while (true) {
      signal.throwIfAborted();
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximum) throw new CityError('INVALID_DATA');
      parts.push(value);
    }
    signal.throwIfAborted();
    const result = new Uint8Array(size);
    let offset = 0;
    for (const part of parts) {
      result.set(part, offset);
      offset += part.byteLength;
    }
    return result.buffer;
  } catch (error) {
    await Promise.allSettled([source.cancel(), reader?.cancel()]);
    signal.throwIfAborted();
    throw error instanceof CityError ? error : new CityError('INVALID_DATA');
  } finally {
    signal.removeEventListener('abort', abort);
    reader?.releaseLock();
    source.releaseLock();
  }
}
function decode(raw: ArrayBuffer): unknown {
  try {
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw));
  } catch {
    throw new CityError('INVALID_DATA');
  }
}
export async function readPublicData(
  path: string,
  expected: string,
  maximum: number,
  signal: AbortSignal,
  namespace: CacheNamespace = 'default'
): Promise<unknown> {
  if (
    !/^\/data\/[\w/.-]+\.json(?:\.gz)?$/.test(path) ||
    path.includes('..') ||
    !/^[a-f0-9]{64}$/.test(expected) ||
    !Number.isSafeInteger(maximum) ||
    maximum < 1 ||
    maximum > 64 * 1024 * 1024
  )
    throw new CityError('INVALID_DATA');
  signal.throwIfAborted();
  if (namespace !== 'default' && namespace !== 'topography' && namespace !== 'city')
    throw new CityError('INVALID_DATA');
  const bucket = cacheBuckets[namespace];
  if (!bucket) throw new CityError('INVALID_DATA');
  let cache: Cache | undefined;
  const key = `${path}?sha256=${expected}`;
  try {
    if (typeof caches !== 'undefined') cache = await caches.open(bucket.name);
  } catch {
    /* 저장소가 차단된 기기도 메모리 조회는 계속한다. */
  }
  const cached = await cache?.match(key).catch(() => undefined);
  if (cached) {
    try {
      const raw = await boundedResponse(cached, maximum, false, signal);
      if ((await digest(raw)) === expected) {
        signal.throwIfAborted();
        return decode(raw);
      }
    } catch {
      signal.throwIfAborted();
    }
    await cache?.delete(key).catch(() => false);
  }
  const response = await fetch(path, { signal, credentials: 'same-origin' });
  if (!response.ok) throw new CityError('NETWORK');
  const raw = await boundedResponse(response, maximum, path.endsWith('.gz'), signal);
  if (raw.byteLength > maximum || (await digest(raw)) !== expected)
    throw new CityError('INVALID_DATA');
  signal.throwIfAborted();
  const value = decode(raw);
  if (cache) {
    const storage = cache;
    // 인증 응답은 저장하지 않고 원본 해시로 고정한 공개 지도만 용량 상한 안에서 보관한다.
    bucket.maintenance = bucket.maintenance
      .then(async () => {
        if (!bucket.sizes) {
          bucket.sizes = new Map();
          for (const request of await storage.keys()) {
            const response = await storage.match(request);
            bucket.sizes.set(
              request.url,
              Number(response?.headers.get('Content-Length') ?? bucket.maximum)
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
        bucket.sizes.delete(absolute);
        bucket.sizes.set(absolute, raw.byteLength);
        let bytes = [...bucket.sizes.values()].reduce((sum, n) => sum + n, 0);
        for (const [oldest, size] of bucket.sizes) {
          if (bytes <= bucket.maximum) break;
          await storage.delete(oldest);
          bucket.sizes.delete(oldest);
          bytes -= size;
        }
      })
      .catch(() => {});
  }
  return value;
}
