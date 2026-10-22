import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, RefreshCw } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type {
  Competition,
  CompetitionCandidates,
  CompetitionCatalog,
  CompetitionResults as Results,
} from '../dto/competitionDto';
import {
  cancelCompetition,
  joinCompetition,
  loadCompetition,
  loadCompetitionCandidates,
  loadCompetitionResults,
  submitCompetition,
} from '../repository/competitionRepository';
import { followLink } from '../../../shared/controller/useAppLocation';
import { errorMessage } from '../../../shared/exception/ApiError';
import { facilities, won } from '../../game/service/gameService';
import { CompetitionResults } from './CompetitionResults';
import { GameAnalysisPanel } from '../../gameanalysis/view/GameAnalysisPanel';
import { competitionTime, phaseNames } from './CompetitionShared';
const jobNames: Record<string, string> = {
  QUEUED: '계산 대기',
  RUNNING: '계산 중',
  SUCCEEDED: '계산 완료',
  FAILED: '계산 실패',
  REJECTED: '제출 거절',
};
export function CompetitionDetail({
  id,
  account,
  catalog,
  onLogin,
}: {
  id: string;
  account: Account | null;
  catalog: CompetitionCatalog;
  onLogin: () => void;
}) {
  const [value, setValue] = useState<Competition | null>(null),
    [results, setResults] = useState<Results | null>(null),
    [candidates, setCandidates] = useState<CompetitionCandidates>([]);
  const [page, setPage] = useState(0),
    [revision, setRevision] = useState(0),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [consent, setConsent] = useState(false),
    [confirmCancel, setConfirmCancel] = useState(false);
  const pending = useRef(false),
    alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError('');
    setResults(null);
    setCandidates([]);
    void (async () => {
      const c = await loadCompetition(id, abort.signal);
      if (abort.signal.aborted) return;
      setValue(c);
      const [r, jobs] = await Promise.all([
        c.canManage || c.joinedAt ? loadCompetitionResults(id, page, abort.signal) : null,
        c.joinedAt && c.mode === 'DISASTER' ? loadCompetitionCandidates(id, abort.signal) : [],
      ]);
      if (!abort.signal.aborted) {
        setResults(r);
        setCandidates(jobs);
      }
    })()
      .catch((e) => {
        if (!abort.signal.aborted) setError(errorMessage(e));
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [id, page, revision]);
  async function action(fn: () => Promise<unknown>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      await fn();
      if (alive.current) {
        setConfirmCancel(false);
        setRevision((v) => v + 1);
      }
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
    } finally {
      pending.current = false;
      if (alive.current) setBusy(false);
    }
  }
  const c = value;
  const href = c
    ? `${c.mode === 'REALTIME' ? '/weekly' : `/disaster/${c.eventId}`}?competition=${c.id}`
    : '';
  return (
    <>
      <div className="contest-heading">
        <a
          className="outline-button"
          href="/competitions"
          onClick={(e) => followLink(e, '/competitions')}
        >
          ← 대회 목록
        </a>
        <button
          className="outline-button"
          disabled={loading || busy}
          onClick={() => setRevision((v) => v + 1)}
        >
          <RefreshCw size={15} />
          새로고침
        </button>
      </div>
      {error && (
        <p role="alert" className="contest-error">
          {error}
        </p>
      )}
      {loading && !c && <p role="status">대회를 불러오는 중입니다.</p>}
      {c && (
        <>
          <section className="contest-panel">
            <div className="contest-heading">
              <div>
                <small>{c.organizationName}</small>
                <h1>{c.title}</h1>
              </div>
              <span className="contest-badge">{phaseNames[c.phase]}</span>
            </div>
            <p className="contest-prose">{c.description}</p>
            <dl className="contest-facts">
              <div>
                <dt>모드</dt>
                <dd>
                  {c.mode === 'REALTIME' ? '실시간 모드' : '재해 모드'}
                  {c.eventId && (
                    <small>{catalog.events.find((e) => e.id === c.eventId)?.title}</small>
                  )}
                </dd>
              </div>
              <div>
                <dt>개최 기간 · 한국 시간</dt>
                <dd>
                  {competitionTime(c.opensAt)} — {competitionTime(c.closesAt)}
                </dd>
              </div>
              <div>
                <dt>대회 맵</dt>
                <dd>
                  {c.rules.districtIds.length === 25
                    ? '서울 전체'
                    : c.rules.districtIds
                        .map((id) => catalog.districts.find((d) => d.id === id)?.name ?? id)
                        .join(' · ')}
                </dd>
              </div>
              <div>
                <dt>1인당 예산</dt>
                <dd>
                  {c.rules.budgetMode === 'CUSTOM' ? '주최자 설정' : '기본 예산'} ·{' '}
                  {c.rules.personalBudgetKrw != null
                    ? won(c.rules.personalBudgetKrw)
                    : catalog.defaultPersonalBudgetKrw != null
                      ? won(catalog.defaultPersonalBudgetKrw)
                      : '조회 중'}
                </dd>
              </div>
              <div>
                <dt>허용 시설</dt>
                <dd>{c.rules.allowedTypes.map((t) => facilities[t].name).join(' · ')}</dd>
              </div>
            </dl>
            <h2>시상</h2>
            {c.rules.awards.length ? (
              <div className="contest-awards">
                {c.rules.awards.map((a, i) => (
                  <div key={i}>
                    <strong>{a.title}</strong>
                    <span>
                      {a.rankFrom === a.rankTo ? `${a.rankFrom}위` : `${a.rankFrom}–${a.rankTo}위`}
                    </span>
                    <b>{a.prizeKrw > 0 ? `1인 ${won(a.prizeKrw)}` : '상 수여'}</b>
                  </div>
                ))}
              </div>
            ) : (
              <p>별도 시상 없음</p>
            )}
            <p className="contest-prose">{c.rules.awardNotice}</p>
            <p className="contest-note">
              {c.mode === 'REALTIME'
                ? '참가 후 대회 기간에 새로 설치한 시설의 기여를 자동 집계합니다. 소속 구와 관계없이 대회에서 선택한 모든 구에 대회 전용 예산으로 설치하고 종료 시점까지만 계산합니다.'
                : '참가 후 지정 재해의 전체 기간 설계를 계산하고, 아래에서 대회 기록으로 접수해 주세요. 종료 전에 접수한 계산은 종료 후 완료되어도 집계됩니다.'}
            </p>
            <div className="contest-heading">
              <span>참가 {c.participantCount.toLocaleString()}명</span>
              {c.canManage && ['OPEN', 'UPCOMING'].includes(c.phase) && (
                <button
                  className="outline-button"
                  disabled={busy}
                  onClick={() => setConfirmCancel((v) => !v)}
                >
                  대회 취소
                </button>
              )}
            </div>
            {confirmCancel && (
              <div className="contest-confirm">
                <p>대회를 취소하면 추가 참가와 제출을 받지 않습니다.</p>
                <button
                  className="solid-button"
                  disabled={busy}
                  onClick={() => void action(() => cancelCompetition(c.id))}
                >
                  취소 확정
                </button>
                <button
                  className="outline-button"
                  disabled={busy}
                  onClick={() => setConfirmCancel(false)}
                >
                  돌아가기
                </button>
              </div>
            )}
            {!account ? (
              <button className="solid-button" onClick={onLogin}>
                로그인하고 참가하기
              </button>
            ) : c.joinedAt ? (
              <div className="contest-actions">
                <span>참가 완료 · {competitionTime(c.joinedAt)}</span>
                {c.phase === 'OPEN' && (
                  <a className="solid-button" href={href} onClick={(e) => followLink(e, href)}>
                    대회 게임 시작
                    <ArrowUpRight size={16} />
                  </a>
                )}
              </div>
            ) : account.memberType === 'PLAYER' && ['OPEN', 'UPCOMING'].includes(c.phase) ? (
              <div className="contest-join">
                <label className="contest-check">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                  대회 조건과 시상 안내에 동의하며, 닉네임·순위·
                  {c.mode === 'REALTIME' ? '시설 설치 시각' : '제출 시각'}을 주최자와 참가자에게
                  공개합니다.
                </label>
                <button
                  className="solid-button"
                  disabled={!consent || busy || loading}
                  onClick={() => void action(() => joinCompetition(c.id, c.rulesHash))}
                >
                  참가 신청
                </button>
              </div>
            ) : (
              !c.canManage && <p>플레이어 회원이 개최 기간 내에 참가할 수 있습니다.</p>
            )}
          </section>
          {c.mode === 'DISASTER' && c.joinedAt && (
            <section className="contest-panel">
              <h2>내 설계 접수</h2>
              <p>참가 후 대회 기간에 만든 설계 중 지역·시설·평가 조건을 충족한 최근 기록입니다.</p>
              {!candidates.length ? (
                <p className="contest-empty">
                  접수할 설계가 없습니다. 대회 게임에서 전체 기간 설계를 제출한 뒤 돌아오세요.
                </p>
              ) : (
                <ul className="contest-candidates">
                  {candidates.map((job) => (
                    <li key={job.id}>
                      <div>
                        <strong>{competitionTime(job.createdAt)}</strong>
                        <span>{jobNames[job.state] ?? job.state}</span>
                      </div>
                      <button
                        className="outline-button"
                        disabled={
                          job.entered ||
                          busy ||
                          c.phase !== 'OPEN' ||
                          ['FAILED', 'REJECTED'].includes(job.state)
                        }
                        onClick={() =>
                          void action(() => submitCompetition(c.id, job.id, c.rulesHash))
                        }
                      >
                        {job.entered ? '접수 완료' : '대회에 접수'}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
          {c.canManage && (
            <GameAnalysisPanel
              endpoint={`/competitions/${encodeURIComponent(c.id)}/analytics`}
              key={`${c.id}:${revision}`}
            />
          )}
          {results && <CompetitionResults value={results} catalog={catalog} onPage={setPage} />}
        </>
      )}
    </>
  );
}
