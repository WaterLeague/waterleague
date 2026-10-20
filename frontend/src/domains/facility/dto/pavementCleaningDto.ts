import { z } from 'zod';

const value = z.number().finite().nonnegative();
const measurements = z
  .object({
    testCount: z.number().int().positive(),
    min: value,
    max: value,
    median: value,
    mean: value,
    standardDeviation: value,
  })
  .strict()
  .refine((v) => v.min <= v.median && v.median <= v.max && v.min <= v.mean && v.mean <= v.max);
const pair = z
  .object({
    id: z.enum([
      'PINEY_WOOD_2014_NEAR',
      'PINEY_WOOD_2014_FAR',
      'WILLOUGHBY_HILLS_2014',
      'WILLOUGHBY_HILLS_2015',
    ]),
    site: z.string().min(1),
    campaign: z.string().min(1),
    location: z.string().min(1),
    method: z.enum([
      'REGENERATIVE_AIR',
      'VACUUM_TRUCK',
      'VACUUM_TRUCK_WITH_JOINT_STONE_REPLACEMENT',
    ]),
    passes: z.number().int().positive(),
    before: measurements,
    after: measurements,
    pValue: value.max(1),
    statisticalTest: z.literal('STUDENT_T_TEST'),
    newConditionValue: z.null(),
    maintenanceCostKrw: z.null(),
  })
  .strict()
  .refine((v) => v.before.testCount === v.after.testCount);

export const pavementCleaningDto = z
  .object({
    schemaVersion: z.literal(1),
    id: z.literal('WINSTON_PICP_CLEANING_OBSERVATIONS_V1'),
    classification: z.literal('PUBLISHED_FIELD_OBSERVATIONS_NOT_SEOUL_PREDICTION'),
    source: z
      .object({
        title: z.string().min(1),
        doi: z.literal('10.1016/j.jenvman.2015.12.026'),
        url: z.literal('https://repository.library.noaa.gov/view/noaa/57786'),
        pdfUrl: z.literal('https://repository.library.noaa.gov/view/noaa/57786/noaa_57786_DS1.pdf'),
        sha256: z.literal('9a9c9a4874d604b60c18f578edb28f02f00ee849f0dbcfba3ae53d1c61a9ce08'),
        documentYear: z.literal(2016),
        version: z.literal('ACCEPTED_MANUSCRIPT'),
        table: z.literal(3),
        pdfPages: z.array(z.number().int().positive()).min(1),
      })
      .strict(),
    material: z.literal('PERMEABLE_INTERLOCKING_CONCRETE_PAVEMENT'),
    measurement: z.literal('SURFACE_INFILTRATION_RATE'),
    unit: z.literal('mm/min'),
    testMethod: z.literal('ASTM_C1781_SINGLE_RING_CONSTANT_HEAD'),
    pairs: z.array(pair).length(4),
    simulationEligible: z.literal(false),
    rankingEligible: z.literal(false),
    limitations: z.array(z.string().min(1)).min(1),
  })
  .strict()
  .refine((v) => new Set(v.pairs.map((p) => p.id)).size === v.pairs.length);

export type PavementCleaning = z.infer<typeof pavementCleaningDto>;
export type CleaningPair = PavementCleaning['pairs'][number];
