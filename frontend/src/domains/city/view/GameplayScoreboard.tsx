import type { WeeklySnapshot } from '../../weekly/dto/weeklyDto';
import { scoreFormat } from '../../weekly/service/scoreFormat';

export function GameplayScoreboard({
  historical,
  authenticated,
  district,
  weekly,
  count,
  score,
  locked = false,
}: {
  historical: boolean;
  authenticated: boolean;
  district?: WeeklySnapshot['current']['districts'][number];
  weekly: WeeklySnapshot | null;
  count: number | null;
  score: number | null;
  locked?: boolean;
}) {
  return (
    <div className="game-scoreboard" aria-label={historical ? '내 재해 기록' : '주간 대항전 기록'}>
      {!historical && (
        <div className="game-score-group" aria-label="우리 구 기록">
          <span>
            {district?.districtName ?? '우리 구'} 순위
            <b>{!authenticated ? '로그인 필요' : district?.rank ? `${district.rank}위` : '—'}</b>
          </span>
          <span>
            우리 구 총점
            <b>
              {district?.scoreM3 == null ? '미계산' : scoreFormat.format(district.scoreM3)}
              {district?.scoreM3 != null && <small> m³</small>}
            </b>
          </span>
        </div>
      )}
      <div className="game-score-group" aria-label="내 시설 기록">
        <span>
          내 설치 시설
          <b>
            {count ?? '—'}
            <small> 곳</small>
          </b>
        </span>
        <span>
          내 총점
          <b>
            {locked ? '로그인 필요' : score == null ? '미계산' : scoreFormat.format(score)}
            {!locked && score !== null && <small> m³</small>}
          </b>
        </span>
      </div>
      {weekly?.current.status === 'PROVISIONAL' && <span className="score-provisional">잠정</span>}
    </div>
  );
}
