import { useEffect, useState } from 'react';
import { loadSites, type SiteQuery } from '../repository/installationRepository';
import { siteKey, type SharedSite } from '../entity/installation';
import { errorMessage } from '../../../shared/exception/ApiError';
const NO_SITES: SharedSite[] = [];

export function useInstallationSites(query: SiteQuery, revision: number, enabled = true) {
  const [page, setPage] = useState({
    scope: '',
    sites: NO_SITES,
    counts: {} as Record<string, number>,
    matchedCount: 0,
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const key = JSON.stringify(query);
  const scope = JSON.stringify([query.districtId, query.type, query.vacant, query.surface]);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setBusy(true);
    setError('');
    const timer = window.setTimeout(() => {
      void loadSites(JSON.parse(key) as SiteQuery, controller.signal)
        .then((value) => {
          if (controller.signal.aborted) return;
          setPage((previous) => {
            const old = new Map(previous.sites.map((site) => [siteKey(site), site]));
            const sites = value.sites.map((site) => {
              const cached = old.get(siteKey(site));
              return cached && JSON.stringify(cached) === JSON.stringify(site) ? cached : site;
            });
            return { scope, sites, counts: value.districtCounts, matchedCount: value.matchedCount };
          });
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(errorMessage(e));
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [key, scope, revision, enabled]);
  // 같은 구의 이동·재조회 중에는 마지막 검증 형상을 유지한다.
  return { ...page, sites: enabled && page.scope === scope ? page.sites : NO_SITES, busy, error };
}
