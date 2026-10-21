import { scopeIntersects, type MapScope } from '../../../shared/service/mapScope';
import { useEffect, useMemo, useState } from 'react';
import type { TraceCatalog, TraceTile } from '../entity/floodTrace';
import type { PlanView } from '../../city/service/planNavigationService';
import { loadTraceCatalog, loadTraceTile } from '../repository/floodTraceRepository';
import { visibleTraceTiles, scopeTraceTile } from '../service/floodTraceService';

export function useFloodTraces(
  enabled: boolean,
  eventId: string,
  camera: PlanView,
  scope?: MapScope
) {
  const [catalog, setCatalog] = useState<TraceCatalog | null>(null);
  const [loaded, setLoaded] = useState<TraceTile[]>([]);
  const [error, setError] = useState(false),
    [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    setError(false);
    void loadTraceCatalog()
      .then((c) => {
        if (active) setCatalog(c);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [enabled, revision]);
  const event = catalog?.events.find((e) => e.id === eventId);
  const keys = visibleTraceTiles(event, camera)
    .filter((t) => scopeIntersects(t.bounds, scope))
    .map((t) => t.id)
    .join(',');
  useEffect(() => {
    if (!enabled || !event) {
      setLoaded([]);
      setLoading(false);
      return;
    }
    let active = true,
      failed = false,
      index = 0;
    const requested = event.tiles.filter((t) => keys.split(',').includes(t.id));
    setLoading(true);
    setError(false);
    setLoaded((old) =>
      old.filter((t) => t.eventId === eventId && requested.some((r) => r.id === t.id))
    );
    const results: TraceTile[] = [];
    const next = async () => {
      while (active && !failed && index < requested.length) {
        const tile = requested[index++];
        try {
          results.push(scopeTraceTile(await loadTraceTile(eventId, tile), scope));
        } catch (error) {
          failed = true;
          throw error;
        }
      }
    };
    void Promise.all(Array.from({ length: Math.min(4, requested.length) }, next))
      .then(() => {
        if (active) {
          setLoaded(results.sort((a, b) => a.id.localeCompare(b.id)));
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setLoaded([]);
          setError(true);
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [enabled, event, eventId, keys, revision, scope]);
  const tiles = useMemo(
    () => (enabled ? loaded.filter((t) => t.eventId === eventId) : []),
    [enabled, loaded, eventId]
  );
  return { catalog, event, tiles, loading, error, retry: () => setRevision((v) => v + 1) };
}
