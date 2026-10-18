import { useEffect, useState } from 'react';
import type { FacilityCatalog } from '../dto/facilityDto';
import { loadFacilityCatalog } from '../repository/facilityRepository';
export function useFacilityCatalog(enabled: boolean, id = 'EPA_LID_PUBLIC_DESIGNS_V3') {
  const [catalog, setCatalog] = useState<FacilityCatalog | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    setCatalog(null);
    setFailed(false);
    void loadFacilityCatalog(id)
      .then((value) => {
        if (active) setCatalog(value);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [enabled, id]);
  return { catalog, failed };
}
