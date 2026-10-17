import { useEffect, useState } from 'react';
import { loadPhysics } from '../repository/physicsRepository';
export function usePhysics(id: string) {
  const [value, setValue] = useState<Awaited<ReturnType<typeof loadPhysics>> | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true,
      pending = false;
    setValue(null);
    setError('');
    async function refresh() {
      if (pending || document.hidden) return;
      pending = true;
      try {
        const next = await loadPhysics(id);
        if (live) {
          setValue(next);
          setError('');
        }
      } catch {
        if (live) setError('계산 상태를 불러오지 못했습니다. 연결 후 다시 갱신됩니다.');
      } finally {
        pending = false;
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 30000);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      live = false;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [id]);
  return { value, error };
}
