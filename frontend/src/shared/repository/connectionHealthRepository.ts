export async function checkConnectionHealth(signal: AbortSignal): Promise<boolean> {
  const response = await fetch('/api/v1/health', {
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
    headers: { Accept: 'application/json' },
    signal,
  });
  if (!response.ok || !response.headers.get('content-type')?.includes('application/json'))
    return false;
  const body: unknown = await response.json();
  return typeof body === 'object' && body !== null && 'status' in body && body.status === 'UP';
}
