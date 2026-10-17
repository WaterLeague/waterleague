import { useEffect, useState } from 'react';
import type { CandidateMap } from '../entity/catalog';
import type { SceneContext } from '../entity/sceneContext';
import { loadSceneContext } from '../repository/sceneContextRepository';

export function useSceneContext(map: CandidateMap) {
  const [state, setState] = useState<{
    map: CandidateMap;
    data: SceneContext | null;
    failed: boolean;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    loadSceneContext(map, abort.signal)
      .then((data) => {
        if (!abort.signal.aborted) setState({ map, data, failed: false });
      })
      .catch(() => {
        if (!abort.signal.aborted) setState({ map, data: null, failed: true });
      });
    return () => abort.abort();
  }, [map, attempt]);
  const current = state?.map === map ? state : null;
  return {
    data: current?.data ?? null,
    failed: current?.failed ?? false,
    retry: () => {
      setState(null);
      setAttempt((n) => n + 1);
    },
  };
}
