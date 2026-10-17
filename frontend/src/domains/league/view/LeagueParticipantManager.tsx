import { useEffect, useState } from 'react';
import type { League } from '../entity/league';
import type { Participant, ParticipantEvent, ParticipantPage } from '../entity/participation';
import * as repo from '../repository/participationRepository';
import { useLeagueAction } from '../controller/useLeagueAction';
import { canRecruit, participantNames } from '../service/participationService';
import { leagueTime } from '../service/leagueService';
import { errorMessage } from '../../../shared/exception/ApiError';
import { ActionMessage, InvitationCode, ParticipantHistory } from './ParticipationShared';
export function LeagueParticipantManager({
  league,
  onInspect,
}: {
  league: League;
  onInspect: () => void;
}) {
  const [page, setPage] = useState<ParticipantPage>({ items: [], nextCursor: null }),
    [cursors, setCursors] = useState<(string | undefined)[]>([undefined]),
    [refresh, setRefresh] = useState(0),
    [selected, setSelected] = useState<Participant | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [active, setActive] = useState(false),
    [issued, setIssued] = useState('');
  const action = useLeagueAction(),
    after = cursors[cursors.length - 1],
    recruiting = canRecruit(league);
  const invite = league.rules.participation?.access === 'INVITE';
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError('');
    Promise.all([
      repo.participants(league.id, after),
      invite ? repo.invitationStatus(league.id) : Promise.resolve(null),
    ])
      .then(([p, status]) => {
        if (current) {
          setPage(p);
          setActive(status?.active ?? false);
        }
      })
      .catch((e) => {
        if (current) setError(errorMessage(e));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [league.id, after, refresh, invite]);
  return (
    <section className="league-participant-manager">
      <div className="page-heading">
        <h3>참가 운영</h3>
        <button className="outline-button" onClick={onInspect}>
          리그 규칙·순위 보기
        </button>
      </div>
      <p>
        회원가입 승인은 관리자, 이 리그의 참가 승인은 주최 조직이 담당합니다. 참가 승인은 연구 자료
        공유 동의와 별개입니다.
      </p>
      {invite && (
        <section className="league-code-management">
          <h4>리그 초대 코드</h4>
          <p>
            {active ? '현재 코드 사용 가능' : '사용 중인 코드 없음'} ·{' '}
            {leagueTime(league.rules.closesAt)}까지
          </p>
          {issued && <InvitationCode code={issued} onClose={() => setIssued('')} />}
          <div className="league-actions">
            <button
              className="outline-button"
              disabled={loading || action.busy || !recruiting}
              onClick={async () => {
                const v = await action.run(() => repo.issueInvitation(league.id));
                if (v) {
                  setIssued(v.code);
                  setRefresh((n) => n + 1);
                }
              }}
            >
              {active ? '리그 코드 교체' : '리그 코드 발급'}
            </button>
            <button
              className="text-button"
              disabled={action.busy || !active || !recruiting}
              onClick={async () => {
                const ok = await action.run(async () => {
                  await repo.revokeInvitation(league.id);
                  return true;
                }, '리그 초대 코드 폐기 완료. 기존 참가 상태는 유지됩니다.');
                if (ok) {
                  setIssued('');
                  setRefresh((n) => n + 1);
                }
              }}
            >
              리그 코드 폐기
            </button>
          </div>
          <small>새 코드를 발급하면 이전 코드는 만료됩니다. 코드 전달은 주최자가 담당합니다.</small>
        </section>
      )}
      <ActionMessage error={action.error || error} notice={action.notice} />
      <div className="page-heading">
        <h4>참가자 검토</h4>
        <button
          className="outline-button"
          disabled={loading || action.busy}
          onClick={() => {
            setSelected(null);
            setCursors([undefined]);
            setRefresh((n) => n + 1);
          }}
        >
          신청 목록 새로고침
        </button>
      </div>
      {loading && <p role="status">신청 목록을 불러오는 중입니다.</p>}
      <div className="participant-list">
        {page.items.map((p) => (
          <button
            className="participant-row"
            key={p.ownerId}
            disabled={loading}
            aria-pressed={selected?.ownerId === p.ownerId}
            onClick={() => setSelected(p)}
          >
            <b>{p.displayName}</b>
            <span>{participantNames[p.state]}</span>
            <small>{leagueTime(p.updatedAt)}</small>
          </button>
        ))}
      </div>
      {!loading && !page.items.length && (
        <p className="empty-state">이 페이지에 참가 신청이 없습니다.</p>
      )}
      <div className="league-pagination">
        <button
          className="text-button"
          disabled={loading || cursors.length === 1}
          onClick={() => {
            setSelected(null);
            setCursors((v) => v.slice(0, -1));
          }}
        >
          이전 신청 페이지
        </button>
        <span>{cursors.length}페이지 · 최대 100건</span>
        <button
          className="text-button"
          disabled={loading || !page.nextCursor}
          onClick={() => {
            setSelected(null);
            setCursors((v) => [...v, page.nextCursor ?? undefined]);
          }}
        >
          다음 신청 페이지
        </button>
      </div>
      {selected && (
        <ParticipantReview
          key={selected.ownerId + ':' + selected.revision}
          league={league}
          person={selected}
          onReviewed={() => {
            setSelected(null);
            setRefresh((n) => n + 1);
          }}
        />
      )}
    </section>
  );
}
function ParticipantReview({
  league,
  person,
  onReviewed,
}: {
  league: League;
  person: Participant;
  onReviewed: () => void;
}) {
  const [events, setEvents] = useState<ParticipantEvent[]>([]),
    [error, setError] = useState(''),
    [reason, setReason] = useState(''),
    [state, setState] = useState<'APPROVED' | 'REJECTED'>(
      person.state === 'PENDING' ? 'APPROVED' : 'REJECTED'
    );
  const action = useLeagueAction();
  useEffect(() => {
    let current = true;
    repo
      .events(league.id, person.ownerId)
      .then((v) => {
        if (current) setEvents(v);
      })
      .catch((e) => {
        if (current) setError(errorMessage(e));
      });
    return () => {
      current = false;
    };
  }, [league.id, person.ownerId]);
  const reviewable = canRecruit(league) && ['PENDING', 'APPROVED'].includes(person.state);
  return (
    <section className="participant-review">
      <h4>
        {person.displayName} · {participantNames[person.state]}
      </h4>
      <ActionMessage error={action.error || error} notice={action.notice} />
      <ParticipantHistory events={events} />
      {reviewable ? (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const result = await action.run(() =>
              repo.decide(league.id, person.ownerId, person.revision, state, reason.trim())
            );
            if (result) onReviewed();
          }}
        >
          <label>
            검토 결정
            <select
              value={state}
              onChange={(e) => setState(e.target.value as 'APPROVED' | 'REJECTED')}
              disabled={action.busy}
            >
              {person.state === 'PENDING' && <option value="APPROVED">참가 승인</option>}
              <option value="REJECTED">참가 반려</option>
            </select>
          </label>
          <label>
            검토 사유
            <textarea
              required
              maxLength={500}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="참가자에게 표시되는 사유입니다."
            />
          </label>
          {state === 'REJECTED' && (
            <p className="footnote">
              팀 소속 참가자를 반려하면 해당 팀의 제출과 순위가 중지됩니다. 재신청도 주최자 승인이
              필요합니다.
            </p>
          )}
          <button className="primary-button" disabled={action.busy || !reason.trim()}>
            검토 결과 저장
          </button>
        </form>
      ) : (
        <p className="footnote">현재 상태에서는 검토 결정을 변경할 수 없습니다.</p>
      )}
    </section>
  );
}
