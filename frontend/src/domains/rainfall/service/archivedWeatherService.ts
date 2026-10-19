import type { ArchivedWeather } from '../dto/archivedWeatherDto';
export function archivedWindAt(value: ArchivedWeather | null, eventId: string, at: string | null) {
  const time = at ? Date.parse(at) : NaN;
  return value?.entries
    .find((e) => e.eventId === eventId)
    ?.samples.find((s) => Date.parse(s.from) <= time && time < Date.parse(s.until))?.windSpeedMs;
}
