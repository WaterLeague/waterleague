import { z } from 'zod';
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const coordinate = z.number().finite().min(-100000).max(100000);
const point = z.tuple([coordinate, coordinate]);
const ring = z.array(point).min(4).max(100000);
const layer = z.number().int().min(0).max(120);
const fid = z.number().int().positive().max(10000000);
const label = z.string().max(200).nullable();
export const topographyTileDto = z.object({
  schemaVersion: z.literal(1),
  id: z.string().regex(/^-?\d+_-?\d+$/),
  points: z.array(z.tuple([layer, fid, z.array(point).min(1).max(10000), label])).max(200000),
  lines: z
    .array(
      z.tuple([layer, fid, z.array(z.array(point).min(2).max(100000)).min(1).max(10000), label])
    )
    .max(200000),
  areas: z
    .array(z.tuple([layer, fid, z.array(z.array(ring).min(1).max(10000)).min(1).max(10000), label]))
    .max(50000),
});
export const topographyIndexDto = z
  .object({
    schemaVersion: z.literal(1),
    id: z.literal('SEOUL_NGII_ALL_LAYERS_V1'),
    sourceSpatialSha256: sha,
    sourceCitySha256: sha,
    sourceStreetLifeSha256: sha,
    sourceSemanticsSha256: sha,
    layers: z
      .array(
        z.object({
          id: z.string().regex(/^N[134][ALP]_[A-H]\d{7}$/),
          name: z.string().min(1).max(100),
          shapeType: z.string(),
          scaleDenominator: z.number().int().positive(),
          role: z.string(),
          symbol: z.string(),
          color: z.string().regex(/^#[a-f0-9]{6}$/),
          renderer: z.string(),
          sourceCount: z.number().int().nonnegative(),
          uniqueDisplayCount: z.number().int().nonnegative(),
          displayPartCount: z.number().int().nonnegative(),
        })
      )
      .length(121),
    tiles: z
      .array(
        z.object({
          id: z.string().regex(/^-?\d+_-?\d+$/),
          file: z.string().regex(/^tiles\/-?\d+_-?\d+\.json\.gz$/),
          bounds: z.tuple([coordinate, coordinate, coordinate, coordinate]),
          sha256: sha,
          bytes: z.number().int().positive().max(33554432),
          storedBytes: z.number().int().positive().max(33554432),
          counts: z.object({
            points: z.number().int().nonnegative(),
            lines: z.number().int().nonnegative(),
            areas: z.number().int().nonnegative(),
          }),
        })
      )
      .max(10000),
    policy: z.object({
      allLayerRenderersBound: z.literal(true),
      tileClippingIsDisplayOnly: z.literal(true),
      hydraulicInputsChanged: z.literal(false),
      geometryRepair: z.literal(false),
      sourceFidBoundToSpatialHash: z.literal(true),
    }),
  })
  .superRefine((index, context) => {
    if (
      new Set(index.layers.map((layer) => layer.id)).size !== 121 ||
      new Set(index.tiles.map((tile) => tile.id)).size !== index.tiles.length ||
      index.tiles.some((tile) => tile.file !== `tiles/${tile.id}.json.gz`)
    )
      context.addIssue({ code: 'custom', message: '전체 지형지물 원본 대응 오류' });
  });
export type TopographyIndex = z.infer<typeof topographyIndexDto>;
export type TopographyTile = z.infer<typeof topographyTileDto>;
export type TopographyEntry = TopographyIndex['tiles'][number];
