import '../../weekly/view/weekly.css';
import { useEffect, useState } from 'react';
import { errorMessage } from '../../../shared/exception/ApiError';
import { loadDisasters } from '../../disaster/repository/disasterRepository';
import type { DisasterCatalog } from '../../disaster/entity/disaster';
import { won } from '../../game/service/gameService';
import { physicalAmount } from '../../physics/service/physicalValueFormat';
import type { HistoricalBoard as Board } from '../entity/historicalSubmission';
import { loadHistoricalBoard } from '../repository/submissionRepository';
import './historical.css';
import { Pagination } from '../../competition/view/CompetitionShared';
import { GameAnalysisPanel } from '../../gameanalysis/view/GameAnalysisPanel';

export function HistoricalBoard({ admin = false }: { admin?: boolean }) {
  const [page, setPage] = useState(0);
  const [catalog, setCatalog] = useState<DisasterCatalog | null>(null);
  const [eventId, setEventId] = useState(''),
    [error, setError] = useState('');
  const [board, setBoard] = useState<Board | null>(null);
  useEffect(() => {
    let alive = true;
    void loadDisasters()
      .then((v) => {
        if (alive) {
          setCatalog(v);
          setEventId(v.events[0]?.id ?? '');
        }
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (!eventId) return;
    let alive = true,
      pending = false;
    setBoard(null);
    setError('');
    async function load() {
      if (pending || document.hidden) return;
      pending = true;
      try {
        const value = await loadHistoricalBoard(eventId, admin, page);
        if (alive) {
          setBoard(value);
          setError('');
        }
      } catch (e) {
        if (alive) setError(errorMessage(e));
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = setInterval(() => void load(), 15000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [eventId, admin, page]);
  return (
    <section className="historical-board" aria-label="재해 모드 랭킹">
      <h2>재해 모드 랭킹</h2>
      <p>같은 사건과 계산 조건에서 제출한 설계의 평가체적 감소량을 비교합니다.</p>
      <label>
        재해 사건{' '}
        <select
          aria-label="랭킹 재해 사건"
          value={eventId}
          onChange={(e) => {
            setEventId(e.target.value);
            setPage(0);
          }}
        >
          {catalog?.events.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title}
            </option>
          ))}
        </select>
      </label>
      {admin && eventId && (
        <GameAnalysisPanel
          endpoint={`/admin/results/historical/${encodeURIComponent(eventId)}/analytics`}
        />
      )}
      <p>
        사건 평가 창 전체를 계산한 제출만 게시합니다. 같은 입력·예산 규칙·계산 조건끼리 비교하고
        회원별 최고 기록을 표시합니다.
      </p>
      {!!board?.withheldSubmissionCount && (
        <p role="status">
          평가 조건이 확인되지 않은 {board.withheldSubmissionCount}건은 순위 게시를 보류합니다.
        </p>
      )}
      <p>
        음수는 평가체적 증가입니다. 미세한 차이는 수치 오차보다 작을 수 있습니다. 표시값은
        반올림하며 순위는 소수 18자리 저장값으로 계산합니다.
      </p>
      {error ? (
        <p role="alert">{error}</p>
      ) : !board ? (
        <p>기록을 불러오는 중입니다.</p>
      ) : !board.groups.length ? (
        <p>이 사건의 완료된 제출 기록이 없습니다.</p>
      ) : (
        board.groups.map((group) => (
          <section key={`${group.rulesHash}:${group.comparisonGroupHash}`}>
            <h2>평가 규칙 {group.rulesHash.slice(0, 12)}</h2>
            <p>계산 조건 {group.comparisonGroupHash.slice(0, 12)} · 같은 저장값은 공동 순위</p>
            {!admin &&
              (() => {
                const own = board.ownEntries?.find(
                  (e) =>
                    e.rulesHash === group.rulesHash &&
                    e.comparisonGroupHash === group.comparisonGroupHash
                );
                return (
                  <div className="weekly-pinned" aria-label="내 재해 순위">
                    <span className="weekly-pinned-rank">{own ? `${own.rank}위` : '—'}</span>
                    <span>
                      {own?.displayName ?? '내 기록'}
                      <small>나</small>
                    </span>
                    <strong title={own ? `${own.differenceM3Exact} m³` : undefined}>
                      {own ? `${physicalAmount(own.differenceM3)} m³` : '점수 없음'}
                    </strong>
                  </div>
                );
              })()}
            <div className="historical-board-scroll">
              <table>
                <thead>
                  <tr>
                    <th>순위</th>
                    <th>플레이어</th>
                    <th>평가체적 감소</th>
                    <th>설치비</th>
                    <th>제출 시각</th>
                  </tr>
                </thead>
                <tbody>
                  {group.entries.map((entry) => (
                    <tr
                      key={entry.id}
                      className={
                        board.ownEntries?.some((e) => e.id === entry.id) ? 'own' : undefined
                      }
                    >
                      <td>{entry.rank}</td>
                      <td>{entry.displayName}</td>
                      <td title={`${entry.differenceM3Exact} m³`}>
                        {physicalAmount(entry.differenceM3)} m³
                      </td>
                      <td>{won(entry.costKrw)}</td>
                      <td>
                        {new Date(entry.submittedAt).toLocaleString('ko-KR', {
                          timeZone: 'Asia/Seoul',
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
      {admin && board && (
        <Pagination
          page={page}
          hasMore={board.groups.some((g) => g.entries.length === 100)}
          onPage={setPage}
        />
      )}
    </section>
  );
}
