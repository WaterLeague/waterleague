import { useEffect, useRef, useState, useCallback } from 'react';
import {
  loadInstallations,
  loadInstallationCounts,
  installSite,
} from '../repository/installationRepository';
import { countInstallations } from '../service/installationCounts';
import type { SharedInstallation, SharedSite } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { errorMessage } from '../../../shared/exception/ApiError';
import type { SiteQuery } from '../repository/installationRepository';
import { useInstallationSites } from './useInstallationSites';
import { mapSiteQuery } from '../service/mapSitesService';
export function useInstallations(query: SiteQuery, live = true, competitionId?: string | null) {
  const [installations, setInstallations] = useState<SharedInstallation[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0);
  const [ready, setReady] = useState(false);
  const [installationCounts, setInstallationCounts] = useState<Record<string, number> | null>(null);
  const context = useInstallationSites(mapSiteQuery(query), revision);
  const filtered = useInstallationSites(
    query,
    revision,
    !!(query.type || query.surface || query.vacant || query.offset)
  );
  const page = query.type || query.surface || query.vacant || query.offset ? filtered : context;
  const alive = useRef(false),
    generation = useRef(0),
    loading = useRef<Promise<void> | null>(null);
  const refresh = useCallback(
    async (force = false) => {
      const requestGeneration = generation.current;
      if (loading.current) {
        await loading.current;
        if (!force) return;
      }
      let listReceived = false;
      const current = () => alive.current && generation.current === requestGeneration;
      // 집계가 먼저 도착하면 즉시 표시하고, 상세 목록 수신 뒤에는 같은 목록의 개수를 사용한다.
      const countsRequest = loadInstallationCounts(competitionId)
        .then((counts) => {
          if (current() && !listReceived) setInstallationCounts(counts);
        })
        .catch(() => {});
      const listRequest = loadInstallations(competitionId).then((v) => {
        if (alive.current && generation.current === requestGeneration) {
          listReceived = true;
          setInstallationCounts(countInstallations(v));
          setInstallations((previous) =>
            JSON.stringify(previous) === JSON.stringify(v) ? previous : v
          );
          setError('');
          setReady(true);
        }
      });
      const request = Promise.allSettled([listRequest, countsRequest]).then(([list]) => {
        if (list.status === 'rejected') throw list.reason;
      });
      loading.current = request;
      try {
        await request;
      } finally {
        if (loading.current === request) loading.current = null;
      }
    },
    [competitionId]
  );
  useEffect(() => {
    generation.current++;
    loading.current = null;
    setInstallations([]);
    setInstallationCounts(null);
    setError('');
    setReady(false);
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
      generation.current++;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', poll);
    };
  }, [refresh, live, competitionId]);
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
    ready,
    installationCounts,
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
      mutate(() => installSite(site.districtId, site.cellId, type, area, competitionId)),
  };
}
