import { z } from 'zod';
const positive = z.number().finite().positive();
export const disasterCatalogDto = z.object({
  events: z
    .array(
      z.object({
        id: z.string().regex(/^seoul-[0-9]{8}$/),
        title: z.string(),
        eventDate: z.iso.date(),
        summary: z.string(),
        evidenceTitle: z.string(),
        evidenceUrl: z.url({ protocol: /^https$/ }),
        regions: z
          .array(
            z.object({
              districtId: z.string().regex(/^[0-9]{7}$/),
              modelHash: z.string().regex(/^[a-f0-9]{64}$/),
              stationName: z.string(),
              stationId: z.string(),
              distanceKm: z.number().finite().min(0).max(10),
              start: z.iso.datetime({ offset: true }),
              end: z.iso.datetime({ offset: true }),
              totalDepthMm: positive,
              depthsMm: z.array(z.number().finite().nonnegative()).min(1).max(1440),
            })
          )
          .min(1)
          .max(25),
      })
    )
    .min(1)
    .max(20),
});
