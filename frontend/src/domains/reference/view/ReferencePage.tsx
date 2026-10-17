import { useState } from 'react';
import { ArrowUpRight, Download } from 'lucide-react';
import type { Lab } from '../../game/entity/game';
import type { ReferencePlan } from '../entity/reference';
import { useReference } from '../controller/useReference';
import { canCopyReference } from '../service/referenceService';
import { facilities, format, won } from '../../game/service/gameService';
import { rainDate } from '../../game/view/RainfallSelector';

export function ReferencePage({
  lab,
  busy,
  onCopy,
}: {
  lab: Lab;
  busy: boolean;
  onCopy: (plan: ReferencePlan) => void;
}) {
  const { data, error, retry } = useReference(lab.modelHash);
  const [index, setIndex] = useState(0);
  if (error)
    return (
      <section className="full-page">
        <p role="alert">{error}</p>
        <button className="outline-button" onClick={retry}>
          다시 불러오기
        </button>
      </section>
    );
  if (!data)
    return (
      <section className="full-page" role="status">
        CPU 기준안을 불러오는 중입니다.
      </section>
    );
  const { report } = data,
    plan = report.plans[index],
    training = plan.evaluations.find((e) => e.modelHash === report.trainingModelHash)!;
  return (
    <section className="full-page reference-page">
      <div className="page-eyebrow">
        COMPUTED REFERENCE <span>SWMM · 탐색 계산</span>
      </div>
      <h1>
        계산이 찾은 배치,
        <br />
        다른 비에도 통할까.
      </h1>
      <p className="lead">
        하나의 비에서 배치를 고른 뒤, 다른 강우 조건에서 다시 계산했습니다.
        <br />
        예산과 탐색 범위를 확인하고, 내 설계의 출발점으로 삼아 보세요.
      </p>
      <div className="reference-method">
        <span>{report.mapTitle ?? 'OSM 초기 지도'} · 공간 버전별 계산 기준안</span>
        <b>고유 후보 {format.format(report.uniqueCandidateEvaluations)}개 계산</b>
        <span>
          {training.rainfall.stationName} · {rainDate(training.rainfall.start)} ·{' '}
          {format.format(training.rainfall.totalDepthMm)}mm에서 배치 선택
        </span>
        <small>
          10m²씩 늘려 추가 비용당 평가체적 저감이 큰 배치 채택. 전역 최적해·현장 검증 결과가
          아닙니다.
        </small>
      </div>
      <div className="reference-budget" role="group" aria-label="CPU 탐색 예산 상한">
        {report.plans.map((p, i) => (
          <button
            key={p.id}
            aria-pressed={i === index}
            className={i === index ? 'active' : ''}
            onClick={() => setIndex(i)}
          >
            <small>예산 상한</small>
            {won(p.budget)}
          </button>
        ))}
      </div>
      <div className="reference-plan">
        <div className="reference-numbers">
          <span>확정 배치 비용</span>
          <strong>{won(plan.cost)}</strong>
          <p>상한에서 {won(plan.budget - plan.cost)} 남김</p>
          <dl>
            <div>
              <dt>선택 단계</dt>
              <dd>{plan.stages.length}회</dd>
            </div>
            <div>
              <dt>후보 평가 요청</dt>
              <dd>
                {plan.candidateEvaluations}회 <small>중복 캐시 포함</small>
              </dd>
            </div>
            <div>
              <dt>선택된 강우 창의 점수 범위</dt>
              <dd>
                {format.format(plan.sampleScoreRange.min)}–
                {format.format(plan.sampleScoreRange.max)} <small>/ 100</small>
              </dd>
            </div>
          </dl>
          <p className="reference-stop">
            {plan.stopReason === 'EVALUATION_LIMIT'
              ? '후보 평가 상한 도달로 탐색 종료'
              : '예산 안에서 수치 허용오차보다 큰 추가 개선이 없어 탐색 종료'}
          </p>
          <button
            className="solid-button"
            disabled={busy || !canCopyReference(lab, plan)}
            onClick={() => onCopy(plan)}
          >
            현재 강우의 내 설계로 복사 <ArrowUpRight size={15} />
          </button>
          <small>새 설계로 열립니다. 저장·계산·공개 제출은 직접 진행합니다.</small>
        </div>
        <div className="reference-placement">
          <h2>배치 명세</h2>
          <p>아래 면적은 모델 내 배치량이며 현장 시공 가능 면적의 검증값이 아닙니다.</p>
          <table>
            <thead>
              <tr>
                <th scope="col">구역</th>
                <th scope="col">시설</th>
                <th scope="col">면적</th>
                <th scope="col">비용</th>
              </tr>
            </thead>
            <tbody>
              {plan.placements.map((p) => (
                <tr key={p.cellId}>
                  <th scope="row">{p.cellId}</th>
                  <td>{facilities[p.facilityType].name}</td>
                  <td>{format.format(p.areaM2)}m²</td>
                  <td>{won(p.areaM2 * lab.model.unitCosts[p.facilityType])}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <details>
            <summary>선택 과정 {plan.stages.length}단계</summary>
            <ol className="reference-stages">
              {plan.stages.map((s, i) => (
                <li key={i}>
                  <b>
                    {i + 1}단계 · {won(s.cost)}
                  </b>
                  <span>
                    평가체적 {format.format(s.accountedDischargeM3)}m³ · 직전 단계보다{' '}
                    {format.format(s.incrementReductionM3)}m³ 감소
                  </span>
                  <small>
                    {s.placements
                      .map((p) => `${p.cellId} ${facilities[p.facilityType].short} ${p.areaM2}m²`)
                      .join(' · ')}
                  </small>
                </li>
              ))}
            </ol>
          </details>
        </div>
      </div>
      <div className="reference-results-heading">
        <div>
          <h2>같은 배치, 네 가지 강우 입력</h2>
          <p>
            평가체적은 유출량과 종료 시 남은 저류량을 함께 반영합니다. 점수 범위는 신뢰구간이
            아닙니다.
          </p>
        </div>
        <span>단위 m³ · 점수 / 100</span>
      </div>
      <div
        className="reference-table-wrap"
        role="region"
        aria-label="CPU 기준안 강우별 계산 결과"
        tabIndex={0}
      >
        <table className="reference-results">
          <thead>
            <tr>
              <th scope="col">관측 조건</th>
              <th scope="col">비교 역할</th>
              <th scope="col">점수</th>
              <th scope="col">기준 평가체적</th>
              <th scope="col">배치 평가체적</th>
              <th scope="col">종료 저류량</th>
              <th scope="col">수지 오차</th>
            </tr>
          </thead>
          <tbody>
            {plan.evaluations.map((e) => (
              <tr key={e.modelHash} className={e.modelHash === lab.modelHash ? 'current' : ''}>
                <th scope="row">
                  {e.rainfall.stationName} · {rainDate(e.rainfall.start)}
                  <small>
                    {format.format(e.rainfall.totalDepthMm)}mm
                    {e.modelHash === lab.modelHash ? ' · 현재 선택' : ''}
                  </small>
                </th>
                <td>
                  {e.role === 'SEARCH_INPUT'
                    ? '배치 선택에 사용'
                    : e.rainfall.stationId === training.rainfall.stationId
                      ? '배치 확정 후 비교'
                      : '같은 날짜의 관측소 비교'}
                </td>
                <td>
                  <b>{format.format(e.score)}</b>
                </td>
                <td>{format.format(e.baseline.accountedDischargeM3)}</td>
                <td>{format.format(e.strategy.accountedDischargeM3)}</td>
                <td>{format.format(e.strategy.finalStorageM3)}</td>
                <td>{e.strategy.runoffContinuityPercent.toFixed(4)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer className="reference-footer">
        <div>
          <b>사람의 순위와 별도인 계산 기준안</b>
          <p>
            사람마다 시도 횟수가 달라 직접적인 경쟁 순위로 사용하지 않습니다. 모든 결과는 현재
            토양·배수·시설 가정에 한정됩니다.
          </p>
          <details>
            <summary>계산 근거와 해석 범위</summary>
            <ul>
              {report.limitations.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            <p>
              결과 SHA-256 <code>{data.reportHash}</code>
            </p>
          </details>
        </div>
        <div className="reference-downloads">
          <a
            className="outline-button"
            href={`/api/v1/references/source?modelHash=${lab.modelHash}`}
          >
            <Download size={15} /> 계산 결과 JSON
          </a>
          <a
            className="outline-button"
            href={`/api/v1/references/ledger?modelHash=${lab.modelHash}`}
          >
            <Download size={15} /> 후보 원장 JSON
          </a>
        </div>
      </footer>
    </section>
  );
}
