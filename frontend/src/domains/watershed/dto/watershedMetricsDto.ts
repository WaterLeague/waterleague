import { z } from 'zod';
const positive = z.number().finite().nonnegative();
const row = z.object({
  outwardVolumeM3: positive,
  inwardVolumeM3: positive,
  peakOutwardM3s: positive,
  peakInwardM3s: positive,
  peakOutwardTimeSeconds: positive,
  peakInwardTimeSeconds: positive,
  coveredSeconds: positive,
  nativeSteps: positive.int(),
});
export const watershedMetricsDto = z
  .object({
    specificationSha256: z.string().regex(/^[a-f0-9]{64}$/),
    complete: z.boolean(),
    method: z.literal('NATIVE_ROUTING_STEP_DIRECTIONAL_TRAPEZOIDAL_INTEGRAL'),
    peakMethod: z.literal('SIMULTANEOUS_SELECTED_OUTFALL_SUM'),
    specification: z.object({
      schemaVersion: z.literal(1),
      policyVersion: z.literal('PUBLIC_NETWORK_ALL_OUTFALLS_v1'),
      startMilliseconds: z.literal(0),
      endMilliseconds: positive.int().positive(),
      networkOutfalls: z.array(z.string().min(1)).min(1).max(1000),
    }),
    outfalls: z.record(z.string(), row),
    combined: row,
  })
  .superRefine((v, ctx) => {
    const ids = v.specification.networkOutfalls;
    const duration = v.specification.endMilliseconds / 1000;
    const entries = Object.values(v.outfalls);
    const close = (a: number, b: number) => Math.abs(a - b) <= Math.max(1e-7, Math.abs(a) * 1e-10);
    const invalid =
      new Set(ids).size !== ids.length ||
      entries.length !== ids.length ||
      ids.some((id) => !Object.hasOwn(v.outfalls, id)) ||
      [...entries, v.combined].some(
        (r) =>
          r.coveredSeconds > duration + 1e-7 ||
          r.peakOutwardTimeSeconds > duration ||
          r.peakInwardTimeSeconds > duration ||
          (v.complete && (!close(r.coveredSeconds, duration) || r.nativeSteps === 0))
      ) ||
      !close(
        entries.reduce((s, r) => s + r.outwardVolumeM3, 0),
        v.combined.outwardVolumeM3
      ) ||
      !close(
        entries.reduce((s, r) => s + r.inwardVolumeM3, 0),
        v.combined.inwardVolumeM3
      );
    if (invalid) ctx.addIssue({ code: 'custom', message: '출구 지표의 평가 범위·체적 불일치' });
  });
export type WatershedMetrics = z.infer<typeof watershedMetricsDto>;
