import { z } from 'zod';
import { cisternGameDto } from '../../facility/dto/cisternGameDto';
import { initializationDto } from './initializationDto';
import { facilityEvidenceDto } from '../../facility/dto/facilityDto';
import { runoffComparisonDto } from './runoffComparisonDto';
import { designContractDto } from './designContractDto';
import { scoreContextDto } from '../../evaluation/dto/scorePolicyDto';
import { lifeCycleCostDto } from '../../cost/dto/lifeCycleCostDto';
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
        cistern: cisternGameDto.nullish(),
        runoffComparison: runoffComparisonDto.nullish(),
        designContract: designContractDto.nullish(),
        scoreContext: scoreContextDto.refine((v) => v.mode === 'WEEKLY').nullish(),
        lifeCycleCost: lifeCycleCostDto.nullish(),
        inflowPolicy: z
          .enum([
            'DIRECT_RAINFALL_ONLY',
            'LEGACY_ALL_IMPERVIOUS_RUNOFF',
            'SELECTED_ROOF_RUNOFF_TO_COVERED_CISTERN',
          ])
          .nullish(),
        areaLimitBasis: z.string().nullish(),
      })
      .nullable(),
  })
  .refine(
    (v) => {
      const demand = v.result?.cistern?.demandScenario;
      return (
        !demand ||
        (Date.parse(demand.evaluationStart) === Date.parse(v.result!.simulationStart) &&
          Date.parse(demand.evaluationEnd) === Date.parse(v.result!.simulatedThrough))
      );
    },
    { message: '주간 평가와 이용조 수요 비교 기간 불일치' }
  )
  .refine(
    (v) => (v.result?.runoffComparison?.schemaVersion ?? 1) < 2 || v.result?.designContract != null,
    { message: '현재 주간 결과의 공통 설계 근거 누락' }
  )
  .refine(
    (v) => {
      const report = v.result?.lifeCycleCost,
        cost = v.result?.designContract?.cost;
      return (
        !report ||
        (!!cost &&
          cost.lifeCycleCostStatus === report.status &&
          cost.lifeCycleCost?.planSha256 === report.planSha256 &&
          cost.lifeCycleCost?.policySha256 === report.policySha256)
      );
    },
    { message: '주간 설계 근거와 생애비용 기록 불일치' }
  );
