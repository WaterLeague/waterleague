import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../../shared/exception/ApiError';
import type {
  CursorPage,
  Decision,
  RequestDetail,
  StrategyReview,
  UtilizationRequest,
} from '../entity/utilization';
import * as repo from '../repository/utilizationRepository';
type ListKind = 'received' | 'sent' | 'reviews';
const empty = <T>(): CursorPage<T> => ({ items: [], nextCursor: null });
export function useUtilizationInbox(accountId: string, institution: boolean, refresh: number) {
  const [received, setReceived] = useState(empty<UtilizationRequest>());
  const [sent, setSent] = useState(empty<UtilizationRequest>());
  const [reviews, setReviews] = useState(empty<StrategyReview>());
  const [selected, setSelected] = useState<{ detail: RequestDetail; own: boolean } | null>(null);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const epoch = useRef(0),
    lock = useRef(false),
    choice = useRef(0);
  useEffect(() => {
    const token = ++epoch.current;
    lock.current = false;
    setBusy(false);
    setError('');
    setSelected(null);
    setReceived(empty());
    setSent(empty());
    setReviews(empty());
    void Promise.all([
      repo.loadRequests(false),
      repo.loadReviews(),
      institution ? repo.loadRequests(true) : Promise.resolve(empty<UtilizationRequest>()),
    ])
      .then(([mine, notes, outgoing]) => {
        if (epoch.current === token) {
          setReceived(mine);
          setReviews(notes);
          setSent(outgoing);
        }
      })
      .catch((e) => {
        if (epoch.current === token) setError(errorMessage(e));
      });
    return () => {
      epoch.current++;
    };
  }, [accountId, institution, refresh]);
  async function open(id: string, own: boolean) {
    if (lock.current) return;
    const token = epoch.current,
      request = ++choice.current;
    setError('');
    setSelected(null);
    try {
      const detail = await repo.loadRequest(id);
      if (token === epoch.current && request === choice.current) setSelected({ detail, own });
    } catch (e) {
      if (token === epoch.current && request === choice.current) setError(errorMessage(e));
    }
  }
  async function decide(decision: Decision) {
    if (!selected?.own || lock.current) return;
    const token = epoch.current,
      r = selected.detail.request;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await repo.decideRequest(r, decision),
        detail = await repo.loadRequest(r.id);
      if (token === epoch.current) {
        setReceived((p) => ({
          ...p,
          items: p.items.map((v) => (v.id === result.id ? result : v)),
        }));
        setSelected({ detail, own: true });
      }
    } catch (e) {
      if (token === epoch.current) setError(errorMessage(e));
      try {
        const detail = await repo.loadRequest(r.id);
        if (token === epoch.current) setSelected({ detail, own: true });
      } catch {
        /* 접근 철회 시 기존 오류 유지 */
      }
    } finally {
      if (token === epoch.current) {
        lock.current = false;
        setBusy(false);
      }
    }
  }
  async function more(kind: ListKind) {
    if (lock.current) return;
    const cursor = { received, sent, reviews }[kind].nextCursor;
    if (!cursor) return;
    const token = epoch.current;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      if (kind === 'reviews') {
        const p = await repo.loadReviews(undefined, cursor);
        if (token === epoch.current)
          setReviews((old) => ({ ...p, items: [...old.items, ...p.items] }));
      } else {
        const p = await repo.loadRequests(kind === 'sent', cursor);
        if (token === epoch.current)
          (kind === 'sent' ? setSent : setReceived)((old) => ({
            ...p,
            items: [...old.items, ...p.items],
          }));
      }
    } catch (e) {
      if (token === epoch.current) setError(errorMessage(e));
    } finally {
      if (token === epoch.current) {
        lock.current = false;
        setBusy(false);
      }
    }
  }
  return { received, sent, reviews, selected, busy, error, open, decide, more };
}
