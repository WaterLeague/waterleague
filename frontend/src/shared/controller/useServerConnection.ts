import { useEffect, useState, useSyncExternalStore } from 'react';
import { onBackendFailure } from '../repository/backendFetch';
import { ServerConnectionService } from '../service/ServerConnectionService';

export function useServerConnection() {
  const [service] = useState(() => new ServerConnectionService());
  const snapshot = useSyncExternalStore(
    service.subscribe,
    service.getSnapshot,
    service.getSnapshot
  );
  useEffect(() => {
    const check = () => {
      if (document.visibilityState !== 'hidden') void service.check();
    };
    const unsubscribe = onBackendFailure(service.checkAfterFailure);
    window.addEventListener('online', check);
    window.addEventListener('offline', check);
    window.addEventListener('focus', check);
    document.addEventListener('visibilitychange', check);
    service.start();
    return () => {
      service.stop();
      unsubscribe();
      window.removeEventListener('online', check);
      window.removeEventListener('offline', check);
      window.removeEventListener('focus', check);
      document.removeEventListener('visibilitychange', check);
    };
  }, [service]);
  return { ...snapshot, retry: service.check };
}
