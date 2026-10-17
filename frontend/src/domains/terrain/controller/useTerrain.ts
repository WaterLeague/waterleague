import { useEffect, useState } from 'react';
import type { Terrain } from '../entity/terrain';
import { loadTerrain } from '../repository/terrainRepository';
export function useTerrain() {
  const [terrain, setTerrain] = useState<Terrain | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void loadTerrain(controller.signal)
      .then((v) => {
        if (!controller.signal.aborted) setTerrain(v);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, []);
  return { terrain, error };
}
