import { z } from 'zod';
import { readPublicData } from '../../../shared/repository/publicDataCache';
import { CandidateDisplayError } from '../exception/CandidateDisplayError';
import type { GroundCandidate } from '../service/candidateTilesService';
const hash = '7b0de50aca0bd23a1c6276d1201b49759070f599bd4db2a5c8fdd09745b083c4';
const catalog = 'd2d9ea2a888ee01d59f253b3848c3c30fdf4b6b3f03662b1202dc9b7a48b88b9';
const coordinate = z.number().finite().min(-100000).max(100000);
const point = z.tuple([coordinate, coordinate]);
const ring = z.array(point).min(4).max(100000);
const sha = z.string().regex(/^[a-f0-9]{64}$/);
export const candidateDisplayRowsDto = z
  .array(
    z.tuple([
      z.string().regex(/^C[a-f0-9]{24}$/),
      z.string().regex(/^11\d{3}$/),
      z.number().int().min(1).max(63),
      z.array(z.array(ring).min(1).max(10000)).min(1).max(10000),
    ])
  )
  .max(50000);
const indexDto = z
  .object({
    schemaVersion: z.literal(1),
    sourceCatalogSha256: z.literal(catalog),
    displayOnly: z.literal(true),
    hydraulicInputsChanged: z.literal(false),
    tiles: z
      .array(
        z.object({
          id: z.string().regex(/^-?\d+_-?\d+$/),
          file: z.string().regex(/^tiles\/-?\d+_-?\d+\.json\.gz$/),
          bounds: z.tuple([coordinate, coordinate, coordinate, coordinate]),
          sha256: sha,
          count: z.number().int().positive().max(50000),
          bytes: z.number().int().positive().max(33554432),
        })
      )
      .max(10000),
  })
  .superRefine((value, ctx) => {
    if (
      new Set(value.tiles.map((t) => t.id)).size !== value.tiles.length ||
      value.tiles.some((t) => t.file !== `tiles/${t.id}.json.gz`)
    )
      ctx.addIssue({ code: 'custom', message: '후보 표시 타일 대응 오류' });
  });
export type CandidateDisplayIndex = z.infer<typeof indexDto>;
let index: CandidateDisplayIndex | undefined;
const cache = new Map<string, { rows: GroundCandidate[]; bytes: number }>();
let bytes = 0;
export async function loadCandidateDisplayIndex(signal: AbortSignal) {
  if (index) return index;
  const result = indexDto.safeParse(
    await readPublicData('/data/seoul-candidates-v1/index.json', hash, 1048576, signal)
  );
  if (!result.success) throw new CandidateDisplayError();
  signal.throwIfAborted();
  return (index = result.data);
}
export async function loadCandidateDisplayTile(
  entry: CandidateDisplayIndex['tiles'][number],
  signal: AbortSignal
) {
  const saved = cache.get(entry.sha256);
  if (saved) {
    cache.delete(entry.sha256);
    cache.set(entry.sha256, saved);
    return saved.rows;
  }
  const parsed = candidateDisplayRowsDto.safeParse(
    await readPublicData(
      '/data/seoul-candidates-v1/' + entry.file,
      entry.sha256,
      entry.bytes,
      signal
    )
  );
  if (
    !parsed.success ||
    parsed.data.length !== entry.count ||
    new Set(parsed.data.map((r) => r[1] + ':' + r[0])).size !== parsed.data.length
  )
    throw new CandidateDisplayError();
  signal.throwIfAborted();
  cache.set(entry.sha256, { rows: parsed.data, bytes: entry.bytes });
  bytes += entry.bytes;
  while (bytes > 32 * 1024 * 1024) {
    const key = cache.keys().next().value!;
    bytes -= cache.get(key)!.bytes;
    cache.delete(key);
  }
  return parsed.data;
}
