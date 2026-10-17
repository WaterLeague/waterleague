import { z } from 'zod';

export const equipmentHistoryDto = z.object({
  version: z.literal('equipment-history-20261018-v1'),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  usage: z.literal('REFERENCE_HISTORY_ONLY'),
  source: z.object({
    id: z.literal('15021421'),
    title: z.string(),
    publisher: z.string(),
    url: z.literal('https://www.data.go.kr/data/15021421/fileData.do'),
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
    license: z.literal('UNRESTRICTED_USE'),
  }),
  eventId: z.string().nullable(),
  eventDate: z.iso.date().nullable(),
  records: z
    .array(
      z.object({
        record: z.object({
          id: z.string(),
          assetId: z.string(),
          sourceRow: z.number().int().positive(),
          name: z.string(),
          address: z.string(),
          installedYear: z.number().int().min(1900).max(2100),
          expandedYear: z.number().int().min(1900).max(2100).nullable(),
          referenceDate: z.iso.date(),
          motorSizeRaw: z.string(),
          motorCount: z.number().int().nonnegative(),
          engineSizeRaw: z.string(),
          engineCount: z.number().int().nonnegative(),
          sizeUnitRaw: z.literal('kW(HP)'),
          linkBasis: z.literal('REVIEWED_DISTRICT_AND_NAME_CROSSWALK'),
        }),
        temporalStatus: z.enum([
          'SOURCE_REFERENCE',
          'NOT_INSTALLED_YET',
          'INSTALLATION_DATE_UNCERTAIN',
          'LATER_EXPANSION',
          'EXPANSION_DATE_UNCERTAIN',
          'INSTALLATION_PRECEDES_EVENT',
        ]),
        sourcePrecedesEvent: z.boolean(),
        simulationIncluded: z.literal(false),
      })
    )
    .max(1000),
});

export type EquipmentHistoryCatalog = z.infer<typeof equipmentHistoryDto>;
