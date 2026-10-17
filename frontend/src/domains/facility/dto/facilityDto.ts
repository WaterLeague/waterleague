import { z } from 'zod';
const parameter = z.object({
  value: z.number().finite(),
  unit: z.string(),
  reference: z.string(),
  basis: z.string(),
  range: z.tuple([z.number().finite(), z.number().finite()]).optional(),
});
export const facilityCatalogDto = z.object({
  id: z.literal('EPA_LID_PUBLIC_DESIGNS_V1'),
  evidence: z.literal('PUBLIC_REFERENCE_DESIGN_NOT_SITE_MEASURED'),
  source: z.object({
    title: z.string(),
    url: z.url().startsWith('https://'),
    sha256: z.string(),
    year: z.number(),
    pages: z.array(z.number()),
  }),
  profiles: z.record(
    z.enum(['RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF']),
    z.object({
      id: z.string(),
      name: z.string(),
      summary: z.string(),
      type: z.string(),
      parameters: z.record(z.string(), parameter),
    })
  ),
  limitations: z.array(z.string()),
});
export type FacilityCatalog = z.infer<typeof facilityCatalogDto>;
