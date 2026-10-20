import { z } from 'zod';
import { watershedLayoutDto, type WatershedLayout } from './watershedLayoutDto';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const amount = z.number().finite().nonnegative();
const residual = z.object({
  sampleCount: z.number().int().positive(),
  coveredCount: z.number().int().nonnegative(),
  complete: z.boolean(),
  meanM: amount.nullable(),
  medianM: amount.nullable(),
  maxM: amount.nullable(),
  lengthWeightedMeanM: amount.nullable(),
});
export const watershedGeoreferenceDto = z.object({
  schemaVersion: z.literal(1),
  id: z.literal('SEOCHO_ROAD_SUPPORTED_LOCATION_V1'),
  method: z.literal('ROAD_SUPPORTED_CRS_HYPOTHESIS_V1'),
  sourceLayoutSha256: hash,
  sourceOriginalSha256: hash,
  evidenceSha256: hash,
  sourceUrl: z.url().startsWith('https://'),
  sourceCrsVerified: z.literal(false),
  assumedSourceCrs: z.literal('EPSG:5181'),
  horizontalCrs: z.literal('EPSG:5186'),
  verticalDatum: z.null(),
  scope: z.literal('PUBLISHED_RESEARCH_MODEL_LOCATION_ASSUMPTION'),
  rankingEligible: z.literal(false),
  historicalReconstructionEligible: z.literal(false),
  roadSource: z.object({ spatialSha256: hash, distributionUpdatedAt: z.string() }),
  bounds: z.tuple([
    z.number().finite(),
    z.number().finite(),
    z.number().finite(),
    z.number().finite(),
  ]),
  comparison: z
    .array(
      z.object({
        sourceCrsHypothesis: z.enum(['EPSG:2097', 'EPSG:5174', 'EPSG:5181', 'EPSG:5186']),
        roadCount: z.number().int().nonnegative(),
        nodes: residual,
        conduits: residual,
      })
    )
    .length(4),
  nodes: watershedLayoutDto.shape.nodes,
  links: watershedLayoutDto.shape.links,
  catchments: watershedLayoutDto.shape.catchments,
  limitations: z.array(z.string()).min(1),
});
export type WatershedGeoreference = z.infer<typeof watershedGeoreferenceDto>;
export const locationReferenceDto = watershedGeoreferenceDto
  .pick({
    id: true,
    method: true,
    sourceLayoutSha256: true,
    sourceOriginalSha256: true,
    evidenceSha256: true,
    assumedSourceCrs: true,
    horizontalCrs: true,
    sourceCrsVerified: true,
  })
  .extend({ profileSha256: hash })
  .strict();

export function sameSourceGeometry(geo: WatershedGeoreference, raw: WatershedLayout) {
  // 같은 중부원점 투영의 북방 가산값 차이만 허용하며 임의 이동·스냅을 거부한다.
  const samePoint = (a: number[], b: number[]) =>
    Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1] - 100000) < 1e-6;
  if (
    geo.nodes.length !== raw.nodes.length ||
    geo.nodes.some(
      (n, i) =>
        n.id !== raw.nodes[i].id ||
        n.kind !== raw.nodes[i].kind ||
        !samePoint(n.coordinate, raw.nodes[i].coordinate)
    )
  )
    return false;
  for (const key of ['links', 'catchments'] as const) {
    if (
      geo[key].length !== raw[key].length ||
      geo[key].some(
        (row, i) =>
          row.id !== raw[key][i].id ||
          row.points.length !== raw[key][i].points.length ||
          row.points.some((p, j) => !samePoint(p, raw[key][i].points[j]))
      )
    )
      return false;
  }
  return (
    geo.links.every(
      (l, i) =>
        l.fromNode === raw.links[i].fromNode &&
        l.toNode === raw.links[i].toNode &&
        l.lengthDeclaredM === raw.links[i].lengthDeclaredM
    ) && geo.catchments.every((c, i) => c.outletNodeId === raw.catchments[i].outletNodeId)
  );
}
