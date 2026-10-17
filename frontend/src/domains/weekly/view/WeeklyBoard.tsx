import { useState } from 'react';
import { Trophy } from 'lucide-react';
import type { WeeklySnapshot } from '../dto/weeklyDto';
import './weekly.css';
export const scoreFormat = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 3 });
const date = (s: string) =>
  new Date(s).toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Seoul',
    hourCycle: 'h23',
  });
export function WeeklyBoard({
  value,
  error,
  ownDistrictId,
  onDistrict,
}: {
  value: WeeklySnapshot | null;
  error: string;
  ownDistrictId: string | null;
  onDistrict: (id: string) => void;
}) {
  const [previous, setPrevious] = useState(false);
  const period = value?.[previous ? 'previous' : 'current'];
  const winners = value?.previous.districts
    .filter((d) => value.previous.winnerDistrictIds.includes(d.districtId))
    .map((d) => d.districtName)
    .join(' · ');
  return (
    <section className="weekly-board" aria-label="서울 공동 주간 순위">
      <header>
        <div>
          <span className="weekly-eyebrow">서울 공동 리그</span>
          <h2>우리 구의 주간 기여</h2>
        </div>
        <div className="weekly-tabs">
          <button aria-pressed={!previous} onClick={() => setPrevious(false)}>
            이번 주
          </button>
          <button aria-pressed={previous} onClick={() => setPrevious(true)}>
            지난주
          </button>
        </div>
      </header>
      {error && <p role="status">{error}</p>}
      {!period ? (
        <p>관측 계산 기록을 불러오는 중입니다.</p>
      ) : (
        <>
          <div className="weekly-period">
            <span>
              {date(period.startsAt)} — {date(period.endsAt)} KST
            </span>
            <strong>
              {period.status === 'FINAL'
                ? '집계 완료'
                : period.status === 'PROVISIONAL'
                  ? '누락 구간 계산 대기'
                  : period.status === 'EMPTY'
                    ? '평가 기록 없음'
                    : '진행 중'}
            </strong>
          </div>
          <div className="weekly-last-winner">
            <Trophy size={16} />
            <span>
              {winners
                ? `지난주 우승 · ${winners}`
                : value?.previous.status === 'PROVISIONAL'
                  ? '지난주 결과는 미평가 구간이 있어 잠정 상태입니다.'
                  : '지난주 확정 우승 구 없음'}
            </span>
          </div>
          {period.own && (
            <p className="weekly-own">
              내 기록 · {period.own.rank === null ? '계산 대기' : `${period.own.rank}위`} ·{' '}
              {scoreFormat.format(period.own.scoreM3)}m³
              {period.own.evaluatedMinutes < period.own.expectedMinutes
                ? ' · 일부 구간 미평가'
                : ''}
            </p>
          )}
          <div className="weekly-tables">
            <div>
              <h3>구별 순위</h3>
              <div className="weekly-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>순위</th>
                      <th>자치구</th>
                      <th>기여 m³</th>
                    </tr>
                  </thead>
                  <tbody>
                    {period.districts.map((d) => (
                      <tr
                        key={d.districtId}
                        className={d.districtId === ownDistrictId ? 'own' : ''}
                      >
                        <td>{d.rank ?? '—'}</td>
                        <th scope="row">
                          <button onClick={() => onDistrict(d.districtId)}>
                            {d.districtName}
                            {d.districtId === ownDistrictId ? ' · 내 구' : ''}
                          </button>
                          {d.evaluatedMinutes < d.expectedMinutes && <small>일부 미평가</small>}
                        </th>
                        <td>{d.evaluatedMinutes ? scoreFormat.format(d.scoreM3) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div>
              <h3>
                개인 순위{' '}
                <small>{period.participantCount.toLocaleString('ko-KR')}명 · 상위 100명</small>
              </h3>
              {!period.players.length ? (
                <p className="weekly-empty">
                  아직 평가된 플레이 기록이 없습니다.
                  <br />
                  우리 구에 시설을 설치하면 관측 강우에 따라 계산됩니다.
                </p>
              ) : (
                <div className="weekly-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>순위</th>
                        <th>플레이어</th>
                        <th>기여 m³</th>
                      </tr>
                    </thead>
                    <tbody>
                      {period.players.map((p) => (
                        <tr
                          key={p.playerId}
                          className={p.playerId === period.own?.playerId ? 'own' : ''}
                        >
                          <td>{p.rank ?? '—'}</td>
                          <th scope="row">
                            {p.nickname}
                            <small>
                              {
                                period.districts.find((d) => d.districtId === p.districtId)
                                  ?.districtName
                              }
                              {p.evaluatedMinutes < p.expectedMinutes ? ' · 일부 미평가' : ''}
                            </small>
                          </th>
                          <td>{p.evaluatedMinutes ? scoreFormat.format(p.scoreM3) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
          <footer>
            <span>{value && date(value.generatedAt)} 갱신</span>
            <details>
              <summary>기여 점수와 집계 기준</summary>
              <p>
                관측 강우를 넣은 시설 없는 조건과 설치 조건의 유출·배수·순저류 체적 차이입니다.
                음수도 반영하며 순위는 반올림 전 값으로 계산합니다. 같은 점수는 공동 순위입니다.
              </p>
              <p>
                실험 조건의 계산 기여이며 실제 현장 저감량은 아닙니다. 계산이 빠진 종료 주는 우승을
                확정하지 않으며, 양수 기여가 있는 최고 구를 우승으로 표시합니다. 최신 관측의 처리
                시간을 고려해 2분 전까지 집계합니다.
              </p>
            </details>
          </footer>
        </>
      )}
    </section>
  );
}
