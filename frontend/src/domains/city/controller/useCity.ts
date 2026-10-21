import type { MapScope } from '../../../shared/service/mapScope';
import { scopeCityTile } from '../service/competitionMapService';
import { useEffect, useMemo, useState } from 'react';
import type { City, CityTile } from '../entity/city';
import { loadCity, loadCityTile, loadCityPlayRegions } from '../repository/cityRepository';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { CityError } from '../exception/CityError';
import { errorMessage } from '../../../shared/exception/ApiError';
import { nearbyTiles } from '../service/cityService';
export function useCity() {
  const [city, setCity] = useState<City | null>(null),
    [regions, setRegions] = useState<CityPlayRegion[]>([]),
    [error, setError] = useState(''),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    void Promise.all([loadCity(controller.signal), loadCityPlayRegions(controller.signal)])
      .then(([v, play]) => {
        if (
          play.some(
            (r) => !v.districts.some((d) => d.id === r.districtId && d.name === r.districtName)
          )
        )
          throw new CityError('INVALID_DATA');
        if (!controller.signal.aborted) {
          setRegions(play);
          setCity(v);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      });
    return () => controller.abort();
  }, [attempt]);
  return { city, regions, error, retry: () => setAttempt((v) => v + 1) };
}
export function useCityTiles(
  city: City,
  camera: { center: [number, number]; distance: number },
  scope?: MapScope
) {
  const [tiles, setTiles] = useState<CityTile[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const wanted = useMemo(() => nearbyTiles(city, camera.center, camera.distance), [city, camera]);
  const key = wanted
    .map((t) => t.id)
    .sort()
    .join(',');
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    setBusy(wanted.length > 0);
    // 새 범위가 준비될 때까지 현재 메시를 유지하고 필요한 타일만 캐시에서 보충한다.
    async function run() {
      const next: CityTile[] = [];
      const retained = new Set(wanted.map((t) => t.id));
      for (let i = 0; i < wanted.length; i += 4) {
        const batch = await Promise.all(
          wanted.slice(i, i + 4).map((t) => loadCityTile(t, controller.signal))
        );
        if (controller.signal.aborted) return;
        next.push(...batch.map((tile) => scopeCityTile(tile, scope)));
        if (i === 0 && wanted.length > 4) {
          const ready = [...next],
            ids = new Set(ready.map((t) => t.id));
          setTiles((previous) =>
            [...ready, ...previous.filter((t) => retained.has(t.id) && !ids.has(t.id))].sort(
              (a, b) => a.id.localeCompare(b.id)
            )
          );
        }
      }
      if (!controller.signal.aborted) setTiles(next.sort((a, b) => a.id.localeCompare(b.id)));
    }
    void run()
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
    // 선택 타일 목록이 같으면 카메라 좌표 변경으로 다시 요청하지 않음.
  }, [city, key, scope]);
  return { tiles, error, busy };
}
