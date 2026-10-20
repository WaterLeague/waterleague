import { ApiError } from '../../../shared/exception/ApiError';
import {
  CISTERN_SPECIFICATIONS_HASH,
  cisternSpecificationCatalogDto,
} from '../dto/cisternSpecificationDto';
const invalid = () => new ApiError(502, 'INVALID_DATA', '공개 이용조 규격을 확인하지 못했습니다.');
export async function loadCisternSpecifications(signal: AbortSignal) {
  const response = await fetch('/api/v1/facilities/cistern-specifications-v1', {
    signal,
    credentials: 'same-origin',
  });
  if (!response.ok || !response.body) throw invalid();
  const reader = response.body.getReader(),
    bytes = new Uint8Array(65536);
  let length = 0;
  const abort = () => {
    void reader.cancel().catch(() => {});
  };
  signal.addEventListener('abort', abort, { once: true });
  try {
    while (true) {
      signal.throwIfAborted();
      const { value, done } = await reader.read();
      if (done) break;
      if (length + value.length > bytes.length) throw invalid();
      bytes.set(value, length);
      length += value.length;
    }
    const raw = bytes.slice(0, length);
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))]
      .map((v) => v.toString(16).padStart(2, '0'))
      .join('');
    signal.throwIfAborted();
    if (hash !== CISTERN_SPECIFICATIONS_HASH) throw invalid();
    return cisternSpecificationCatalogDto.parse(
      JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw))
    );
  } catch (error) {
    await reader.cancel().catch(() => {});
    signal.throwIfAborted();
    throw error instanceof ApiError ? error : invalid();
  } finally {
    signal.removeEventListener('abort', abort);
    reader.releaseLock();
  }
}
