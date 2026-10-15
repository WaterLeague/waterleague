import { useEffect, useState } from 'react';
import { loadCatalog } from '../repository/catalogRepository';
export function useCatalog() {
  const [data,setData] = useState<Awaited<ReturnType<typeof loadCatalog>> | null>(null);
  const [error,setError] = useState<string | null>(null);
  const [attempt,setAttempt] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setError(null);
    loadCatalog(abort.signal).then(setData).catch(error => { if (!abort.signal.aborted) setError(error instanceof Error ? error.message : '자료 연결을 확인해 주세요.'); });
    return () => abort.abort();
  },[attempt]);
  return { data,error,retry: () => setAttempt(a => a+1) };
}
