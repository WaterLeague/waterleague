import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { TraceTileIndex } from '../entity/floodTrace';

beforeEach(() => vi.resetModules());
afterEach(() => vi.unstubAllGlobals());
const content = {
  eventId: 'seoul-20220808',
  id: '0_0',
  path: 'M0,0 L1,0 L0,-1 Z',
  triangleVertices: [0, 0, 1, 0, 0, 1],
};
async function fixture(value = content): Promise<{ raw: string; index: TraceTileIndex }> {
  const raw = JSON.stringify(value);
  const bytes = new TextEncoder().encode(raw);
  const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return { raw, index: { id: '0_0', bounds: [0, 0, 4000, 4000], bytes: bytes.length, sha256 } };
}
test('같은 타일 요청 공유와 원문 해시·바이트 확인 후 재사용', async () => {
  const { raw, index } = await fixture();
  const fetch = vi.fn().mockResolvedValue(new Response(raw));
  vi.stubGlobal('fetch', fetch);
  const { loadTraceTile } = await import('./floodTraceRepository');
  const first = loadTraceTile(content.eventId, index);
  expect(loadTraceTile(content.eventId, index)).toBe(first);
  await expect(first).resolves.toEqual(content);
  await expect(loadTraceTile(content.eventId, index)).resolves.toEqual(content);
  expect(fetch).toHaveBeenCalledOnce();
});
test('같은 길이 변조 응답 거부와 실패 캐시 제거 후 재시도', async () => {
  const { raw, index } = await fixture();
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(raw.replace('M0,0', 'M9,0')))
    .mockResolvedValueOnce(new Response(raw));
  vi.stubGlobal('fetch', fetch);
  const { loadTraceTile } = await import('./floodTraceRepository');
  await expect(loadTraceTile(content.eventId, index)).rejects.toThrow();
  await expect(loadTraceTile(content.eventId, index)).resolves.toEqual(content);
  expect(fetch).toHaveBeenCalledTimes(2);
});
test('다른 사건 응답과 잘린 형상 거부', async () => {
  const other = await fixture({ ...content, eventId: 'seoul-20100921' });
  const valid = await fixture();
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(new Response(other.raw))
      .mockResolvedValueOnce(new Response(valid.raw.slice(1)))
  );
  const { loadTraceTile } = await import('./floodTraceRepository');
  await expect(loadTraceTile(content.eventId, other.index)).rejects.toThrow();
  await expect(loadTraceTile(content.eventId, valid.index)).rejects.toThrow();
});
