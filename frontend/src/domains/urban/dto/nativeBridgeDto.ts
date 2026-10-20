import { z } from 'zod';
const coordinate = z.number().finite().min(-100000).max(100000);
const point = z.tuple([coordinate, coordinate]);
const polygons = z
  .array(z.array(z.array(point).min(4).max(100000)).min(1).max(1000))
  .min(1)
  .max(10000);
const sourceId = z.string().regex(/^ngii:N1[AL]_[A-H]\d{7}:[a-f0-9]{64}$/);
const roadId = z.string().regex(/^ngii:N1L_(?:A0020000|A0150000):[a-f0-9]{64}:part:\d+$/);
export const bridgeProfileDto = z
  .object({
    roadIds: z.array(roadId).min(0).max(10000),
    coordinates: z.array(point).min(2).max(100000),
    span: z.tuple([z.number().finite().nonnegative(), z.number().finite().positive()]),
    polygons,
    steps: z.boolean().optional(),
    rail: z.boolean().optional(),
    lanes: z.number().int().min(0).max(32).optional(),
    displayWidthM: z.number().finite().positive().max(1000),
  })
  .superRefine((value, context) => {
    let length = 0;
    for (let i = 1; i < value.coordinates.length; i++)
      length += Math.hypot(
        value.coordinates[i][0] - value.coordinates[i - 1][0],
        value.coordinates[i][1] - value.coordinates[i - 1][1]
      );
    if (
      (!value.roadIds.length && !value.steps) ||
      value.span[0] >= value.span[1] ||
      value.span[1] > length + 0.01
    )
      context.addIssue({ code: 'custom', message: '교량 접속 범위 오류' });
  });
export const nativeBridgeGroupDto = z.object({
  id: sourceId,
  role: z.enum(['BRIDGE_AREA', 'PEDESTRIAN_OVERPASS_AREA', 'GRADE_SEPARATED_INTERSECTION_AREA']),
  sourceIds: z.array(sourceId).min(1).max(10000),
  sourceFids: z.array(z.number().int().positive()).min(1).max(10000),
  bounds: z.tuple([coordinate, coordinate, coordinate, coordinate]),
  polygons,
  outlinePolygons: polygons.optional(),
  names: z.array(z.string().max(200)).max(1).optional(),
  kinds: z.array(z.string().max(50)).max(2).optional(),
  profiles: z.array(bridgeProfileDto).max(10000),
  walkPaths: z.array(z.array(point).min(2).max(100000)).max(10000).optional(),
  sidewalks: z
    .array(
      z.object({
        sourceId,
        polygons,
        paths: z.array(z.array(point).min(2).max(100000)).max(10000),
      })
    )
    .max(10000)
    .optional(),
});
export const nativeBridgesDto = z
  .object({ schemaVersion: z.literal(1), groups: z.array(nativeBridgeGroupDto).max(10000) })
  .superRefine((value, context) => {
    const ids = value.groups.flatMap((g) => g.sourceIds);
    if (
      new Set(ids).size !== ids.length ||
      value.groups.some(
        (g) => g.id !== g.sourceIds[0] || g.sourceIds.length !== g.sourceFids.length
      )
    )
      context.addIssue({ code: 'custom', message: '교량 원본 대응 오류' });
  });
export type NativeBridgeGroup = z.infer<typeof nativeBridgeGroupDto>;
export type NativeBridgeProfile = z.infer<typeof bridgeProfileDto> & {
  deckPolygons: NativeBridgeGroup['polygons'];
  deckLiftM?: number;
};
