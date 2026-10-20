import { useEffect, useMemo, useState } from 'react';
import { CITY_HASH } from '../repository/cityRepository';
import { loadCityOverview, type CityOverview } from '../repository/cityOverviewRepository';
import { overviewBuildings } from '../service/cityOverviewVisibility';
export const overviewInstanceLimit = 130000;
export function useCityOverview(
  center: [number, number],
  distance: number,
  detailTileIds: ReadonlySet<string>
) {
  const [coarse, setCoarse] = useState<CityOverview | null>(null),
    [fine, setFine] = useState<CityOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const fineNeeded = distance < 10000;
  useEffect(() => {
    const request = new AbortController();
    void loadCityOverview(100, CITY_HASH, request.signal)
      .then((data) => {
        if (!request.signal.aborted) setCoarse(data);
      })
      .catch(() => {
        if (!request.signal.aborted) setFailed(true);
      });
    return () => request.abort();
  }, []);
  useEffect(() => {
    if (!fineNeeded) return;
    const request = new AbortController();
    void loadCityOverview(25, CITY_HASH, request.signal)
      .then((data) => {
        if (!request.signal.aborted) setFine(data);
      })
      .catch(() => {
        if (!request.signal.aborted) setFailed(true);
      });
    return () => request.abort();
  }, [fineNeeded]);
  const x = Math.round(center[0] / 500) * 500,
    y = Math.round(center[1] / 500) * 500;
  const radius = Math.ceil(Math.max(1500, distance * 0.9) / 500) * 500;
  const data = fineNeeded && fine ? fine : coarse;
  const visible = useMemo(
    () => overviewBuildings(coarse, fineNeeded ? fine : null, [x, y], radius, detailTileIds),
    [coarse, fine, detailTileIds, fineNeeded, x, y, radius]
  );
  return { data, visible, failed };
}
