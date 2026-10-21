import { readPublicData, type CacheNamespace } from '../../../shared/repository/publicDataCache';
import { CityError } from '../../city/exception/CityError';
import { nativeUrbanIndexDto, nativeUrbanTileDto } from '../dto/nativeUrbanDto';

export const NATIVE_URBAN_HASH = '1cbdbe94b9f5b04a0c506fea3d9452d914a0cf757c065de4d436b9e34e476d3d';
let index: ReturnType<typeof nativeUrbanIndexDto.parse> | undefined;
export async function loadNativeUrbanTile(
  id: string,
  cityHash: string,
  signal: AbortSignal,
  namespace: CacheNamespace = 'default'
) {
  const manifest =
    index ??
    nativeUrbanIndexDto.parse(
      await readPublicData(
        '/data/seoul-street-life-v1/index.json',
        NATIVE_URBAN_HASH,
        524288,
        signal,
        namespace
      )
    );
  if (
    manifest.sourceCitySha256 !== cityHash ||
    new Set(manifest.tiles.map((tile) => tile.id)).size !== manifest.tiles.length ||
    manifest.tiles.some((tile) => tile.file !== `tiles/${tile.id}.json.gz`)
  )
    throw new CityError('INVALID_DATA');
  if (!signal.aborted) index = manifest;
  const entry = manifest.tiles.find((tile) => tile.id === id);
  if (!entry) throw new CityError('INVALID_DATA');
  const parsed = nativeUrbanTileDto.safeParse(
    await readPublicData(
      '/data/seoul-street-life-v1/' + entry.file,
      entry.sha256,
      entry.bytes,
      signal,
      namespace
    )
  );
  if (!parsed.success || parsed.data.id !== id) throw new CityError('INVALID_DATA');
  return parsed.data;
}
