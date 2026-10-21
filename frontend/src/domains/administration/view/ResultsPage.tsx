import { useEffect, useState } from 'react';
import { followLink } from '../../../shared/controller/useAppLocation';
import { errorMessage } from '../../../shared/exception/ApiError';
import { loadCompetitionCatalog } from '../../competition/repository/competitionRepository';
import type { CompetitionCatalog } from '../../competition/dto/competitionDto';
import { InstallationTimes, Pagination } from '../../competition/view/CompetitionShared';
import { HistoricalBoard } from '../../historical/view/HistoricalBoard';
import { scoreFormat } from '../../weekly/service/scoreFormat';
import {
  loadSeasons,
  loadSeasonResults,
  type SeasonResults,
} from '../repository/resultsRepository';
import '../../competition/view/competition.css';
const statuses: Record<string, string> = {
  EMPTY: '기록 없음',
  IN_PROGRESS: '진행 중 순위',
  PROVISIONAL: '최종 계산 중',
  FINAL: '최종 결과',
  WITHHELD: '비교 보류',
};
export function ResultsPage() {
  const [mode, setMode] = useState('weekly'),
    [seasons, setSeasons] = useState<string[]>([]),
    [week, setWeek] = useState(''),
    [page, setPage] = useState(0),
    [catalog, setCatalog] = useState<CompetitionCatalog | null>(null),
    [result, setResult] = useState<SeasonResults | null>(null),
    [error, setError] = useState(''),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    void Promise.all([loadSeasons(abort.signal), loadCompetitionCatalog(abort.signal)])
      .then(([s, c]) => {
        if (!abort.signal.aborted) {
          setSeasons(s);
          setWeek((v) => v || s[0] || '');
          setCatalog(c);
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(errorMessage(e));
      });
    return () => abort.abort();
  }, [revision]);
  useEffect(() => {
    if (!week || mode !== 'weekly') return;
    const abort = new AbortController();
    setResult(null);
    setError('');
    void loadSeasonResults(week, page, abort.signal)
      .then((r) => {
        if (!abort.signal.aborted) setResult(r);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(errorMessage(e));
      });
    return () => abort.abort();
  }, [week, page, mode, revision]);
  return (
    <main className="full-page contests-page">
      <div className="contest-heading">
        <div>
          <small>ADMINISTRATION</small>
          <h1>결과 관리</h1>
          <p>주간 시즌, 재해 기록과 대회 결과를 확인합니다.</p>
        </div>
        <button className="outline-button" onClick={() => setRevision((v) => v + 1)}>
          새로고침
        </button>
      </div>
      <div className="competition-switch" role="group" aria-label="관리 결과 유형">
        {[
          ['weekly', '주간 서울 대항전'],
          ['historical', '재해 모드'],
          ['competitions', '대회'],
        ].map(([id, label]) => (
          <button
            key={id}
            className={mode === id ? 'active' : ''}
            aria-pressed={mode === id}
            onClick={() => setMode(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="contest-error">
          {error}
        </p>
      )}
      {mode === 'historical' ? (
        <HistoricalBoard admin />
      ) : mode === 'competitions' ? (
        <section className="contest-panel">
          <h2>대회별 결과</h2>
          <p>대회 목록에서 대회를 선택하면 진행 중 순위와 종료 결과를 볼 수 있습니다.</p>
          <a
            className="solid-button"
            href="/competitions"
            onClick={(e) => followLink(e, '/competitions')}
          >
            대회 목록 열기
          </a>
        </section>
      ) : (
        <>
          <div className="contest-admin-filters">
            <label>
              시즌{' '}
              <select
                aria-label="주간 시즌"
                value={week}
                onChange={(e) => {
                  setWeek(e.target.value);
                  setPage(0);
                }}
              >
                {seasons.map((s) => (
                  <option key={s} value={s}>
                    {s} 시작 시즌
                  </option>
                ))}
              </select>
            </label>
            {result && <span className="contest-badge">{statuses[result.period.status]}</span>}
          </div>
          {!result || !catalog ? (
            <p role="status">시즌 기록을 불러오는 중입니다.</p>
          ) : (
            <>
              <section className="contest-panel">
                <h2>구별 순위</h2>
                <div className="contest-table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>순위</th>
                        <th>구</th>
                        <th>기여 m³</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.period.districts.map((d) => (
                        <tr key={d.districtId}>
                          <td>{d.rank ?? '—'}</td>
                          <th scope="row">{d.districtName}</th>
                          <td title={d.scoreM3Exact ?? undefined}>
                            {d.scoreM3 === null ? '미확정' : scoreFormat.format(d.scoreM3)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section className="contest-panel">
                <h2>플레이어별 순위 · {result.period.participantCount}명</h2>
                <p>
                  설치 시각은 한국 시간입니다. 계산 미완료·조건 불일치는 확정 순위로 처리하지
                  않습니다.
                </p>
                <div className="contest-table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>순위</th>
                        <th>플레이어</th>
                        <th>소속 구</th>
                        <th>기여 m³</th>
                        <th>시설 설치 시각</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.period.players.map((p) => (
                        <tr key={p.playerId}>
                          <td>{p.rank ?? '—'}</td>
                          <th scope="row">{p.nickname}</th>
                          <td>{catalog.districts.find((d) => d.id === p.districtId)?.name}</td>
                          <td title={p.scoreM3Exact ?? undefined}>
                            {p.scoreM3 === null ? '미확정' : scoreFormat.format(p.scoreM3)}
                          </td>
                          <td>
                            <InstallationTimes
                              items={result.installations.filter((i) => i.playerId === p.playerId)}
                              catalog={catalog}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!result.period.players.length && (
                  <p className="contest-empty">이 시즌의 설치 기록이 없습니다.</p>
                )}
                <Pagination page={page} hasMore={result.hasMore} onPage={setPage} />
              </section>
            </>
          )}
        </>
      )}
    </main>
  );
}
