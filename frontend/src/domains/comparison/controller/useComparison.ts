import { useEffect, useRef, useState } from 'react';
import type { ComparisonSummary, RainfallComparison } from '../entity/comparison';
import * as repo from '../repository/comparisonRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useComparison(enabled: boolean) {
  const [items, setItems] = useState<ComparisonSummary[]>([]),
    [detail, setDetail] = useState<RainfallComparison | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const alive = useRef(true),
    sequence = useRef(0),
    pending = useRef<{ fingerprint: string; key: string } | null>(null);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      sequence.current++;
    };
  }, []);
  useEffect(() => {
    let current = true;
    if (enabled)
      repo
        .loadComparisons()
        .then((v) => {
          if (current) setItems(v);
        })
        .catch((e) => {
          if (current) setError(errorMessage(e));
        });
    return () => {
      current = false;
    };
  }, [enabled]);
  const active = detail?.jobs.some((j) => j.state === 'QUEUED' || j.state === 'RUNNING') ?? false;
  useEffect(() => {
    if (!detail || !active) return;
    const id = detail.id,
      token = sequence.current;
    let current = true,
      running = false;
    const timer = window.setInterval(() => {
      if (running) return;
      running = true;
      repo
        .loadComparison(id)
        .then((v) => {
          if (current && token === sequence.current) setDetail(v);
        })
        .catch((e) => {
          if (current && token === sequence.current) setError(errorMessage(e));
        })
        .finally(() => {
          running = false;
        });
    }, 2000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [detail?.id, active]);
  async function open(id: string) {
    const token = ++sequence.current;
    setDetail(null);
    setError('');
    setBusy(true);
    try {
      const d = await repo.loadComparison(id);
      if (token === sequence.current && alive.current) setDetail(d);
    } catch (e) {
      if (token === sequence.current && alive.current) setError(errorMessage(e));
    } finally {
      if (token === sequence.current && alive.current) setBusy(false);
    }
  }
  async function create(versionId: string, hashes: string[]) {
    const fingerprint = versionId + '|' + [...hashes].sort().join('|');
    if (pending.current?.fingerprint !== fingerprint)
      pending.current = { fingerprint, key: crypto.randomUUID() };
    const token = ++sequence.current;
    setDetail(null);
    setError('');
    setBusy(true);
    try {
      const d = await repo.createComparison(versionId, hashes, pending.current.key);
      if (token !== sequence.current || !alive.current) return;
      setDetail(d);
      pending.current = null;
      const rows = await repo.loadComparisons();
      if (alive.current && token === sequence.current) setItems(rows);
    } catch (e) {
      if (token === sequence.current && alive.current) setError(errorMessage(e));
    } finally {
      if (token === sequence.current && alive.current) setBusy(false);
    }
  }
  return { items, detail, error, busy, open, create };
}
