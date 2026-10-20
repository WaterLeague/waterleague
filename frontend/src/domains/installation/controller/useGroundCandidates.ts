import { useEffect, useState } from 'react';
import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
import { candidateTypes, type GroundCandidate } from '../service/candidateTilesService';
const hash = '4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7';
const point = z.tuple([z.number().finite(), z.number().finite()]);
const ring = z.array(point).min(4).max(20000);
const shape = z.discriminatedUnion('type', [
  z.object({ type: z.literal('Polygon'), coordinates: z.array(ring).min(1).max(500) }),
  z.object({
    type: z.literal('MultiPolygon'),
    coordinates: z.array(z.array(ring).min(1).max(500)).min(1).max(1000),
  }),
]);
const response = z.object({
  catalogSha256: z.literal(hash),
  coordinateSystem: z.literal('EPSG:5186'),
  sites: z
    .array(
      z.object({
        id: z.string().regex(/^C[a-f0-9]{24}$/),
        districtId: z.string().regex(/^11\d{3}$/),
        geometry: shape,
        kind: z.literal('GROUND'),
        allowedTypes: z.array(z.enum(candidateTypes)).min(1),
      })
    )
    .max(2000),
});
const cache = new Map<string, { rows: GroundCandidate[]; bytes: number }>();
let cachedBytes = 0;
export function useGroundCandidates(center: [number, number], distance: number) {
  const [rows, setRows] = useState<GroundCandidate[]>([]),
    [error, setError] = useState('');
  const x = Math.round(center[0] / 100) * 100,
    y = Math.round(center[1] / 100) * 100;
  const radius = Math.min(1000, Math.max(200, Math.ceil((distance * 0.7) / 100) * 100));
  const close = distance <= 1800;
  useEffect(() => {
    const controller = new AbortController();
    if (!close) {
      setRows([]);
      setError('');
      return;
    }
    const key = `${x}:${y}:${radius}`;
    const timer = window.setTimeout(() => {
      const saved = cache.get(key);
      if (saved) {
        cache.delete(key);
        cache.set(key, saved);
        setRows(saved.rows);
        setError('');
        return;
      }
      const params = new URLSearchParams({
        minx: String(x + 198128 - radius),
        maxx: String(x + 198128 + radius),
        miny: String(y + 551989 - radius),
        maxy: String(y + 551989 + radius),
        kind: 'GROUND',
        limit: '2000',
      });
      void api<unknown>('/spatial/play/sites?' + params, 'GET', undefined, controller.signal)
        .then((value) => {
          const source = response.parse(value);
          let points = 0;
          const result: GroundCandidate[] = source.sites.map((cell) => {
            const components =
              cell.geometry.type === 'Polygon'
                ? [cell.geometry.coordinates]
                : cell.geometry.coordinates;
            const polygons = components.map((component) =>
              component.map((ring) =>
                ring.map(([a, b]): [number, number] => {
                  points++;
                  return [a - 198128, b - 551989];
                })
              )
            );
            const mask = cell.allowedTypes.reduce(
              (bits, type) => bits | (1 << candidateTypes.indexOf(type)),
              0
            );
            return [cell.id, cell.districtId, mask, polygons];
          });
          if (controller.signal.aborted) return;
          const bytes = points * 16;
          if (bytes <= 32 * 1024 * 1024) {
            cache.set(key, { rows: result, bytes });
            cachedBytes += bytes;
            while (cachedBytes > 32 * 1024 * 1024) {
              const oldest = cache.keys().next().value!;
              cachedBytes -= cache.get(oldest)!.bytes;
              cache.delete(oldest);
            }
          }
          setRows(result);
          setError('');
        })
        .catch(() => {
          if (!controller.signal.aborted)
            setError('원형 후보를 불러오지 못했습니다. 범위가 조밀하면 더 확대해 주세요.');
        });
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [x, y, radius, close]);
  return { rows, error };
}
