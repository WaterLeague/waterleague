import { startTransition, useEffect, useMemo, useState } from 'react';
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
    const request = new AbortController();
    const ready = new Map<string, TopographyBuffers>();
    let frame: number | undefined;
    setError('');
    setBusy(entries.length > 0);
    const publish = (complete: boolean) => {
      if (request.signal.aborted) return;
      const next = entries.flatMap((entry) => {
        const data = ready.get(entry.id);
        return data ? [{ id: entry.id, data }] : [];
      });
      startTransition(() =>
        setTiles((previous) => {
          // 이동 중 부분 교체는 빈 영역과 반복 인스턴싱을 만들므로 완료된 시야를 함께 교체한다.
          if (!complete && previous.length) return previous;
          const values = next;
          return values.length === previous.length &&
            values.every((tile, i) => tile.id === previous[i].id && tile.data === previous[i].data)
            ? previous
            : values;
        })
      );
    };
    async function run() {
      await Promise.all(
        entries.map(async (entry) => {
          const data = await requestTopographyTile(
            entry,
            index!.layers,
            terrain,
            plan,
            request.signal
          );
          if (request.signal.aborted) return;
          ready.set(entry.id, data);
          if (frame === undefined)
            frame = requestAnimationFrame(() => {
              frame = undefined;
              publish(false);
            });
        })
      );
      if (frame !== undefined) {
        cancelAnimationFrame(frame);
        frame = undefined;
      }
      publish(true);
    }
    void run()
      .catch(() => {
        if (!request.signal.aborted) setError(new TopographyError().message);
      })
      .finally(() => {
        if (!request.signal.aborted) setBusy(false);
      });
    return () => {
      request.abort();
      if (frame !== undefined) cancelAnimationFrame(frame);
    };
    // 같은 타일 목록에서는 카메라 이동으로 작업을 취소하거나 형상을 다시 만들지 않는다.
  }, [index, key, terrain, plan]);
  return { index, tiles, error, busy };
}
