import { z } from 'zod';
const amount = z.number().finite().nonnegative();
export const floodAmountClose = (a: number, b: number) =>
  Math.abs(a - b) <= Math.max(1e-8, Math.abs(b) * 1e-9);
export const nodeFloodingDto = z
  .object({
    schemaVersion: z.literal(1),
    method: z.literal('NATIVE_ROUTING_STEP_FLOODING_TRAPEZOIDAL_INTEGRAL'),
    layoutSha256: z.string().regex(/^[a-f0-9]{64}$/),
    startSeconds: z.literal(0),
    endSeconds: amount.positive(),
    nodes: z
      .array(
        z.object({
          id: z.string().min(1).max(127),
          kind: z.enum(['JUNCTION', 'OUTFALL', 'STORAGE']),
          mapped: z.boolean(),
          floodingM3: amount,
        })
      )
      .min(1)
      .max(2000),
    totalFloodingM3: amount,
    sumNodeFloodingM3: amount,
    balanceDifferenceM3: z.number().finite(),
  })
  .superRefine((v, ctx) => {
    const sum = v.nodes.reduce((s, n) => s + n.floodingM3, 0);
    if (
      new Set(v.nodes.map((n) => n.id)).size !== v.nodes.length ||
      !floodAmountClose(sum, v.sumNodeFloodingM3) ||
      !floodAmountClose(sum, v.totalFloodingM3) ||
      !floodAmountClose(v.balanceDifferenceM3, v.sumNodeFloodingM3 - v.totalFloodingM3)
    )
      ctx.addIssue({ code: 'custom', message: '절점 월류 합계·원장 불일치' });
  });
export type NodeFlooding = z.infer<typeof nodeFloodingDto>;
