import { cityDto, cityTileDto } from '../dto/cityDto';
import { CityError } from '../exception/CityError';
export function mapCity(value: unknown) {
  const result = cityDto.safeParse(value);
  if (!result.success) throw new CityError('INVALID_DATA');
  const data = result.data;
  if (
    new Set(data.districts.map((d) => d.id)).size !== 25 ||
    new Set(data.tiles.map((t) => t.id)).size !== data.tiles.length ||
    data.tiles.reduce((n, t) => n + t.buildingCount, 0) !== data.buildingCount ||
    data.tiles.some((t) => t.file !== `tiles/${t.id}.json.gz`)
  )
    throw new CityError('INVALID_DATA');
  return data;
}
export function mapCityTile(value: unknown, id: string, count: number) {
  const result = cityTileDto.safeParse(value);
  if (
    !result.success ||
    result.data.id !== id ||
    result.data.buildings.length !== count ||
    new Set(result.data.buildings.map((b) => b.id)).size !== count
  )
    throw new CityError('INVALID_DATA');
  return result.data;
}
