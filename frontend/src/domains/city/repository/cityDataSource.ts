import { readPublicData } from '../../../shared/repository/publicDataCache';
import { CityError } from '../exception/CityError';
import { mapCity, mapCityTile } from '../mapper/cityMapper';
import type { City, CityTile, TileEntry } from '../entity/city';
import { cityPlayDto } from '../dto/cityPlayDto';
import { loadNativeUrbanTile } from '../../urban/repository/nativeUrbanRepository';
import { CITY_HASH, CITY_PATH } from './cityVersion';
let cityCache: City | undefined;
let regionsCache: import('../dto/cityPlayDto').CityPlayRegion[] | undefined;
async function read(path: string, expected: string, signal: AbortSignal, maximum: number) {
  return readPublicData(path, expected, maximum, signal, 'city');
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
  const [raw, urban] = await Promise.all([
    read(`/data/seoul-native-v1/${entry.file}`, entry.sha256, signal, entry.bytes),
    loadNativeUrbanTile(entry.id, CITY_HASH, signal, 'city'),
  ]);
  const data: CityTile = { ...mapCityTile(raw, entry.id, entry.buildingCount), urban };
  return data;
}
