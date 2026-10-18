import { z } from 'zod';
const rainGardenBoundaryDto = z.object({
  method: z.literal('RG_NATIVE_SOIL_SEEPAGE_V1'),
  seepageMmH: z.number().finite().positive(),
  basis: z.enum(['TEXTURE_CLASS_LITERATURE_ESTIMATE', 'UNRESOLVED_DESIGN_ASSUMPTION']),
  liner: z.literal('UNLINED_DESIGN_NOT_SITE_CONFIRMED'),
  storageThicknessMm: z.literal(0),
});
export const nativeSoilBoundaryDto = z.union([
  rainGardenBoundaryDto,
  z.object({
    method: z.literal('BC_NATIVE_SOIL_SEEPAGE_V1'),
    seepageMmH: z.number().finite().positive(),
    basis: z.literal('TEXTURE_CLASS_LITERATURE_ESTIMATE'),
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
});
export const facilityCatalogDto = z
  .object({
    id: z.enum(['EPA_LID_PUBLIC_DESIGNS_V1', 'EPA_LID_PUBLIC_DESIGNS_V2']),
    evidence: z.literal('PUBLIC_REFERENCE_DESIGN_NOT_SITE_MEASURED'),
    source: facilitySourceDto,
    profiles: z.object({
      RAIN_GARDEN: facilityProfileDto,
      PERMEABLE_PAVEMENT: facilityProfileDto,
      GREEN_ROOF: facilityProfileDto,
      BIORETENTION: facilityProfileDto.optional(),
    }),
    limitations: z.array(z.string()),
  })
  .refine(
    (value) =>
      value.id !== 'EPA_LID_PUBLIC_DESIGNS_V2' || value.profiles.BIORETENTION !== undefined,
    { message: '생물저류 설계 제원 누락' }
  );
export type FacilityCatalog = z.infer<typeof facilityCatalogDto>;
export type FacilityEvidence = z.infer<typeof facilityEvidenceDto>;
