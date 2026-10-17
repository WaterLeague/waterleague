import { useEffect, useRef, useState, useCallback } from 'react';
import {
  loadInstallations,
  loadSites,
  installSite,
  removeInstallation,
} from '../repository/installationRepository';
import type { SharedInstallation, SharedSite } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useInstallations() {
  const [sites, setSites] = useState<SharedSite[]>([]),
    [installations, setInstallations] = useState<SharedInstallation[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const alive = useRef(false),
    loading = useRef<Promise<void> | null>(null);
  const refresh = useCallback(async (force = false) => {
    if (loading.current) {
      await loading.current;
      if (!force) return;
    }
    const request = loadInstallations().then((v) => {
      if (alive.current) setInstallations(v);
    });
    loading.current = request;
    try {
      await request;
    } finally {
      if (loading.current === request) loading.current = null;
    }
  }, []);
  useEffect(() => {
    alive.current = true;
    let disposed = false;
    void loadSites()
      .then((v) => {
        if (!disposed) setSites(v);
      })
      .catch((e) => {
        if (!disposed) setError(errorMessage(e));
      });
    const poll = () => {
      if (!document.hidden)
        void refresh().catch((e) => {
          if (!disposed) setError(errorMessage(e));
        });
    };
    poll();
    const timer = window.setInterval(poll, 15000);
    document.addEventListener('visibilitychange', poll);
    return () => {
      disposed = true;
      alive.current = false;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', poll);
    };
  }, [refresh]);
  const mutate = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError('');
    try {
      await action();
      await refresh(true);
      return true;
    } catch (e) {
      setError(errorMessage(e));
      try {
        await refresh(true);
      } catch {}
      return false;
    } finally {
      setBusy(false);
    }
  };
  return {
    sites,
    installations,
    error,
    busy,
    refresh,
    install: (site: SharedSite, type: FacilityType, area: number) =>
      mutate(() => installSite(site.districtId, site.cellId, type, area)),
    remove: (id: string) => mutate(() => removeInstallation(id)),
  };
}
