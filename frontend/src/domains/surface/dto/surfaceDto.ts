import { z } from 'zod';
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const num = z.number().finite();
const coordinate = num.min(-60000).max(60000);
const point = z.tuple([coordinate, coordinate]);
export const surfaceCatalogDto = z.object({
  schemaVersion: z.literal(1),
  catalogSha256: sha,
  surfaceResultSha256: sha,
  classification: z.string().max(120),
  startUtc: z.iso.datetime({ offset: true }),
  coordinateSystem: z.literal('EPSG:5186'),
  originProjected: z.tuple([num, num]),
  verticalPlacement: z.literal('TERRAIN_DRAPED_SCALAR_NOT_WATER_ELEVATION'),
  triangleCount: z.number().int().min(1).max(200000),
  timesSeconds: z
    .array(num.nonnegative())
    .min(1)
    .max(10000)
    .refine((a) => a[0] === 0 && a.every((v, i) => i === 0 || v > a[i - 1])),
  limitations: z.array(z.string().max(1000)).max(50),
});
export const surfaceFrameDto = z.object({
  catalogSha256: sha,
  sourceSha256: sha,
  index: z.number().int().min(0).max(9999),
  timeSeconds: num.nonnegative(),
  wholeDomainStorageM3: num,
  cells: z
    .array(
      z.object({
        triangleId: z.number().int().min(0).max(199999),
        vertices: z.tuple([point, point, point]),
        depthM: num.min(-1e-10),
        speedMps: num.nonnegative(),
      })
    )
    .max(8192)
    .refine((a) => new Set(a.map((c) => c.triangleId)).size === a.length),
});
