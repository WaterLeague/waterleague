import { readPublicData } from '../../../shared/repository/publicDataCache';
import { CityError } from '../exception/CityError';
import { mapCity, mapCityTile } from '../mapper/cityMapper';
import type { City, CityTile, TileEntry } from '../entity/city';
import { cityPlayDto } from '../dto/cityPlayDto';
export const CITY_HASH = 'd988b2b86c73a2e577c5c2574fdd0e7e052f5f5a68ee090cd6643fa4deab6f41';
export const CITY_PATH = '/data/seoul-v1/city.json';
const cache = new Map<string, CityTile>();
let cityCache: City | undefined;
let regionsCache: import('../dto/cityPlayDto').CityPlayRegion[] | undefined;
let eligibilityCache: import('../dto/cityEligibilityDto').CityEligibility | undefined;
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
      '/data/seoul-play-v2.json',
      '4187dbcf06bbcf0cb36212ae6d983969098ab9d947afe083702487e3ec910121',
      signal,
      100000
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

import { cityEligibilityDto } from '../dto/cityEligibilityDto';
export async function loadCityEligibility(signal: AbortSignal) {
  if (eligibilityCache) return eligibilityCache;
  const value = cityEligibilityDto.parse(
    await read(
      '/data/seoul-site-eligibility-v1.json',
      '2699d3067b4a9dfcded5d41e960ab184761bc00139401ec8318b28742b337dc6',
      signal,
      4000000
    )
  );
  const result = {
    roofIds: new Set(value.roofSourceIds),
    legacySiteSources: value.legacySiteSources,
  };
  if (!signal.aborted) eligibilityCache = result;
  return result;
}
