import { useEffect, useMemo, useState } from 'react';
import { CandidateDisplayError } from '../exception/CandidateDisplayError';
import {
  loadCandidateDisplayIndex,
  loadCandidateDisplayTile,
  type CandidateDisplayIndex,
} from '../repository/candidateDisplayRepository';
import {
  mergeCandidateParts,
  nearbyCandidateTiles,
  type GroundCandidate,
} from '../service/candidateTilesService';
export function useGroundCandidates(center: [number, number], distance: number) {
  const [index, setIndex] = useState<CandidateDisplayIndex | null>(null);
  const [rows, setRows] = useState<GroundCandidate[]>([]),
    [error, setError] = useState('');
  useEffect(() => {
    const request = new AbortController();
    void loadCandidateDisplayIndex(request.signal)
      .then((value) => {
        if (!request.signal.aborted) setIndex(value);
      })
      .catch(() => {
        if (!request.signal.aborted) setError(new CandidateDisplayError().message);
      });
    return () => request.abort();
  }, []);
  const entries = useMemo(
    () => (index ? nearbyCandidateTiles(index.tiles, center, distance) : []),
    [index, center, distance]
  );
  const key = entries
    .map((t) => t.id)
    .sort()
    .join(',');
  useEffect(() => {
    const request = new AbortController();
    if (!entries.length) {
      setRows([]);
      return;
    }
    setError('');
    async function run() {
      const parts: GroundCandidate[][] = [];
      for (let i = 0; i < entries.length; i += 4) {
        parts.push(
          ...(await Promise.all(
            entries.slice(i, i + 4).map((t) => loadCandidateDisplayTile(t, request.signal))
          ))
        );
      }
      if (!request.signal.aborted) setRows(mergeCandidateParts(parts));
    }
    void run().catch(() => {
      if (!request.signal.aborted) setError(new CandidateDisplayError().message);
    });
    return () => request.abort();
    // 같은 타일 안의 카메라 이동은 후보 형상 재생성을 일으키지 않는다.
  }, [key]);
  return { rows, error };
}
