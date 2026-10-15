import { useRef, useState } from 'react';
import type { League } from '../entity/league';
import type { Participation, TeamPreview } from '../entity/participation';
import * as repo from '../repository/participationRepository';
import { useLeagueAction } from '../controller/useLeagueAction';
import { canRecruit, participantNames, validInvitation } from '../service/participationService';
import { leagueTime } from '../service/leagueService';
import { ActionMessage, InvitationCode, ParticipantHistory } from './ParticipationShared';
export function ParticipationPanel({
  league,
  data,
  onChanged,
}: {
  league: League;
  data: Participation | null;
  onChanged: (hide?: boolean) => Promise<void>;
}) {
  const action = useLeagueAction(),
    [accepted, setAccepted] = useState(false),
    [withdrawAccepted, setWithdrawAccepted] = useState(false);
  if (!data) return <p role="status">참가 상태를 확인하는 중입니다.</p>;
  const p = data.participant,
    rules = league.rules.participation;
  if (!rules) return null;
  const active = p && ['PENDING', 'APPROVED'].includes(p.state);
  return (
    <section className="participation-panel">
      <div className="page-heading">
        <h3>내 참가 상태</h3>
        <span className={'state ' + (p?.state === 'APPROVED' ? 'done' : '')}>
          {p ? participantNames[p.state] : '참가 전'}
        </span>
      </div>
      <ActionMessage {...action} />
      {p?.state === 'PENDING' && (
        <p>주최자의 검토를 기다리고 있습니다. 승인이 완료되면 제출할 수 있습니다.</p>
      )}
      {p?.reviewRequired && p.state !== 'APPROVED' && (
        <p>주최자 검토가 필요합니다. 다시 신청해도 자동 승인되지 않습니다.</p>
      )}
      {data.events[0]?.reason && (
        <blockquote className="review-reason">{data.events[0].reason}</blockquote>
      )}
      {!active &&
        canRecruit(league) &&
        (rules.access === 'PUBLIC' ? (
          <>
            <label className="league-check">
              <input
                type="checkbox"
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
              />
              위 고정 규칙과 참가 방식 확인. 연구 공유는 별도 동의
            </label>
            <button
              className="primary-button"
              disabled={!accepted || action.busy}
              onClick={async () => {
                const ok = await action.run(async () => {
                  await repo.join(league.id, league.rulesHash);
                  return true;
                }, '참가 요청 처리 완료. 현재 상태를 확인하세요.');
                if (ok) {
                  setAccepted(false);
                  await onChanged();
                }
              }}
            >
              {rules.admission === 'APPROVAL' || p?.reviewRequired
                ? '참가 승인 신청'
                : '이 리그에 참가'}
            </button>
          </>
        ) : (
          <p>참가 신청은 주최자의 현재 리그 초대 코드로 진행하세요.</p>
        ))}
      {p?.state === 'APPROVED' && rules.entryMode === 'TEAM' && (
        <TeamPanel league={league} data={data} onChanged={onChanged} />
      )}
      {data.team && p?.state !== 'APPROVED' && (
        <p>
          기존 팀 ‘{data.team.name}’과 누적 제출 횟수가 보존됩니다. 재승인 시 같은 팀으로
          복귀합니다.
        </p>
      )}
      <ParticipantHistory events={data.events} />
      {active && (
        <details className="participation-withdraw">
          <summary>리그 참가 철회</summary>
          <p>
            {data.team
              ? '참가를 철회하면 팀 전체의 신규 제출과 순위 표시가 중지됩니다. 첫 제출 뒤 고정된 팀 구성과 누적 횟수는 유지됩니다.'
              : '철회하면 순위에서 제외됩니다. 기존 제출 이력과 누적 횟수는 삭제되지 않습니다.'}
          </p>
          <label className="league-check">
            <input
              type="checkbox"
              checked={withdrawAccepted}
              onChange={(e) => setWithdrawAccepted(e.target.checked)}
            />
            참가 철회의 영향 확인
          </label>
          <button
            className="outline-button"
            disabled={action.busy || !withdrawAccepted}
            onClick={async () => {
              const ok = await action.run(async () => {
                await repo.withdraw(league.id, p.revision);
                return true;
              }, '참가 철회 완료. 신청 이력은 보존됩니다.');
              if (ok) {
                setWithdrawAccepted(false);
                await onChanged(rules.access === 'INVITE');
              }
            }}
          >
            리그 참가 철회 확정
          </button>
        </details>
      )}
    </section>
  );
}
function TeamPanel({
  league,
  data,
  onChanged,
}: {
  league: League;
  data: Participation;
  onChanged: () => Promise<void>;
}) {
  const action = useLeagueAction(),
    [name, setName] = useState(''),
    [code, setCode] = useState(''),
    [preview, setPreview] = useState<TeamPreview | null>(null),
    [issued, setIssued] = useState(''),
    [accepted, setAccepted] = useState(false),
    [leaving, setLeaving] = useState(false);
  const generation = useRef(0),
    team = data.team,
    recruiting = canRecruit(league);
  return (
    <section className="team-panel">
      <h4>{team ? team.name : '함께 도전할 팀'}</h4>
      <ActionMessage {...action} />
      {issued && <InvitationCode code={issued} onClose={() => setIssued('')} />}
      {team ? (
        <>
          <p>
            팀 전체 제출 {team.submissionCount} / {league.rules.submissionLimit}회 · 최고 점수 반영
          </p>
          <ul className="team-members">
            {team.members.map((m, i) => (
              <li key={i}>
                <b>
                  {m.displayName}
                  {m.self ? ' (나)' : ''}
                </b>
                <span>
                  {m.captain ? '팀장' : '팀원'} · {m.eligible ? '참가 가능' : '참가 불가'}
                </span>
              </li>
            ))}
          </ul>
          {!team.eligible && (
            <p className="form-error">
              참가 불가 상태인 팀원이 있습니다. 모두 참가 가능한 상태가 되면 팀 제출과 순위가
              복원됩니다.
            </p>
          )}
          {team.frozenAt ? (
            <p className="scope-note">
              {leagueTime(team.frozenAt)} 첫 제출 이후 팀 구성이 고정되었습니다.
            </p>
          ) : (
            <>
              {team.captain && recruiting && (
                <div className="team-invitation">
                  <p>
                    {team.invitationActive
                      ? '팀 초대 코드 사용 가능'
                      : '사용 중인 팀 초대 코드 없음'}
                  </p>
                  <div className="league-actions">
                    <button
                      className="outline-button"
                      disabled={action.busy}
                      onClick={async () => {
                        const v = await action.run(() => repo.issueTeamInvitation(league.id));
                        if (v) {
                          setIssued(v.code);
                          await onChanged();
                        }
                      }}
                    >
                      {team.invitationActive ? '팀 코드 교체' : '팀 코드 발급'}
                    </button>
                    <button
                      className="text-button"
                      disabled={action.busy || !team.invitationActive}
                      onClick={async () => {
                        const ok = await action.run(async () => {
                          await repo.revokeTeamInvitation(league.id);
                          return true;
                        }, '팀 코드 폐기 완료. 기존 팀원은 유지됩니다.');
                        if (ok) {
                          setIssued('');
                          await onChanged();
                        }
                      }}
                    >
                      팀 코드 폐기
                    </button>
                  </div>
                  <small>
                    교체하면 이전 코드를 사용할 수 없습니다. 팀 가입에는 별도 리그 참가 승인이
                    필요합니다.
                  </small>
                </div>
              )}
              {recruiting && (
                <div className="team-leave">
                  <button
                    className="text-button"
                    disabled={action.busy || (team.captain && team.members.length > 1)}
                    onClick={() => setLeaving((v) => !v)}
                  >
                    {team.captain ? '팀 해산' : '팀에서 나가기'}
                  </button>
                  {team.captain && team.members.length > 1 && (
                    <p className="footnote">팀장은 다른 팀원이 모두 나간 뒤 해산할 수 있습니다.</p>
                  )}
                  {leaving && (
                    <div>
                      <p>첫 제출 전 팀 소속을 해제합니다. 리그 참가 승인은 유지됩니다.</p>
                      <button
                        className="outline-button"
                        disabled={action.busy}
                        onClick={async () => {
                          const ok = await action.run(async () => {
                            await repo.leaveTeam(league.id);
                            return true;
                          }, '팀 소속 해제 완료');
                          if (ok) {
                            setLeaving(false);
                            setIssued('');
                            await onChanged();
                          }
                        }}
                      >
                        {team.captain ? '팀 해산 확정' : '팀 탈퇴 확정'}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </>
      ) : recruiting ? (
        <>
          <p>
            각자 계산한 설계를 한 팀으로 제출합니다. 팀 전체 제출 한도를 공유하며, 첫 제출 후에는
            팀원을 바꿀 수 없습니다.
          </p>
          <label className="league-check">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
            />
            팀 공유 한도·첫 제출 이후 구성 고정 확인
          </label>
          <form
            className="team-create"
            onSubmit={async (e) => {
              e.preventDefault();
              const v = await action.run(
                () => repo.createTeam(league.id, name.trim()),
                '팀 생성 완료'
              );
              if (v) {
                setIssued(v.code);
                setName('');
                await onChanged();
              }
            }}
          >
            <label>
              새 팀 이름
              <input
                value={name}
                maxLength={60}
                required
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button className="outline-button" disabled={action.busy || !name.trim() || !accepted}>
              팀 만들기
            </button>
          </form>
          <form
            className="invitation-input"
            onSubmit={async (e) => {
              e.preventDefault();
              const revision = generation.current;
              const v = await action.run(() => repo.previewTeam(league.id, code.trim()));
              if (v && revision === generation.current) setPreview(v);
            }}
          >
            <label>
              팀 초대 코드
              <input
                value={code}
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                maxLength={43}
                onChange={(e) => {
                  generation.current++;
                  setCode(e.target.value);
                  setPreview(null);
                }}
              />
            </label>
            <button
              className="outline-button"
              disabled={action.busy || !validInvitation(code.trim())}
            >
              초대 팀 확인
            </button>
          </form>
          {preview && (
            <div className="team-preview">
              <strong>{preview.name}</strong>
              <p>
                {preview.memberCount} / {preview.teamSizeLimit}명
              </p>
              <button
                className="primary-button"
                disabled={action.busy || !accepted || preview.memberCount >= preview.teamSizeLimit}
                onClick={async () => {
                  const revision = generation.current;
                  const ok = await action.run(async () => {
                    await repo.joinTeam(league.id, code.trim(), preview.id, preview.rulesHash);
                    return true;
                  }, '팀 가입 완료');
                  if (ok && revision === generation.current) {
                    generation.current++;
                    setCode('');
                    setPreview(null);
                    await onChanged();
                  }
                }}
              >
                이 팀에 가입
              </button>
            </div>
          )}
        </>
      ) : (
        <p>현재 팀 구성 기간이 아닙니다.</p>
      )}
    </section>
  );
}
