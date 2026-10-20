import { useEffect, useMemo, useState } from 'react';
import type { Terrain } from '../../terrain/entity/terrain';
import type { TopographyIndex } from '../dto/topographyDto';
import type { TopographyBuffers } from '../entity/topography';
import { loadTopographyIndex, requestTopographyTile } from '../repository/topographyRepository';
import { nearbyTopographyTiles } from '../service/topographyVisibilityService';
import { TopographyError } from '../exception/TopographyError';
export function useTopography(
  center: [number, number],
  distance: number,
  terrain: Terrain | null,
  plan: boolean
) {
  const [index, setIndex] = useState<TopographyIndex | null>(null),
    [tiles, setTiles] = useState<{ id: string; data: TopographyBuffers }[]>([]);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const request = new AbortController();
    void loadTopographyIndex(request.signal)
      .then((value) => {
        if (!request.signal.aborted) setIndex(value);
      })
      .catch(() => {
        if (!request.signal.aborted) setError(new TopographyError().message);
      });
    return () => request.abort();
  }, []);
  const entries = useMemo(
    () => (index ? nearbyTopographyTiles(index, center, distance) : []),
    [index, center, distance]
  );
  const key = entries
    .map((entry) => entry.id)
    .sort()
    .join(',');
  useEffect(() => {
    if (!index) return;
    const request = new AbortController(),
      next: { id: string; data: TopographyBuffers }[] = [];
    setError('');
    setBusy(entries.length > 0);
    async function run() {
      const wanted = new Set(entries.map((entry) => entry.id));
      setTiles((previous) => previous.filter((tile) => wanted.has(tile.id)));
      for (const entry of entries) {
        const data = await requestTopographyTile(
          entry,
          index!.layers,
          terrain,
          plan,
          request.signal
        );
        if (request.signal.aborted) return;
        next.push({ id: entry.id, data });
        const ready = [...next];
        setTiles((previous) => [
          ...ready,
          ...previous.filter(
            (tile) => !ready.some((value) => value.id === tile.id) && wanted.has(tile.id)
          ),
        ]);
      }
      if (!request.signal.aborted) setTiles(next);
    }
    void run()
      .catch(() => {
        if (!request.signal.aborted) setError(new TopographyError().message);
      })
      .finally(() => {
        if (!request.signal.aborted) setBusy(false);
      });
    return () => request.abort();
    // 같은 타일 목록에서는 카메라 이동으로 작업을 취소하거나 형상을 다시 만들지 않는다.
  }, [index, key, terrain, plan]);
  return { index, tiles, error, busy };
}
