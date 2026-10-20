import { z } from 'zod';
import { initializationDto } from './initializationDto';
import { facilityEvidenceDto } from '../../facility/dto/facilityDto';
import { runoffComparisonDto } from './runoffComparisonDto';
import { designContractDto } from './designContractDto';
const value = z.number().finite();
export const physicsDto = z
  .object({
    installationId: z.uuid(),
    status: z.enum(['WAITING', 'RUNNING', 'UNAVAILABLE', 'DELAYED', 'READY']),
    message: z.string(),
    attemptedAt: z.iso.datetime().nullable(),
    simulatedThrough: z.iso.datetime().nullable(),
    result: z
      .object({
        stationId: z.string(),
        stationName: z.string(),
        simulationStart: z.iso.datetime(),
        simulatedThrough: z.iso.datetime(),
        engineVersion: z.literal('5.2.4'),
        validationLevel: z.literal('EXPLORATORY'),
        precipitationM3: value,
        infiltrationM3: value,
        evaporationM3: value,
        runoffM3: value,
        storageM3: value,
        surfaceDepthMm: value,
        soilMoisture: value.nullable(),
        storageDepthMm: value.nullable(),
        runoffContinuityPercent: value,
        evaporationMethod: z.string(),
        initialState: z.string(),
        initialization: initializationDto.nullish(),
        facilityDesign: facilityEvidenceDto.nullish(),
        runoffComparison: runoffComparisonDto.nullish(),
        designContract: designContractDto.nullish(),
        inflowPolicy: z.enum(['DIRECT_RAINFALL_ONLY', 'LEGACY_ALL_IMPERVIOUS_RUNOFF']).nullish(),
        areaLimitBasis: z.string().nullish(),
      })
      .nullable(),
  })
  .refine(
    (v) => v.result?.runoffComparison?.schemaVersion !== 2 || v.result.designContract != null,
    { message: '현재 주간 결과의 공통 설계 근거 누락' }
  );
