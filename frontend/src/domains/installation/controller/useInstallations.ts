import { useEffect, useRef, useState, useCallback } from 'react';
import { loadInstallations, loadSites, installSite } from '../repository/installationRepository';
import type { SharedInstallation, SharedSite } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { errorMessage } from '../../../shared/exception/ApiError';
import type { SiteQuery } from '../repository/installationRepository';
const NO_SITES: SharedSite[] = [];
export function useInstallations(query: SiteQuery, live = true) {
  const [sitePage, setSitePage] = useState<{ scope: string; sites: SharedSite[] }>({
      scope: '',
      sites: [],
    }),
    [installations, setInstallations] = useState<SharedInstallation[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [counts, setCounts] = useState<Record<string, number>>({}),
    [matchedCount, setMatchedCount] = useState(0),
    [siteBusy, setSiteBusy] = useState(false),
    [siteError, setSiteError] = useState(''),
    [revision, setRevision] = useState(0);
  const key = JSON.stringify(query);
  const scope = JSON.stringify([query.districtId, query.type, query.vacant, query.surface]);
  useEffect(() => {
    let disposed = false;
    const controller = new AbortController();
    setSiteBusy(true);
    setSiteError('');
    const timer = window.setTimeout(() => {
      void loadSites(JSON.parse(key) as SiteQuery, controller.signal)
        .then((page) => {
          if (!disposed) {
            setSitePage((previous) => {
              const old = new Map(
                previous.sites.map((site) => [`${site.districtId}:${site.cellId}`, site])
              );
              const sites = page.sites.map((site) => {
                const cached = old.get(`${site.districtId}:${site.cellId}`);
                return cached && JSON.stringify(cached) === JSON.stringify(site) ? cached : site;
              });
              return { scope, sites };
            });
            setCounts(page.districtCounts);
            setMatchedCount(page.matchedCount);
          }
        })
        .catch((e) => {
          if (!disposed) {
            setSitePage({ scope, sites: [] });
            setSiteError(errorMessage(e));
          }
        })
        .finally(() => {
          if (!disposed) setSiteBusy(false);
        });
    }, 250);
    return () => {
      disposed = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [key, scope, revision]);
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
    // 카메라 이동 중에는 이전 형상을 유지하되 구·시설 조건이 달라지면 즉시 숨긴다.
    sites: sitePage.scope === scope ? sitePage.sites : NO_SITES,
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
  };
}
