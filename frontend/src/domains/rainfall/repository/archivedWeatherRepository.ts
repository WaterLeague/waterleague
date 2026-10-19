import { archivedWeatherDto } from '../dto/archivedWeatherDto';
export async function loadArchivedWeather(eventId: string, signal: AbortSignal) {
  if (!/^seoul-(20220808|20110727|20100921)$/.test(eventId)) return null;
  const response = await fetch(`/data/water-weather-v2/${eventId}.json`, {
    signal,
    credentials: 'same-origin',
  });
  if (!response.ok) return null;
  const body = await response.text();
  if (body.length > 1048576) return null;
  const result = archivedWeatherDto.safeParse(JSON.parse(body));
  return result.success && result.data.eventId === eventId ? result.data : null;
}
