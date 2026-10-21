import { ApiError } from '../exception/ApiError';

const failureListeners = new Set<() => void>();

export function onBackendFailure(listener: () => void) {
  failureListeners.add(listener);
  return () => {
    failureListeners.delete(listener);
  };
}

export async function backendFetch(url: string, options?: RequestInit): Promise<Response> {
  try {
    const response = await fetch(url, options);
    if (response.status >= 500) failureListeners.forEach((listener) => listener());
    return response;
  } catch (error) {
    if (options?.signal?.aborted || (error instanceof Error && error.name === 'AbortError'))
      throw error;
    failureListeners.forEach((listener) => listener());
    throw new ApiError(
      0,
      'SERVER_UNAVAILABLE',
      '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'
    );
  }
}
