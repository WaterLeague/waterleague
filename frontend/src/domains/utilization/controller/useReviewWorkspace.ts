import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../../shared/exception/ApiError';
import type { CursorPage, ReviewState, StrategyReview } from '../entity/utilization';
import * as repo from '../repository/utilizationRepository';
export function useReviewWorkspace(jobId: string, onRequested: () => void) {
  const [reviews, setReviews] = useState<CursorPage<StrategyReview>>({
    items: [],
    nextCursor: null,
  });
  const [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false);
  const epoch = useRef(0),
    lock = useRef(false),
    pending = useRef<{ fingerprint: string; key: string } | null>(null);
  useEffect(() => {
    const token = ++epoch.current;
    setReviews({ items: [], nextCursor: null });
    setError('');
    setNotice('');
    void repo
      .loadReviews(jobId)
      .then((p) => {
        if (token === epoch.current) setReviews(p);
      })
      .catch((e) => {
        if (token === epoch.current) setError(errorMessage(e));
      });
    return () => {
      epoch.current++;
    };
  }, [jobId]);
  async function request(title: string, purpose: string) {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    const token = epoch.current;
    const fingerprint = JSON.stringify([jobId, title, purpose]);
    if (pending.current?.fingerprint !== fingerprint)
      pending.current = { fingerprint, key: crypto.randomUUID() };
    try {
      await repo.createRequest(jobId, title, purpose, pending.current.key);
      if (token !== epoch.current) return false;
      pending.current = null;
      setNotice('활용 동의 요청을 등록했습니다. 보낸 요청에서 상태를 확인할 수 있습니다.');
      onRequested();
      return true;
    } catch (e) {
      if (token === epoch.current) setError(errorMessage(e));
      return false;
    } finally {
      if (token === epoch.current) {
        lock.current = false;
        setBusy(false);
      }
    }
  }
  async function review(state: ReviewState, reason: string, limitations: string) {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    const token = epoch.current;
    try {
      const result = await repo.createReview(jobId, state, reason, limitations);
      if (token !== epoch.current) return false;
      setReviews((old) => ({ ...old, items: [result, ...old.items] }));
      setNotice('검토 의견을 기록했습니다. 설계 소유자에게도 표시됩니다.');
      return true;
    } catch (e) {
      if (token === epoch.current) setError(errorMessage(e));
      return false;
    } finally {
      if (token === epoch.current) {
        lock.current = false;
        setBusy(false);
      }
    }
  }
  async function more() {
    if (lock.current || !reviews.nextCursor) return;
    lock.current = true;
    setBusy(true);
    const token = epoch.current;
    try {
      const p = await repo.loadReviews(jobId, reviews.nextCursor);
      if (token === epoch.current)
        setReviews((old) => ({ ...p, items: [...old.items, ...p.items] }));
    } catch (e) {
      if (token === epoch.current) setError(errorMessage(e));
    } finally {
      if (token === epoch.current) {
        lock.current = false;
        setBusy(false);
      }
    }
  }
  return { reviews, error, notice, busy, request, review, more };
}
