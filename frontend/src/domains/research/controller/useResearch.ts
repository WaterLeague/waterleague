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
  useEffect(() => {
    let active = true;
    setDetail(null);
    setEntries([]);
    setConsents([]);
    setError('');
    selection.current++;
    if (account && account.role === 'MEMBER') {
      repo
        .loadConsents()
        .then((v) => {
          if (active) setConsents(v);
        })
        .catch((e) => {
          if (active) setError(errorMessage(e));
        });
      if (isOrganizationMember(account))
        repo
          .loadResearch(modelHash)
          .then((v) => {
            if (active) setEntries(v);
          })
          .catch((e) => {
            if (active) setError(errorMessage(e));
          });
    }
    return () => {
      active = false;
    };
  }, [account, modelHash]);
  async function inspect(id: string) {
    const request = ++selection.current;
    setError('');
    setDetail(null);
    try {
      const d = await repo.loadResearchDetail(id);
      if (request === selection.current) {
        setDetail(d);
        setRevision(d.history.length - 1);
      }
    } catch (e) {
      if (request === selection.current) setError(errorMessage(e));
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
  return { consents, entries, detail, error, revision, setRevision, inspect, consent };
}
