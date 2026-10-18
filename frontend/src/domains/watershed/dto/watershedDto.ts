import { cisternCostCatalogDto, cisternCostSnapshotDto } from './cisternCostDto';
import { conduitCatalogDto, conduitDesignDto } from './conduitDto';
import { storageCatalogDto, storageDesignDto, storageSummaryDto } from './storageDto';
import { z } from 'zod';
import { watershedCostCatalogDto, watershedCostSnapshotDto } from './watershedCostDto';
import { watershedLayoutDto } from './watershedLayoutDto';
import { watershedMetricsDto } from './watershedMetricsDto';
import { nodeFloodingDto, floodAmountClose } from './nodeFloodingDto';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const amount = z.number().finite();
export const networkFacilityDto = z.enum([
  'BIORETENTION',
  'INFILTRATION_TRENCH',
  'VEGETATIVE_SWALE',
  'RAINWATER_CISTERN',
]);
export type NetworkFacility = z.infer<typeof networkFacilityDto>;
export const watershedCatalogDto = z
  .object({
    catalogHash: hash,
    cisternCostCatalogHash: hash.optional(),
    cisternCostCatalog: cisternCostCatalogDto.optional(),
    conduitCatalogHash: hash.optional(),
    conduitCatalog: conduitCatalogDto.optional(),
    storageCatalogHash: hash.optional(),
    storageCatalog: storageCatalogDto.optional(),
    costCatalogHash: hash.optional(),
    costCatalog: watershedCostCatalogDto.optional(),
    layoutHash: hash.optional(),
    layout: watershedLayoutDto.optional(),
    catalog: z.object({
      id: z.string(),
      sourceOriginalSha256: hash,
      title: z.string(),
      sourceUrl: z.url().startsWith('https://'),
      attribution: z.object({ title: z.string(), authors: z.array(z.string()), year: z.number() }),
      licence: z.object({ short_name: z.string(), url: z.url().regex(/^https?:\/\//) }),
      catchments: z
        .array(
          z.object({
            id: z.string(),
            areaM2: amount.positive(),
            imperviousM2: amount.nonnegative(),
            outletNodeId: z.string(),
          })
        )
        .min(1),
      templates: z.record(
        networkFacilityDto,
        z.object({
          label: z.string(),
          parameters: z.record(z.string(), z.unknown()),
          initialSaturationPercent: amount,
        })
      ),
      numericalProfile: z.object({ id: z.string() }),
      rankingEligible: z.literal(false),
      historicalReconstructionEligible: z.literal(false),
      horizontalCrs: z.null(),
      verticalDatum: z.null(),
      completeInstalledCostKrw: z.null(),
      limitations: z.array(z.string()),
    }),
  })
  .superRefine((v, ctx) => {
    if (Boolean(v.cisternCostCatalog) !== Boolean(v.cisternCostCatalogHash))
      ctx.addIssue({ code: 'custom', message: '이용조 견적 목록·해시 누락' });
    if (
      Boolean(v.conduitCatalog) !== Boolean(v.conduitCatalogHash) ||
      (v.conduitCatalog &&
        (v.conduitCatalog.sourceCatalogSha256 !== v.catalogHash ||
          v.conduitCatalog.sourceOriginalSha256 !== v.catalog.sourceOriginalSha256))
    )
      ctx.addIssue({ code: 'custom', message: '관로 목록과 공개 원본 불일치' });
    if (
      Boolean(v.storageCatalog) !== Boolean(v.storageCatalogHash) ||
      (v.storageCatalog &&
        (v.storageCatalog.sourceCatalogSha256 !== v.catalogHash ||
          v.storageCatalog.sourceOriginalSha256 !== v.catalog.sourceOriginalSha256))
    )
      ctx.addIssue({ code: 'custom', message: '저류조 연결과 공개 관망 불일치' });
    if (
      Boolean(v.layout) !== Boolean(v.layoutHash) ||
      (v.layout &&
        (v.layout.sourceOriginalSha256 !== v.catalog.sourceOriginalSha256 ||
          v.layout.catchments.length !== v.catalog.catchments.length ||
          v.layout.catchments.some(
            (c) =>
              !v.catalog.catchments.some((p) => p.id === c.id && p.outletNodeId === c.outletNodeId)
          )))
    )
      ctx.addIssue({ code: 'custom', message: '표시 구역과 계산 구역 불일치' });
  });
export type WatershedCatalog = z.infer<typeof watershedCatalogDto>;
export interface NetworkPlacement {
  id: string;
  facilityType: NetworkFacility;
  catchmentId: string;
  areaM2: number;
  treatedImperviousM2: number;
}
const totals = z.object({
  floodingM3: amount,
  outflowM3: amount,
  storageM3: amount,
  balanceResidualM3: amount,
});
const caseDto = z.object({
  nodeFlooding: nodeFloodingDto.optional(),
  conduits: z
    .array(z.object({ id: z.string(), conduitId: z.string(), flowM3s: amount, depthM: amount }))
    .optional(),
  conduitStateTimeSeconds: amount.nonnegative().optional(),
  connectedStorage: storageSummaryDto.optional(),
  id: z.enum(['baseline', 'strategy']),
  numericalStatus: z.enum(['PASSED', 'FAILED']),
  complete: z.boolean().optional(),
  evaluationMetrics: watershedMetricsDto.optional(),
  totals: totals.optional(),
  calendarShortfallSeconds: amount.optional(),
  runoffContinuityPercent: amount.optional(),
  routingContinuityPercent: amount.optional(),
  convergence: z.object({ nonConvergedSteps: amount.nonnegative() }).optional(),
  facilities: z
    .array(
      z.object({
        swmmId: z.string(),
        subcatchmentId: z.string(),
        areaM2: amount,
        surfaceDepthMm: amount,
        soilMoisture: amount.nullable().optional(),
        finalStorageM3: amount,
        balanceResidualM3: amount,
        numericalStatus: z.enum(['PASSED', 'FAILED']),
      })
    )
    .optional(),
});
export const watershedResultDto = z
  .object({
    catalogHash: hash,
    classification: z.literal('PUBLIC_NETWORK_REFERENCE_DESIGN_COMPARISON'),
    networkLayout: z.object({ sha256: hash, layout: watershedLayoutDto }).optional(),
    engine: z.object({ engineVersion: z.string() }),
    numericalProfile: z.object({ id: z.string() }),
    numericalStatus: z.enum(['PASSED', 'FAILED']),
    cases: z.array(caseDto).length(2),
    signedReductionM3: z.object({ floodingM3: amount, outflowM3: amount }).nullable(),
    signedPeakReductionM3s: amount.nullable().optional(),
    rankingEligible: z.literal(false),
    historicalReconstructionEligible: z.literal(false),
    completeInstalledCostKrw: z.null(),
    budgetChargedKrw: z.null(),
    costing: watershedCostSnapshotDto.optional(),
    cisternCosting: cisternCostSnapshotDto.optional(),
    limitations: z.array(z.string()),
  })
  .superRefine((value, ctx) => {
    const baseline = value.cases.find((c) => c.id === 'baseline');
    const strategy = value.cases.find((c) => c.id === 'strategy');
    const layout = value.networkLayout;
    if (!layout && value.cases.some((c) => c.nodeFlooding))
      ctx.addIssue({ code: 'custom', message: '절점 월류의 원본 관망도 누락' });
    if (layout) {
      for (const c of value.cases) {
        const report = c.nodeFlooding;
        if (!report) {
          if (c.numericalStatus === 'PASSED')
            ctx.addIssue({ code: 'custom', message: '절점 월류 기록 누락' });
          continue;
        }
        if (
          report.layoutSha256 !== layout.sha256 ||
          !c.totals ||
          !floodAmountClose(report.totalFloodingM3, c.totals.floodingM3) ||
          (c.evaluationMetrics &&
            report.endSeconds !== c.evaluationMetrics.specification.endMilliseconds / 1000) ||
          report.nodes.filter((n) => n.mapped).length !== layout.layout.nodes.length ||
          report.nodes.some((n) =>
            n.mapped
              ? !layout.layout.nodes.some((p) => p.id === n.id && p.kind === n.kind)
              : n.kind !== 'STORAGE' || layout.layout.nodes.some((p) => p.id === n.id)
          )
        )
          ctx.addIssue({ code: 'custom', message: '절점 월류·관망도·평가 범위 불일치' });
      }
      if (
        baseline?.nodeFlooding &&
        strategy?.nodeFlooding &&
        baseline.nodeFlooding.endSeconds !== strategy.nodeFlooding.endSeconds
      )
        ctx.addIssue({ code: 'custom', message: '절점 월류 비교 기간 불일치' });
    }
    const valid =
      baseline &&
      strategy &&
      value.cases.every(
        (c) =>
          c.numericalStatus === 'PASSED' &&
          c.complete &&
          c.totals &&
          (!c.connectedStorage ||
            (c.connectedStorage.numericalStatus === 'PASSED' &&
              c.connectedStorage.wholeRunLedger.numericalStatus === 'PASSED' &&
              c.connectedStorage.wholeRunLedger.facilities.length > 0 &&
              c.connectedStorage.wholeRunLedger.facilities.every(
                (f) =>
                  f.numericalStatus === 'PASSED' &&
                  Math.abs(f.balanceResidualM3) <= f.allowedResidualM3 &&
                  f.floodingM3 <= 1e-9 &&
                  Math.max(f.initialStorageM3, f.finalStorageM3) <= f.capacityM3 + 1e-8
              )))
      );
    if (!baseline || !strategy || (value.numericalStatus === 'PASSED' && !valid))
      ctx.addIssue({ code: 'custom', message: '계산 상태와 원 지표 불일치' });
    if (value.numericalStatus === 'FAILED' && value.signedReductionM3 !== null)
      ctx.addIssue({ code: 'custom', message: '실패한 계산의 효과 표시 금지' });
    if (value.numericalStatus === 'FAILED' && value.signedPeakReductionM3s != null)
      ctx.addIssue({ code: 'custom', message: '실패한 계산의 첨두 비교 금지' });
    const bm = baseline?.evaluationMetrics;
    const sm = strategy?.evaluationMetrics;
    if (value.numericalStatus === 'PASSED' && (bm || sm || value.signedPeakReductionM3s != null)) {
      if (
        !bm?.complete ||
        !sm?.complete ||
        bm.specificationSha256 !== sm.specificationSha256 ||
        JSON.stringify(bm.specification) !== JSON.stringify(sm.specification) ||
        value.signedPeakReductionM3s == null ||
        Math.abs(
          value.signedPeakReductionM3s - (bm.combined.peakOutwardM3s - sm.combined.peakOutwardM3s)
        ) > 1e-10
      )
        ctx.addIssue({ code: 'custom', message: '첨두 비교의 평가 범위·변화량 불일치' });
    }
    if (value.numericalStatus === 'PASSED') {
      if (!value.signedReductionM3) ctx.addIssue({ code: 'custom', message: '효과 비교 누락' });
      else if (baseline?.totals && strategy?.totals) {
        for (const metric of ['floodingM3', 'outflowM3'] as const) {
          const expected = baseline.totals[metric] - strategy.totals[metric];
          if (
            Math.abs(value.signedReductionM3[metric] - expected) >
            Math.max(1e-8, Math.abs(expected) * 1e-10)
          )
            ctx.addIssue({ code: 'custom', message: '원 지표와 변화량 불일치' });
        }
      }
    }
  });
export type WatershedResult = z.infer<typeof watershedResultDto>;
export const watershedJobDto = z
  .object({
    id: z.uuid(),
    catalogHash: hash,
    state: z.enum(['QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'REJECTED']),
    createdAt: z.iso.datetime(),
    design: z.object({
      conduits: conduitDesignDto.optional(),
      storage: storageDesignDto.optional(),
      costing: watershedCostSnapshotDto.optional(),
      cisternCosting: cisternCostSnapshotDto.optional(),
      placements: z.array(
        z.object({
          id: z.string(),
          facilityType: networkFacilityDto,
          subcatchmentId: z.string(),
          parameters: z.record(z.string(), z.unknown()).optional(),
          areaM2: amount,
          treatedImperviousM2: amount,
        })
      ),
    }),
    result: watershedResultDto.nullable(),
    message: z.string(),
  })
  .superRefine((value, ctx) => {
    const references = value.design.cisternCosting;
    const cisterns = value.design.placements.filter((p) => p.facilityType === 'RAINWATER_CISTERN');
    if (
      (references &&
        (references.items.length !== cisterns.length ||
          references.items.some(
            (i) =>
              !cisterns.some(
                (p) =>
                  p.id === i.placementId &&
                  typeof p.parameters?.storageDepthMm === 'number' &&
                  Math.abs((p.areaM2 * p.parameters.storageDepthMm) / 1000 - i.capacityM3) < 1e-9
              )
          ))) ||
      (value.result && JSON.stringify(value.result.cisternCosting) !== JSON.stringify(references))
    )
      ctx.addIssue({ code: 'custom', message: '이용조 견적과 설계·결과 불일치' });
    const pipes = value.design.conduits?.placements ?? [];
    if (
      value.result?.numericalStatus === 'PASSED' &&
      pipes.length &&
      value.result.cases.some(
        (c) =>
          c.conduitStateTimeSeconds == null ||
          c.conduits?.length !== pipes.length ||
          pipes.some(
            (p) =>
              c.conduits?.filter((r) => p.id === r.id && p.conduitId === r.conduitId).length !== 1
          )
      )
    )
      ctx.addIssue({ code: 'custom', message: '관로 설계와 최종 계산 상태 불일치' });
    const tanks = value.design.storage?.placements ?? [];
    const ledger = value.result?.cases.find((c) => c.id === 'strategy')?.connectedStorage
      ?.wholeRunLedger.facilities;
    if (
      (value.result?.numericalStatus === 'PASSED' && tanks.length > 0 && !ledger) ||
      (ledger &&
        (ledger.length !== tanks.length ||
          ledger.some(
            (f) =>
              !tanks.some(
                (t) =>
                  t.id === f.id &&
                  Math.abs(f.capacityM3 - t.depthAreaCurve[1].depthM * t.depthAreaCurve[1].areaM2) <
                    1e-8
              )
          )))
    )
      ctx.addIssue({ code: 'custom', message: '저류조 설계와 계산 원장 불일치' });
    const cost = value.design.costing;
    if (
      cost &&
      (cost.items.length !== value.design.placements.length ||
        cost.items.some(
          (i) =>
            !value.design.placements.some(
              (p) =>
                p.id === i.placementId && p.facilityType === i.facilityType && p.areaM2 === i.areaM2
            )
        ))
    )
      ctx.addIssue({ code: 'custom', message: '설계와 참고 공사비 수량 불일치' });
    if (value.result && JSON.stringify(value.result.costing) !== JSON.stringify(cost))
      ctx.addIssue({ code: 'custom', message: '요청과 결과의 참고 공사비 불일치' });
    if (
      (value.state === 'SUCCEEDED' && !value.result) ||
      (value.result && value.catalogHash !== value.result.catalogHash)
    )
      ctx.addIssue({ code: 'custom', message: '실행과 결과 불일치' });
  });
export type WatershedJob = z.infer<typeof watershedJobDto>;
