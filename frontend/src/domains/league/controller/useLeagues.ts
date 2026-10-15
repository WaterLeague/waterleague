import { useEffect, useRef, useState } from 'react';
import type { Account } from '../../account/entity/account';
import { isOrganizationMember } from '../../account/entity/account';
import type { League, LeagueDetail, OwnSubmission, LeagueDraft } from '../entity/league';
import type { Job } from '../../game/entity/game';
import * as repo from '../repository/leagueRepository';
import { loadJobs } from '../../game/repository/gameRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
export function useLeagues(account: Account | null) {
  const [leagues, setLeagues] = useState<League[]>([]),
    [managed, setManaged] = useState<League[]>([]),
    [detail, setDetail] = useState<LeagueDetail | null>(null),
    [own, setOwn] = useState<OwnSubmission[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false),
    [refresh, setRefresh] = useState(0);
  const selection = useRef(0),
    alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      selection.current++;
    };
  }, []);
  useEffect(() => {
    let current = true;
    setError('');
    repo
      .loadLeagues()
      .then((v) => {
        if (current) setLeagues(v);
      })
      .catch((e) => {
        if (current) setError(errorMessage(e));
      });
    if (isOrganizationMember(account))
      repo
        .loadLeagues(true)
        .then((v) => {
          if (current) setManaged(v);
        })
        .catch((e) => {
          if (current) setError(errorMessage(e));
        });
    if (account?.role === 'MEMBER')
      loadJobs()
        .then((v) => {
          if (current) setJobs(v);
        })
        .catch((e) => {
          if (current) setError(errorMessage(e));
        });
    return () => {
      current = false;
    };
  }, [account, refresh]);
  async function inspect(id: string) {
    const request = ++selection.current;
    setDetail(null);
    setOwn([]);
    setError('');
    try {
      const d = await repo.loadLeague(id);
      if (request !== selection.current) return;
      setDetail(d);
      if (account?.role === 'MEMBER') {
        const submitted = await repo.loadOwn(id);
        if (request === selection.current) setOwn(submitted);
      }
    } catch (e) {
      if (request === selection.current) setError(errorMessage(e));
    }
  }
  async function action<T>(work: () => Promise<T>, message: string) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const value = await work();
      if (alive.current) {
        setNotice(message);
        setRefresh((v) => v + 1);
      }
      return value;
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
      return undefined;
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function submit(jobId: string) {
    if (!detail) return;
    const l = detail.league;
    const ok = await action(async () => {
      await repo.submit(l.id, jobId, l.rulesHash);
      return true;
    }, '리그 기록 제출 완료. 연구 공유는 별도 동의 설정에 따릅니다.');
    if (ok && alive.current) await inspect(l.id);
  }
  const save = (id: string | null, draft: LeagueDraft) =>
    action(() => repo.saveDraft(id, draft), '비공개 초안 저장 완료. 규칙을 검토한 후 공개하세요.');
  const publish = (l: League) =>
    action(
      () => repo.publish(l.id, l.revision, l.rulesHash),
      '리그 공개 완료. 평가 규칙이 고정되었습니다.'
    );
  const cancel = (l: League, reason: string) =>
    action(() => repo.cancel(l.id, reason), '리그 취소 완료. 신규 제출이 차단됩니다.');
  return {
    leagues,
    managed,
    detail,
    own,
    jobs,
    error,
    notice,
    busy,
    inspect,
    submit,
    save,
    publish,
    cancel,
    refresh: () => {
      setRefresh((n) => n + 1);
      if (detail) void inspect(detail.league.id);
    },
  };
}
