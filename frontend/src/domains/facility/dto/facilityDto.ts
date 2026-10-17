import { z } from 'zod';
export const nativeSoilBoundaryDto = z.object({
  method: z.literal('RG_NATIVE_SOIL_SEEPAGE_V1'),
  seepageMmH: z.number().finite().positive(),
  basis: z.enum(['TEXTURE_CLASS_LITERATURE_ESTIMATE', 'UNRESOLVED_DESIGN_ASSUMPTION']),
  liner: z.literal('UNLINED_DESIGN_NOT_SITE_CONFIRMED'),
  storageThicknessMm: z.literal(0),
});
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
export const facilityCatalogDto = z.object({
  id: z.literal('EPA_LID_PUBLIC_DESIGNS_V1'),
  evidence: z.literal('PUBLIC_REFERENCE_DESIGN_NOT_SITE_MEASURED'),
  source: facilitySourceDto,
  profiles: z.record(
    z.enum(['RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF']),
    facilityProfileDto
  ),
  limitations: z.array(z.string()),
});
export type FacilityCatalog = z.infer<typeof facilityCatalogDto>;
export type FacilityEvidence = z.infer<typeof facilityEvidenceDto>;
