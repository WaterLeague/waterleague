import { useEffect, useState } from 'react';
import { loadReference } from '../repository/referenceRepository';
import type { CpuReference } from '../entity/reference';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useReference() {
  const [data, setData] = useState<CpuReference | null>(null),
    [error, setError] = useState(''),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    loadReference()
      .then((v) => {
        if (active) setData(v);
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [retry]);
  return { data, error, retry: () => setRetry((n) => n + 1) };
}
