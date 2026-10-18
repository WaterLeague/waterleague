import { z } from 'zod';
const id = z.string().min(1).max(127);
const coordinate = z.tuple([z.number().finite(), z.number().finite()]);
export const watershedLayoutDto = z
  .object({
    schemaVersion: z.literal(1),
    id: z.string(),
    sourceOriginalSha256: z.string().regex(/^[a-f0-9]{64}$/),
    sourceUrl: z.url().startsWith('https://'),
    classification: z.literal('PUBLISHED_MODEL_COORDINATES_NOT_GEOREFERENCED'),
    coordinateUnitsDeclared: z.literal('Meters'),
    horizontalCrs: z.null(),
    nodes: z
      .array(z.object({ id, kind: z.enum(['JUNCTION', 'OUTFALL']), coordinate }))
      .min(1)
      .max(1000),
    links: z
      .array(
        z.object({
          id,
          fromNode: id,
          toNode: id,
          points: z.array(coordinate).min(2).max(1000),
          lengthDeclaredM: z.number().finite().positive(),
        })
      )
      .max(2000),
    catchments: z
      .array(z.object({ id, outletNodeId: id, points: z.array(coordinate).min(3).max(1000) }))
      .min(1)
      .max(1000),
    limitations: z.array(z.string()),
  })
  .superRefine((v, ctx) => {
    const nodes = new Map(v.nodes.map((n) => [n.id, n]));
    const pointEqual = (a: number[], b: number[]) => a[0] === b[0] && a[1] === b[1];
    if (
      nodes.size !== v.nodes.length ||
      new Set(v.links.map((l) => l.id)).size !== v.links.length ||
      new Set(v.catchments.map((c) => c.id)).size !== v.catchments.length ||
      v.catchments.some((c) => !nodes.has(c.outletNodeId)) ||
      v.links.some(
        (l) =>
          !nodes.has(l.fromNode) ||
          !nodes.has(l.toNode) ||
          !pointEqual(l.points[0], nodes.get(l.fromNode)!.coordinate) ||
          !pointEqual(l.points[l.points.length - 1], nodes.get(l.toNode)!.coordinate)
      )
    )
      ctx.addIssue({ code: 'custom', message: '공개 관망 경계·연결 불일치' });
  });
export type WatershedLayout = z.infer<typeof watershedLayoutDto>;
