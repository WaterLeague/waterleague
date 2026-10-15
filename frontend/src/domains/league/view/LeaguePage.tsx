import { useState } from 'react';
import { Plus, ArrowRight, RefreshCw, Trophy } from 'lucide-react';
import { isOrganizationMember, type Account } from '../../account/entity/account';
import type { Lab } from '../../game/entity/game';
import { facilities, format, won } from '../../game/service/gameService';
import { useLeagues } from '../controller/useLeagues';
import { eligibleJobs, leagueTime, phaseNames } from '../service/leagueService';
import type { League } from '../entity/league';
import { LeagueEditor } from './LeagueEditor';
import { LeagueRulesPanel } from './LeagueRulesPanel';
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
    candidates = selected ? eligibleJobs(selected, l.jobs) : [];
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
                    이 규칙으로 공개
                  </button>
                  <p>
                    공개 후에는 수정할 수 없습니다. 오류가 있으면 사유를 남겨 취소하고 새 리그를
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
            </div>
          )}
        </section>
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
              onClick={() => {
                setJobId('');
                setAccepted(false);
                void l.inspect(v.id);
              }}
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
              {account?.memberType === 'PLAYER' && selected.phase === 'OPEN' && (
                <form
                  className="league-submit"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void l.submit(jobId);
                  }}
                >
                  <h3>계산한 설계 제출</h3>
                  <p>
                    내 제출 {l.own.length} / {selected.rules.submissionLimit}회. 리그 공개 이후
                    계산한 동일 모델의 결과를 선택하세요.
                  </p>
                  <label>
                    완료된 계산
                    <select required value={jobId} onChange={(e) => setJobId(e.target.value)}>
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
                    <p className="footnote">설계실에서 저장·계산을 마친 뒤 새로고침하세요.</p>
                  )}
                  <label className="league-check">
                    <input
                      type="checkbox"
                      checked={accepted}
                      onChange={(e) => setAccepted(e.target.checked)}
                    />
                    위 고정 규칙과 공개 닉네임·점수·비용의 순위 게시 확인
                  </label>
                  <button
                    className="outline-button"
                    disabled={
                      l.busy ||
                      !accepted ||
                      !jobId ||
                      l.own.length >= selected.rules.submissionLimit
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
              <h3>리그 순위</h3>
              <div className="league-table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>순위</th>
                      <th>플레이어</th>
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
                <p className="empty-state">아직 검증을 통과한 제출 기록이 없습니다.</p>
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
              <p>리그를 선택해 규칙과 기록을 확인하세요.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
