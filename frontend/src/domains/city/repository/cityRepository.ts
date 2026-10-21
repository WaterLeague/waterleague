import type { City, CityTile, TileEntry } from '../entity/city';
import type { CityPlayRegion } from '../dto/cityPlayDto';
import { requestCityData } from './cityDataClient';
export { CITY_HASH, CITY_PATH } from './cityVersion';
const cache = new Map<string, CityTile>();
let cityCache: City | undefined;
let regionsCache: CityPlayRegion[] | undefined;
export async function loadCity(signal: AbortSignal): Promise<City> {
  signal.throwIfAborted();
  if (cityCache) return cityCache;
  const city = (await requestCityData({ kind: 'city' }, signal)) as City;
  signal.throwIfAborted();
  cityCache = city;
  return city;
}
export async function loadCityPlayRegions(signal: AbortSignal): Promise<CityPlayRegion[]> {
  signal.throwIfAborted();
  if (regionsCache) return regionsCache;
  const regions = (await requestCityData({ kind: 'regions' }, signal)) as CityPlayRegion[];
  signal.throwIfAborted();
  regionsCache = regions;
  return regions;
}
export async function loadCityTile(entry: TileEntry, signal: AbortSignal): Promise<CityTile> {
  signal.throwIfAborted();
  const cached = cache.get(entry.sha256);
  if (cached) {
    cache.delete(entry.sha256);
    cache.set(entry.sha256, cached);
    return cached;
  }
  const tile = (await requestCityData({ kind: 'tile', entry }, signal)) as CityTile;
  signal.throwIfAborted();
  cache.set(entry.sha256, tile);
  while (cache.size > 24) cache.delete(cache.keys().next().value!);
  return tile;
}
