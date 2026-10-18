import { useEffect, useState } from 'react';
import type { CostRecord } from '../dto/costDto';
import { loadCostRecord } from '../repository/costRepository';

export function useCostRecord(id: string) {
  const [state, setState] = useState<{ id: string; value?: CostRecord; failed?: boolean }>({ id });
  useEffect(() => {
    const controller = new AbortController();
    void loadCostRecord(id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setState({ id, value });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ id, failed: true });
      });
    return () => controller.abort();
  }, [id]);
  return state.id === id ? state : { id };
}
