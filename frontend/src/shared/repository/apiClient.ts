import { ApiError } from '../exception/ApiError';
let csrf: { token: string; headerName: string } | null = null;
export async function refreshCsrf() {
  const r = await fetch('/api/v1/auth/csrf', { credentials: 'same-origin', cache: 'no-store' });
  if (!r.ok) throw new ApiError(r.status, 'CSRF_UNAVAILABLE', '서버 연결을 확인해 주세요.');
  csrf = (await r.json()) as { token: string; headerName: string };
  return csrf;
}
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') {
    const token = csrf ?? (await refreshCsrf());
    headers[token.headerName] = token.token;
  }
  const response = await fetch('/api/v1' + path, {
    method,
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let problem: Record<string, string> = {};
    try {
      problem = await response.json();
    } catch {
      /* 공통 오류 형식이 없는 통신 실패 처리 */
    }
    throw new ApiError(
      response.status,
      problem.code ?? 'NETWORK_ERROR',
      problem.detail ?? problem.title ?? '서버 연결을 확인해 주세요.'
    );
  }
  if (response.status === 204 || response.headers.get('content-length') === '0')
    return undefined as T;
  const text = await response.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}
