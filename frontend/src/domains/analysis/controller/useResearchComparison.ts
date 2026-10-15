import { useEffect, useRef, useState } from 'react';
import type { ResearchComparison, ResearchComparisonSummary } from '../entity/analysis';
import * as repo from '../repository/analysisRepository';
import { comparisonFingerprint } from '../service/analysisService';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useResearchComparison() {
  const [items, setItems] = useState<ResearchComparisonSummary[]>([]),
    [detail, setDetail] = useState<ResearchComparison | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const alive = useRef(true),
    epoch = useRef(0),
    running = useRef(false),
    pending = useRef<{ fingerprint: string; key: string } | null>(null);
  useEffect(() => {
    alive.current = true;
    let current = true;
    const token = epoch.current;
    repo
      .loadComparisons()
      .then((v) => {
        if (current && token === epoch.current) setItems(v);
      })
      .catch((e) => {
        if (current && token === epoch.current) setError(errorMessage(e));
      });
    return () => {
      current = false;
      alive.current = false;
      epoch.current++;
    };
  }, []);
  async function load(work: () => Promise<ResearchComparison>, created = false) {
    if (running.current) return;
    running.current = true;
    const token = ++epoch.current;
    setBusy(true);
    setError('');
    setDetail(null);
    try {
      const d = await work();
      if (!alive.current || token !== epoch.current) return;
      setDetail(d);
      if (created) pending.current = null;
      const rows = await repo.loadComparisons();
      if (alive.current && token === epoch.current) setItems(rows);
    } catch (e) {
      if (alive.current && token === epoch.current) {
        setError(errorMessage(e));
        setDetail(null);
        setItems([]);
      }
    } finally {
      if (alive.current && token === epoch.current) {
        running.current = false;
        setBusy(false);
      }
    }
  }
  const active =
    detail?.comparison.jobs.some((j) => j.state === 'QUEUED' || j.state === 'RUNNING') ?? false;
  useEffect(() => {
    if (!detail) return;
    const id = detail.id,
      token = epoch.current;
    let current = true,
      polling = false;
    async function refresh() {
      if (polling || document.visibilityState !== 'visible') return;
      polling = true;
      try {
        const value = await repo.loadComparison(id);
        if (current && alive.current && token === epoch.current) setDetail(value);
      } catch (e) {
        if (current && alive.current && token === epoch.current) {
          setDetail(null);
          setItems([]);
          setError(errorMessage(e));
        }
      } finally {
        polling = false;
      }
    }
    const timer = window.setInterval(() => void refresh(), active ? 2000 : 30000);
    window.addEventListener('focus', refresh);
    return () => {
      current = false;
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
    };
  }, [detail?.id, active]);
  function create(sourceJobId: string, hashes: string[]) {
    if (running.current) return;
    const fingerprint = comparisonFingerprint(sourceJobId, hashes);
    if (pending.current?.fingerprint !== fingerprint)
      pending.current = { fingerprint, key: crypto.randomUUID() };
    const key = pending.current.key;
    void load(() => repo.createComparison(sourceJobId, hashes, key), true);
  }
  return {
    items,
    detail,
    busy,
    error,
    create,
    open: (id: string) => void load(() => repo.loadComparison(id)),
  };
}
