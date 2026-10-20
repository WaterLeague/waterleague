import { z } from 'zod';
import { readPublicData } from '../../../shared/repository/publicDataCache';
const point = z.tuple([z.number().finite(), z.number().finite()]);
export const cityCoverageDto = z.object({
  schemaVersion: z.literal(1),
  sourceSpatialSha256: z.literal(
    '4eeb19430451d115807398df34cea75557ff1c152438c56750c8b0fafa395373'
  ),
  areas: z
    .array(
      z.object({
        id: z.string().max(80),
        status: z.enum(['UNSUPPORTED', 'COARSE_ONLY']),
        areaM2: z.number().positive(),
        polygons: z
          .array(z.array(z.array(point).min(4).max(50000)).min(1).max(1000))
          .min(1)
          .max(1000),
        center: point,
        bounds: z.tuple([
          z.number().finite(),
          z.number().finite(),
          z.number().finite(),
          z.number().finite(),
        ]),
      })
    )
    .max(1000),
});
export type CityCoverageArea = z.infer<typeof cityCoverageDto>['areas'][number];
export const CITY_COVERAGE_HASH =
  '81180f46e215a149088d033c34751a02a19201958fdfd37b62f32b669aa28f3c';
let cached: CityCoverageArea[] | undefined;
export async function loadCityCoverage(signal: AbortSignal) {
  if (cached) return cached;
  const value = cityCoverageDto.parse(
    await readPublicData('/data/seoul-coverage-v1.json', CITY_COVERAGE_HASH, 4194304, signal)
  );
  if (!signal.aborted) cached = value.areas;
  return value.areas;
}
