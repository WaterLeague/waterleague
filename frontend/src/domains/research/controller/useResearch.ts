import { useEffect, useState, useRef } from 'react';
import { isOrganizationMember, type Account } from '../../account/entity/account';
import type { Consent, ResearchEntry, ResearchDetail } from '../entity/research';
import * as repo from '../repository/researchRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useResearch(account: Account | null, modelHash: string) {
  const [consents, setConsents] = useState<Consent[]>([]),
    [entries, setEntries] = useState<ResearchEntry[]>([]),
    [detail, setDetail] = useState<ResearchDetail | null>(null),
    [error, setError] = useState(''),
    [revision, setRevision] = useState(0);
  const owner = useRef(account?.id);
  owner.current = account?.id;
  const selection = useRef(0);
  const detailId = useRef<string | null>(null);
  const refreshAccess = useRef<() => void>(() => {});
  useEffect(() => {
    let active = true;
    let epoch = 0,
      fetching = false;
    setDetail(null);
    setEntries([]);
    setConsents([]);
    setError('');
    selection.current++;
    detailId.current = null;
    async function refresh(hide = false) {
      if (!account || account.role !== 'MEMBER' || (fetching && !hide)) return;
      const token = ++epoch,
        id = detailId.current;
      if (hide) {
        selection.current++;
        setDetail(null);
        setEntries([]);
      }
      const selected = selection.current;
      fetching = true;
      try {
        const [sharing, rows, current] = await Promise.all([
          repo.loadConsents(),
          isOrganizationMember(account) ? repo.loadResearch(modelHash) : Promise.resolve([]),
          isOrganizationMember(account) && id ? repo.loadResearchDetail(id) : Promise.resolve(null),
        ]);
        if (!active || token !== epoch) return;
        setConsents(sharing);
        setEntries(rows);
        setError('');
        if (selected === selection.current && id === detailId.current) {
          setDetail(current);
          if (current) setRevision((v) => Math.min(v, current.history.length - 1));
        }
      } catch (e) {
        if (active && token === epoch) {
          selection.current++;
          setEntries([]);
          setDetail(null);
          setError(errorMessage(e));
          detailId.current = null;
        }
      } finally {
        if (token === epoch) fetching = false;
      }
    }
    const revisit = () => void refresh(true);
    const visibility = () => {
      if (document.visibilityState === 'visible') revisit();
      else {
        epoch++;
        fetching = false;
        selection.current++;
        setEntries([]);
        setDetail(null);
      }
    };
    refreshAccess.current = revisit;
    void refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh();
    }, 30000);
    window.addEventListener('focus', revisit);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      active = false;
      epoch++;
      window.clearInterval(timer);
      window.removeEventListener('focus', revisit);
      document.removeEventListener('visibilitychange', visibility);
      if (refreshAccess.current === revisit) refreshAccess.current = () => {};
    };
  }, [account, modelHash]);
  async function inspect(id: string) {
    const request = ++selection.current;
    detailId.current = id;
    setError('');
    setDetail(null);
    try {
      const d = await repo.loadResearchDetail(id);
      if (request === selection.current) {
        setDetail(d);
        setRevision(d.history.length - 1);
      }
    } catch (e) {
      if (request === selection.current) {
        setError(errorMessage(e));
        detailId.current = null;
      }
    }
  }
  async function consent(id: string, value: boolean) {
    const identity = owner.current;
    try {
      await repo.setConsent(id, value);
      const next = await repo.loadConsents();
      if (identity === owner.current) setConsents(next);
    } catch (e) {
      if (identity === owner.current) setError(errorMessage(e));
    }
  }
  return {
    consents,
    entries,
    detail,
    error,
    revision,
    setRevision,
    inspect,
    consent,
    refreshAccess: () => refreshAccess.current(),
  };
}
