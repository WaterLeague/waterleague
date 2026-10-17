import { useEffect, useState } from 'react';
import { loadWeekly } from '../repository/weeklyRepository';
import type { WeeklySnapshot } from '../dto/weeklyDto';
export function useWeekly(enabled: boolean, viewerId: string | null) {
  const [value, setValue] = useState<WeeklySnapshot | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true,
      pending = false;
    setValue(null);
    setError('');
    if (!enabled) return;
    async function refresh() {
      if (document.hidden || pending) return;
      pending = true;
      try {
        const next = await loadWeekly();
        if (active) {
          setValue(next);
          setError('');
        }
      } catch {
        if (active) setError('주간 순위를 갱신하지 못했습니다. 표시된 시각의 기록입니다.');
      } finally {
        pending = false;
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 30000);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [enabled, viewerId]);
  return { value, error };
}
