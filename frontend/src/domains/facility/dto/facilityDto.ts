import { z } from 'zod';
export const swaleDesignDto = z.object({
  method: z.enum(['CONTAINED_FIXED_WIDTH_STRAIGHT_DESIGN_V1', 'CONTAINED_COMPONENT_RECTANGLE_V2']),
  topWidthM: z.literal(2),
  maxLengthM: z.number().positive(),
  maxAreaM2: z.number().positive(),
  center: z.tuple([z.number().finite(), z.number().finite()]),
  direction: z.tuple([z.number().finite(), z.number().finite()]),
  coordinates: z.array(z.tuple([z.number().finite(), z.number().finite()])).length(5),
  slopeBasis: z.enum([
    'REGIONAL_TERRAIN_PROXY_NOT_LONGITUDINAL_SURVEY',
    'PUBLIC_DESIGN_SLOPE_NOT_SURVEY',
  ]),
  outlet: z.literal('SURFACE_RUNOFF_UNCONNECTED_TO_NETWORK'),
});
export const trenchDesignDto = swaleDesignDto.extend({
  topWidthM: z.literal(1),
  slopeBasis: z.literal('LEVEL_STORAGE_DESIGN_NOT_SURVEY'),
});
export type TrenchDesign = z.infer<typeof trenchDesignDto>;
export type SwaleDesign = z.infer<typeof swaleDesignDto>;
const rainGardenBoundaryDto = z.object({
  method: z.literal('RG_NATIVE_SOIL_SEEPAGE_V1'),
  seepageMmH: z.number().finite().positive(),
  basis: z.enum([
    'TEXTURE_CLASS_LITERATURE_ESTIMATE',
    'UNRESOLVED_DESIGN_ASSUMPTION',
    'PUBLIC_REFERENCE_SCENARIO_NOT_LOCAL_MEASUREMENT',
  ]),
  liner: z.literal('UNLINED_DESIGN_NOT_SITE_CONFIRMED'),
  storageThicknessMm: z.literal(0),
});
export const nativeSoilBoundaryDto = z.union([
  rainGardenBoundaryDto,
  z.object({
    method: z.literal('IT_NATIVE_SOIL_SEEPAGE_V1'),
    seepageMmH: z.number().finite().positive(),
    basis: z.enum([
      'TEXTURE_CLASS_LITERATURE_ESTIMATE',
      'PUBLIC_REFERENCE_SCENARIO_NOT_LOCAL_MEASUREMENT',
    ]),
    liner: z.literal('UNLINED_DESIGN_NOT_SITE_CONFIRMED'),
    storageThicknessMm: z.literal(914.4),
    underdrain: z.literal('NONE_DIRECT_RAIN_INFILTRATION_DESIGN'),
  }),
  z.object({
    method: z.literal('BC_NATIVE_SOIL_SEEPAGE_V1'),
    seepageMmH: z.number().finite().positive(),
    basis: z.enum([
      'TEXTURE_CLASS_LITERATURE_ESTIMATE',
      'PUBLIC_REFERENCE_SCENARIO_NOT_LOCAL_MEASUREMENT',
    ]),
    liner: z.literal('UNLINED_DESIGN_NOT_SITE_CONFIRMED'),
    storageThicknessMm: z.literal(304.8),
    underdrain: z.literal('NONE_DIRECT_RAIN_INFILTRATION_DESIGN'),
  }),
]);
const parameter = z.object({
  value: z.number().finite(),
  unit: z.string(),
  reference: z.string(),
  basis: z.string(),
  range: z.tuple([z.number().finite(), z.number().finite()]).optional(),
});
export const facilitySourceDto = z.object({
  title: z.string(),
  url: z.url().startsWith('https://'),
  sha256: z.string(),
  year: z.number(),
  pages: z.array(z.number()),
});
export const facilityProfileDto = z.object({
  id: z.string(),
  name: z.string(),
  summary: z.string(),
  type: z.string(),
  parameters: z.record(z.string(), parameter),
});
export const facilityEvidenceDto = z.object({
  catalogSha256: z.string().regex(/^[a-f0-9]{64}$/),
  evidence: z.literal('PUBLIC_REFERENCE_DESIGN_NOT_SITE_MEASURED'),
  source: facilitySourceDto,
  profile: facilityProfileDto,
  limitations: z.array(z.string()),
  nativeSoilBoundary: nativeSoilBoundaryDto.optional(),
  swaleDesign: swaleDesignDto.optional(),
  trenchDesign: trenchDesignDto.optional(),
});
export const facilityCatalogDto = z
  .object({
    id: z.enum([
      'EPA_LID_PUBLIC_DESIGNS_V1',
      'EPA_LID_PUBLIC_DESIGNS_V2',
      'EPA_LID_PUBLIC_DESIGNS_V3',
      'EPA_LID_PUBLIC_DESIGNS_V4',
    ]),
    evidence: z.literal('PUBLIC_REFERENCE_DESIGN_NOT_SITE_MEASURED'),
    source: facilitySourceDto,
    profiles: z.object({
      RAIN_GARDEN: facilityProfileDto,
      PERMEABLE_PAVEMENT: facilityProfileDto,
      GREEN_ROOF: facilityProfileDto,
      BIORETENTION: facilityProfileDto.optional(),
      VEGETATIVE_SWALE: facilityProfileDto.optional(),
      INFILTRATION_TRENCH: facilityProfileDto.optional(),
    }),
    limitations: z.array(z.string()),
  })
  .refine(
    (value) =>
      (value.id === 'EPA_LID_PUBLIC_DESIGNS_V1' || value.profiles.BIORETENTION !== undefined) &&
      (!['EPA_LID_PUBLIC_DESIGNS_V3', 'EPA_LID_PUBLIC_DESIGNS_V4'].includes(value.id) ||
        value.profiles.VEGETATIVE_SWALE !== undefined) &&
      (value.id !== 'EPA_LID_PUBLIC_DESIGNS_V4' ||
        value.profiles.INFILTRATION_TRENCH !== undefined),
    { message: '생물저류 설계 제원 누락' }
  );
export type FacilityCatalog = z.infer<typeof facilityCatalogDto>;
export type FacilityEvidence = z.infer<typeof facilityEvidenceDto>;
