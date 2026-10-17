import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, onSessionExpired, refreshCsrf, resetSessionToken } from './apiClient';
import { authenticate, logout } from '../../domains/account/repository/accountRepository';
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
const expired = () => json({ code: 'AUTHENTICATION_REQUIRED', detail: '로그인이 필요합니다' }, 401);
const token = () => json({ token: 'fresh-token', headerName: 'X-CSRF-TOKEN' });
let unsubscribe = () => {};
beforeEach(() => resetSessionToken());
afterEach(() => {
  unsubscribe();
  vi.unstubAllGlobals();
});
describe('세션 만료 복구', () => {
  it('중단된 지도 조회의 통신 취소와 세션 유지', async () => {
    const cancel = new AbortController();
    const listener = vi.fn();
    unsubscribe = onSessionExpired(listener);
    const fetcher = vi.fn(
      (_url: string, options: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          options.signal?.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true }
          );
        })
    );
    vi.stubGlobal('fetch', fetcher);
    const request = api('/installations/sites', 'GET', undefined, cancel.signal);
    const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    cancel.abort();
    await rejected;
    expect(fetcher.mock.calls[0][1].signal).toBe(cancel.signal);
    expect(listener).not.toHaveBeenCalled();
  });
  it('병렬 변경 요청의 첫 CSRF 조회 공유와 만료 알림', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation((url: string) =>
        Promise.resolve(url.endsWith('/csrf') ? token() : expired())
      );
    vi.stubGlobal('fetch', fetcher);
    const listener = vi.fn();
    unsubscribe = onSessionExpired(listener);
    const results = await Promise.allSettled([api('/a', 'POST', {}), api('/b', 'POST', {})]);
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/csrf'))).toHaveLength(1);
    expect(results.every((result) => result.status === 'rejected')).toBe(true);
    expect(listener).toHaveBeenCalled();
    await refreshCsrf();
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/csrf'))).toHaveLength(2);
  });
  it('이전 세션의 지연 401로 새 로그인 해제 금지', async () => {
    let finish!: (response: Response) => void;
    const delayed = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.endsWith('/old')) return delayed;
        return Promise.resolve(url.endsWith('/csrf') ? token() : json({ id: 'new-account' }));
      })
    );
    const listener = vi.fn();
    unsubscribe = onSessionExpired(listener);
    const oldRequest = api('/old');
    await expect(authenticate('login', 'player', 'not-a-real-password')).resolves.toEqual({
      id: 'new-account',
    });
    finish(expired());
    await expect(oldRequest).rejects.toMatchObject({ code: 'SESSION_CHANGED' });
    expect(listener).not.toHaveBeenCalled();
  });
  it('만료된 토큰 대신 새 토큰으로 로그아웃하며 이미 만료된 세션 허용', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(json({ token: 'expired-token', headerName: 'X-CSRF-TOKEN' }))
      .mockResolvedValueOnce(token())
      .mockResolvedValueOnce(expired());
    vi.stubGlobal('fetch', fetcher);
    await refreshCsrf();
    await expect(logout()).resolves.toBeUndefined();
    expect(fetcher.mock.calls[2][1].headers['X-CSRF-TOKEN']).toBe('fresh-token');
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
  it('로그아웃 서버 실패를 성공으로 처리하거나 변경 요청 재전송 금지', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(token())
      .mockResolvedValueOnce(json({ code: 'INTERNAL_ERROR' }, 500));
    vi.stubGlobal('fetch', fetcher);
    await expect(logout()).rejects.toMatchObject({ status: 500 });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it('일반 인증 실패와 권한 거부는 세션 만료 알림 대상 제외', async () => {
    const listener = vi.fn();
    unsubscribe = onSessionExpired(listener);
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json({ code: 'INVALID_CREDENTIALS' }, 401))
        .mockResolvedValueOnce(json({ code: 'ACCESS_DENIED' }, 403))
    );
    await expect(api('/auth/login')).rejects.toMatchObject({ code: 'INVALID_CREDENTIALS' });
    await expect(api('/restricted')).rejects.toMatchObject({ code: 'ACCESS_DENIED' });
    expect(listener).not.toHaveBeenCalled();
  });
});
