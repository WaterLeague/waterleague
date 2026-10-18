import { z } from 'zod';
import { surfaceCatalogDto } from './surfaceDto';
const sha = z.string().regex(/^[a-f0-9]{64}$/);
export const publicSurfaceDto = z
  .object({
    serverNow: z.iso.datetime({ offset: true }),
    runs: z
      .array(
        z
          .object({
            id: z.uuid(),
            basinId: z.string().regex(/^[a-z0-9-]{1,80}$/),
            name: z.string().min(1).max(120),
            inputBundleSha256: sha,
            numericalPolicySha256: sha,
            lastFrameAt: z.iso.datetime({ offset: true }),
            catalog: surfaceCatalogDto,
          })
          .refine(
            (run) =>
              run.catalog.classification === 'PUBLIC_INPUT_UNCALIBRATED_CURRENT_BASELINE' &&
              Math.abs(
                Date.parse(run.lastFrameAt) -
                  (Date.parse(run.catalog.startUtc) + run.catalog.timesSeconds.at(-1)! * 1000)
              ) < 0.001
          )
      )
      .max(128),
  })
  .refine(
    (value) =>
      new Set(value.runs.map((r) => r.id)).size === value.runs.length &&
      new Set(value.runs.map((r) => r.basinId)).size === value.runs.length
  );
export type PublicSurfaceCurrent = z.infer<typeof publicSurfaceDto>;
