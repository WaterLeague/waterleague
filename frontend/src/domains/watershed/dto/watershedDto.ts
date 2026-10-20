import { cisternDesignDto } from './cisternDto';
import { pumpCatalogDto, pumpDesignDto, pumpOperationDto } from './pumpDto';
import { cisternCostCatalogDto, cisternCostSnapshotDto } from './cisternCostDto';
import { conduitCatalogDto, conduitDesignDto } from './conduitDto';
import { storageCatalogDto, storageDesignDto, storageSummaryDto } from './storageDto';
import { z } from 'zod';
import { watershedCostCatalogDto, watershedCostSnapshotDto } from './watershedCostDto';
import { watershedLayoutDto } from './watershedLayoutDto';
import {
  watershedGeoreferenceDto,
  sameSourceGeometry,
  locationReferenceDto,
} from './watershedGeoreferenceDto';
import { watershedMetricsDto } from './watershedMetricsDto';
import { nodeFloodingDto, floodAmountClose } from './nodeFloodingDto';
import { metricComparisonDto } from '../../physics/dto/metricComparisonDto';
import { cisternLifeCycleCostsDto } from '../../cost/dto/lifeCycleCostDto';
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
    pumpCatalogHash: hash.optional(),
    pumpCatalog: pumpCatalogDto.optional(),
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
    georeferenceHash: hash.optional(),
    georeference: watershedGeoreferenceDto.optional(),
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
    const geo = v.georeference;
    if (
      Boolean(geo) !== Boolean(v.georeferenceHash) ||
      (geo &&
        (!v.layout ||
          geo.sourceLayoutSha256 !== v.layoutHash ||
          geo.sourceOriginalSha256 !== v.catalog.sourceOriginalSha256 ||
          !sameSourceGeometry(geo, v.layout!)))
    )
      ctx.addIssue({ code: 'custom', message: '관망 위치 가정과 원 계산 구역 불일치' });
    if (Boolean(v.pumpCatalog) !== Boolean(v.pumpCatalogHash))
      ctx.addIssue({ code: 'custom', message: '펌프 곡선·해시 누락' });
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
  execution: z
    .strictObject({
      schema: z.literal(1),
      scope: z.literal('PUBLIC_NETWORK_CASE_V1'),
      mode: z.enum(['COMPUTED', 'REUSED']),
      computationKey: hash,
    })
    .optional(),
  nodeFlooding: nodeFloodingDto.optional(),
  conduits: z
    .array(z.object({ id: z.string(), conduitId: z.string(), flowM3s: amount, depthM: amount }))
    .optional(),
  conduitStateTimeSeconds: amount.nonnegative().optional(),
  connectedStorage: storageSummaryDto.optional(),
  networkCistern: storageSummaryDto.optional(),
  pumpOperation: pumpOperationDto.optional(),
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
    schemaVersion: z.union([z.literal(1), z.literal(2)]).default(1),
    catalogHash: hash,
    classification: z.literal('PUBLIC_NETWORK_REFERENCE_DESIGN_COMPARISON'),
    locationReference: locationReferenceDto.optional(),
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
    cisternLifeCycleCosts: cisternLifeCycleCostsDto.optional(),
    limitations: z.array(z.string()),
    metricComparison: metricComparisonDto.optional(),
  })
  .superRefine((value, ctx) => {
    const baseline = value.cases.find((c) => c.id === 'baseline');
    const strategy = value.cases.find((c) => c.id === 'strategy');
    const assessment = value.metricComparison;
    if (value.schemaVersion === 2 && !assessment)
      ctx.addIssue({ code: 'custom', message: '현재 원 지표 비교 계약 누락' });
    const withheld = assessment?.metrics.some((m) => m.status === 'WITHHELD') ?? false;
    if (assessment) {
      if (assessment.scope !== 'PUBLISHED_NETWORK_REFERENCE_DESIGN')
        ctx.addIssue({ code: 'custom', message: '관망 평가 범위 불일치' });
      for (const m of assessment.metrics) {
        const raw =
          m.id === 'networkOutflowM3'
            ? [baseline?.totals?.outflowM3, strategy?.totals?.outflowM3]
            : m.id === 'networkFloodingM3'
              ? [baseline?.totals?.floodingM3, strategy?.totals?.floodingM3]
              : m.id === 'networkPeakM3s'
                ? [
                    baseline?.evaluationMetrics?.combined.peakOutwardM3s,
                    strategy?.evaluationMetrics?.combined.peakOutwardM3s,
                  ]
                : m.id === 'networkFloodingSeconds' &&
                    (baseline?.evaluationMetrics?.floodingDuration ||
                      strategy?.evaluationMetrics?.floodingDuration)
                  ? [
                      baseline?.evaluationMetrics?.floodingDuration?.floodingSeconds,
                      strategy?.evaluationMetrics?.floodingDuration?.floodingSeconds,
                    ]
                  : null;
        if (
          raw
            ? m.baseline !== (raw[0] ?? null) ||
              m.strategy !== (raw[1] ?? null) ||
              (m.status === 'COMPARABLE' &&
                (value.numericalStatus !== 'PASSED' || raw.some((n) => n === undefined)))
            : m.status !== 'UNAVAILABLE'
        )
          ctx.addIssue({ code: 'custom', message: '원 관망 지표와 비교 원값 불일치' });
      }
      for (const c of value.cases) {
        const duration = c.evaluationMetrics?.floodingDuration;
        const nodes = c.nodeFlooding;
        if (
          duration &&
          nodes?.durationMethod &&
          duration.startSeconds === 0 &&
          duration.endSeconds === nodes.endSeconds
        ) {
          const seconds = nodes.nodes.map((n) => n.floodingSeconds!);
          if (
            duration.floodingSeconds + 1e-6 < Math.max(...seconds) ||
            duration.floodingSeconds > seconds.reduce((s, n) => s + n, 0) + 1e-6
          )
            ctx.addIssue({ code: 'custom', message: '관망·지점별 월류 시간 범위 불일치' });
        }
      }
      const window = assessment.window,
        bm = baseline?.evaluationMetrics,
        sm = strategy?.evaluationMetrics;
      if (
        assessment.metrics.some((m) => m.status === 'COMPARABLE') &&
        (window?.kind !== 'ELAPSED_SECONDS' ||
          !bm?.complete ||
          !sm?.complete ||
          window.specificationSha256 !== bm.specificationSha256 ||
          bm.specificationSha256 !== sm.specificationSha256 ||
          window.start !== bm.specification.startMilliseconds / 1000 ||
          window.end !== bm.specification.endMilliseconds / 1000)
      )
        ctx.addIssue({ code: 'custom', message: '원 관망 평가 창과 비교 범위 불일치' });
      if (withheld && (value.signedReductionM3 !== null || value.signedPeakReductionM3s != null))
        ctx.addIssue({ code: 'custom', message: '보류한 비교의 개선량 표시 금지' });
    }
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
              : (n.kind !== 'STORAGE' &&
                  !(
                    n.kind === 'JUNCTION' &&
                    (c.pumpOperation?.pumps.some((p) => p.deliveryNodeId === n.id) ||
                      c.networkCistern?.wholeRunLedger.inletPipe?.nodeId === n.id ||
                      Object.values(c.networkCistern?.wholeRunLedger.outletPipes ?? {}).some(
                        (p) => p?.nodeId === n.id
                      ))
                  )) ||
                layout.layout.nodes.some((p) => p.id === n.id)
          )
        )
          ctx.addIssue({ code: 'custom', message: '절점 월류·관망도·평가 범위 불일치' });
      }
      if (
        baseline?.nodeFlooding &&
        strategy?.nodeFlooding &&
        (baseline.nodeFlooding.endSeconds !== strategy.nodeFlooding.endSeconds ||
          baseline.nodeFlooding.durationMethod !== strategy.nodeFlooding.durationMethod)
      )
        ctx.addIssue({ code: 'custom', message: '절점 월류 비교 기간·시간 산정 방식 불일치' });
    }
    const valid =
      baseline &&
      strategy &&
      value.cases.every(
        (c) =>
          c.numericalStatus === 'PASSED' &&
          c.complete &&
          c.totals &&
          (!c.pumpOperation ||
            (c.pumpOperation.curveStatus === 'PASSED' &&
              c.pumpOperation.deliveryStatus === 'PASSED')) &&
          [c.connectedStorage, c.networkCistern].every(
            (s) =>
              !s ||
              (s.numericalStatus === 'PASSED' &&
                s.wholeRunLedger.numericalStatus === 'PASSED' &&
                s.wholeRunLedger.facilities.length > 0 &&
                s.wholeRunLedger.facilities.every(
                  (f) =>
                    f.numericalStatus === 'PASSED' &&
                    Math.abs(f.balanceResidualM3) <= f.allowedResidualM3 &&
                    f.floodingM3 <= 1e-9 &&
                    Math.max(f.initialStorageM3, f.finalStorageM3) <= f.capacityM3 + 1e-8
                ))
          )
      );
    if (!baseline || !strategy || (value.numericalStatus === 'PASSED' && !valid))
      ctx.addIssue({ code: 'custom', message: '계산 상태와 원 지표 불일치' });
    if (value.numericalStatus === 'FAILED' && value.signedReductionM3 !== null)
      ctx.addIssue({ code: 'custom', message: '실패한 계산의 효과 표시 금지' });
    if (value.numericalStatus === 'FAILED' && value.signedPeakReductionM3s != null)
      ctx.addIssue({ code: 'custom', message: '실패한 계산의 첨두 비교 금지' });
    const bm = baseline?.evaluationMetrics;
    const sm = strategy?.evaluationMetrics;
    if (
      value.numericalStatus === 'PASSED' &&
      !withheld &&
      (bm || sm || value.signedPeakReductionM3s != null)
    ) {
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
    if (value.numericalStatus === 'PASSED' && !withheld) {
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
      locationReference: locationReferenceDto.optional(),
      cistern: cisternDesignDto.optional(),
      conduits: conduitDesignDto.optional(),
      pumps: pumpDesignDto.optional(),
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
    if (
      value.result &&
      JSON.stringify(value.design.locationReference) !==
        JSON.stringify(value.result.locationReference)
    )
      ctx.addIssue({ code: 'custom', message: '설계와 결과의 위치 가정 불일치' });
    if (
      value.result?.schemaVersion === 2 &&
      value.design.placements.some((p) => p.facilityType === 'RAINWATER_CISTERN') &&
      value.result.metricComparison?.metrics.some(
        (m) =>
          m.id.startsWith('network') &&
          (m.id !== 'networkFloodingSeconds' ||
            value.result?.cases.some((c) => c.evaluationMetrics?.floodingDuration)) &&
          (m.status !== 'WITHHELD' ||
            (m.reason !== 'UNMODELED_COVER_RAIN' && m.reason !== 'NUMERICAL_FAILURE'))
      )
    )
      ctx.addIssue({ code: 'custom', message: '구형 덮개 이용조의 비교 보류 사유 누락' });
    const cisterns = value.design.placements
      .filter((p) => p.facilityType === 'RAINWATER_CISTERN')
      .map((p) => ({
        id: p.id,
        capacityM3:
          typeof p.parameters?.storageDepthMm === 'number'
            ? (p.areaM2 * p.parameters.storageDepthMm) / 1000
            : NaN,
      }));
    const tank = value.design.cistern;
    if (tank)
      cisterns.push({ id: tank.id, capacityM3: tank.footprintM2 * tank.depthAreaCurve[1].depthM });
    if (value.result) {
      for (const c of value.result.cases) {
        const ledger = c.networkCistern?.wholeRunLedger.facilities;
        const inlet = c.networkCistern?.wholeRunLedger.inletPipe;
        for (const [kind, suffix] of [
          ['drain', 'D'],
          ['overflow', 'O'],
        ] as const) {
          const pipe = c.networkCistern?.wholeRunLedger.outletPipes?.[kind];
          const design = tank?.[kind === 'drain' ? 'drainPipe' : 'overflowPipe'];
          if (
            c.networkCistern &&
            (Boolean(pipe) !== Boolean(design) ||
              (pipe &&
                (pipe.nodeId !== 'WLCT_' + tank?.id + '_' + suffix + 'J' ||
                  pipe.linkId !== 'WLCT_' + tank?.id + '_' + suffix + 'C' ||
                  !value.result.networkLayout?.layout.catchments.some(
                    (c) => c.id === tank?.subcatchmentId && c.outletNodeId === pipe.receiverNodeId
                  ) ||
                  (c.nodeFlooding &&
                    !c.nodeFlooding.nodes.some(
                      (n) =>
                        n.id === pipe.nodeId &&
                        n.kind === 'JUNCTION' &&
                        !n.mapped &&
                        floodAmountClose(n.floodingM3, pipe.floodingM3)
                    )))))
          )
            ctx.addIssue({ code: 'custom', message: '배수 연결관 설계와 접속부 월류 원장 불일치' });
        }
        if (
          c.networkCistern &&
          (Boolean(inlet) !== Boolean(tank?.inletPipe) ||
            (inlet &&
              (inlet.nodeId !== 'WLCT_' + tank?.id + '_U' ||
                inlet.linkId !== 'WLCT_' + tank?.id + '_I' ||
                (c.nodeFlooding &&
                  !c.nodeFlooding.nodes.some(
                    (n) =>
                      n.id === inlet.nodeId &&
                      n.kind === 'JUNCTION' &&
                      !n.mapped &&
                      floodAmountClose(n.floodingM3, inlet.floodingM3)
                  )))))
        )
          ctx.addIssue({ code: 'custom', message: '집수 연결관 설계와 입구 월류 원장 불일치' });
        if (
          (ledger &&
            (c.id !== 'strategy' ||
              !tank ||
              ledger.length !== 1 ||
              ledger[0].id !== tank.id ||
              ledger[0].nodeId !== 'WLCT_' + tank.id ||
              Math.abs(ledger[0].capacityM3 - tank.footprintM2 * tank.depthAreaCurve[1].depthM) >
                1e-8)) ||
          (c.id === 'strategy' && c.numericalStatus === 'PASSED' && tank && !ledger)
        )
          ctx.addIssue({ code: 'custom', message: '이용조 설계와 수리 계산 원장 불일치' });
        if (
          ledger &&
          tank &&
          ledger.some(
            (r) =>
              (r.drainOperation ?? 'GRAVITY_ORIFICE') !==
              ('mode' in tank.drain ? 'CLOSED_NO_WITHDRAWAL' : 'GRAVITY_ORIFICE')
          )
        )
          ctx.addIssue({ code: 'custom', message: '이용조 배출 조건과 계산 원장 불일치' });
        if (
          c.id === 'strategy' &&
          c.numericalStatus === 'PASSED' &&
          tank?.schemaVersion === 3 &&
          (!ledger ||
            ledger.some(
              (r) =>
                r.nativeCapacityM3 === undefined ||
                r.initialAvailableM3 === undefined ||
                r.finalAvailableM3 === undefined ||
                r.reuseStatus !== 'NOT_CALCULATED_NO_USE_DEMAND' ||
                r.reuseM3 !== null
            ))
        )
          ctx.addIssue({
            code: 'custom',
            message: '공동 집수 이용조의 현재 용량·재이용 상태 누락',
          });
      }
    }
    if (
      (references &&
        (references.items.length !== cisterns.length ||
          references.items.some(
            (i) =>
              !cisterns.some(
                (p) => p.id === i.placementId && Math.abs(p.capacityM3 - i.capacityM3) < 1e-9
              )
          ))) ||
      (value.result && JSON.stringify(value.result.cisternCosting) !== JSON.stringify(references))
    )
      ctx.addIssue({ code: 'custom', message: '이용조 견적과 설계·결과 불일치' });
    const pumps = value.design.pumps?.placements ?? [];
    const finance = value.result?.cisternLifeCycleCosts;
    if (
      finance &&
      (!references ||
        finance.catalogHash !== references.catalogHash ||
        finance.items.length !== references.items.length ||
        finance.items.some((i) => {
          const item = references.items.find((r) => r.placementId === i.placementId);
          return (
            !item ||
            i.quotes.length !== item.quotes.length ||
            i.quotes.some((q) => {
              const quote = item.quotes.find((r) => r.id === q.id);
              const initial = q.report.categories.find((c) => c.id === 'INITIAL');
              return (
                !quote ||
                q.report.status !== 'PARTIAL' ||
                q.report.currency !== 'KRW' ||
                initial?.presentValue !== quote.quotedSubtotalKrw.toFixed(2) ||
                q.report.functionalUnit !==
                  `${item.equivalentUnits} x 2.35 m3 CAPACITY_EQUIVALENT_ONLY`
              );
            })
          );
        }))
    )
      ctx.addIssue({ code: 'custom', message: '이용조 견적과 생애비용 계산 입력 불일치' });
    if (value.result)
      for (const c of value.result.cases) {
        const expected = c.id === 'strategy' ? pumps : [];
        const rows = c.pumpOperation?.pumps ?? [];
        if (
          (rows.length !== expected.length && c.numericalStatus === 'PASSED') ||
          rows.some((r) => !expected.some((p) => r.linkId === 'WLPU_' + p.id)) ||
          rows.some(
            (r) =>
              c.nodeFlooding &&
              (r.observedSeconds !== c.nodeFlooding.endSeconds ||
                !c.nodeFlooding.nodes.some(
                  (n) =>
                    n.id === r.deliveryNodeId &&
                    !n.mapped &&
                    n.kind === 'JUNCTION' &&
                    floodAmountClose(n.floodingM3, r.deliveryFloodingM3)
                ))
          )
        )
          ctx.addIssue({ code: 'custom', message: '펌프 설계·운전·토출 월류 기록 불일치' });
      }
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
