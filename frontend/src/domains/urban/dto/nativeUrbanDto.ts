import { z } from 'zod';
const coordinate = z.number().finite().min(-60000).max(60000);
const point = z.tuple([coordinate, coordinate]);
const ring = z.array(point).min(4).max(20000);
const polygons = z.array(z.array(ring).min(1).max(500)).min(1).max(1000);
const objectId = z.string().regex(/^ngii:[A-Za-z0-9_]+:[a-f0-9]{64}$/);
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const tileId = z.string().regex(/^-?\d+_-?\d+$/);
const district = z.string().regex(/^11\d{3}$/);
export const nativeUrbanIndexDto = z.object({
  schemaVersion: z.literal(1),
  sourceCitySha256: sha,
  sourceObjectsSha256: sha,
  sourceSpatialSha256: sha,
  sourceSceneSha256: sha,
  originProjected: z.tuple([z.literal(198128), z.literal(551989)]),
  tiles: z
    .array(
      z.object({
        id: tileId,
        file: z.string().regex(/^tiles\/-?\d+_-?\d+\.json\.gz$/),
        sha256: sha,
        bytes: z.number().int().positive().max(4194304),
      })
    )
    .max(2000),
  policy: z.object({
    sourceGeometryPreserved: z.literal(true),
    routesAreObserved: z.literal(false),
    parkingStallsProvided: z.literal(false),
    parkedCarsAreObserved: z.literal(false),
    hydraulicInputsChanged: z.literal(false),
    bridgeHeightIsSurveyed: z.literal(false),
    pedestrianClearanceM: z.literal(0.4),
    bridgeDisplayLiftM: z.literal(6.5),
  }),
});
export const nativeUrbanTileDto = z
  .object({
    schemaVersion: z.literal(1),
    id: tileId,
    crosswalks: z
      .array(
        z.object({
          id: objectId,
          districtId: district,
          polygons,
          stripes: z.array(z.array(ring).min(1).max(500)).max(5000),
        })
      )
      .max(2000),
    walkPaths: z
      .array(
        z.object({
          id: z.string().max(160),
          sourceObjectId: objectId,
          districtId: district,
          coordinates: z.array(point).min(2).max(20000),
        })
      )
      .max(20000),
    parkingLots: z
      .array(
        z.object({
          id: objectId,
          districtId: district,
          polygons,
          surfacePolygons: polygons,
          bounds: z.tuple([coordinate, coordinate, coordinate, coordinate]),
          displayOnly: z.literal(true),
          supports: z.array(z.never()).length(0),
          slots: z
            .array(
              z.object({
                center: point,
                angle: z.literal(0),
                corners: ring,
                seed: z.number().min(0).lt(1),
              })
            )
            .max(120),
        })
      )
      .max(2000),
  })
  .superRefine((tile, context) => {
    for (const values of [tile.crosswalks, tile.walkPaths, tile.parkingLots])
      if (new Set(values.map((value) => value.id)).size !== values.length)
        context.addIssue({ code: 'custom', message: '교통 표시 식별자 중복' });
    for (const path of tile.walkPaths)
      if (!path.id.startsWith(path.sourceObjectId + ':walk:'))
        context.addIssue({ code: 'custom', message: '보행 표시 원형 대응 오류' });
  });
export type NativeUrbanTile = z.infer<typeof nativeUrbanTileDto>;
