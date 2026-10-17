import { useEffect, useState } from 'react';
import type { Participation, ParticipationSummary } from '../entity/participation';
import { loadParticipation } from '../repository/participationRepository';
import { participantNames } from '../service/participationService';
import { leagueTime } from '../service/leagueService';
import { errorMessage } from '../../../shared/exception/ApiError';
import { ParticipantHistory } from './ParticipationShared';
export function LeagueApplications({
  items,
  owner,
  onSelect,
}: {
  items: ParticipationSummary[];
  owner: string;
  onSelect: (id: string) => void;
}) {
  const [history, setHistory] = useState<ParticipationSummary | null>(null);
  return (
    <section className="league-applications">
      <h2>
        내 신청·참가 이력 <small>{items.length}</small>
      </h2>
      {!items.length && (
        <p className="footnote">아직 신청한 리그가 없습니다. 공개 리그나 초대 코드로 참가하세요.</p>
      )}
      <div className="application-list">
        {items.map((p) => (
          <article key={p.leagueId}>
            <span className={'state ' + (p.state === 'APPROVED' ? 'done' : '')}>
              {participantNames[p.state]}
            </span>
            <h3>{p.title}</h3>
            <p>
              {p.organizationName} · {p.access === 'INVITE' ? '초대 전용' : '전체 공개'}
            </p>
            <small>{leagueTime(p.updatedAt)}</small>
            <div className="league-actions">
              {(p.access === 'PUBLIC' || ['PENDING', 'APPROVED'].includes(p.state)) && (
                <button className="outline-button" onClick={() => onSelect(p.leagueId)}>
                  규칙·참가 관리
                </button>
              )}
              <button className="text-button" onClick={() => setHistory(p)}>
                내 신청 이력
              </button>
            </div>
            {p.access === 'INVITE' && ['REJECTED', 'WITHDRAWN'].includes(p.state) && (
              <p className="footnote">다시 신청하려면 주최자의 현재 리그 초대 코드를 입력하세요.</p>
            )}
          </article>
        ))}
      </div>
      {history && (
        <ApplicationHistory
          key={history.leagueId + history.updatedAt}
          item={history}
          owner={owner}
          onClose={() => setHistory(null)}
        />
      )}
    </section>
  );
}
function ApplicationHistory({
  item,
  owner,
  onClose,
}: {
  item: ParticipationSummary;
  owner: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<Participation | null>(null),
    [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    loadParticipation(item.leagueId, owner)
      .then((p) => {
        if (current) setData(p);
      })
      .catch((e) => {
        if (current) setError(errorMessage(e));
      });
    return () => {
      current = false;
    };
  }, [item.leagueId, owner]);
  return (
    <section className="participation-panel">
      <div className="page-heading">
        <h3>{item.title} · 내 신청 이력</h3>
        <button className="text-button" onClick={onClose}>
          이력 닫기
        </button>
      </div>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : data ? (
        <>
          <p>
            {data.participant && participantNames[data.participant.state]} · 누적 제출{' '}
            {data.submissionCount}회
          </p>
          <ParticipantHistory events={data.events} />
        </>
      ) : (
        <p role="status">이력을 불러오는 중입니다.</p>
      )}
    </section>
  );
}
