import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../../shared/exception/ApiError';
import type { HistoricalDraft, HistoricalJob } from '../entity/historical';
import type { HistoricalSubmission } from '../entity/historicalSubmission';
import {
  listSubmissions,
  loadSubmission,
  submissionPlacements,
  submitHistorical,
} from '../repository/submissionRepository';

export function useHistoricalSubmission(
  enabled: boolean,
  owner: string | undefined,
  eventId: string
) {
  const [records, setRecords] = useState<HistoricalSubmission[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const epoch = useRef(0);
  const pending = useRef<{ fingerprint: string; key: string; jobId?: string } | null>(null);
  useEffect(() => {
    const generation = ++epoch.current;
    setRecords([]);
    setBusy(false);
    setError('');
    pending.current = null;
    if (enabled && owner && eventId)
      void listSubmissions(eventId)
        .then((v) => {
          if (epoch.current === generation)
            setRecords((old) => [...old, ...v.filter((x) => !old.some((y) => y.id === x.id))]);
        })
        .catch((e) => {
          if (epoch.current === generation) setError(errorMessage(e));
        });
    return () => {
      epoch.current++;
    };
  }, [enabled, owner, eventId]);
  useEffect(() => {
    const active = records.filter((j) => ['QUEUED', 'RUNNING'].includes(j.state));
    if (!active.length) return;
    const generation = epoch.current;
    let alive = true,
      polling = false;
    const timer = window.setInterval(async () => {
      if (polling || document.hidden) return;
      polling = true;
      try {
        const updated = await Promise.all(active.map((j) => loadSubmission(j.id)));
        if (alive && generation === epoch.current)
          setRecords((old) => old.map((j) => updated.find((v) => v.id === j.id) ?? j));
      } catch (e) {
        if (alive && generation === epoch.current) setError(errorMessage(e));
      } finally {
        polling = false;
      }
    }, 1500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [records]);
  async function submit(drafts: HistoricalDraft[], jobs: Record<string, HistoricalJob>) {
    if (!owner || busy || !drafts.length) return;
    const generation = epoch.current;
    const placements = submissionPlacements(drafts, jobs),
      fingerprint = JSON.stringify([eventId, placements]);
    if (
      pending.current?.fingerprint !== fingerprint ||
      records.some(
        (j) => j.id === pending.current?.jobId && ['FAILED', 'REJECTED'].includes(j.state)
      )
    )
      pending.current = { fingerprint, key: crypto.randomUUID() };
    const key = pending.current.key;
    setBusy(true);
    setError('');
    try {
      const next = await submitHistorical(eventId, key, placements);
      if (generation === epoch.current) {
        if (pending.current?.key === key) pending.current.jobId = next.id;
        setRecords((old) => [next, ...old.filter((j) => j.id !== next.id)]);
        if (['FAILED', 'REJECTED'].includes(next.state)) pending.current = null;
      }
    } catch (e) {
      if (generation === epoch.current) setError(errorMessage(e));
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  }
  return { records, busy, error, submit };
}
