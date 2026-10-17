import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../../shared/exception/ApiError';
import { loadSpatial } from '../repository/spatialRepository';
import type { SpatialReference } from '../entity/spatial';
export function useSpatial() {
  const [data, setData] = useState<SpatialReference | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const active = useRef(true),
    loading = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  async function load() {
    if (loading.current) return;
    loading.current = true;
    setBusy(true);
    setError('');
    try {
      const value = await loadSpatial();
      if (active.current) setData(value);
    } catch (e) {
      if (active.current) setError(errorMessage(e));
    } finally {
      loading.current = false;
      if (active.current) setBusy(false);
    }
  }
  return { data, busy, error, load };
}
