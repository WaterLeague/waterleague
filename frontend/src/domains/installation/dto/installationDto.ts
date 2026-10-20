import { z } from 'zod';
import {
  swaleDesignDto,
  trenchDesignDto,
  nativeSoilBoundaryDto,
} from '../../facility/dto/facilityDto';
import { costSourceDto } from '../../cost/dto/costDto';
import { conditionIds, eligibilityDto, siteSuitabilityDto } from './siteSuitabilityDto';
const facility = z.enum([
  'RAIN_GARDEN',
  'PERMEABLE_PAVEMENT',
  'GREEN_ROOF',
  'BIORETENTION',
  'VEGETATIVE_SWALE',
  'INFILTRATION_TRENCH',
  'RAINWATER_CISTERN',
]);
const point = z.tuple([z.number().finite(), z.number().finite()]);
export const publicAssetPolicyDto = z.object({
  version: z.enum([
    'seoul-basin-footprints-20261018-v1',
    'seoul-basin-footprints-20261018-v2',
    'seoul-basin-footprints-20261018-v3',
    'seoul-basin-footprints-20261018-v4',
    'seoul-infrastructure-occupancy-20261019-v5',
    'seoul-native-infrastructure-20261020-v1',
  ]),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  sourceSha256: z.string().regex(/^[a-f0-9]{64}$/),
  scope: z.enum([
    'CURRENT_MAPPED_GEOMETRY_NEW_GROUND_PLACEMENTS_ONLY',
    'CURRENT_MAPPED_GROUND_AND_RESERVED_BUILDINGS',
    'CURRENT_NATIVE_POINT_ASSOCIATIONS_REFERENCE_ONLY',
  ]),
  historicalExistenceVerified: z.literal(false),
});
export const installationDto = z.object({
  id: z.uuid(),
  districtId: z.string(),
  cellId: z.string(),
  ownerId: z.uuid(),
  ownerName: z.string().max(40),
  facilityType: facility,
  areaM2: z.number().positive(),
  cost: z.number().nonnegative(),
  installedAt: z.iso.datetime(),
  seasonEndsAt: z.iso.datetime().nullish(),
  center: point,
  heightM: z.number().nonnegative(),
  scoreM3: z.number().finite().nullable().optional(),
  evaluatedThrough: z.iso.datetime().nullable().optional(),
});
export const siteDto = z
  .object({
    existingInfrastructure: z
      .object({
        policy: publicAssetPolicyDto,
        assets: z
          .array(
            z.object({
              districtId: z.string(),
              cellId: z.string(),
              siteModelHash: z.string().regex(/^[a-f0-9]{64}$/),
              assetId: z.string(),
              assetName: z.string(),
              overlapAreaM2: z.number().positive(),
            })
          )
          .min(1),
      })
      .nullish(),
    districtId: z.string(),
    cellId: z.string(),
    name: z.string(),
    address: z.string().max(300).nullish(),
    kind: z.enum(['ROOF', 'GROUND']),
    polygons: z
      .array(z.array(z.array(point).min(4).max(20000)).min(1).max(500))
      .min(1)
      .max(1000),
    sourceRole: z.enum([
      'BUILDING_FOOTPRINT',
      'ROAD_AREA',
      'SIDEWALK_AREA',
      'PARKING_AREA',
      'CULTIVATION_LANDSCAPE_AREA',
    ]),
    referenceInfrastructure: z
      .object({
        policy: publicAssetPolicyDto,
        references: z
          .array(
            z.object({
              assetId: z.string(),
              assetName: z.string(),
              relation: z.literal('PUBLIC_POINT_COVERED_BY_NATIVE_CANDIDATE'),
              verticalLayer: z.literal('UNKNOWN'),
              footprintVerified: z.literal(false),
            })
          )
          .max(1000),
      })
      .nullish(),
    center: point,
    heightM: z.number().nonnegative(),
    areaM2: z.number().positive(),
    maxAreaM2: z.number().positive(),
    allowedTypes: z.array(facility).min(1),
    unitCosts: z.object({
      RAIN_GARDEN: z.number().positive(),
      PERMEABLE_PAVEMENT: z.number().positive(),
      GREEN_ROOF: z.number().positive(),
      BIORETENTION: z.number().positive().optional(),
      VEGETATIVE_SWALE: z.number().positive().optional(),
      INFILTRATION_TRENCH: z.number().positive().optional(),
      RAINWATER_CISTERN: z.number().positive().optional(),
    }),
    costSourceSha256: z.string().regex(/^[a-f0-9]{64}$/),
    costModel: z.object({
      currency: z.literal('KRW'),
      unit: z.literal('KRW_PER_SQUARE_METRE'),
      facilities: z.object({
        RAIN_GARDEN: costSourceDto,
        PERMEABLE_PAVEMENT: costSourceDto,
        GREEN_ROOF: costSourceDto,
        BIORETENTION: costSourceDto.optional(),
        VEGETATIVE_SWALE: costSourceDto.optional(),
        INFILTRATION_TRENCH: costSourceDto.optional(),
        RAINWATER_CISTERN: costSourceDto.optional(),
      }),
    }),
    sourceIds: z.array(z.string()),
    areaLimitBasis: z.enum(['PUBLIC_NATIVE_DESIGN_GEOMETRY']).optional(),
    siteEligibility: eligibilityDto.optional(),
    suitability: siteSuitabilityDto.optional(),
    inflowPolicy: z.literal('DIRECT_RAINFALL_ONLY').optional(),
    facilityDesignSet: z
      .object({ id: z.string(), sha256: z.string().regex(/^[a-f0-9]{64}$/) })
      .nullish(),
    initializationPolicy: z
      .object({ method: z.string(), warmupMinutes: z.number().int().positive() })
      .nullish(),
    physicalInputs: z
      .object({
        streetPlacement: z
          .object({
            streetId: z.string().regex(/^way\/[0-9]+:[0-9]+$/),
            role: z.enum(['ROADWAY', 'SIDEWALK', 'WALKWAY']),
            widthM: z.number().positive(),
            widthBasis: z.literal('DESIGN_ASSUMPTION'),
            sourceDate: z.string(),
            roadWidthBasis: z.enum(['OSM_WIDTH_TAG', 'DISPLAY_ASSUMPTION']),
          })
          .optional(),
        flowLengthM: z.number().positive(),
        runoffWidthM: z.number().positive(),
        widthMethod: z.literal('FOOTPRINT_AREA_OVER_LONG_AXIS'),
        slopePercent: z.number().nonnegative(),
        slopeMethod: z.enum(['PUBLIC_REFERENCE_SURFACE_SCENARIO']),
        terrainResolutionM: z.number().positive().optional(),
        nImpervious: z.number().positive().optional(),
        surfaceTag: z.string().nullable(),
        imperviousBasis: z.string(),
        soilStatus: z.string(),
        soilClass: z.string().optional(),
        conductivityMmH: z.number().positive().optional(),
        conductivityRangeMmH: z.tuple([z.number().positive(), z.number().positive()]).optional(),
        suctionMm: z.number().positive().optional(),
        rainGardenBoundary: nativeSoilBoundaryDto.optional(),
        bioretentionBoundary: nativeSoilBoundaryDto.optional(),
        swaleDesign: swaleDesignDto.optional(),
        trenchDesign: trenchDesignDto.optional(),
        trenchBoundary: nativeSoilBoundaryDto.optional(),
      })
      .optional(),
    modelHash: z.string().regex(/^[a-f0-9]{64}$/),
  })
  .refine(
    (site) =>
      !site.suitability ||
      (site.siteEligibility === site.suitability.status &&
        site.suitability.checks.length === conditionIds[site.kind].length &&
        conditionIds[site.kind].every((id) =>
          site.suitability!.checks.some((row) => row.id === id)
        ))
  );

export const sitePageDto = z.object({
  sites: z.array(siteDto).max(200),
  districtCounts: z.record(z.string(), z.number().int().nonnegative()),
  matchedCount: z.number().int().nonnegative(),
  offset: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
});
