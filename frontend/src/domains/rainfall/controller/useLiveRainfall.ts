import { useCallback, useEffect, useRef, useState } from 'react';
import type { LiveRainfall } from '../entity/liveRainfall';
import { loadLiveRainfall } from '../repository/liveRainfallRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useLiveRainfall() {
  const [value, setValue] = useState<LiveRainfall | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [now, setNow] = useState(Date.now());
  const alive = useRef(false),
    pending = useRef<number | null>(null),
    generation = useRef(0);
  const refresh = useCallback(async () => {
    if (pending.current !== null || document.hidden || !alive.current) return;
    const epoch = generation.current;
    pending.current = epoch;
    setBusy(true);
    setError('');
    try {
      const v = await loadLiveRainfall();
      if (alive.current && epoch === generation.current) setValue(v);
    } catch (e) {
      if (alive.current && epoch === generation.current) {
        setValue(null);
        setError(errorMessage(e));
      }
    } finally {
      if (pending.current === epoch) pending.current = null;
      if (alive.current && epoch === generation.current) {
        setBusy(false);
        setNow(Date.now());
      }
    }
  }, []);
  useEffect(() => {
    alive.current = true;
    generation.current++;
    pending.current = null;
    void refresh();
    const timer = window.setInterval(() => {
      setNow(Date.now());
      void refresh();
    }, 60000);
    const visible = () => {
      setNow(Date.now());
      if (!document.hidden) void refresh();
    };
    document.addEventListener('visibilitychange', visible);
    return () => {
      alive.current = false;
      generation.current++;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [refresh]);
  return { value, busy, error, now, refresh };
}
