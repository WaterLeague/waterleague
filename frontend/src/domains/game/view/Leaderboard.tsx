import { useEffect, useState } from 'react';
import { Trophy, ArrowUpRight } from 'lucide-react';
import { loadBoard } from '../repository/gameRepository';
import type { Board, Lab } from '../entity/game';
import { format, won } from '../service/gameService';
import { errorMessage } from '../../../shared/exception/ApiError';
export function Leaderboard({ lab }: { lab: Lab }) {
  const [board, setBoard] = useState<Board | null>(null),
    [error, setError] = useState('');
  const refresh = () =>
    loadBoard(lab.modelHash)
      .then(setBoard)
      .catch((e) => setError(errorMessage(e)));
  useEffect(() => {
    void refresh();
  }, [lab.modelHash]);
  return (
    <section className="full-page">
      <div className="page-eyebrow">
        THE LEAGUE <span>EXPLORATORY</span>
      </div>
      <div className="page-heading">
        <h1>같은 비, 다른 해답.</h1>
        <button className="outline-button" onClick={() => void refresh()}>
          기록 새로고침 <ArrowUpRight size={15} />
        </button>
      </div>
      <p className="lead">같은 관측 강우와 같은 예산. 내가 만든 설계의 결과를 비교합니다.</p>
      <div className="scope-note">
        <Trophy size={20} />
        <p>
          <b>
            {lab.model.rainfall.stationName} {lab.model.rainfall.stationId} ·{' '}
            {new Date(lab.model.rainfall.start).toLocaleDateString('ko-KR', {
              timeZone: 'Asia/Seoul',
            })}{' '}
            · {lab.model.rainfall.totalDepthMm} mm
          </b>{' '}
          · 검증 전 모델의 연습 경쟁입니다. 공식 현장 평가·실제 공사효과 순위가 아닙니다. 점수가
          같으면 같은 순위입니다.
        </p>
      </div>
      {error && <p role="alert">{error}</p>}
      <table className="data-table">
        <thead>
          <tr>
            <th>순위</th>
            <th>플레이어</th>
            <th>평가체적 저감</th>
            <th>추정 비용</th>
            <th>제출일</th>
          </tr>
        </thead>
        <tbody>
          {board?.entries.map((e) => (
            <tr key={e.displayName}>
              <td className={e.rank === 1 ? 'first-rank' : ''}>
                {String(e.rank).padStart(2, '0')}
              </td>
              <td>
                <b>{e.displayName}</b>
              </td>
              <td>
                {format.format(e.score)}
                <small> 점</small>
              </td>
              <td>{won(e.cost)}</td>
              <td>{new Date(e.submittedAt).toLocaleDateString('ko-KR')}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {board && !board.entries.length && (
        <div className="empty-state">
          <Trophy size={36} />
          <h3>첫 번째 기록을 기다립니다.</h3>
          <p>설계실에서 시설을 배치하고 계산한 뒤 기록을 제출하세요.</p>
        </div>
      )}
      <p className="footnote">
        점수 = 기준안 대비 (유출 + 최종저류 − 초기저류) 감소율 × 100. 음수도 보존합니다. 화면은 소수
        둘째 자리, 순위는 서버 정밀도 기준입니다.
      </p>
    </section>
  );
}
