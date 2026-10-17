import { useEffect, useState } from 'react';
import { loadReference } from '../repository/referenceRepository';
import type { CpuReference } from '../entity/reference';
import { ApiError, errorMessage } from '../../../shared/exception/ApiError';
export function useReference(modelHash: string) {
  const [data, setData] = useState<CpuReference | null>(null),
    [error, setError] = useState(''),
    [unavailable, setUnavailable] = useState(false),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    setData(null);
    setUnavailable(false);
    loadReference(modelHash)
      .then((v) => {
        if (active) setData(v);
      })
      .catch((e) => {
        if (active) {
          if (e instanceof ApiError && e.status === 404) setUnavailable(true);
          else setError(errorMessage(e));
        }
      });
    return () => {
      active = false;
    };
  }, [retry, modelHash]);
  return {
    data: data?.report.modelHashes.includes(modelHash) ? data : null,
    error,
    unavailable,
    retry: () => setRetry((n) => n + 1),
  };
}
