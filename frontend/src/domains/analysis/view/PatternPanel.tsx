import { useState } from 'react';
import type { ResearchEntry } from '../../research/entity/research';
import { usePatternAnalysis } from '../controller/usePatternAnalysis';
import { facilities, format, won } from '../../game/service/gameService';
export function PatternPanel({ entries }: { entries: ResearchEntry[] }) {
  const [selected, setSelected] = useState<string[]>([]),
    [topK, setTopK] = useState(5);
  const ids = selected.filter((id) => entries.some((e) => e.jobId === id));
  const p = usePatternAnalysis(ids, topK),
    result = p.result;
  return (
    <section className="analysis-section" aria-label="상위 배치 패턴 분석">
      <h3>
        <span className="analysis-step">02</span> 상위 설계가 공유하는 배치
      </h3>
      <p className="analysis-intro">
        현재 강우의 동의된 제출 중 분석할 기록을 선택하세요. 같은 물리 배치는 한 번만 집계하고, 상위
        경계의 동점을 모두 포함합니다.
      </p>
      <fieldset className="pattern-selection" disabled={p.busy}>
        <legend>분석 표본 선택 · {ids.length}/50개</legend>
        <div className="pattern-select-actions">
          <button
            className="text-button"
            disabled={!entries.length}
            onClick={() => setSelected(entries.slice(0, 50).map((e) => e.jobId))}
          >
            최대 50개 선택
          </button>
          <button className="text-button" disabled={!ids.length} onClick={() => setSelected([])}>
            선택 해제
          </button>
        </div>
        <div className="pattern-samples">
          {entries.map((e) => (
            <label className="pattern-sample" key={e.jobId}>
              <input
                type="checkbox"
                checked={ids.includes(e.jobId)}
                disabled={!ids.includes(e.jobId) && ids.length >= 50}
                onChange={(event) =>
                  setSelected(
                    event.target.checked ? [...ids, e.jobId] : ids.filter((id) => id !== e.jobId)
                  )
                }
              />
              <span>
                <b>
                  {format.format(e.score)}점 · {won(e.cost)}
                </b>
                <small>
                  버전 {e.revision} · 계산 {e.jobId.slice(0, 8)} ·{' '}
                  {new Date(e.submittedAt).toLocaleDateString('ko-KR')}
                </small>
                <span>{e.designNote || '설계 메모 없음'}</span>
              </span>
            </label>
          ))}
        </div>
        {!entries.length && <p>현재 강우에 분석할 동의 기록이 없습니다.</p>}
        <div className="pattern-controls">
          <label>
            상위 고유 설계 기준
            <select
              aria-label="상위 고유 설계 기준"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            >
              {Array.from({ length: 20 }, (_, i) => i + 1).map((n) => (
                <option value={n} key={n}>
                  {n}개 + 경계 동점
                </option>
              ))}
            </select>
          </label>
          <button
            className="outline-button"
            disabled={!ids.length || p.busy}
            onClick={() => void p.run()}
          >
            {p.busy ? '집계 중' : '선택한 기록의 패턴 분석'}
          </button>
        </div>
      </fieldset>
      {p.error && (
        <p className="form-error" role="alert">
          {p.error}
        </p>
      )}
      {result && (
        <div className="pattern-result" aria-label="배치 패턴 집계 결과">
          <div className="pattern-counts" role="status">
            <p>
              <b>{result.requestedCount}</b>
              <span>선택 계산</span>
            </p>
            <p>
              <b>{result.uniqueInputCount}</b>
              <span>고유 배치 · 중복 {result.duplicateInputCount}개 제외</span>
            </p>
            <p>
              <b>{result.includedCount}</b>
              <span>상위 집계 설계 · 동점 포함</span>
            </p>
          </div>
          <p className="analysis-intro">
            경계 점수 {result.cutoffScore.toFixed(8)}점 · 비용 {won(result.minimumCostKrw)}–
            {won(result.maximumCostKrw)}. 사람 수가 아닌 설계 수입니다.
          </p>
          <h4>구역별 시설 빈도</h4>
          {result.placements.length ? (
            <div
              className="reference-table-wrap"
              role="region"
              aria-label="구역별 시설 빈도표"
              tabIndex={0}
            >
              <table className="reference-results pattern-table">
                <thead>
                  <tr>
                    <th scope="col">구역 · 시설</th>
                    <th scope="col">포함 설계 중 등장 빈도</th>
                    <th scope="col">설치 면적 범위 m²</th>
                    <th scope="col">설치 설계 평균 m²</th>
                    <th scope="col">전체 설계 평균 m²</th>
                  </tr>
                </thead>
                <tbody>
                  {result.placements.map((v) => (
                    <tr key={v.cellId + v.facilityType}>
                      <th scope="row">
                        {v.cellId}
                        <small>{facilities[v.facilityType].name}</small>
                      </th>
                      <td>
                        <b>{v.frequencyPercent.toFixed(2)}%</b> · {v.designCount}/
                        {result.includedCount}
                        <meter
                          min={0}
                          max={100}
                          value={v.frequencyPercent}
                          aria-label={`${v.cellId} ${facilities[v.facilityType].name} 등장 비율`}
                        />
                      </td>
                      <td>
                        {format.format(v.minimumAreaM2)}–{format.format(v.maximumAreaM2)}
                      </td>
                      <td>{v.meanInstalledAreaM2.toFixed(4)}</td>
                      <td>{v.meanAllDesignAreaM2.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="scope-note">집계 설계에 설치된 시설이 없습니다.</p>
          )}
          <p className="micro-note">
            설치 설계 평균은 해당 시설이 있는 설계만, 전체 설계 평균은 미설치를 0으로 포함한{' '}
            {result.includedCount}개 설계를 분모로 합니다.
          </p>
          <h4>시설 종류의 동시 등장</h4>
          <ul className="pattern-pairs">
            {result.facilityPairs.map((v) => (
              <li key={v.first + v.second}>
                <span>
                  {facilities[v.first].name} + {facilities[v.second].name}
                </span>
                <b>
                  {v.designCount}/{result.includedCount} · {v.frequencyPercent.toFixed(2)}%
                </b>
              </li>
            ))}
          </ul>
          <details className="pattern-evidence">
            <summary>집계에 포함된 설계와 해석 범위</summary>
            <code className="hash-value">모델 SHA-256: {result.modelHash}</code>
            <ul>
              {result.designs.map((d) => (
                <li key={d.jobId}>
                  <b>
                    {d.score.toFixed(8)}점 · {won(d.costKrw)}
                  </b>
                  <code className="hash-value">계산 {d.jobId}</code>
                  <code className="hash-value">원본 입력 {d.inputHash}</code>
                  <code className="hash-value">물리 배치 {d.physicalHash}</code>
                </li>
              ))}
            </ul>
            <ul>
              {result.limitations.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </details>
          <p className="comparison-scope">
            선택한 동의 표본 안의 기술 통계입니다. 자주 등장한 시설이 더 효과적이라는 인과관계나
            현장 시공 권고를 뜻하지 않습니다.
          </p>
        </div>
      )}
    </section>
  );
}
