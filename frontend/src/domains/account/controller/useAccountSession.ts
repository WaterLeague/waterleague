import { useEffect, useState, useSyncExternalStore } from 'react';
import { AccountSessionService } from '../service/accountSessionService';
import { onSessionExpired } from '../../../shared/repository/apiClient';

export function useAccountSession() {
  const [session] = useState(() => new AccountSessionService());
  const value = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  useEffect(() => {
    const unsubscribe = onSessionExpired(session.expire);
    void session.load();
    return unsubscribe;
  }, [session]);
  return {
    ...value,
    setAccount: session.setAccount,
    setError: session.setError,
    signOut: session.signOut,
  };
}
