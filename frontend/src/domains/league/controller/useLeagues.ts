import { useEffect, useRef, useState } from 'react';
import type { Account } from '../../account/entity/account';
import { isOrganizationMember } from '../../account/entity/account';
import type { League, LeagueDetail, OwnSubmission, LeagueDraft } from '../entity/league';
import type { Participation, ParticipationSummary } from '../entity/participation';
import type { Job } from '../../game/entity/game';
import * as repo from '../repository/leagueRepository';
import * as people from '../repository/participationRepository';
import { loadJobs } from '../../game/repository/gameRepository';
import { errorMessage } from '../../../shared/exception/ApiError';
import { useLeagueAction } from './useLeagueAction';
export function useLeagues(account: Account | null) {
  const [leagues, setLeagues] = useState<League[]>([]),
    [managed, setManaged] = useState<League[]>([]),
    [applications, setApplications] = useState<ParticipationSummary[]>([]),
    [detail, setDetail] = useState<LeagueDetail | null>(null),
    [participation, setParticipation] = useState<Participation | null>(null),
    [own, setOwn] = useState<OwnSubmission[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [loadError, setLoadError] = useState(''),
    [refresh, setRefresh] = useState(0),
    [inspecting, setInspecting] = useState(false);
  const selection = useRef(0),
    alive = useRef(true),
    selectedId = useRef<string | null>(null);
  const action = useLeagueAction();
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      selection.current++;
    };
  }, []);
  useEffect(() => {
    let current = true;
    setLoadError('');
    const failed = (e: unknown) => {
      if (current) setLoadError(errorMessage(e));
    };
    repo
      .loadLeagues()
      .then((v) => {
        if (current) setLeagues(v);
      })
      .catch(failed);
    if (isOrganizationMember(account))
      repo
        .loadLeagues(true)
        .then((v) => {
          if (current) setManaged(v);
        })
        .catch(failed);
    if (account?.memberType === 'PLAYER') {
      loadJobs()
        .then((v) => {
          if (current) setJobs(v);
        })
        .catch(failed);
      people
        .loadApplications()
        .then((v) => {
          if (current) setApplications(v);
        })
        .catch(failed);
    }
    return () => {
      current = false;
    };
  }, [account, refresh]);
  function close() {
    selection.current++;
    selectedId.current = null;
    setDetail(null);
    setOwn([]);
    setParticipation(null);
    setInspecting(false);
  }
  async function inspect(id: string) {
    const request = ++selection.current;
    if (selectedId.current !== id) {
      setDetail(null);
      setOwn([]);
      setParticipation(null);
    }
    selectedId.current = id;
    setLoadError('');
    setInspecting(true);
    try {
      const d = await repo.loadLeague(id);
      const [submitted, p] =
        account?.memberType === 'PLAYER'
          ? await Promise.all([
              repo.loadOwn(id),
              d.league.rules.participation
                ? people.loadParticipation(id, account.id)
                : Promise.resolve(null),
            ])
          : [[], null];
      if (request !== selection.current || !alive.current) return;
      setDetail(d);
      setOwn(submitted);
      setParticipation(p);
    } catch (e) {
      if (request === selection.current && alive.current) {
        setDetail(null);
        setOwn([]);
        setParticipation(null);
        setLoadError(errorMessage(e));
      }
    } finally {
      if (request === selection.current && alive.current) setInspecting(false);
    }
  }
  async function changed(id: string, hide = false) {
    setRefresh((v) => v + 1);
    if (selectedId.current === id) {
      if (hide) close();
      else await inspect(id);
    }
  }
  async function submit(jobId: string) {
    if (!detail) return;
    const l = detail.league;
    const selectionAtStart = selection.current;
    const ok = await action.run(async () => {
      await repo.submit(l.id, jobId, l.rulesHash);
      return true;
    }, '리그 기록 제출 완료. 연구 공유는 별도 동의 설정에 따릅니다.');
    if (ok && alive.current && selectionAtStart === selection.current) await changed(l.id);
  }
  async function mutation<T>(work: () => Promise<T>, message: string) {
    const result = await action.run(work, message);
    if (result !== undefined && alive.current) setRefresh((v) => v + 1);
    return result;
  }
  const save = (id: string | null, draft: LeagueDraft) =>
    mutation(
      () => repo.saveDraft(id, draft),
      '비공개 초안 저장 완료. 규칙을 검토한 후 발행하세요.'
    );
  const publish = (l: League) =>
    mutation(
      () => repo.publish(l.id, l.revision, l.rulesHash),
      '리그 발행 완료. 평가·참가 규칙이 고정되었습니다.'
    );
  const cancel = (l: League, reason: string) =>
    mutation(() => repo.cancel(l.id, reason), '리그 취소 완료. 신규 제출이 차단됩니다.');
  return {
    leagues,
    managed,
    applications,
    detail,
    participation,
    own,
    jobs,
    error: action.error || loadError,
    notice: action.notice,
    busy: action.busy,
    inspecting,
    inspect,
    close,
    changed,
    submit,
    save,
    publish,
    cancel,
    refreshLists: () => setRefresh((v) => v + 1),
    refresh: () => {
      setRefresh((v) => v + 1);
      if (selectedId.current) void inspect(selectedId.current);
    },
  };
}
