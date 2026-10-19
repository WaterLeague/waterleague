import { useEffect, useState } from 'react';
import type { ArchivedWeather } from '../dto/archivedWeatherDto';
import { loadArchivedWeather } from '../repository/archivedWeatherRepository';
export function useArchivedWaterWeather(enabled: boolean) {
  const [value, setValue] = useState<ArchivedWeather | null>(null);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void loadArchivedWeather(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setValue(result);
      })
      .catch(() => {
        // 풍속 자료 결측을 임의의 바람으로 대체하지 않는다.
      });
    return () => controller.abort();
  }, [enabled]);
  return value;
}
