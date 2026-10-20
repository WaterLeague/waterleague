import { readPublicData } from '../../../shared/repository/publicDataCache';
import { CityError } from '../exception/CityError';
import { mapCity, mapCityTile } from '../mapper/cityMapper';
import type { City, CityTile, TileEntry } from '../entity/city';
import { cityPlayDto } from '../dto/cityPlayDto';
export const CITY_HASH = '67a8b80b7036590973b7db99053521333f9405e1076a7939bfe491c43296dd6c';
export const CITY_PATH = '/data/seoul-native-v1/city.json';
const cache = new Map<string, CityTile>();
let cityCache: City | undefined;
let regionsCache: import('../dto/cityPlayDto').CityPlayRegion[] | undefined;
async function read(path: string, expected: string, signal: AbortSignal, maximum: number) {
  return readPublicData(path, expected, maximum, signal);
}
export async function loadCity(signal: AbortSignal) {
  if (cityCache) return cityCache;
  const value = mapCity(await read(CITY_PATH, CITY_HASH, signal, 16000000));
  if (!signal.aborted) cityCache = value;
  return value;
}
export async function loadCityPlayRegions(signal: AbortSignal) {
  if (regionsCache) return regionsCache;
  const result = cityPlayDto.safeParse(
    await read(
      '/data/seoul-native-v1/game.json',
      'f08b92fa00db08126e86b379583299a831764b958a4f131de4647ebde95e6fdb',
      signal,
      524288
    )
  );
  if (!result.success) throw new CityError('INVALID_DATA');
  if (!signal.aborted) regionsCache = result.data.regions;
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
    await read(`/data/seoul-native-v1/${entry.file}`, entry.sha256, signal, entry.bytes),
    entry.id,
    entry.buildingCount
  );
  if (!signal.aborted) {
    cache.set(entry.sha256, data);
    while (cache.size > 24) cache.delete(cache.keys().next().value!);
  }
  return data;
}
