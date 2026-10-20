import { z } from 'zod';
import { initializationDto } from './initializationDto';
import { nativeFlowGraphDto } from './flowGraphDto';

const sha = z.string().regex(/^[a-f0-9]{64}$/);
const area = z.number().finite().positive();
export const designContractDto = z
  .object({
    sha256: sha,
    version: z.literal('NATIVE_DIRECT_SURFACE_COMPARISON_V1'),
    spatial: z.object({
      coordinateSystem: z.literal('EPSG:5186'),
      playCatalogSha256: sha,
      sitesSha256: sha,
      objectsSha256: sha,
      geometrySha256: sha,
      sourceObjectId: z.string().min(1).max(160),
      candidateId: z.string().regex(/^C[a-f0-9]{24}$/),
      districtId: z.string().regex(/^11\d{3}$/),
      evaluationSurfaceAreaM2: area,
    }),
    facility: z.object({
      type: z.enum([
        'RAIN_GARDEN',
        'PERMEABLE_PAVEMENT',
        'GREEN_ROOF',
        'BIORETENTION',
        'VEGETATIVE_SWALE',
        'INFILTRATION_TRENCH',
      ]),
      areaM2: area,
      designSet: z.object({ id: z.string(), sha256: sha }),
      referenceScenario: z.record(z.string(), z.unknown()),
    }),
    connection: z.object({
      inflowPolicy: z.literal('DIRECT_RAINFALL_ONLY'),
      directRainAreaM2: area,
      externalCatchment: z.null(),
      drainageNode: z.null(),
      network: z.null(),
      status: z.literal('UNCONNECTED_SURFACE_EXPLORATION'),
    }),
    evaluation: z.object({
      start: z.iso.datetime({ offset: true }),
      end: z.iso.datetime({ offset: true }),
      timeZone: z.literal('UTC'),
      scope: z.literal('SELECTED_SURFACE_OUTLET_NOT_SEWER_OR_RIVER'),
      runoffStepSeconds: z.literal(1),
      scoreRule: z.literal('BASELINE_MINUS_STRATEGY_RUNOFF_DRAINAGE_AND_NET_STORAGE_M3'),
      initialization: initializationDto.nullish(),
      windowMethod: z.enum(['INSTALLATION_OFFSET_AFTER_ANTECEDENT', 'FULL_EVENT_AFTER_ANTECEDENT']),
    }),
    units: z.object({
      coordinate: z.literal('m'),
      area: z.literal('m2'),
      volume: z.literal('m3'),
      flow: z.literal('m3/s'),
      rainfall: z.literal('mm'),
      cost: z.literal('KRW'),
    }),
    cost: z.object({
      status: z.enum(['RECORDED', 'NOT_RECORDED']),
      snapshotSha256: sha.nullable(),
      sourceSha256: sha,
      budgetPolicy: z.record(z.string(), z.unknown()),
      completeInstalledCostStatus: z.literal('UNCONFIRMED'),
      lifeCycleCostStatus: z.enum(['NOT_CALCULATED', 'UNAVAILABLE', 'PARTIAL', 'COMPLETE']),
      lifeCycleCost: z.object({ reportSha256: sha, planSha256: sha, policySha256: sha }).nullish(),
    }),
    engine: z.looseObject({
      engineVersion: z.literal('5.2.4'),
      binarySha256: sha,
      adapterSha256: sha,
    }),
    inputFiles: z.object({
      'model.json': sha,
      'placement.json': sha,
      'baseline.inp': sha,
      'strategy.inp': sha,
    }),
    commonInpSections: z.object({
      OPTIONS: sha,
      RAINGAGES: sha,
      EVAPORATION: sha,
      TIMESERIES: sha,
    }),
    implementationSha256: sha,
    flowGraph: nativeFlowGraphDto.optional(),
  })
  .refine(
    (v) =>
      v.facility.areaM2 <= v.spatial.evaluationSurfaceAreaM2 &&
      v.facility.areaM2 === v.connection.directRainAreaM2 &&
      Date.parse(v.evaluation.start) < Date.parse(v.evaluation.end) &&
      (v.cost.status === 'RECORDED') === (v.cost.snapshotSha256 !== null)
  )
  .refine(
    (v) => (v.cost.lifeCycleCostStatus === 'NOT_CALCULATED') === (v.cost.lifeCycleCost == null)
  )
  .refine((v) => {
    const graph = v.flowGraph;
    if (!graph) return true;
    const candidate = 'candidate:' + v.spatial.candidateId;
    const facility = 'facility:' + v.spatial.candidateId;
    const outlet = 'surface-outlet:' + v.spatial.candidateId;
    const remainder = 'remainder:' + v.spatial.candidateId;
    const budget = graph.areaBudgets[0];
    return (
      graph.nodes.length === 5 &&
      graph.sourceHashes.siteCatalog === v.spatial.playCatalogSha256 &&
      graph.sourceHashes.objectCatalog === v.spatial.objectsSha256 &&
      graph.sourceHashes.candidateGeometry === v.spatial.geometrySha256 &&
      Object.entries(v.inputFiles).every(([name, hash]) => graph.sourceHashes[name] === hash) &&
      graph.nodes.some(
        (n) =>
          n.id === candidate &&
          n.candidateId === v.spatial.candidateId &&
          n.districtId === v.spatial.districtId
      ) &&
      graph.nodes.some(
        (n) =>
          n.id === facility &&
          n.facilityType === v.facility.type &&
          Number(n.areaM2) === v.facility.areaM2
      ) &&
      graph.nodes.some(
        (n) =>
          n.id === 'object:' + v.spatial.sourceObjectId &&
          n.sourceObjectId === v.spatial.sourceObjectId
      ) &&
      graph.areaBudgets.length === 1 &&
      budget.sourceNodeId === candidate &&
      budget.completePartition &&
      budget.allocations.length === 2 &&
      budget.allocations.some(
        (a) => a.targetNodeId === facility && Number(a.areaM2) === v.facility.areaM2
      ) &&
      budget.allocations.some((a) => a.targetNodeId === remainder) &&
      Number(budget.availableM2) === v.spatial.evaluationSurfaceAreaM2 &&
      graph.evaluationPoints.length === 1 &&
      graph.evaluationPoints[0].nodeId === outlet &&
      Date.parse(graph.evaluationPoints[0].start) === Date.parse(v.evaluation.start) &&
      Date.parse(graph.evaluationPoints[0].end) === Date.parse(v.evaluation.end)
    );
  });
export type DesignContractData = z.infer<typeof designContractDto>;
