import { useEffect, useState } from 'react';
import { Plus, ArrowRight, RefreshCw, Trophy } from 'lucide-react';
import { isOrganizationMember, type Account } from '../../account/entity/account';
import type { Lab } from '../../game/entity/game';
import { facilities, format, won } from '../../game/service/gameService';
import { useLeagues } from '../controller/useLeagues';
import { eligibleJobs, leagueTime, phaseNames } from '../service/leagueService';
import type { League } from '../entity/league';
import { LeagueEditor } from './LeagueEditor';
import { LeagueRulesPanel } from './LeagueRulesPanel';
import { LeagueInviteForm } from './LeagueInviteForm';
import { LeagueApplications } from './LeagueApplications';
import { ParticipationPanel } from './ParticipationPanel';
import { LeagueParticipantManager } from './LeagueParticipantManager';
import { canSubmit } from '../service/participationService';
export function LeaguePage({
  account,
  lab,
  onDesign,
}: {
  account: Account | null;
  lab: Lab;
  onDesign: (league: League) => void;
}) {
  const l = useLeagues(account),
    [editing, setEditing] = useState<League | null | undefined>(undefined),
    [review, setReview] = useState<League | null>(null),
    [reason, setReason] = useState(''),
    [jobId, setJobId] = useState(''),
    [accepted, setAccepted] = useState(false);
  const detail = l.detail,
    selected = detail?.league,
    candidates = selected ? eligibleJobs(selected, l.jobs, l.own) : [];
  const selectedJob = candidates.some((j) => j.id === jobId) ? jobId : '';
  const eligible = selected ? canSubmit(selected, l.participation) : false;
  const used = selected?.rules.participation
    ? (l.participation?.submissionCount ?? 0)
    : l.own.length;
  function choose(id: string) {
    setJobId('');
    setAccepted(false);
    void l.inspect(id);
  }
  useEffect(() => {
    setReview((old) => (old ? (l.managed.find((v) => v.id === old.id) ?? old) : old));
  }, [l.managed]);

  return (
    <section className="full-page league-page">
      <div className="page-eyebrow">
        INSTITUTION LEAGUES <span>EXPLORATORY</span>
      </div>
      <div className="page-heading">
        <h1>하나의 질문, 함께 찾는 설계.</h1>
        <button className="outline-button" disabled={l.busy} onClick={l.refresh}>
          <RefreshCw size={15} />
          새로고침
        </button>
      </div>
      <p className="lead">주최자가 정한 예산과 시설, 같은 관측 강우 아래에서 배치를 비교합니다.</p>
      <div className="scope-note">
        <Trophy />
        <p>
          모든 현재 리그는 탐색 모델 기반입니다. 순위는 실제 공사 효과의 보증이 아니며, 기관 개설
          여부로 검증 등급이 바뀌지 않습니다.
        </p>
      </div>
      {l.error && (
        <p className="form-error" role="alert">
          {l.error}
        </p>
      )}
      {l.notice && <p role="status">{l.notice}</p>}
      {isOrganizationMember(account) && (
        <section className="league-management">
          <div className="page-heading">
            <h2>우리 조직의 리그</h2>
            <button
              className="outline-button"
              disabled={l.busy}
              onClick={() => {
                setEditing(null);
                setReview(null);
              }}
            >
              <Plus size={16} />
              리그 만들기
            </button>
          </div>
          <div className="league-managed-list">
            {l.managed.map((v) => (
              <button
                key={v.id}
                disabled={l.busy}
                aria-pressed={review?.id === v.id}
                onClick={() => {
                  setReview(v);
                  setReason('');
                  setEditing(undefined);
                }}
              >
                <b>{v.title}</b>
                <span>
                  {phaseNames[v.phase]} · {won(v.rules.budget)}
                </span>
              </button>
            ))}
          </div>
          {editing !== undefined && (
            <LeagueEditor
              key={editing?.id + ':' + editing?.revision}
              league={editing}
              lab={lab}
              busy={l.busy}
              onClose={() => setEditing(undefined)}
              onSave={async (d) => {
                const v = await l.save(editing?.id ?? null, d);
                if (v) {
                  setEditing(undefined);
                  setReview(v);
                }
              }}
            />
          )}
          {review && (
            <div className="league-review">
              <LeagueRulesPanel league={review} />
              {review.state === 'DRAFT' ? (
                <div className="league-actions">
                  <button
                    className="outline-button"
                    disabled={l.busy}
                    onClick={() => {
                      setEditing(review);
                      setReview(null);
                    }}
                  >
                    초안 수정
                  </button>
                  <button
                    className="primary-button"
                    disabled={l.busy || !review.playable}
                    onClick={async () => {
                      const v = await l.publish(review);
                      if (v) setReview(v);
                    }}
                  >
                    이 규칙으로 발행
                  </button>
                  <p>
                    발행 후에는 수정할 수 없습니다. 오류가 있으면 사유를 남겨 취소하고 새 리그를
                    만드세요.
                  </p>
                </div>
              ) : review.state === 'PUBLISHED' ? (
                <form
                  className="league-cancel"
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const v = await l.cancel(review, reason);
                    if (v) setReview(v);
                  }}
                >
                  <label>
                    취소 사유
                    <textarea
                      required
                      maxLength={500}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      rows={2}
                    />
                  </label>
                  <button
                    className="outline-button"
                    disabled={l.busy || !reason.trim()}
                    type="submit"
                  >
                    사유 기록 후 리그 취소
                  </button>
                </form>
              ) : null}
              {review.state !== 'DRAFT' && review.rules.participation && (
                <LeagueParticipantManager
                  key={review.id + ':' + review.revision}
                  league={review}
                  onInspect={() => choose(review.id)}
                />
              )}
            </div>
          )}
        </section>
      )}
      {account?.memberType === 'PLAYER' && (
        <>
          <LeagueApplications items={l.applications} owner={account.id} onSelect={choose} />
          <LeagueInviteForm
            onJoined={(id) => {
              l.refreshLists();
              choose(id);
            }}
          />
        </>
      )}
      {!account && (
        <p className="scope-note">
          공개 규칙과 순위는 누구나 볼 수 있습니다. 참가 신청과 초대 코드 확인은 로그인 후
          이용하세요.
        </p>
      )}
      <div className="league-layout">
        <div className="league-list">
          <h2>
            공개 리그 <small>{l.leagues.length}</small>
          </h2>
          {l.leagues.map((v) => (
            <button
              className="league-card"
              key={v.id}
              aria-pressed={selected?.id === v.id}
              disabled={l.busy}
              onClick={() => choose(v.id)}
            >
              <span className="state">{phaseNames[v.phase]}</span>
              <h3>{v.title}</h3>
              <p>{v.organizationName}</p>
              <strong>{won(v.rules.budget)}</strong>
              <small>{v.rules.allowedTypes.map((t) => facilities[t].name).join(' · ')}</small>
              <span className="league-card-end">
                {leagueTime(v.rules.closesAt)} 마감
                <ArrowRight size={16} />
              </span>
            </button>
          ))}
          {!l.leagues.length && (
            <div className="empty-state">
              <Trophy size={32} />
              <h3>공개된 리그가 없습니다.</h3>
              <p>승인된 기업·기관·정부 회원이 고정 규칙을 검토한 후 공개합니다.</p>
            </div>
          )}
        </div>
        <div className="league-detail">
          {selected && detail ? (
            <>
              <LeagueRulesPanel league={selected} />
              <p className="footnote">
                관측 강우 {detail.lab.model.rainfall.totalDepthMm} mm ·{' '}
                {detail.lab.model.rainfall.stationName} ·{' '}
                {leagueTime(detail.lab.model.rainfall.start)}
              </p>
              {account?.memberType === 'PLAYER' && selected.rules.participation && (
                <ParticipationPanel
                  key={selected.id}
                  league={selected}
                  data={l.participation}
                  onChanged={(hide) => l.changed(selected.id, hide)}
                />
              )}
              {selected.playable && ['OPEN', 'SCHEDULED'].includes(selected.phase) ? (
                <button className="primary-button" onClick={() => onDesign(selected)}>
                  이 조건으로 새 설계 시작 <ArrowRight size={16} />
                </button>
              ) : !selected.playable ? (
                <p className="scope-note">
                  이 리그의 모델은 현재 배포 모델과 다릅니다. 고정 조건과 기존 기록을 열람할 수
                  있습니다.
                </p>
              ) : null}
              {account?.memberType === 'PLAYER' && eligible && (
                <form
                  className="league-submit"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (selectedJob) void l.submit(selectedJob);
                  }}
                >
                  <h3>계산한 설계 제출</h3>
                  <p>
                    {selected.rules.participation?.entryMode === 'TEAM'
                      ? '팀 전체 제출'
                      : '내 제출'}{' '}
                    {used} / {selected.rules.submissionLimit}회. 리그 발행 이후 계산한 동일 모델의
                    결과를 선택하세요.
                  </p>
                  <label>
                    완료된 계산
                    <select
                      required
                      value={selectedJob}
                      onChange={(e) => {
                        setJobId(e.target.value);
                        setAccepted(false);
                      }}
                    >
                      <option value="">제출할 계산 선택</option>
                      {candidates.map((j) => (
                        <option value={j.id} key={j.id}>
                          {leagueTime(j.createdAt)} · {format.format(j.result?.score ?? 0)}점 ·{' '}
                          {j.id.slice(0, 8)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {!candidates.length && (
                    <p className="footnote">
                      아직 제출하지 않은 계산이 없습니다. 설계실에서 새 계산을 마친 뒤
                      새로고침하세요.
                    </p>
                  )}
                  <label className="league-check">
                    <input
                      type="checkbox"
                      checked={accepted}
                      onChange={(e) => setAccepted(e.target.checked)}
                    />
                    위 고정 규칙과{' '}
                    {selected.rules.participation?.entryMode === 'TEAM' ? '팀 이름' : '닉네임'}
                    ·점수·비용의{' '}
                    {selected.rules.participation?.access === 'INVITE'
                      ? '참가자 대상'
                      : '공개'}{' '}
                    순위 게시 확인
                  </label>
                  <button
                    className="outline-button"
                    disabled={
                      l.busy ||
                      !accepted ||
                      !selectedJob ||
                      used >= selected.rules.submissionLimit ||
                      l.inspecting
                    }
                    type="submit"
                  >
                    이 계산을 리그에 제출
                  </button>
                  <p className="footnote">
                    세부 기록 연구 공유는 연구실에서 별도로 동의합니다. 리그 참가만으로 연구 동의가
                    생기지 않습니다.
                  </p>
                </form>
              )}
              {account?.memberType === 'PLAYER' &&
                selected.phase === 'OPEN' &&
                !eligible &&
                selected.rules.participation && (
                  <p className="scope-note">
                    {used >= selected.rules.submissionLimit
                      ? '이 리그의 제출 한도를 모두 사용했습니다.'
                      : selected.rules.participation.entryMode === 'TEAM'
                        ? '참가 승인과 팀 구성을 확인하면 계산한 설계를 제출할 수 있습니다.'
                        : '리그에 참가하면 계산한 설계를 제출할 수 있습니다.'}
                  </p>
                )}
              <h3>리그 순위</h3>
              <div className="league-table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>순위</th>
                      <th>
                        {selected.rules.participation?.entryMode === 'TEAM' ? '팀' : '플레이어'}
                      </th>
                      <th>점수</th>
                      <th>추정 비용</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.entries.map((e, i) => (
                      <tr key={i}>
                        <td>{e.rank}</td>
                        <td>{e.displayName}</td>
                        <td>{format.format(e.score)}</td>
                        <td>{won(e.cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!detail.entries.length && (
                <p className="empty-state">
                  {detail.boardVisible === false
                    ? '초대 전용 리그의 순위는 참가 승인 후 볼 수 있습니다.'
                    : '아직 검증을 통과한 제출 기록이 없습니다.'}
                </p>
              )}
              {l.own.length > 0 && (
                <details>
                  <summary>내 제출 기록 {l.own.length}개</summary>
                  {l.own.map((e) => (
                    <p key={e.jobId}>
                      {leagueTime(e.submittedAt)} · {format.format(e.score)}점 · {won(e.cost)}
                    </p>
                  ))}
                </details>
              )}
            </>
          ) : (
            <div className="empty-state">
              <Trophy size={32} />
              <p role="status">
                {l.inspecting
                  ? '리그 정보를 불러오는 중입니다.'
                  : '리그를 선택해 규칙과 기록을 확인하세요.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
