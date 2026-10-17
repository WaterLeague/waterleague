import { z } from 'zod';
const coordinate = z.number().min(-60000).max(60000);
const point = z.tuple([coordinate, coordinate]);
const ring = z.array(point).min(4).max(20000);
const polygons = z.array(z.array(ring).min(1).max(500)).min(1).max(1000);
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const bounds = z.tuple([coordinate, coordinate, coordinate, coordinate]);
export const cityBuildingDto = z.object({
  id: z.string().regex(/^(way|relation)\/[0-9]+$/),
  polygons,
  center: point,
  heightM: z.number().positive().max(650),
  heightSource: z.enum(['OSM_HEIGHT_TAG', 'LEVELS_ESTIMATE', 'VISUAL_ASSUMPTION']),
  areaM2: z.number().nonnegative(),
});
export const cityTileDto = z.object({
  schemaVersion: z.literal(1),
  id: z.string().regex(/^-?\d+_-?\d+$/),
  buildings: z.array(cityBuildingDto).max(10000),
});
export const cityDto = z.object({
  schemaVersion: z.literal(1),
  id: z.literal('seoul-osm-20261016'),
  sourceSha256: sha,
  sourceDate: z.literal('2026-10-16'),
  attribution: z.string(),
  licenseUrl: z.literal('https://www.openstreetmap.org/copyright'),
  coordinateSystem: z.literal('EPSG:5186'),
  originProjected: z.tuple([z.number(), z.number()]),
  tileSizeM: z.literal(1000),
  bounds,
  boundary: polygons,
  districts: z
    .array(
      z.object({
        id: z.string(),
        name: z.string().max(40),
        polygons,
        center: point,
        areaKm2: z.number().positive(),
      })
    )
    .length(25),
  surfaces: z.array(z.object({ kind: z.enum(['water', 'green']), polygons })).max(10000),
  roads: z
    .array(z.object({ class: z.string(), coordinates: z.array(point).min(2).max(20000) }))
    .max(100000),
  overviewBuildings: z.array(cityBuildingDto).max(1200),
  buildingCount: z.number().int().positive(),
  tiles: z
    .array(
      z.object({
        id: z.string().regex(/^-?\d+_-?\d+$/),
        file: z.string().regex(/^tiles\/-?\d+_-?\d+\.json$/),
        bounds,
        buildingCount: z.number().int().positive().max(10000),
        sha256: sha,
        bytes: z.number().int().positive().max(10000000),
      })
    )
    .max(2000),
  playAreas: z
    .array(
      z.object({
        id: z.string(),
        name: z.string(),
        center: point,
        status: z.literal('EXPLORATORY'),
      })
    )
    .max(1000),
  limitations: z.array(z.string().max(500)).max(20),
});
