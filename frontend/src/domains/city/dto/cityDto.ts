import { z } from 'zod';
const coordinate = z.number().finite().min(-60000).max(60000);
const point = z.tuple([coordinate, coordinate]);
const ring = z.array(point).min(4).max(20000);
const polygons = z.array(z.array(ring).min(1).max(500)).min(1).max(1000);
const sha = z.string().regex(/^[a-f0-9]{64}$/);
const bounds = z.tuple([coordinate, coordinate, coordinate, coordinate]);
const objectId = z.string().regex(/^ngii:[A-Za-z0-9_]+:[a-f0-9]{64}$/);
const candidate = z.string().regex(/^C[a-f0-9]{24}$/);
const geometry = z.discriminatedUnion('type', [
  z.object({ type: z.literal('Polygon'), coordinates: z.array(ring).min(1).max(500) }),
  z.object({ type: z.literal('MultiPolygon'), coordinates: polygons }),
  z.object({ type: z.literal('LineString'), coordinates: z.array(point).min(2).max(20000) }),
  z.object({
    type: z.literal('MultiLineString'),
    coordinates: z.array(z.array(point).min(2).max(20000)).min(1).max(1000),
  }),
]);
export const nativeFeatureDto = z
  .object({
    id: objectId,
    role: z.enum([
      'ROAD_AREA',
      'SIDEWALK_AREA',
      'ROAD_CENTERLINE',
      'BRIDGE_AREA',
      'TUNNEL_AREA',
      'RAILWAY_AREA',
      'RAIL_CENTERLINE',
      'RIVER_WATER_AREA',
      'LAKE_RESERVOIR_AREA',
      'CULTIVATION_LANDSCAPE_AREA',
    ]),
    districtId: z.string().regex(/^11\d{3}$/),
    geometry,
    center: point,
    sourceAreaM2: z.number().nonnegative().nullable(),
    sourceLengthM: z.number().nonnegative().nullable(),
    geometryEligibility: z.string(),
    candidateId: candidate.nullable(),
    allowedMask: z.number().int().min(0).max(63),
    roadClass: z.string().nullable().optional(),
    oneWayObservation: z.string().nullable().optional(),
    trafficDirection: z.enum(['BIDIRECTIONAL', 'UNKNOWN']).optional(),
    reportedWidthRaw: z.string().nullable().optional(),
    reportedWidthUnit: z.literal('NOT_CONFIRMED').optional(),
  })
  .superRefine((feature, context) => {
    const area = feature.geometry.type === 'Polygon' || feature.geometry.type === 'MultiPolygon';
    // 면의 길이·선의 면적은 0으로 채우지 않고 원자료의 미정의 상태를 보존한다.
    if (
      area
        ? feature.sourceAreaM2 === null || feature.sourceLengthM !== null
        : feature.sourceAreaM2 !== null || feature.sourceLengthM === null
    )
      context.addIssue({ code: 'custom', message: '도형 종류와 면적·길이 불일치' });
  });
export const cityBuildingDto = z.object({
  id: objectId,
  districtId: z.string().regex(/^11\d{3}$/),
  polygons,
  center: point,
  heightM: z.number().positive().max(650),
  heightSource: z.enum(['FLOOR_COUNT_DISPLAY_ASSUMPTION', 'UNKNOWN_HEIGHT_FLAT_DISPLAY']),
  areaM2: z.number().positive(),
  candidateId: candidate.nullable(),
  geometryEligibility: z.string(),
});
export const cityTileDto = z.object({
  schemaVersion: z.literal(2),
  id: z.string().regex(/^-?\d+_-?\d+$/),
  buildings: z.array(cityBuildingDto).max(14000),
  nativeFeatures: z.array(nativeFeatureDto).max(20000),
});
export const cityDto = z.object({
  schemaVersion: z.literal(2),
  id: z.literal('seoul-ngii-20260307'),
  sourceSha256: sha,
  sourceObjectsSha256: sha,
  siteCatalogSha256: sha,
  sourceDate: z.literal('2026-03-07'),
  attribution: z.string(),
  licenseUrl: z.literal('https://www.data.go.kr/data/15059719/fileData.do'),
  coordinateSystem: z.literal('EPSG:5186'),
  originProjected: z.tuple([z.literal(198128), z.literal(551989)]),
  tileSizeM: z.literal(1000),
  bounds,
  boundary: polygons,
  districts: z
    .array(
      z.object({
        id: z.string().regex(/^11\d{3}$/),
        name: z.string().max(40),
        polygons,
        center: point,
        areaKm2: z.number().positive(),
      })
    )
    .length(25),
  surfaces: z
    .array(
      z.object({
        kind: z.enum(['water', 'green']),
        polygons,
        sourceObjectId: objectId,
        displayToleranceM: z.literal(5),
      })
    )
    .max(10000),
  roads: z
    .array(z.object({ class: z.string(), coordinates: z.array(point).min(2).max(20000) }))
    .length(0),
  overviewBuildings: z.array(cityBuildingDto).max(1200),
  buildingCount: z.number().int().positive(),
  tiles: z
    .array(
      z.object({
        id: z.string().regex(/^-?\d+_-?\d+$/),
        file: z.string().regex(/^tiles\/-?\d+_-?\d+\.json\.gz$/),
        bounds,
        buildingCount: z.number().int().nonnegative().max(14000),
        featureCount: z.number().int().nonnegative().max(20000),
        sha256: sha,
        bytes: z.number().int().positive().max(16777216),
        storedSha256: sha,
        storedBytes: z.number().int().positive().max(16777216),
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
    .length(0),
  limitations: z.array(z.string().max(500)).max(20),
});
