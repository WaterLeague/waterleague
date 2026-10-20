import { z } from 'zod';

const sha = z.string().regex(/^[a-f0-9]{64}$/);
const id = z.string().min(1).max(256);
const areaPattern = /^(0|[1-9]\d{0,12})(\.\d{1,18})?$/;
const area = z.string().regex(areaPattern);
const scaled = (value: string) => {
  if (!areaPattern.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole + fraction.padEnd(18, '0'));
};

export const nativeFlowGraphDto = z
  .object({
    sha256: sha,
    version: z.literal('PUBLIC_SOURCE_FLOW_GRAPH_V1'),
    mode: z.literal('NATIVE_DIRECT_SURFACE'),
    implementationSha256: sha,
    sourceHashes: z
      .record(id, sha)
      .refine((v) => Object.keys(v).length > 0 && Object.keys(v).length <= 64),
    spatialStatus: z.object({
      horizontalCrs: z.literal('EPSG:5186'),
      verticalDatum: z.literal('UNCONFIRMED'),
      drainageNetworkLink: z.literal('UNCONNECTED'),
      surfaceGridLink: z.literal('UNCONNECTED'),
    }),
    nodes: z
      .array(
        z.object({
          id,
          kind: id,
          source: id,
          candidateId: id.optional(),
          districtId: id.optional(),
          sourceObjectId: id.optional(),
          facilityType: id.optional(),
          areaM2: area.optional(),
        })
      )
      .min(1)
      .max(4096),
    edges: z.array(z.object({ id, from: id, to: id, kind: id })).max(8192),
    areaBudgets: z
      .array(
        z.object({
          id,
          sourceNodeId: id,
          availableM2: area,
          unit: z.literal('m2'),
          surfaceClass: z.literal('TOTAL'),
          completePartition: z.boolean(),
          allocations: z.array(z.object({ id, targetNodeId: id, areaM2: area })).max(4096),
        })
      )
      .max(4096),
    inputBindings: z.array(z.object({ nodeId: id, role: id, source: id, pointer: id })).max(16384),
    evaluationPoints: z
      .array(
        z.object({
          nodeId: id,
          kind: z.literal('COMPUTED_SURFACE_OUTLET'),
          start: z.iso.datetime({ offset: true }),
          end: z.iso.datetime({ offset: true }),
          method: id,
        })
      )
      .min(1)
      .max(4096),
    unresolved: z.array(id).max(64),
  })
  .superRefine((v, ctx) => {
    const nodes = new Set(v.nodes.map((n) => n.id));
    const allocations = new Set<string>();
    const fail = () => ctx.addIssue({ code: 'custom', message: '연결·면적 배분 근거 불일치' });
    if (
      nodes.size !== v.nodes.length ||
      new Set(v.edges.map((e) => e.id)).size !== v.edges.length ||
      new Set(v.areaBudgets.map((b) => b.id)).size !== v.areaBudgets.length ||
      v.nodes.some((n) => !Object.hasOwn(v.sourceHashes, n.source)) ||
      v.edges.some((e) => !nodes.has(e.from) || !nodes.has(e.to)) ||
      v.inputBindings.some(
        (b) => !nodes.has(b.nodeId) || !Object.hasOwn(v.sourceHashes, b.source)
      ) ||
      v.evaluationPoints.some(
        (p) => !nodes.has(p.nodeId) || Date.parse(p.start) >= Date.parse(p.end)
      )
    )
      fail();
    for (const b of v.areaBudgets) {
      let used = 0n;
      for (const a of b.allocations) {
        if (allocations.has(a.id) || !nodes.has(a.targetNodeId)) fail();
        allocations.add(a.id);
        const quantity = scaled(a.areaM2);
        if (quantity === null) fail();
        else used += quantity;
      }
      const available = scaled(b.availableM2);
      if (
        available === null ||
        !nodes.has(b.sourceNodeId) ||
        used > available ||
        (b.completePartition && used !== available)
      )
        fail();
    }
  });
