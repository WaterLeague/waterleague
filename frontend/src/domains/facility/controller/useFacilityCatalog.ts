import { useEffect, useState } from 'react';
import type { FacilityCatalog } from '../dto/facilityDto';
import { loadFacilityCatalog } from '../repository/facilityRepository';
export function useFacilityCatalog(enabled: boolean) {
  const [catalog, setCatalog] = useState<FacilityCatalog | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    void loadFacilityCatalog()
      .then((value) => {
        if (active) setCatalog(value);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [enabled]);
  return { catalog, failed };
}
