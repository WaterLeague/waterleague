import { z } from 'zod';
import { initializationDto } from '../../physics/dto/initializationDto';
import { facilityEvidenceDto } from '../../facility/dto/facilityDto';
import { budgetRecordEvidenceDto } from '../../budget/dto/budgetDto';
const num = z.number().finite();
const time = z.string().datetime({ offset: true });
const facility = z.enum([
  'RAIN_GARDEN',
  'PERMEABLE_PAVEMENT',
  'GREEN_ROOF',
  'BIORETENTION',
  'VEGETATIVE_SWALE',
  'INFILTRATION_TRENCH',
]);
export const sharedConsentsDto = z.array(
  z.object({ organizationId: z.uuid(), name: z.string(), granted: z.boolean() })
);
export const sharedRecordsDto = z.object({
  weekStart: z.iso.date(),
  scope: z.enum(['OWNER', 'CONSENTED_ORGANIZATION']),
  entries: z.array(
    z.object({
      jobId: z.uuid(),
      installationId: z.uuid(),
      districtId: z.string(),
      playerName: z.string(),
      facilityType: facility,
      areaM2: num,
      costKrw: num,
      installedAt: time,
      removedAt: time.nullable(),
      scoreM3: num,
      playerScoreM3: num,
      evaluatedMinutes: z.number().int(),
      evaluatedThrough: time,
      bundleAvailable: z.boolean(),
    })
  ),
});
const sample = z.object({
  at: time,
  precipitationM3: num,
  infiltrationM3: num,
  evaporationM3: num,
  surfaceRunoffM3: num,
  lidDrainageM3: num,
  storageM3: num,
  initialStorageM3: num,
  accountedDischargeM3: num,
  runoffM3s: num,
  surfaceDepthMm: num.nullable(),
  soilMoisture: num.nullable(),
  storageDepthMm: num.nullable(),
  balanceResidualM3: num,
});
export const sharedDetailDto = z
  .object({
    jobId: z.uuid(),
    installation: z.object({
      id: z.uuid(),
      districtId: z.string(),
      cellId: z.string(),
      playerName: z.string(),
      facilityType: facility,
      areaM2: num,
      costKrw: num,
      installedAt: time,
      removedAt: time.nullable(),
    }),
    request: z.object({
      modelSha256: z.string(),
      forcingSha256: z.string(),
      weeklyRuleVersion: z.string(),
      engine: z.record(z.string(), z.unknown()),
    }),
    model: z.object({
      cells: z.array(z.record(z.string(), z.unknown())),
      hydrology: z.record(z.string(), z.unknown()),
      physicsEvidence: z.unknown(),
      assumptions: z.array(z.string()),
      unitCosts: z.record(z.string(), num),
      costModel: z.unknown(),
      budget: num,
      budgetPolicy: z.unknown(),
      sharedSiteSource: z.unknown(),
    }),
    summary: z.object({
      stationName: z.string(),
      simulationStart: time,
      simulatedThrough: time,
      runoffContinuityPercent: num,
      validationLevel: z.literal('EXPLORATORY'),
    }),
    baselineFinal: sample,
    initialization: initializationDto.nullish(),
    facilityDesign: facilityEvidenceDto.nullish(),
    strategyFinal: sample,
    evaporation: z.object({
      method: z.string(),
      assumptions: z.array(z.string()),
      sourceHashes: z.array(z.string()),
    }),
    sourceArchive: z
      .object({ complete: z.boolean(), missingHashes: z.array(z.string()) })
      .nullish(),
    frames: z.array(
      z.object({
        baseline: sample,
        strategy: sample,
        contribution: z.object({ at: time, incrementM3: num, cumulativeM3: num }),
      })
    ),
    sampleCount: z.number().int(),
    frameStride: z.number().int(),
    manifestSha256: z.string(),
    budgetLedger: budgetRecordEvidenceDto.nullish(),
  })
  .refine(
    (value) =>
      !value.budgetLedger ||
      (value.budgetLedger.calculationId === value.jobId &&
        value.budgetLedger.installationId === value.installation.id),
    { message: '선택한 계산과 예산 원장 연결 불일치' }
  );
export type SharedRecords = z.infer<typeof sharedRecordsDto>;
export type SharedDetail = z.infer<typeof sharedDetailDto>;
export type SharedConsent = z.infer<typeof sharedConsentsDto>[number];
