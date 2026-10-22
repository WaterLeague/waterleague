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
  districtLevels: z
    .array(
      z.object({
        districtId: z.string().regex(/^11\d{3}$/),
        spacingM: z.union([z.literal(100), z.literal(25)]),
        file: z.string().regex(/^districts\/11\d{3}\/(?:100|25)\.json\.gz$/),
        sha256: sha,
        bytes: z.number().int().positive().max(32000000),
        count: z.number().int().nonnegative().max(1000000),
      })
    )
    .length(50),
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
  'a8a530be747fe0294c6b141826f92699afb278e0f6cd76bfcc057ab6cae119a7';
let index: z.infer<typeof indexDto> | undefined;
const cache = new Map<string, CityOverview>();
export async function loadCityOverview(
  spacingM: 25 | 100,
  cityHash: string,
  signal: AbortSignal,
  districtIds?: string[]
) {
  const selection =
    districtIds && districtIds.length < 25 ? [...new Set(districtIds)].sort() : undefined;
  const key = `${spacingM}:${selection?.join(',') ?? 'all'}`;
  const cached = cache.get(key);
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
  const entries = selection
    ? selection.map((id) =>
        index!.districtLevels.find((e) => e.districtId === id && e.spacingM === spacingM)
      )
    : [index.levels.find((e) => e.spacingM === spacingM)];
  if (!entries.length || entries.some((e) => !e)) throw new CityError('INVALID_DATA');
  const buildings: OverviewBuilding[] = [];
  for (let i = 0; i < entries.length; i += 4) {
    const batches = await Promise.all(
      entries.slice(i, i + 4).map(async (entry) => {
        if (!entry) throw new CityError('INVALID_DATA');
        const data = levelDto.safeParse(
          await readPublicData(
            '/data/seoul-overview-v1/' + entry.file,
            entry.sha256,
            entry.bytes,
            signal
          )
        );
        if (
          !data.success ||
          data.data.spacingM !== spacingM ||
          data.data.buildings.length !== entry.count ||
          data.data.buildings.some(
            (b) =>
              b[6] >= index!.tileIds.length ||
              (selection &&
                (!selection.includes(index!.districts[b[5]]) ||
                  entry.file !== `districts/${index!.districts[b[5]]}/${spacingM}.json.gz`))
          )
        )
          throw new CityError('INVALID_DATA');
        return data.data.buildings;
      })
    );
    // 서울 전체 확대 자료는 함수 인자 개수 한도를 넘으므로 한 항목씩 병합한다.
    for (const batch of batches) {
      for (const building of batch) buildings.push(building);
    }
  }
  const value = { buildings, districts: index.districts, tileIds: index.tileIds };
  if (!signal.aborted) cache.set(key, value);
  return value;
}
