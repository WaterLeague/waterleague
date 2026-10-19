import { useEffect, useRef, useState, useCallback } from 'react';
import { loadInstallations, installSite } from '../repository/installationRepository';
import type { SharedInstallation, SharedSite } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { errorMessage } from '../../../shared/exception/ApiError';
import type { SiteQuery } from '../repository/installationRepository';
import { useInstallationSites } from './useInstallationSites';
import { mapSiteQuery } from '../service/mapSitesService';
export function useInstallations(query: SiteQuery, live = true) {
  const [installations, setInstallations] = useState<SharedInstallation[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0);
  const context = useInstallationSites(mapSiteQuery(query), revision);
  const filtered = useInstallationSites(
    query,
    revision,
    !!(query.type || query.surface || query.vacant || query.offset)
  );
  const page = query.type || query.surface || query.vacant || query.offset ? filtered : context;
  const alive = useRef(false),
    loading = useRef<Promise<void> | null>(null);
  const refresh = useCallback(async (force = false) => {
    if (loading.current) {
      await loading.current;
      if (!force) return;
    }
    const request = loadInstallations().then((v) => {
      if (alive.current) {
        setInstallations((previous) =>
          JSON.stringify(previous) === JSON.stringify(v) ? previous : v
        );
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
    if (!live) return;
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
  }, [refresh, live]);
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
    sites: page.sites,
    mapSites: context.sites,
    counts: context.counts,
    matchedCount: page.matchedCount,
    siteBusy: page.busy,
    siteError: page.error || context.error,
    retrySites: () => setRevision((v) => v + 1),
    installations,
    error,
    busy,
    refresh,
    install: (site: SharedSite, type: FacilityType, area: number) =>
      mutate(() => installSite(site.districtId, site.cellId, type, area)),
  };
}
