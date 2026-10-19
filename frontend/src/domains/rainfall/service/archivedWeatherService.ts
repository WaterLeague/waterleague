import type { ArchivedWeather } from '../dto/archivedWeatherDto';
export function archivedWindAt(
  value: ArchivedWeather | null,
  eventId: string,
  at: string | null,
  districtId: string
) {
  if (!value || value.eventId !== eventId || !at) return undefined;
  const elapsed = (Date.parse(at) - Date.parse(value.start)) / 1000;
  if (!Number.isFinite(elapsed) || elapsed < 0 || Date.parse(at) >= Date.parse(value.end))
    return undefined;
  const sample = value.stations.find((s) => s.districtIds.includes(districtId))?.samples[
    Math.floor(elapsed / 60)
  ];
  return sample ? { windSpeedMs: sample[0], windDirectionDeg: sample[1] } : undefined;
}
