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
import type { SiteQuery } from '../repository/installationRepository';
export function useInstallations(query: SiteQuery) {
  const [sites, setSites] = useState<SharedSite[]>([]),
    [installations, setInstallations] = useState<SharedInstallation[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [counts, setCounts] = useState<Record<string, number>>({}),
    [matchedCount, setMatchedCount] = useState(0),
    [siteBusy, setSiteBusy] = useState(false),
    [siteError, setSiteError] = useState(''),
    [revision, setRevision] = useState(0);
  const key = JSON.stringify(query);
  useEffect(() => {
    let disposed = false;
    setSiteBusy(true);
    setSites([]);
    setSiteError('');
    const timer = window.setTimeout(() => {
      void loadSites(JSON.parse(key) as SiteQuery)
        .then((page) => {
          if (!disposed) {
            setSites(page.sites);
            setCounts(page.districtCounts);
            setMatchedCount(page.matchedCount);
          }
        })
        .catch((e) => {
          if (!disposed) setSiteError(errorMessage(e));
        })
        .finally(() => {
          if (!disposed) setSiteBusy(false);
        });
    }, 250);
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [key, revision]);
  const alive = useRef(false),
    loading = useRef<Promise<void> | null>(null);
  const refresh = useCallback(async (force = false) => {
    if (loading.current) {
      await loading.current;
      if (!force) return;
    }
    const request = loadInstallations().then((v) => {
      if (alive.current) {
        setInstallations(v);
        setError('');
      }
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
      setRevision((v) => v + 1);
      return true;
    } catch (e) {
      try {
        await refresh(true);
      } catch {}
      setError(errorMessage(e));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return {
    sites,
    counts,
    matchedCount,
    siteBusy,
    siteError,
    retrySites: () => setRevision((v) => v + 1),
    installations,
    error,
    busy,
    refresh,
    install: (site: SharedSite, type: FacilityType, area: number) =>
      mutate(() => installSite(site.districtId, site.cellId, type, area)),
    remove: (id: string) => mutate(() => removeInstallation(id)),
  };
}
