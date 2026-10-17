import { useEffect, useState } from 'react';
import { loadReference } from '../repository/referenceRepository';
import type { CpuReference } from '../entity/reference';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useReference(modelHash: string) {
  const [data, setData] = useState<CpuReference | null>(null),
    [error, setError] = useState(''),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    setData(null);
    loadReference(modelHash)
      .then((v) => {
        if (active) setData(v);
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [retry, modelHash]);
  return {
    data: data?.report.modelHashes.includes(modelHash) ? data : null,
    error,
    retry: () => setRetry((n) => n + 1),
  };
}
