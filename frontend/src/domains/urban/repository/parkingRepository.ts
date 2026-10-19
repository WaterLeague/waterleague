import { z } from 'zod';
import { read } from './urbanRepository';
import type { ParkingData } from '../entity/parking';
const point = z.tuple([z.number().min(-60000).max(60000), z.number().min(-60000).max(60000)]);
const ring = z.array(point).min(4).max(20000);
const schema = z.object({
  schemaVersion: z.literal(1),
  sourceDate: z.literal('2026-10-16'),
  modelInput: z.literal(false),
  displayRoadWidths: z
    .array(
      z.object({
        id: z.string().regex(/^way\/\d+:\d+$/),
        lanes: z.number().int().min(1).max(8),
        widthM: z.number().positive().max(80),
      })
    )
    .max(100000),
  streetCatalogSha256: z.literal(
    '13d7a611ec46e0930a92951646edc2fd10a566627ad51ec164c9574a4f8dab9a'
  ),
  lots: z
    .array(
      z.object({
        id: z.string().regex(/^(way|relation)\/\d+$/),
        polygons: z.array(z.array(ring).min(1).max(500)).min(1).max(1000),
        surfacePolygons: z.array(z.array(ring).min(1).max(500)).max(10000),
        supports: z
          .array(
            z.object({
              center: point,
              angle: z.number().finite(),
              width: z.number().positive().max(80),
            })
          )
          .max(10000),
        bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]),
        slots: z
          .array(
            z.object({
              center: point,
              angle: z.number().finite(),
              corners: ring,
              seed: z.number().min(0).max(1),
            })
          )
          .max(160),
      })
    )
    .max(10000),
  routes: z
    .array(
      z.object({
        id: z.string().regex(/^way\/\d+:\d+$/),
        reason: z.enum(['OSM_PARKING_AISLE', 'PUBLIC_PARKING_BOUNDARY']),
        parts: z.array(z.array(point).min(2).max(30000)).max(1000),
      })
    )
    .max(100000),
});
let cache: ParkingData | null = null;
export async function loadParking(signal: AbortSignal) {
  if (cache) return cache;
  const value = schema.parse(
    await read(
      '/data/city-parking-v1.json',
      '19ad1b5d5b56bf4a98f0878ccb1d2436b87785abb1845acc3ece8de19b272447',
      16000000,
      signal
    )
  );
  if (!signal.aborted) cache = value;
  return value;
}
