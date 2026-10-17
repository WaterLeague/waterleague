import { z } from 'zod';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const point = z.tuple([z.number().finite(), z.number().finite()]);
const localPoint = z.tuple([
  z.number().finite().min(-500.001).max(500.001),
  z.number().finite().min(-500.001).max(500.001),
]);
const ring = z
  .array(localPoint)
  .min(4)
  .max(20000)
  .refine((r) => r[0][0] === r.at(-1)![0] && r[0][1] === r.at(-1)![1]);
const polygons = z.array(z.array(ring).min(1).max(1000)).min(1).max(2000);
export const sceneContextSourceDto = z.object({
  file: z.string().regex(/^seoul-context-v\d+-\d+\.json$/),
  sha256: hash,
  bytes: z
    .number()
    .int()
    .positive()
    .max(2 * 1024 * 1024),
});
export const sceneContextDto = z
  .object({
    schemaVersion: z.literal(1),
    modelInput: z.literal(false),
    mapId: z.string().regex(/^seoul-osm-v1-\d+$/),
    baseMapSha256: hash,
    sourceSha256: hash,
    sourceDate: z.string(),
    coordinateSystem: z.literal('EPSG:5186_LOCAL_TRANSLATION'),
    originProjected: point,
    widthM: z.literal(1000),
    depthM: z.literal(1000),
    features: z
      .array(
        z.object({
          id: z.string().regex(/^(way|relation)\/\d+$/),
          kind: z.enum(['road', 'rail', 'green', 'water']),
          name: z.string(),
          classification: z.string(),
          polygons,
          widthM: z.number().positive().max(80).optional(),
          widthEvidence: z.enum(['OSM_WIDTH_TAG', 'DISPLAY_ASSUMPTION']).optional(),
          structure: z.enum(['SURFACE', 'BRIDGE']).optional(),
        })
      )
      .max(5000),
    labels: z.array(z.object({ name: z.string(), center: localPoint })).max(3),
    attribution: z.string(),
    limitations: z.array(z.string()),
  })
  .refine(
    (context) =>
      new Set(context.features.map((f) => `${f.kind}:${f.id}`)).size === context.features.length &&
      context.features.every(
        (f) =>
          (f.kind !== 'road' && f.kind !== 'rail') ||
          (f.widthM != null && f.widthEvidence != null && f.structure != null)
      )
  );
