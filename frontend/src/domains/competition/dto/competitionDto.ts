import { z } from 'zod';
export const facilityTypeDto = z.enum([
  'RAIN_GARDEN',
  'PERMEABLE_PAVEMENT',
  'GREEN_ROOF',
  'BIORETENTION',
  'VEGETATIVE_SWALE',
  'INFILTRATION_TRENCH',
  'RAINWATER_CISTERN',
]);
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const awardDto = z.object({
  title: z.string(),
  rankFrom: z.number().int(),
  rankTo: z.number().int(),
  prizeKrw: z.number().nonnegative(),
});
export const competitionDto = z.object({
  id: z.uuid(),
  title: z.string(),
  description: z.string(),
  organizationName: z.string(),
  mode: z.enum(['REALTIME', 'DISASTER']),
  eventId: z.string().nullable(),
  opensAt: z.iso.datetime(),
  closesAt: z.iso.datetime(),
  phase: z.enum(['UPCOMING', 'OPEN', 'ENDED', 'CANCELLED']),
  rulesHash: hash,
  canManage: z.boolean(),
  joinedAt: z.iso.datetime().nullable(),
  participantCount: z.number().int(),
  rules: z.object({
    districtIds: z.array(z.string()),
    allowedTypes: z.array(facilityTypeDto),
    awards: z.array(awardDto),
    awardNotice: z.string(),
    scorePolicySha256: hash,
  }),
});
export const catalogDto = z.object({
  districts: z.array(z.object({ id: z.string(), name: z.string() })),
  events: z.array(z.object({ id: z.string(), title: z.string() })),
  facilityTypes: z.array(facilityTypeDto),
  serverNow: z.iso.datetime(),
});
export const installationDto = z.object({
  id: z.uuid(),
  playerId: z.uuid(),
  districtId: z.string(),
  facilityType: facilityTypeDto,
  areaM2: z.number(),
  installedAt: z.iso.datetime(),
});
export const resultDto = z.object({
  competition: competitionDto,
  status: z.enum([
    'UPCOMING',
    'IN_PROGRESS',
    'PROVISIONAL',
    'WITHHELD',
    'EMPTY',
    'FINAL',
    'CANCELLED',
  ]),
  page: z.number().int(),
  hasMore: z.boolean(),
  missingSeconds: z.number(),
  pendingCalculations: z.boolean(),
  generatedAt: z.iso.datetime(),
  groups: z.array(
    z.object({
      comparisonGroup: z.string(),
      count: z.number(),
      entries: z.array(
        z.object({
          playerId: z.uuid(),
          nickname: z.string(),
          rank: z.number().int().nullable(),
          scoreM3: z.number().nullable(),
          scoreM3Exact: z.string().nullable(),
          comparable: z.boolean(),
          submittedAt: z.iso.datetime().optional(),
          installations: z.array(installationDto).optional(),
          evaluatedSeconds: z.number().optional(),
          expectedSeconds: z.number().optional(),
        })
      ),
    })
  ),
});
export const candidatesDto = z.array(
  z.object({ id: z.uuid(), state: z.string(), createdAt: z.iso.datetime(), entered: z.boolean() })
);
export const listDto = z.object({
  items: z.array(competitionDto),
  page: z.number().int(),
  hasMore: z.boolean(),
});
export type Competition = z.infer<typeof competitionDto>;
export type CompetitionCatalog = z.infer<typeof catalogDto>;
export type CompetitionResults = z.infer<typeof resultDto>;
export type CompetitionCandidates = z.infer<typeof candidatesDto>;
export type Award = z.infer<typeof awardDto>;
export type CompetitionCreate = {
  requestKey: string;
  title: string;
  description: string;
  mode: Competition['mode'];
  eventId: string | null;
  districtIds: string[];
  allowedTypes: z.infer<typeof facilityTypeDto>[];
  opensAt: string;
  closesAt: string;
  awards: Award[];
  awardNotice: string;
};
