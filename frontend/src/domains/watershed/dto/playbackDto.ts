import { z } from 'zod';
const amount = z.number().finite();
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const source = z.object({
  id: z.enum(['baseline', 'strategy']),
  framesSha256: hash,
  resultSha256: hash,
  numericalStatus: z.enum(['PASSED', 'FAILED']),
});
const pair = <T extends { id: string }>(rows: T[]) =>
  rows.length === 2 && new Set(rows.map((r) => r.id)).size === 2;
export const playbackCatalogDto = z.object({
  jobId: z.uuid(),
  inputHash: hash,
  method: z.literal('PREVIOUS_RECORDED_STATE_NO_INTERPOLATION'),
  depthScaleM: amount.nonnegative(),
  timesSeconds: z
    .array(amount.nonnegative())
    .min(2)
    .max(20000)
    .refine((v) => v[0] === 0 && v.every((t, i) => i === 0 || t > v[i - 1])),
  sources: z.array(source).length(2).refine(pair),
});
const state = z
  .object({
    timeSeconds: amount.nonnegative(),
    nodes: z
      .array(
        z.object({
          id: z.string().min(1).max(127),
          type: z.number().int().min(0).max(4),
          headM: amount,
          depthM: amount,
          storageM3: amount,
          overflowM3s: amount,
        })
      )
      .min(1)
      .max(512),
    links: z
      .array(
        z.object({
          id: z.string().min(1).max(127),
          flowM3s: amount,
          depthM: amount,
          setting: amount,
        })
      )
      .max(1024),
  })
  .refine(
    (v) =>
      new Set(v.nodes.map((n) => n.id)).size === v.nodes.length &&
      new Set(v.links.map((n) => n.id)).size === v.links.length
  );
export const playbackFrameDto = z
  .object({
    jobId: z.uuid(),
    inputHash: hash,
    requestedTimeSeconds: amount.nonnegative(),
    cases: z
      .array(source.extend({ ageSeconds: amount.nonnegative(), state }))
      .length(2)
      .refine(pair),
  })
  .refine((v) =>
    v.cases.every(
      (c) =>
        c.state.timeSeconds <= v.requestedTimeSeconds &&
        Math.abs(v.requestedTimeSeconds - c.state.timeSeconds - c.ageSeconds) <= 1e-9
    )
  );
export type PlaybackCatalog = z.infer<typeof playbackCatalogDto>;
export type PlaybackFrame = z.infer<typeof playbackFrameDto>;
