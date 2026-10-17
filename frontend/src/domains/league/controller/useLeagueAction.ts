import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useLeagueAction() {
  const epoch = useRef(0),
    alive = useRef(true),
    running = useRef(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      epoch.current++;
      running.current = false;
    };
  }, []);
  async function run<T>(work: () => Promise<T>, message = ''): Promise<T | undefined> {
    if (running.current || !alive.current) return undefined;
    running.current = true;
    const request = epoch.current;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const value = await work();
      if (!alive.current || request !== epoch.current) return undefined;
      setNotice(message);
      return value;
    } catch (e) {
      if (alive.current && request === epoch.current) setError(errorMessage(e));
      return undefined;
    } finally {
      if (alive.current && request === epoch.current) {
        running.current = false;
        setBusy(false);
      }
    }
  }
  return { busy, error, notice, run };
}
