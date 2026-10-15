import { useEffect, useRef, useState } from 'react';
import * as repo from '../repository/approvalRepository';
import type { MemberApplication, Review } from '../entity/application';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useApprovals() {
  const [status, setStatus] = useState('PENDING'),
    [rows, setRows] = useState<MemberApplication[]>([]),
    [selected, setSelected] = useState<MemberApplication | null>(null),
    [reviews, setReviews] = useState<Review[]>([]),
    [organizations, setOrganizations] = useState<{ id: string; name: string }[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(''),
    [hasMore, setHasMore] = useState(false),
    [refresh, setRefresh] = useState(0);
  const request = useRef(0),
    selection = useRef(0),
    alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      request.current++;
      selection.current++;
    };
  }, []);
  useEffect(() => {
    let active = true;
    repo
      .loadOrganizations()
      .then((v) => {
        if (active) setOrganizations(v);
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [refresh]);
  useEffect(() => {
    const current = ++request.current;
    setRows([]);
    setSelected(null);
    setReviews([]);
    selection.current++;
    setError('');
    setBusy(true);
    repo
      .loadApplications(status)
      .then((v) => {
        if (current === request.current) {
          setRows(v);
          setHasMore(v.length === 100);
        }
      })
      .catch((e) => {
        if (current === request.current) setError(errorMessage(e));
      })
      .finally(() => {
        if (current === request.current) setBusy(false);
      });
  }, [status, refresh]);
  async function inspect(member: MemberApplication) {
    setSelected(member);
    setReviews([]);
    const current = ++selection.current;
    try {
      const v = await repo.loadReviews(member.id);
      if (current === selection.current) setReviews(v);
    } catch (e) {
      if (current === selection.current) setError(errorMessage(e));
    }
  }
  async function more() {
    const current = request.current;
    setBusy(true);
    try {
      const v = await repo.loadApplications(status, rows.at(-1)?.id);
      if (current === request.current) {
        setRows((old) => [...old, ...v]);
        setHasMore(v.length === 100);
      }
    } catch (e) {
      if (current === request.current) setError(errorMessage(e));
    } finally {
      if (current === request.current) setBusy(false);
    }
  }
  async function decide(decision: string, reason: string, org: string) {
    if (!selected) return;
    setBusy(true);
    setError('');
    try {
      await repo.reviewApplication(selected.id, decision, selected.approvalStatus, reason, org);
      if (alive.current) {
        setNotice('검토 결과 저장 완료. 해당 회원의 기존 세션을 해제했습니다.');
        setRefresh((n) => n + 1);
      }
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return {
    status,
    setStatus,
    rows,
    selected,
    reviews,
    organizations,
    error,
    busy,
    notice,
    hasMore,
    inspect,
    more,
    decide,
  };
}
