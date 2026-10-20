import { z } from 'zod';
const hash = z.string().regex(/^[a-f0-9]{64}$/),
  time = z.iso.datetime({ offset: true });
export const leagueDto = z.object({
  id: z.uuid(),
  organizationId: z.uuid(),
  organizationName: z.string().max(100),
  revision: z.number().int().positive(),
  state: z.enum(['DRAFT', 'PUBLISHED', 'CANCELLED']),
  phase: z.enum(['DRAFT', 'SCHEDULED', 'OPEN', 'CLOSED', 'CANCELLED']),
  title: z.string().max(100),
  question: z.string().max(2000),
  rulesHash: hash,
  executionHash: hash.nullable(),
  publishedAt: time.nullable(),
  cancellationReason: z.string().max(500).nullable(),
  playable: z.boolean(),
  rules: z.object({
    schemaVersion: z.union([z.literal(1), z.literal(2), z.literal(3)]),
    modelHash: hash,
    engineRevision: z.string().regex(/^[a-f0-9]{40}$/),
    generatorSha256: hash,
    scoreRule: z.literal('ACCOUNTED_DISCHARGE_REDUCTION_V1'),
    currency: z.literal('KRW'),
    budget: z.number().int().positive().max(300000000),
    allowedTypes: z
      .array(
        z.enum([
          'RAIN_GARDEN',
          'PERMEABLE_PAVEMENT',
          'GREEN_ROOF',
          'BIORETENTION',
          'VEGETATIVE_SWALE',
          'INFILTRATION_TRENCH',
          'RAINWATER_CISTERN',
        ])
      )
      .min(1)
      .max(3),
    submissionLimit: z.number().int().min(1).max(100),
    opensAt: time,
    closesAt: time,
    validationLevel: z.literal('EXPLORATORY'),
    official: z.literal(false),
    participation: z
      .object({
        access: z.enum(['PUBLIC', 'INVITE']),
        admission: z.enum(['OPEN', 'APPROVAL']),
        entryMode: z.enum(['INDIVIDUAL', 'TEAM']),
        teamSizeLimit: z.number().int().min(2).max(10).nullable(),
      })
      .nullable()
      .optional(),
    placementLimit: z.number().int().min(1).max(1000).nullable().optional(),
    areaLimitM2: z.number().positive().max(1000000).multipleOf(0.01).nullable().optional(),
    award: z
      .object({
        prizeKrw: z.number().int().min(0).max(1000000000),
        winnerCount: z.number().int().min(0).max(1000),
        notice: z.string().max(2000),
      })
      .nullable()
      .optional(),
  }),
});
