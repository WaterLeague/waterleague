import { z } from 'zod';
const point = z.tuple([z.number().finite(), z.number().finite()]);
const ring = z
  .array(point)
  .min(4)
  .refine((r) => r[0][0] === r.at(-1)![0] && r[0][1] === r.at(-1)![1]);
const polygons = z.array(z.array(ring).min(1)).min(1);
const building = z
  .object({
    id: z.string().regex(/^((way|relation)\/\d+|\d{9}:[A-Za-z0-9_-]{1,80})$/),
    kind: z.literal('building'),
    name: z.string(),
    coordinates: z.array(point).default([]),
    polygons: polygons.optional(),
    geographicCoordinates: z.array(point).default([]),
    heightM: z.number().positive().max(650),
    heightSource: z.enum(['OSM_TAG', 'LEVELS_ESTIMATE', 'VISUAL_ASSUMPTION']),
    displayAreaM2: z.number().positive(),
    center: point,
    osmVersion: z.string().nullable().default(null),
    sourceUpdatedAt: z.string().nullable().default(null),
  })
  .refine((b) => !!b.polygons || b.coordinates.length >= 4);
const transport = z.object({
  id: z.string(),
  kind: z.literal('transport'),
  transportType: z.enum(['roads', 'railways', 'bridges', 'parking']),
  polygons,
});
const road = z.object({
  id: z.string(),
  kind: z.literal('road'),
  name: z.string(),
  coordinates: z.array(point).min(2),
  highway: z.string(),
});
export const mapDto = z.object({
  id: z.string(),
  title: z.string(),
  subtitle: z.string(),
  origin: point,
  originProjected: point.optional(),
  bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  widthM: z.number().positive(),
  depthM: z.number().positive(),
  validationLevel: z.literal('DRAFT'),
  officialEvaluationAvailable: z.literal(false),
  sourceHash: z.string().regex(/^[a-f0-9]{64}$/),
  features: z.array(z.discriminatedUnion('kind', [building, road, transport])),
  attribution: z.string(),
  licenseUrl: z.enum([
    'https://www.openstreetmap.org/copyright',
    'https://www.data.go.kr/data/15059719/fileData.do',
  ]),
  limitations: z.array(z.string()),
});
export type MapDto = z.infer<typeof mapDto>;
export const rainAuditDto = z.object({
  rowCount: z.number().int(),
  stationId: z.string(),
  status: z.literal('REJECTED_FOR_SIMULATION'),
  reason: z.string(),
  sourceHash: z.string(),
  usableRainfallEventCount: z.literal(0),
});
export type RainAudit = z.infer<typeof rainAuditDto>;
