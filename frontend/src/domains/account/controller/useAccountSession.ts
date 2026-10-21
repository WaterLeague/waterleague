import { useEffect, useState, useSyncExternalStore } from 'react';
import { AccountSessionService } from '../service/accountSessionService';
import { onSessionExpired } from '../../../shared/repository/apiClient';
import { useServerConnected } from '../../../shared/controller/serverConnectionContext';

export function useAccountSession() {
  const connected = useServerConnected();
  const [session] = useState(() => new AccountSessionService());
  const value = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  useEffect(() => {
    if (!connected) return;
    const unsubscribe = onSessionExpired(session.expire);
    void session.load();
    return unsubscribe;
  }, [session, connected]);
  return {
    ...value,
    setAccount: session.setAccount,
    setError: session.setError,
    signOut: session.signOut,
  };
}
