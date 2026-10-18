import { z } from 'zod';
const n = z.number().finite();
const point = z.tuple([n, n]);
export const cisternLayoutRequestDto = z.object({
  widthM: n.min(0.01).max(10000),
  wallThicknessM: n.min(0.001).max(10),
  offsetXM: n.min(-100000).max(100000),
  offsetYM: n.min(-100000).max(100000),
  rotationDeg: n.min(0).lt(360),
});
export const cisternGeometryDto = z.object({
  method: z.literal('RECTANGULAR_INTERNAL_SECTION_WITH_WALL_V1'),
  sourceModelHash: z.string().regex(/^[a-f0-9]{64}$/),
  center: point,
  internalWidthM: n.positive(),
  internalLengthM: n.positive(),
  wallThicknessM: n.positive(),
  outerWidthM: n.positive(),
  outerLengthM: n.positive(),
  storageDepthM: n.positive(),
  rotationDeg: n.min(0).lt(360),
  coordinates: z.array(point).length(5),
  contained: z.literal(true),
});
export type CisternLayoutRequest = z.infer<typeof cisternLayoutRequestDto>;
export type CisternGeometry = z.infer<typeof cisternGeometryDto>;
export type CisternGeometryPreview = Omit<CisternGeometry, 'contained'> & { contained: boolean };
