import { useEffect, useState } from 'react';
import { loadCityCoverage, type CityCoverageArea } from '../repository/cityCoverageRepository';
export function useCityCoverage() {
  const [areas, setAreas] = useState<CityCoverageArea[]>([]);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const request = new AbortController();
    void loadCityCoverage(request.signal)
      .then((data) => {
        if (!request.signal.aborted) setAreas(data);
      })
      .catch(() => {
        if (!request.signal.aborted) setFailed(true);
      });
    return () => request.abort();
  }, []);
  return { areas, failed };
}
