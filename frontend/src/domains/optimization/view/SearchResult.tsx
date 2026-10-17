import { useState } from 'react';
import { Download } from 'lucide-react';
import type { Lab } from '../../game/entity/game';
import type { CandidateMap } from '../../catalog/entity/catalog';
import type { ResearchSearch } from '../entity/search';
import { searchArmNames, searchState } from '../service/searchService';
import { facilities, format, won } from '../../game/service/gameService';
import { jobStateNames } from '../../comparison/service/comparisonService';
import { MapViewport } from '../../catalog/view/MapViewport';
import { Hydrograph } from '../../game/view/Hydrograph';
export function SearchResult({
  detail: d,
  lab,
  map,
}: {
  detail: ResearchSearch;
  lab: Lab;
  map: CandidateMap | null;
}) {
  const [view, setView] = useState('candidate:' + d.candidates[0].id),
    [cell, setCell] = useState<string | null>(null),
    g = d.generation;
  const candidate = d.candidates.find((c) => 'candidate:' + c.id === view),
    source = g.sources.find((s) => 'source:' + s.sample.jobId === view),
    placements = candidate?.placements ?? source?.placements ?? [];
  const label = candidate ? `${searchArmNames[candidate.arm]} ${candidate.ordinal}` : '원본 배치',
    cost = candidate?.costKrw ?? source?.sample.costKrw ?? 0;
  return (
    <div className="search-result" aria-label="후보 탐색 결과">
      <div className="page-heading">
        <div>
          <h4>같은 강우, 같은 예산의 후보 비교</h4>
          <p role="status">{searchState(d)}</p>
          <p className="micro-note">
            예산 {won(g.settings.budgetKrw)} · 시드 {g.settings.seed} · 방법당{' '}
            {g.settings.candidatesPerArm}개
          </p>
        </div>
        <a className="outline-button" href={`/api/v1/research/searches/${d.id}/provenance`}>
          <Download size={14} />
          생성 계보 JSON
        </a>
      </div>
      <div className="search-scoreboard">
        <div>
          <span>선택 원본 최고점</span>
          <b>
            {d.sourceBestScore.toFixed(8)}
            <small>점</small>
          </b>
          <p>
            {g.requestedCount}개 기록 → 고유 {g.uniquePhysicalCount}개<br />
            학습 {g.trainingCount}개 · 경계 동점 포함
          </p>
        </div>
        {d.arms.map((a) => (
          <div key={a.arm}>
            <span>{searchArmNames[a.arm]}</span>
            <b>
              {a.bestScore === null ? '—' : a.bestScore.toFixed(8)}
              <small>점</small>
            </b>
            <p>
              성공 {a.succeeded}/{a.total} · 대기 {a.queued} · 실행 {a.running}
              <br />
              실패 {a.failed} · 거부 {a.rejected}
            </p>
            <progress
              aria-label={`${searchArmNames[a.arm]} 처리 완료`}
              max={a.total}
              value={a.succeeded + a.failed + a.rejected}
            />
          </div>
        ))}
      </div>
      <p className="comparison-scope">
        {d.completeComparison
          ? '두 방법의 모든 후보 계산이 끝났습니다.'
          : '모든 후보가 성공하기 전에는 완전한 비교가 아닙니다.'}{' '}
        방법 사이 동일 후보 {g.sharedCandidateCount}개. 이 표본·시드 한 번의 결과로 방법의
        우수성이나 현장 효과를 판단할 수 없습니다.
      </p>
      <div
        className="reference-table-wrap"
        role="region"
        aria-label="후보별 계산 비교표"
        tabIndex={0}
      >
        <table className="reference-results search-results-table">
          <thead>
            <tr>
              <th scope="col">후보</th>
              <th scope="col">상태</th>
              <th scope="col">참고 비용</th>
              <th scope="col">점수</th>
              <th scope="col">원본 최고 대비</th>
              <th scope="col">평가체적 m³</th>
              <th scope="col">종료 저류 m³</th>
              <th scope="col">수지 오차</th>
              <th scope="col">자료</th>
            </tr>
          </thead>
          <tbody>
            {d.candidates.map((c) => (
              <tr key={c.id} className={candidate?.id === c.id ? 'search-selected' : ''}>
                <th scope="row">
                  <button
                    className="text-button"
                    aria-pressed={candidate?.id === c.id}
                    onClick={() => {
                      setView('candidate:' + c.id);
                      setCell(null);
                    }}
                  >
                    {searchArmNames[c.arm]} {c.ordinal}
                    <small>배치 보기</small>
                  </button>
                </th>
                <td>
                  {jobStateNames[c.state]}
                  {c.errorCode && <small className="comparison-error">계산 실패 · 검토 필요</small>}
                </td>
                <td>{won(c.costKrw)}</td>
                <td>{c.score === null ? '—' : c.score.toFixed(8)}</td>
                <td>
                  {c.score === null
                    ? '—'
                    : `${c.score - d.sourceBestScore > 0 ? '+' : ''}${(c.score - d.sourceBestScore).toFixed(8)}점`}
                </td>
                <td>{c.result ? format.format(c.result.strategy.accountedDischargeM3) : '—'}</td>
                <td>{c.result ? format.format(c.result.strategy.finalStorageM3) : '—'}</td>
                <td>
                  {c.result ? c.result.strategy.runoffContinuityPercent.toFixed(4) + '%' : '—'}
                </td>
                <td>
                  {c.state === 'SUCCEEDED' ? (
                    <a
                      className="comparison-bundle"
                      href={`/api/v1/research/searches/${d.id}/candidates/${c.id}/bundle`}
                    >
                      <Download size={13} />
                      재현 ZIP
                    </a>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="micro-note">
        점수는 시설 없는 기준안 대비 유출·잔여 저류 평가체적 감소율입니다. 음수는 기준안보다
        평가체적이 큰 결과입니다. 참고 단가는 현행 서울 공사 견적이 아닙니다.
      </p>
      <div className="search-inspection" aria-label="탐색 배치 검토">
        <div className="page-heading">
          <div>
            <h4>배치 검토 · {label}</h4>
            <p>
              {placements.length}개 시설 · {won(cost)} · 읽기 전용
            </p>
          </div>
          <label>
            검토할 배치
            <select
              aria-label="검토할 탐색 배치"
              value={view}
              onChange={(e) => {
                setView(e.target.value);
                setCell(null);
              }}
            >
              <optgroup label="생성 후보">
                {d.candidates.map((c) => (
                  <option key={c.id} value={'candidate:' + c.id}>
                    {searchArmNames[c.arm]} {c.ordinal}
                  </option>
                ))}
              </optgroup>
              <optgroup label="선택 원본">
                {g.sources.map((s) => (
                  <option key={s.sample.jobId} value={'source:' + s.sample.jobId}>
                    원본 {s.sample.jobId.slice(0, 8)} · {s.sample.score.toFixed(8)}점
                    {s.selected ? ' · 학습 포함' : ''}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
        </div>
        <div className="search-placement-layout">
          <div>
            <div className="search-map">
              {map ? (
                <MapViewport
                  map={map}
                  cells={lab.model.cells}
                  placements={placements}
                  selectedCell={cell}
                  onSelect={(id) => setCell(lab.model.cells.some((c) => c.id === id) ? id : null)}
                />
              ) : (
                <p className="empty-state">
                  공간자료를 불러오지 못했습니다. 시설 목록으로 배치를 확인할 수 있습니다.
                </p>
              )}
            </div>
            <p className="micro-note">
              공개 건물 경계 · 표고 평탄화·일부 높이 추정 · 설치 가능성 가정. 실제 지형·침수 깊이
              또는 시공 적합성 표시가 아닙니다.
            </p>
          </div>
          <div className="search-placement-list">
            <h4>시설과 면적</h4>
            {placements.map((p) => (
              <button
                key={p.cellId}
                aria-pressed={cell === p.cellId}
                onClick={() => setCell(p.cellId)}
              >
                <span>
                  <b>
                    {p.cellId} · {facilities[p.facilityType].name}
                  </b>
                  <small>{format.format(p.areaM2)} m²</small>
                </span>
                <span>{won(p.areaM2 * lab.model.unitCosts[p.facilityType])}</span>
              </button>
            ))}
            {!placements.length && <p>설치 시설 없음</p>}
          </div>
        </div>
        {candidate?.result && (
          <Hydrograph result={candidate.result} rainfall={lab.model.rainfall} designLabel={label} />
        )}
      </div>
      <details className="pattern-evidence">
        <summary>학습 표본·생성 조건·해시와 해석 범위</summary>
        <p>
          고유 배치 상위 {g.settings.topK}개와 경계 동점 · 경계 {g.cutoffScore.toFixed(8)}점. 구역별
          시설·면적 비율 범주 빈도에 1을 더해 추첨합니다. 구역 간 상호작용을 학습하는 모델이나 전역
          최적화가 아닙니다.
        </p>
        <code className="hash-value">모델 {d.modelHash}</code>
        <code className="hash-value">생성 계보 {d.provenanceHash}</code>
        <code className="hash-value">요청 {d.requestHash}</code>
        <ul>
          {g.arms.map((a) => (
            <li key={a.arm}>
              {searchArmNames[a.arm]}: {a.attempts}회 시도 · 빈 배치 {a.emptyRejected} · 원본 중복{' '}
              {a.sourceRejected} · 방법 내 중복 {a.duplicateRejected} 제외
            </li>
          ))}
        </ul>
        <ul>
          {g.sources.map((s) => (
            <li key={s.sample.jobId}>
              <b>
                {s.selected ? '학습 포함' : '상위 제외 또는 물리 중복'} ·{' '}
                {s.sample.score.toFixed(8)}점 · {won(s.sample.costKrw)}
              </b>
              <code className="hash-value">원본 계산 {s.sample.jobId}</code>
              <code className="hash-value">원본 입력 {s.sample.inputHash}</code>
              <code className="hash-value">물리 배치 {s.physicalHash}</code>
            </li>
          ))}
        </ul>
        <p>
          선택한 모든 원본의 현재 연구 동의가 필요합니다. 철회 후 후속 열람·다운로드가 차단됩니다.
          이미 내려받은 자료는 자동 회수되지 않습니다. 생성 계보 JSON과 후보 ZIP으로 추첨
          규칙·입력·계산을 다시 검증할 수 있습니다.
        </p>
      </details>
    </div>
  );
}
