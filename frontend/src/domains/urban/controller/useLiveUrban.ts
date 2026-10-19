import { useEffect, useState } from 'react';
import type { LivePlace } from '../entity/liveUrban';
import { loadLiveAreas, loadLivePlaces } from '../repository/liveUrbanRepository';
import { freshReading, visibleLiveAreas } from '../service/liveUrbanService';
export function useLiveUrban(center: [number, number], distance: number, historical: boolean) {
  const [places, setPlaces] = useState<LivePlace[]>([]);
  const [checkedAt, setCheckedAt] = useState(Date.now);
  const x = Math.round(center[0] / 250) * 250,
    y = Math.round(center[1] / 250) * 250;
  const scale = distance >= 8500 ? 8500 : Math.ceil(distance / 250) * 250;
  useEffect(() => {
    if (historical || scale >= 8500) return;
    let controller: AbortController | null = null;
    let disposed = false;
    const refresh = async () => {
      controller?.abort();
      if (document.hidden || disposed) return;
      controller = new AbortController();
      const signal = controller.signal;
      try {
        const areas = await loadLiveAreas(signal);
        const selected = visibleLiveAreas(areas, [x, y], scale);
        const values = await loadLivePlaces(selected, signal);
        if (!signal.aborted && !disposed) {
          setPlaces((previous) =>
            values.map((value) => {
              const old = previous.find((p) => p.id === value.id);
              return {
                ...value,
                population: value.population ?? freshReading(old?.population, Date.now()),
                traffic: value.traffic ?? freshReading(old?.traffic, Date.now()),
              };
            })
          );
          setCheckedAt(Date.now());
        }
      } catch {
        // 실패 시에도 기존 값의 유효기간을 연장하지 않는다.
        if (!signal.aborted && !disposed) setCheckedAt(Date.now());
      }
    };
    const timer = window.setTimeout(() => {
      void refresh();
    }, 300);
    const poll = window.setInterval(() => {
      void refresh();
    }, 60000);
    const visibility = () => {
      void refresh();
    };
    document.addEventListener('visibilitychange', visibility);
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearInterval(poll);
      controller?.abort();
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [x, y, scale, historical]);
  // 만료 경계에서는 공개 응답이 늦어져도 화면의 ‘현재’ 표시를 제거한다.
  useEffect(() => {
    const expiry = places
      .flatMap((p) => [p.population, p.traffic])
      .filter((p) => p && Date.parse(p.validUntil) > Date.now())
      .map((p) => Date.parse(p!.validUntil));
    if (!expiry.length) return;
    const timer = window.setTimeout(
      () => setCheckedAt(Date.now()),
      Math.max(1, Math.min(...expiry) - Date.now() + 1)
    );
    return () => clearTimeout(timer);
  }, [places, checkedAt]);
  const active = historical || scale >= 8500 ? [] : places;
  return {
    places: active,
    current: active.filter(
      (p) => freshReading(p.population, checkedAt) || freshReading(p.traffic, checkedAt)
    ),
    checkedAt,
  };
}
