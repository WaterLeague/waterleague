import { useEffect, useState } from 'react';
import { errorMessage } from '../../../shared/exception/ApiError';
import { loadDisasters } from '../../disaster/repository/disasterRepository';
import type { DisasterCatalog } from '../../disaster/entity/disaster';
import { won } from '../../game/service/gameService';
import { physicalAmount } from '../../physics/service/physicalValueFormat';
import type { HistoricalBoard as Board } from '../entity/historicalSubmission';
import { loadHistoricalBoard } from '../repository/submissionRepository';
import './historical.css';

export function HistoricalBoard() {
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
        const value = await loadHistoricalBoard(eventId);
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
  }, [eventId]);
  return (
    <section className="full-page historical-board" aria-label="재해 실험 기록 경쟁">
      <h1>재해 실험 기록 경쟁</h1>
      <p>현재 형상·과거 강우 스트레스 시험 · 독립 표면 평가체적 감소 순위</p>
      <label>
        재해 사건{' '}
        <select
          aria-label="기록 경쟁 재해 사건"
          value={eventId}
          onChange={(e) => setEventId(e.target.value)}
        >
          {catalog?.events.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title}
            </option>
          ))}
        </select>
      </label>
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
        음수는 평가체적 증가입니다. 미세한 차이는 수치 오차보다 작을 수 있습니다. 연결 유역
        침수·첨두 지표가 없어 총점은 보류합니다. 표시값은 반올림하며 순위는 소수 18자리 저장값으로
        계산합니다.
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
                    <tr key={entry.id}>
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
    </section>
  );
}
