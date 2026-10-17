import { useEffect, useRef, useState } from 'react';
import type { SharedRecords, SharedDetail, SharedConsent } from '../dto/sharedResearchDto';
import * as repo from '../repository/sharedResearchRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
export function currentWeek() {
  const day = new Date(Date.now() + 9 * 3600000);
  day.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7));
  return day.toISOString().slice(0, 10);
}
export function useSharedResearch(actor: string, institution: boolean, week: string) {
  const [records, setRecords] = useState<SharedRecords | null>(null),
    [detail, setDetail] = useState<SharedDetail | null>(null),
    [consents, setConsents] = useState<SharedConsent[]>([]),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true),
    [saving, setSaving] = useState(false);
  const scopeKey = `${actor}:${institution}:${week}`;
  const [loadedScope, setLoadedScope] = useState(scopeKey);
  const selected = useRef<string | null>(null),
    selection = useRef(0),
    life = useRef(0),
    refreshRef = useRef(() => {});
  useEffect(() => {
    const generation = ++life.current;
    let active = true,
      epoch = 0,
      busy = false;
    selection.current++;
    selected.current = null;
    setRecords(null);
    setDetail(null);
    setConsents([]);
    setError('');
    setLoading(true);
    setSaving(false);
    setLoadedScope(`${actor}:${institution}:${week}`);
    async function refresh(hide = false) {
      if (!active || (busy && !hide) || document.visibilityState !== 'visible') return;
      const token = ++epoch,
        id = selected.current,
        pick = selection.current;
      busy = true;
      if (hide) {
        setRecords(null);
        setDetail(null);
      }
      try {
        const [list, sharing, record] = await Promise.all([
          repo.loadRecords(institution, week),
          repo.loadConsents(),
          id ? repo.loadDetail(institution, id) : Promise.resolve(null),
        ]);
        if (!active || generation !== life.current || token !== epoch) return;
        setRecords(list);
        setConsents(sharing);
        setError('');
        if (pick === selection.current && id === selected.current) setDetail(record);
      } catch (e) {
        if (active && token === epoch) {
          selection.current++;
          selected.current = null;
          setRecords(null);
          setDetail(null);
          setError(errorMessage(e));
        }
      } finally {
        if (active && token === epoch) {
          busy = false;
          setLoading(false);
        }
      }
    }
    const revisit = () => {
      selection.current++;
      void refresh(true);
    };
    const visibility = () => {
      if (document.visibilityState === 'visible') revisit();
      else {
        epoch++;
        selection.current++;
        busy = false;
        setRecords(null);
        setDetail(null);
      }
    };
    refreshRef.current = revisit;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30000);
    window.addEventListener('focus', revisit);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      active = false;
      life.current++;
      selection.current++;
      window.clearInterval(timer);
      window.removeEventListener('focus', revisit);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [actor, institution, week]);
  async function inspect(id: string) {
    const token = ++selection.current,
      generation = life.current;
    selected.current = id;
    setDetail(null);
    setError('');
    try {
      const next = await repo.loadDetail(institution, id);
      if (token === selection.current && generation === life.current) setDetail(next);
    } catch (e) {
      if (token === selection.current && generation === life.current) {
        setError(errorMessage(e));
        selected.current = null;
      }
    }
  }
  async function consent(id: string, granted: boolean) {
    const generation = life.current;
    setSaving(true);
    try {
      await repo.setConsent(id, granted);
      const next = await repo.loadConsents();
      if (generation === life.current) {
        setConsents(next);
        setError('');
        refreshRef.current();
      }
    } catch (e) {
      if (generation === life.current) setError(errorMessage(e));
    } finally {
      if (generation === life.current) setSaving(false);
    }
  }
  return {
    records: loadedScope === scopeKey ? records : null,
    detail: loadedScope === scopeKey ? detail : null,
    consents,
    error,
    loading,
    saving,
    inspect,
    consent,
    refresh: () => refreshRef.current(),
  };
}
