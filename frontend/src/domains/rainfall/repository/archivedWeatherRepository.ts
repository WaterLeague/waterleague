import { archivedWeatherDto } from '../dto/archivedWeatherDto';
export async function loadArchivedWeather(signal: AbortSignal) {
  const response = await fetch('/data/water-weather-v1.json', {
    signal,
    credentials: 'same-origin',
  });
  if (!response.ok) return null;
  const body = await response.text();
  if (body.length > 131072) return null;
  const result = archivedWeatherDto.safeParse(JSON.parse(body));
  return result.success ? result.data : null;
}
