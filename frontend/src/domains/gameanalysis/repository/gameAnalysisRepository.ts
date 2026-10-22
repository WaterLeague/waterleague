import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
const count = z.number().int().nonnegative();
const amount = z.number().finite();
const measure = z.object({
  key: z.string(),
  label: z.string(),
  count,
  areaM2: amount.nonnegative(),
});
export const gameAnalysisDto = z.object({
  scope: z.enum(['weekly', 'historical', 'competition']),
  scopeId: z.string(),
  generatedAt: z.iso.datetime(),
  snapshotHash: z.string().regex(/^[a-f0-9]{64}$/),
  summaryAvailable: z.boolean(),
  facts: z
    .object({
      mode: z.enum(['WEEKLY', 'REALTIME', 'DISASTER']),
      status: z.string(),
      participants: count,
      records: count,
      scoredRecords: count,
      facilities: z.array(measure),
      districts: z.array(measure),
      activity: z.array(z.object({ day: z.iso.date(), count })),
      scoreGroups: z.array(
        z.object({
          key: z.string(),
          count,
          totalM3: amount,
          minimumM3: amount,
          maximumM3: amount,
          negative: count,
          zero: count,
          positive: count,
        })
      ),
    })
    .refine(
      (f) =>
        f.scoredRecords <= f.records &&
        f.scoreGroups.every((g) => g.negative + g.zero + g.positive === g.count)
    ),
});
const summaryDto = z.object({
  model: z.string(),
  generatedAt: z.iso.datetime(),
  snapshotHash: z.string().regex(/^[a-f0-9]{64}$/),
  overview: z.string().max(1800),
  findings: z
    .array(
      z.object({
        text: z.string().max(800),
        evidence: z.enum(['participation', 'facilities', 'districts', 'activity', 'scores']),
      })
    )
    .max(5),
  cautions: z.array(z.string().max(800)).max(4),
});
export type GameAnalysis = z.infer<typeof gameAnalysisDto>;
export type GameSummary = z.infer<typeof summaryDto>;
export const loadGameAnalysis = async (endpoint: string, signal: AbortSignal) =>
  gameAnalysisDto.parse(await api(endpoint, 'GET', undefined, signal));
export const generateGameSummary = async (
  endpoint: string,
  snapshotHash: string,
  signal: AbortSignal
) => {
  const [path, query] = endpoint.split('?');
  return summaryDto.parse(
    await api(`${path}/summary${query ? `?${query}` : ''}`, 'POST', { snapshotHash }, signal)
  );
};
