import { z } from 'zod';
const point = z.tuple([z.number().finite(), z.number().finite()]);
const building = z.object({ id: z.string().regex(/^way\/\d+$/), kind: z.literal('building'), name: z.string(), coordinates: z.array(point).min(4),
  geographicCoordinates: z.array(point), heightM: z.number().positive().max(500), heightSource: z.enum(['OSM_TAG','LEVELS_ESTIMATE','VISUAL_ASSUMPTION']), displayAreaM2: z.number().positive(), center: point,
  osmVersion: z.string().nullable(), sourceUpdatedAt: z.string().nullable() });
const road = z.object({ id: z.string(), kind: z.literal('road'), name: z.string(), coordinates: z.array(point).min(2), highway: z.string() });
export const mapDto = z.object({ id: z.string(), title: z.string(), subtitle: z.string(), origin: point, bounds: z.tuple([z.number(),z.number(),z.number(),z.number()]),
  widthM: z.number().positive(), depthM: z.number().positive(), validationLevel: z.literal('DRAFT'), officialEvaluationAvailable: z.literal(false),
  sourceHash: z.string().regex(/^[a-f0-9]{64}$/), features: z.array(z.discriminatedUnion('kind',[building,road])), attribution: z.string(), licenseUrl: z.literal('https://www.openstreetmap.org/copyright'), limitations: z.array(z.string()) });
export type MapDto = z.infer<typeof mapDto>;
export const rainAuditDto = z.object({ rowCount: z.number().int(), stationId: z.string(), status: z.literal('REJECTED_FOR_SIMULATION'), reason: z.string(), sourceHash: z.string(), usableRainfallEventCount: z.literal(0) });
export type RainAudit = z.infer<typeof rainAuditDto>;
