import { afterEach, describe, expect, it, vi } from 'vitest';
import { backendFetch, onBackendFailure } from './backendFetch';
import { checkConnectionHealth } from './connectionHealthRepository';

let unsubscribe = () => {};
afterEach(() => {
  unsubscribe();
  vi.unstubAllGlobals();
});

describe('백엔드 연결 확인', () => {
  it('권한·입력 오류와 의도적인 취소는 단절 알림에서 제외', async () => {
    const listener = vi.fn();
    unsubscribe = onBackendFailure(listener);
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(null, { status: 401 }))
        .mockResolvedValueOnce(new Response(null, { status: 403 }))
        .mockResolvedValueOnce(new Response(null, { status: 422 }))
        .mockRejectedValueOnce(new DOMException('Aborted', 'AbortError'))
    );
    await backendFetch('/api/v1/test');
    await backendFetch('/api/v1/test');
    await backendFetch('/api/v1/test');
    await expect(backendFetch('/api/v1/test')).rejects.toMatchObject({ name: 'AbortError' });
    expect(listener).not.toHaveBeenCalled();
  });

  it('서버 오류는 확인 알림만 전송하고 네트워크 실패를 안전한 문구로 반환', async () => {
    const listener = vi.fn();
    unsubscribe = onBackendFailure(listener);
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockRejectedValueOnce(new TypeError('private host detail'));
    vi.stubGlobal('fetch', fetcher);
    expect((await backendFetch('/api/v1/test')).status).toBe(503);
    await expect(backendFetch('/api/v1/test', { method: 'POST' })).rejects.toMatchObject({
      code: 'SERVER_UNAVAILABLE',
      status: 0,
      message: '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.',
    });
    expect(listener).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('캐시·인증 없이 새 상태를 확인하고 HTML 대체 응답·실패 상태 거부', async () => {
    const json = (status: string, code = 200) =>
      new Response(JSON.stringify({ status }), {
        status: code,
        headers: { 'Content-Type': 'application/json' },
      });
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(json('UP'))
      .mockResolvedValueOnce(
        new Response('<html>SPA</html>', { headers: { 'Content-Type': 'text/html' } })
      )
      .mockResolvedValueOnce(json('DOWN'))
      .mockResolvedValueOnce(json('UP', 503));
    vi.stubGlobal('fetch', fetcher);
    const signal = new AbortController().signal;
    expect(await checkConnectionHealth(signal)).toBe(true);
    expect(fetcher.mock.calls[0]).toEqual([
      '/api/v1/health',
      expect.objectContaining({
        signal,
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
      }),
    ]);
    expect(await checkConnectionHealth(signal)).toBe(false);
    expect(await checkConnectionHealth(signal)).toBe(false);
    expect(await checkConnectionHealth(signal)).toBe(false);
  });
});
