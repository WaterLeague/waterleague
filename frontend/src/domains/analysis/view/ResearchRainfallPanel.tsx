import { sameMapModels } from '../../game/service/modelFamilyService';
import { useEffect, useState } from 'react';
import { Download, Play } from 'lucide-react';
import type { RainfallCatalog } from '../../game/entity/game';
import type { ResearchDetail } from '../../research/entity/research';
import { useResearchComparison } from '../controller/useResearchComparison';
import { format, won } from '../../game/service/gameService';
import { rainDate } from '../../game/service/gameTimeService';
import { comparisonState, jobStateNames } from '../../comparison/service/comparisonService';
export function ResearchRainfallPanel({
  source,
  catalog,
}: {
  source: ResearchDetail | null;
  catalog: RainfallCatalog | null;
}) {
  const c = useResearchComparison(),
    [selected, setSelected] = useState<string[]>([]);
  useEffect(() => {
    setSelected(
      sameMapModels(catalog, source?.version.modelHash)
        .filter((m) => m.modelHash !== source?.version.modelHash)
        .slice(0, 2)
        .map((m) => m.modelHash) ?? []
    );
  }, [source?.simulation.id, catalog]);
  const detail = c.detail;
  return (
    <section className="analysis-section" aria-label="기관 다강우 재계산">
      <h3>
        <span className="analysis-step">01</span> 같은 배치, 다른 관측 강우
      </h3>
      <div className="comparison-create">
        <div>
          <h4>위에서 선택한 제출 기록</h4>
          {source ? (
            <>
              <p>
                <b>
                  버전 {source.version.revision} · {won(source.version.cost)}
                </b>
              </p>
              <p>
                {source.version.placements.length}개 시설 ·{' '}
                {format.format(source.lab.model.rainfall.totalDepthMm)}mm
              </p>
              <code className="hash-value">원본 계산 {source.simulation.id}</code>
              <small>
                이 제출 버전의 배치를 그대로 복사합니다. 위 이력 슬라이더의 선택은 반영하지
                않습니다.
              </small>
            </>
          ) : (
            <p>위의 동의된 제출 기록을 선택해 주세요.</p>
          )}
        </div>
        <fieldset disabled={!source || c.busy || !catalog}>
          <legend>실제 관측 강우 2–3개 선택</legend>
          {sameMapModels(catalog, source?.version.modelHash).map((m) => (
            <label key={m.modelHash}>
              <input
                type="checkbox"
                checked={selected.includes(m.modelHash)}
                disabled={!selected.includes(m.modelHash) && selected.length >= 3}
                onChange={(e) =>
                  setSelected((old) =>
                    e.target.checked ? [...old, m.modelHash] : old.filter((h) => h !== m.modelHash)
                  )
                }
              />
              <span>
                {m.rainfall.stationName} · {rainDate(m.rainfall.start)}
                <small>
                  {format.format(m.rainfall.totalDepthMm)}mm
                  {m.modelHash === source?.version.modelHash ? ' · 원본 강우' : ''}
                </small>
              </span>
            </label>
          ))}
          <button
            className="outline-button"
            disabled={!source || selected.length < 2 || c.busy}
            onClick={() => {
              if (source) c.create(source.simulation.id, selected);
            }}
          >
            <Play size={14} />
            {c.busy ? '요청 처리 중' : '기관 재계산 시작'}
          </button>
          <small>
            원본 소유자의 활성 계산 3개, 기관 요청 계산 9개 이내. 결과는 순위에 자동 제출되지
            않습니다.
          </small>
        </fieldset>
      </div>
      {c.error && (
        <p className="form-error" role="alert">
          {c.error}
        </p>
      )}
      <div className="comparison-history">
        <label>
          우리 기관의 재계산 기록
          <select
            aria-label="우리 기관의 재계산 기록"
            value={detail?.id ?? ''}
            disabled={c.busy}
            onChange={(e) => {
              if (e.target.value) c.open(e.target.value);
            }}
          >
            <option value="">기록 선택</option>
            {c.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title} ·{' '}
                {new Date(item.createdAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}
              </option>
            ))}
          </select>
        </label>
      </div>
      {detail && (
        <div className="comparison-detail" aria-label="기관 강우별 결과">
          <div className="page-heading">
            <div>
              <h4>{detail.comparison.title}</h4>
              <p role="status">
                {comparisonState(detail.comparison)} · 원본 비용{' '}
                {won(detail.comparison.sourceVersion.cost)}
              </p>
              <code className="hash-value">이 비교의 원본 계산 {detail.sourceJobId}</code>
            </div>
            <button className="text-button" disabled={c.busy} onClick={() => c.open(detail.id)}>
              기관 결과 새로고침
            </button>
          </div>
          <div
            className="reference-table-wrap"
            role="region"
            aria-label="기관 강우별 결과표"
            tabIndex={0}
          >
            <table className="reference-results">
              <thead>
                <tr>
                  <th scope="col">관측 강우</th>
                  <th scope="col">상태</th>
                  <th scope="col">점수</th>
                  <th scope="col">기준 평가체적 m³</th>
                  <th scope="col">배치 평가체적 m³</th>
                  <th scope="col">종료 저류 m³</th>
                  <th scope="col">수지 오차</th>
                  <th scope="col">재현 자료</th>
                </tr>
              </thead>
              <tbody>
                {detail.comparison.jobs.map((j) => {
                  const m = catalog?.models.find((m) => m.modelHash === j.modelHash);
                  return (
                    <tr key={j.id}>
                      <th scope="row">
                        {m
                          ? `${m.rainfall.stationName} · ${rainDate(m.rainfall.start)}`
                          : '과거 등록 강우'}
                        <small>
                          {m
                            ? `${format.format(m.rainfall.totalDepthMm)}mm`
                            : j.modelHash.slice(0, 12)}
                        </small>
                      </th>
                      <td>
                        {jobStateNames[j.state]}
                        {j.errorCode && (
                          <small className="comparison-error">계산 실패 · 검토 필요</small>
                        )}
                      </td>
                      <td>
                        <b>{j.result ? format.format(j.result.score) : '—'}</b>
                      </td>
                      <td>
                        {j.result ? format.format(j.result.baseline.accountedDischargeM3) : '—'}
                      </td>
                      <td>
                        {j.result ? format.format(j.result.strategy.accountedDischargeM3) : '—'}
                      </td>
                      <td>{j.result ? format.format(j.result.strategy.finalStorageM3) : '—'}</td>
                      <td>
                        {j.result
                          ? j.result.strategy.runoffContinuityPercent.toFixed(4) + '%'
                          : '—'}
                      </td>
                      <td>
                        {j.state === 'SUCCEEDED' ? (
                          <a
                            className="comparison-bundle"
                            href={`/api/v1/research/comparisons/${detail.id}/jobs/${j.id}/bundle`}
                          >
                            <Download size={13} />
                            재현 ZIP
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="comparison-scope">
            점수는 각 강우의 시설 없는 기준안 대비 평가체적 감소율입니다. 강우별 점수를 합산하지
            않습니다. 관측 창 길이와 종료 저류량을 함께 검토해 주세요. 원본 동의 철회 후에는 이
            결과와 재현 파일의 후속 접근이 차단됩니다.
          </p>
        </div>
      )}
    </section>
  );
}
