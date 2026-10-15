import { z } from 'zod';
const point = z.tuple([z.number().min(127.04).max(127.07), z.number().min(37.53).max(37.56)]);
const ring = z
  .array(point)
  .min(4)
  .max(10000)
  .refine((points) => {
    const first = points[0],
      last = points[points.length - 1];
    return first[0] === last[0] && first[1] === last[1];
  });
export const spatialDto = z.object({
  provider: z.string(),
  layer: z.literal('LT_C_SPBD'),
  requestedCrs: z.literal('EPSG:4326'),
  sourceUrl: z.literal('https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=spbd&apiVer=2'),
  retrievedAt: z.iso.datetime(),
  use: z.literal('DISPLAY_COMPARISON_ONLY'),
  rawRetained: z.literal(false),
  bounds: z.tuple([
    z.literal(127.0525),
    z.literal(37.543),
    z.literal(127.0555),
    z.literal(37.5455),
  ]),
  buildings: z
    .array(
      z.object({
        id: z.string().min(1).max(100),
        name: z.string().max(200),
        aboveGroundFloors: z.number().int().min(1).max(200).nullable(),
        polygons: z.array(z.array(ring).min(1).max(100)).min(1).max(100),
      })
    )
    .min(1)
    .max(1000),
});
