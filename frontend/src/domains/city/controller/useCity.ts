import { useEffect, useState } from 'react';
import type { City, CityTile } from '../entity/city';
import {
  loadCity,
  loadCityTile,
  loadCityPlayRegions,
  loadCityEligibility,
} from '../repository/cityRepository';
import type { CityEligibility } from '../dto/cityEligibilityDto';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { CityError } from '../exception/CityError';
import { errorMessage } from '../../../shared/exception/ApiError';
import { nearbyTiles } from '../service/cityService';
export function useCity() {
  const [city, setCity] = useState<City | null>(null),
    [eligibility, setEligibility] = useState<CityEligibility | null>(null),
    [regions, setRegions] = useState<CityPlayRegion[]>([]),
    [error, setError] = useState(''),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    void Promise.all([
      loadCity(controller.signal),
      loadCityPlayRegions(controller.signal),
      loadCityEligibility(controller.signal),
    ])
      .then(([v, play, eligible]) => {
        if (
          play.some(
            (r) => !v.districts.some((d) => d.id === r.districtId && d.name === r.districtName)
          )
        )
          throw new CityError('INVALID_DATA');
        if (!controller.signal.aborted) {
          setRegions(play);
          setEligibility(eligible);
          setCity(v);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      });
    return () => controller.abort();
  }, [attempt]);
  return { city, regions, eligibility, error, retry: () => setAttempt((v) => v + 1) };
}
export function useCityTiles(city: City, camera: { center: [number, number]; distance: number }) {
  const [tiles, setTiles] = useState<CityTile[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const wanted = nearbyTiles(city, camera.center, camera.distance);
  const key = wanted.map((t) => t.id).join(',');
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    setBusy(wanted.length > 0);
    setTiles((previous) => previous.filter((t) => wanted.some((w) => w.id === t.id)));
    // 동시에 네 타일만 전송해 이동 중 취소와 메모리 사용을 제한.
    async function run() {
      for (let i = 0; i < wanted.length; i += 4) {
        const batch = await Promise.all(
          wanted.slice(i, i + 4).map((t) => loadCityTile(t, controller.signal))
        );
        if (controller.signal.aborted) return;
        setTiles((previous) => [
          ...previous.filter((t) => !batch.some((b) => b.id === t.id)),
          ...batch,
        ]);
      }
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
  }, [city, key]);
  return { tiles, error, busy };
}
