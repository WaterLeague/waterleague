import { z } from 'zod';
import { readPublicData } from '../../../shared/repository/publicDataCache';
import { CityError } from '../exception/CityError';
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const indexDto = z.object({
  schemaVersion: z.literal(1),
  sourceCitySha256: sha,
  districts: z.array(z.string().regex(/^11\d{3}$/)).length(25),
  tileIds: z.array(z.string().regex(/^-?\d+_-?\d+$/)).max(2000),
  levels: z
    .array(
      z.object({
        spacingM: z.union([z.literal(100), z.literal(25)]),
        file: z.string().regex(/^(?:100|25)\.json\.gz$/),
        sha256: sha,
        bytes: z.number().int().positive().max(32000000),
        count: z.number().int().positive().max(1000000),
      })
    )
    .length(2),
  policy: z.object({
    displayOnly: z.literal(true),
    axisAlignedBoundingBoxes: z.literal(true),
    selectionEnabled: z.literal(false),
    hydraulicInputsChanged: z.literal(false),
    heightSourceUnchanged: z.literal(true),
  }),
});
const xy = z.number().finite().min(-60000).max(60000);
const record = z.tuple([
  xy,
  xy,
  z.number().positive().max(20000),
  z.number().positive().max(20000),
  z.number().positive().max(650),
  z.number().int().min(0).max(24),
  z.number().int().min(0).max(1999),
]);
const levelDto = z.object({
  schemaVersion: z.literal(1),
  spacingM: z.union([z.literal(100), z.literal(25)]),
  buildings: z.array(record).max(1000000),
});
export type OverviewBuilding = z.infer<typeof record>;
export type CityOverview = {
  buildings: OverviewBuilding[];
  districts: string[];
  tileIds: string[];
};
export const CITY_OVERVIEW_HASH =
  'f8904b9679f6c0fda8d3c3b2139efb74e449aa17851ac047a65d6b420e80414d';
let index: z.infer<typeof indexDto> | undefined;
const cache = new Map<number, CityOverview>();
export async function loadCityOverview(spacingM: 25 | 100, cityHash: string, signal: AbortSignal) {
  const cached = cache.get(spacingM);
  if (cached) return cached;
  const parsed = indexDto.safeParse(
    index ??
      (await readPublicData(
        '/data/seoul-overview-v1/index.json',
        CITY_OVERVIEW_HASH,
        524288,
        signal
      ))
  );
  if (!parsed.success || parsed.data.sourceCitySha256 !== cityHash)
    throw new CityError('INVALID_DATA');
  index = parsed.data;
  const entry = index.levels.find((level) => level.spacingM === spacingM);
  if (!entry || entry.file !== `${spacingM}.json.gz`) throw new CityError('INVALID_DATA');
  const data = levelDto.safeParse(
    await readPublicData('/data/seoul-overview-v1/' + entry.file, entry.sha256, entry.bytes, signal)
  );
  if (
    !data.success ||
    data.data.spacingM !== spacingM ||
    data.data.buildings.length !== entry.count ||
    data.data.buildings.some((building) => building[6] >= index!.tileIds.length)
  )
    throw new CityError('INVALID_DATA');
  const value = {
    buildings: data.data.buildings,
    districts: index.districts,
    tileIds: index.tileIds,
  };
  if (!signal.aborted) cache.set(spacingM, value);
  return value;
}
