import { useEffect, useState } from 'react';
import { z } from 'zod';
import { readPublicData } from '../../../shared/repository/publicDataCache';
import {
  candidateKey,
  candidateBounds,
  type GroundCandidate,
} from '../service/candidateTilesService';
const row = z.tuple([
  z.string().regex(/^[A-Za-z0-9-]+$/),
  z.string().regex(/^\d+$/),
  z.number().int().min(1).max(63),
  z.array(z.number().finite().min(-60000).max(60000)).min(8).max(200000),
  z.array(z.array(z.number().finite().min(-60000).max(60000)).min(8).max(200000)).optional(),
]);
const reference = z.object({
  id: z.string(),
  file: z.string().regex(/^tiles\/-?\d+_-?\d+\.json$/),
  bytes: z.number().int().positive().max(4000000),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]),
});
const catalogDto = z.object({
  schemaVersion: z.literal(1),
  tiles: z.array(reference).max(1000),
  overview: z.object({
    file: z.literal('overview.json'),
    bytes: z.number().int().positive().max(40000000),
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
  }),
});
let catalog: z.infer<typeof catalogDto> | null = null;
const cache = new Map<string, { rows: GroundCandidate[]; bytes: number }>();
let cacheBytes = 0;
let overview: GroundCandidate[] | null = null;
export function useGroundCandidates(center: [number, number], distance: number) {
  const [rows, setRows] = useState<GroundCandidate[]>([]),
    [error, setError] = useState('');
  const x = Math.round(center[0] / 200) * 200,
    y = Math.round(center[1] / 200) * 200;
  const range = Math.ceil(distance / 400) * 400;
  useEffect(() => {
    const controller = new AbortController();

    void (async () => {
      if (!catalog)
        catalog = catalogDto.parse(
          await readPublicData(
            '/data/site-display-v1/catalog.json',
            '7cefc001bd3b64410d2121b91e96508e74b04000292b7fa4dd172da487c88ace',
            120000,
            controller.signal
          )
        );
      if (range > 5000) {
        if (!overview)
          overview = z
            .array(row)
            .max(200000)
            .parse(
              await readPublicData(
                '/data/site-display-v1/overview.json',
                catalog.overview.sha256,
                catalog.overview.bytes,
                controller.signal
              )
            );
        controller.signal.throwIfAborted();
        setRows(overview);
        setError('');
        return;
      }
      const b = candidateBounds([x, y], range);
      const refs = catalog.tiles.filter(
        (t) => t.bounds[0] < b[2] && t.bounds[2] > b[0] && t.bounds[1] < b[3] && t.bounds[3] > b[1]
      );
      const next: GroundCandidate[] = [];
      for (let i = 0; i < refs.length; i += 4) {
        const values = await Promise.all(
          refs.slice(i, i + 4).map(async (r) => {
            const saved = cache.get(r.sha256);
            if (saved) {
              cache.delete(r.sha256);
              cache.set(r.sha256, saved);
              return saved.rows;
            }
            const data = z
              .array(row)
              .max(15000)
              .parse(
                await readPublicData(
                  '/data/site-display-v1/' + r.file,
                  r.sha256,
                  r.bytes,
                  controller.signal
                )
              );
            if (!controller.signal.aborted) {
              cache.set(r.sha256, { rows: data, bytes: r.bytes });
              cacheBytes += r.bytes;
              while (cacheBytes > 32 * 1024 * 1024) {
                const key = cache.keys().next().value!;
                cacheBytes -= cache.get(key)!.bytes;
                cache.delete(key);
              }
            }
            return data;
          })
        );
        controller.signal.throwIfAborted();
        next.push(...values.flat());
      }
      const unique = [...new Map(next.map((r) => [candidateKey(r), r])).values()];
      setRows((previous) =>
        previous.length === unique.length && previous.every((r, i) => r === unique[i])
          ? previous
          : unique
      );
      setError('');
    })().catch(() => {
      if (!controller.signal.aborted) setError('설치 가능 구역을 불러오지 못했습니다.');
    });
    return () => controller.abort();
  }, [x, y, range]);
  return { rows, error };
}
