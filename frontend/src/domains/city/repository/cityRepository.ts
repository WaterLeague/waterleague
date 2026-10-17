import { CityError } from '../exception/CityError';
import { mapCity, mapCityTile } from '../mapper/cityMapper';
import type { CityTile, TileEntry } from '../entity/city';
import { cityPlayDto } from '../dto/cityPlayDto';
export const CITY_HASH = 'd988b2b86c73a2e577c5c2574fdd0e7e052f5f5a68ee090cd6643fa4deab6f41';
export const CITY_PATH = '/data/seoul-v1/city.json';
const cache = new Map<string, CityTile>();
async function read(path: string, expected: string, signal: AbortSignal, maximum: number) {
  try {
    const response = await fetch(path, { signal, credentials: 'same-origin' });
    if (!response.ok) throw new CityError('NETWORK');
    const raw = await response.arrayBuffer();
    if (raw.byteLength > maximum) throw new CityError('INVALID_DATA');
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))]
      .map((v) => v.toString(16).padStart(2, '0'))
      .join('');
    if (hash !== expected) throw new CityError('INVALID_DATA');
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw)) as unknown;
  } catch (error) {
    if (signal.aborted || error instanceof CityError) throw error;
    throw new CityError('NETWORK');
  }
}
export async function loadCity(signal: AbortSignal) {
  return mapCity(await read(CITY_PATH, CITY_HASH, signal, 16000000));
}
export async function loadCityPlayRegions(signal: AbortSignal) {
  const result = cityPlayDto.safeParse(
    await read(
      '/data/seoul-play-v2.json',
      '4187dbcf06bbcf0cb36212ae6d983969098ab9d947afe083702487e3ec910121',
      signal,
      100000
    )
  );
  if (!result.success) throw new CityError('INVALID_DATA');
  return result.data.regions;
}
export async function loadCityTile(entry: TileEntry, signal: AbortSignal) {
  const cached = cache.get(entry.sha256);
  if (cached) {
    cache.delete(entry.sha256);
    cache.set(entry.sha256, cached);
    return cached;
  }
  const data = mapCityTile(
    await read(`/data/seoul-v1/${entry.file}`, entry.sha256, signal, entry.bytes),
    entry.id,
    entry.buildingCount
  );
  if (!signal.aborted) {
    cache.set(entry.sha256, data);
    while (cache.size > 24) cache.delete(cache.keys().next().value!);
  }
  return data;
}
