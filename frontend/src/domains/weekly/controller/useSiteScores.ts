import { useState, useEffect } from 'react';
import { loadSiteScores } from '../repository/weeklyRepository';
import type { SiteScoresPage } from '../dto/siteScoresDto';
export function useSiteScores(district: string, cell: string) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const cursor = cursors[cursors.length - 1];
  const [value, setValue] = useState<SiteScoresPage | null>(null),
    [error, setError] = useState('');
  useEffect(() => {
    let active = true,
      pending = false;
    const controller = new AbortController();
    setValue(null);
    setError('');
    async function refresh() {
      if (document.hidden || pending) return;
      pending = true;
      try {
        const next = await loadSiteScores(district, cell, cursor, controller.signal);
        if (active) {
          setValue(next);
          setError('');
        }
      } catch {
        if (active) setError('시설 점수를 갱신하지 못했습니다. 마지막 확인 기록입니다.');
      } finally {
        pending = false;
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      active = false;
      controller.abort();
      clearInterval(timer);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [district, cell, cursor]);
  return {
    value,
    error,
    hasPrevious: cursors.length > 1,
    previous: () => setCursors((v) => (v.length > 1 ? v.slice(0, -1) : v)),
    next: () => {
      if (value?.nextAfterId) setCursors((v) => [...v, value.nextAfterId]);
    },
  };
}
