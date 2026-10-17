import { ApiError } from '../exception/ApiError';
type Csrf = { token: string; headerName: string };
let csrf: Csrf | null = null;
let pendingCsrf: Promise<Csrf> | null = null;
let sessionEpoch = 0;
const expiredListeners = new Set<() => void>();

export function onSessionExpired(listener: () => void) {
  expiredListeners.add(listener);
  return () => {
    expiredListeners.delete(listener);
  };
}
export function resetSessionToken() {
  sessionEpoch++;
  csrf = null;
  pendingCsrf = null;
}
function sessionChanged() {
  return new ApiError(409, 'SESSION_CHANGED', '로그인 상태가 변경되었습니다. 다시 시도해 주세요.');
}
export function refreshCsrf(): Promise<Csrf> {
  if (pendingCsrf) return pendingCsrf;
  const epoch = sessionEpoch;
  const request = (async () => {
    const r = await fetch('/api/v1/auth/csrf', { credentials: 'same-origin', cache: 'no-store' });
    if (!r.ok) throw new ApiError(r.status, 'CSRF_UNAVAILABLE', '서버 연결을 확인해 주세요.');
    const token = (await r.json()) as Csrf;
    if (epoch !== sessionEpoch) throw sessionChanged();
    csrf = token;
    return token;
  })();
  pendingCsrf = request;
  void request
    .finally(() => {
      if (pendingCsrf === request) pendingCsrf = null;
    })
    .catch(() => {});
  return request;
}
export async function api<T>(
  path: string,
  method = 'GET',
  body?: unknown,
  signal?: AbortSignal
): Promise<T> {
  const epoch = sessionEpoch;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') {
    const token = csrf ?? (await refreshCsrf());
    if (epoch !== sessionEpoch) throw sessionChanged();
    headers[token.headerName] = token.token;
  }
  const response = await fetch('/api/v1' + path, {
    method,
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (epoch !== sessionEpoch) throw sessionChanged();
  if (!response.ok) {
    let problem: Record<string, string> = {};
    try {
      problem = await response.json();
    } catch {
      /* 공통 오류 형식이 없는 통신 실패 처리 */
    }
    if (epoch !== sessionEpoch) throw sessionChanged();
    if (response.status === 401 && problem.code === 'AUTHENTICATION_REQUIRED') {
      csrf = null;
      pendingCsrf = null;
      expiredListeners.forEach((listener) => listener());
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
  if (epoch !== sessionEpoch) throw sessionChanged();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}
