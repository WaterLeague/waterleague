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
    sourceFids: z.array(z.number().int().positive()).max(10000).optional(),
    coordinates: z.array(point).min(2).max(100000),
    span: z.tuple([z.number().finite().nonnegative(), z.number().finite().positive()]),
    polygons: z.array(z.array(z.array(point).min(4).max(100000)).min(1).max(1000)).max(10000),
    steps: z.boolean().optional(),
    islandConnection: z.boolean().optional(),
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
  groundCutPolygons: polygons.optional(),
  attachmentPolygons: polygons.optional(),
  sourceSurfaceCuts: z
    .array(
      z.object({ sourceFids: z.array(z.number().int().positive()).min(1).max(10000), polygons })
    )
    .max(10000)
    .optional(),
  surfaceCuts: z
    .array(
      z.object({
        roles: z
          .array(
            z.enum([
              'ROAD_AREA',
              'INTERSECTION_AREA',
              'INTERCHANGE_AREA',
              'CROSSWALK_AREA',
              'TRAFFIC_SAFETY_AREA',
              'SIDEWALK_AREA',
              'RAILWAY_AREA',
            ])
          )
          .min(1)
          .max(7),
        polygons,
      })
    )
    .max(3)
    .optional(),
  preservedUnderpassPolygons: polygons.optional(),
  names: z.array(z.string().max(200)).max(1).optional(),
  kinds: z.array(z.string().max(50)).max(2).optional(),
  profiles: z.array(bridgeProfileDto).max(10000),
  lowerDeck: z
    .object({
      name: z.enum(['잠수교', '청담대교 하부 전철']),
      rail: z.boolean(),
      displayOnly: z.literal(true),
      geometryBasis: z.literal('SOURCE_AXIS_CLIPPED_TO_SOURCE_BRIDGE'),
      sourceUrl: z.enum([
        'https://news.seoul.go.kr/env/archives/520397',
        'https://news.seoul.go.kr/citybuild/archives/208956',
      ]),
      displayWidthM: z.number().positive().max(30),
      deckLiftM: z.literal(6.5),
      polygons,
      sidewalks: z.array(z.array(z.array(point).min(4).max(100000)).min(1).max(1000)).max(10000),
      walkPaths: z.array(z.array(point).min(2).max(100000)).max(10000),
      railPaths: z.array(z.array(point).min(2).max(100000)).max(10000),
      approaches: z.array(bridgeProfileDto).max(100),
    })
    .optional(),
  walkPaths: z.array(z.array(point).min(2).max(100000)).max(10000).optional(),
  sidewalks: z
    .array(
      z.object({
        sourceId,
        sourceFids: z.array(z.number().int().positive()).max(10000).optional(),
        polygons,
        paths: z.array(z.array(point).min(2).max(100000)).max(10000),
        approaches: z
          .array(
            z.object({
              profileIndex: z.number().int().nonnegative(),
              polygons,
              paths: z.array(z.array(point).min(2).max(100000)).max(10000),
            })
          )
          .max(10000)
          .optional(),
      })
    )
    .max(10000)
    .optional(),
});
export const nativeBridgesDto = z
  .object({
    schemaVersion: z.literal(1),
    groups: z.array(nativeBridgeGroupDto).max(10000),
    waterPolygons: polygons.optional(),
  })
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
export type NativeBridgeGroup = Omit<z.infer<typeof nativeBridgeGroupDto>, 'profiles'> & {
  displayDatumPolygons?: z.infer<typeof polygons>;
  displayWaterPolygons?: z.infer<typeof polygons>;
  profiles: (z.infer<typeof bridgeProfileDto> & { connections?: ProfileConnection[] })[];
};
export type ProfileConnection = {
  side: 0 | 1;
  gapM: number;
  deckPolygons: z.infer<typeof polygons>;
  deckLiftM: number;
  endpointTarget?: NativeBridgeProfile & { point: [number, number] };
};
export type NativeBridgeProfile = z.infer<typeof bridgeProfileDto> & {
  deckPolygons: NativeBridgeGroup['polygons'];
  deckLiftM?: number;
  connections?: ProfileConnection[];
};
