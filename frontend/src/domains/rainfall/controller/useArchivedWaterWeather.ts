import { useEffect, useState } from 'react';
import type { ArchivedWeather } from '../dto/archivedWeatherDto';
import { loadArchivedWeather } from '../repository/archivedWeatherRepository';
export function useArchivedWaterWeather(enabled: boolean, eventId: string) {
  const [value, setValue] = useState<ArchivedWeather | null>(null);
  useEffect(() => {
    if (!enabled) return;
    setValue(null);
    const controller = new AbortController();
    void loadArchivedWeather(eventId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setValue(result);
      })
      .catch(() => {
        // 기상 자료 결측을 임의의 바람으로 대체하지 않는다.
      });
    return () => controller.abort();
  }, [enabled, eventId]);
  return value;
}
