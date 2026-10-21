import type { CompetitionCatalog, CompetitionResults as Results } from '../dto/competitionDto';
import { InstallationTimes, Pagination, competitionTime, resultNames } from './CompetitionShared';
import { scoreFormat } from '../../weekly/service/scoreFormat';
export function CompetitionResults({
  value,
  catalog,
  onPage,
}: {
  value: Results;
  catalog: CompetitionCatalog;
  onPage: (page: number) => void;
}) {
  return (
    <section className="contest-panel">
      <div className="contest-heading">
        <h2>대회 결과</h2>
        <span className="contest-badge">{resultNames[value.status]}</span>
      </div>
      <p>
        같은 평가 조건끼리 순위를 비교합니다. 같은 점수는 공동 순위이며, 미완료 계산이 있으면 결과를
        확정하지 않습니다.
      </p>
      {value.missingSeconds > 0 && (
        <p role="status">
          {Math.ceil(value.missingSeconds / 60).toLocaleString()}분의 시설 평가가 아직 완료되지
          않았습니다.
        </p>
      )}
      {value.pendingCalculations && <p role="status">마감 전에 접수된 설계를 계산하고 있습니다.</p>}
      {!value.groups.length && <p className="contest-empty">집계할 기록이 없습니다.</p>}
      {value.groups.map((g, index) => (
        <section key={g.comparisonGroup} className="contest-result-group">
          <h3>
            {g.comparisonGroup === 'WITHHELD' ? '계산 대기 · 비교 보류' : `평가 그룹 ${index + 1}`}{' '}
            <small>{g.count}명</small>
          </h3>
          <div className="contest-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>순위</th>
                  <th>플레이어</th>
                  <th>기여 m³</th>
                  <th>{value.competition.mode === 'REALTIME' ? '설치 시각' : '제출 시각'}</th>
                </tr>
              </thead>
              <tbody>
                {g.entries.map((r, i) => (
                  <tr key={`${r.playerId}:${i}`}>
                    <td>{r.rank ?? '—'}</td>
                    <th scope="row">
                      {r.nickname}
                      {r.evaluatedSeconds !== undefined &&
                        r.evaluatedSeconds < (r.expectedSeconds ?? 0) && <small>일부 미평가</small>}
                    </th>
                    <td title={r.scoreM3Exact === null ? undefined : `${r.scoreM3Exact} m³`}>
                      {r.scoreM3 === null ? '미확정' : scoreFormat.format(r.scoreM3)}
                    </td>
                    <td>
                      {value.competition.mode === 'REALTIME' ? (
                        <InstallationTimes items={r.installations ?? []} catalog={catalog} />
                      ) : r.submittedAt ? (
                        competitionTime(r.submittedAt)
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      <Pagination page={value.page} hasMore={value.hasMore} onPage={onPage} />
      <small>{competitionTime(value.generatedAt)} 기준 · 시상은 주최자 안내에 따라 진행</small>
    </section>
  );
}
