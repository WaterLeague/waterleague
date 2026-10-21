import { useEffect, useState } from 'react';
import type { Budget } from '../dto/budgetDto';
import { loadBudget } from '../repository/budgetRepository';
export function useBudget(
  revision: number,
  accountId: string | null,
  competitionId?: string | null
) {
  const [value, setValue] = useState<Budget | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    setValue(null);
    let active = true,
      pending = false;
    async function refresh() {
      if (document.hidden || pending) return;
      pending = true;
      try {
        const next = await loadBudget(competitionId);
        if (active) {
          setValue(next);
          setError('');
        }
      } catch {
        if (active) setError('개인 예산을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.');
      } finally {
        pending = false;
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [revision, accountId, competitionId]);
  return { value, error };
}
