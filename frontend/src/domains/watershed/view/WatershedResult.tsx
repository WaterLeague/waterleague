import type { WatershedJob } from '../dto/watershedDto';
import { WatershedCosts } from './WatershedCosts';
import { WatershedPeaks } from './WatershedPeaks';
import { networkNames } from '../service/watershedDesign';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';
const totalAmount = (value: number) =>
  value !== 0 && Math.abs(value) < 0.000001
    ? number(value)
    : value.toLocaleString('ko-KR', { maximumFractionDigits: 6 });
export const jobLabels = {
  QUEUED: '계산 대기',
  RUNNING: '관망 계산 중',
  SUCCEEDED: '보고서 생성',
  FAILED: '계산 실패',
  REJECTED: '요청 거부',
};
export function WatershedResult({ job }: { job: WatershedJob }) {
  const result = job.result;
  const baseline = result?.cases.find((c) => c.id === 'baseline');
  const strategy = result?.cases.find((c) => c.id === 'strategy');
  const comparable =
    job.state === 'SUCCEEDED' && result?.numericalStatus === 'PASSED' && result.signedReductionM3;
  return (
    <section className="watershed-result" aria-label="관망 계산 결과">
      <header>
        <h3>내 관망 설계 결과</h3>
        <span className="watershed-status">{jobLabels[job.state]}</span>
      </header>
      <time dateTime={job.createdAt}>{new Date(job.createdAt).toLocaleString('ko-KR')}</time>
      <ul>
        {job.design.placements.map((p) => (
          <li key={p.id}>
            {p.subcatchmentId} · {networkNames[p.facilityType]} {number(p.areaM2)} m² · 처리{' '}
            {number(p.treatedImperviousM2)} m²
          </li>
        ))}
      </ul>
      {job.design.costing && <WatershedCosts costing={job.design.costing} />}
      {(job.state === 'QUEUED' || job.state === 'RUNNING') && (
        <p role="status">
          시설 없는 기준안과 설계안을 같은 공개 관망에서 계산합니다. 창을 닫아도 서버 계산은
          계속됩니다.
        </p>
      )}
      {(job.state === 'FAILED' || job.state === 'REJECTED') && (
        <p role="alert">계산을 완료하지 못했습니다. 효과는 표시하지 않습니다.</p>
      )}
      {result && (
        <>
          <p
            className={result.numericalStatus === 'PASSED' ? 'watershed-pass' : 'watershed-warning'}
          >
            {result.numericalStatus === 'PASSED'
              ? '수치 검사 통과 · 현장 정확도 검증과 구분'
              : '수치 검사 실패 · 효과 비교 보류'}
          </p>
          {comparable && (
            <>
              {(['floodingM3', 'outflowM3'] as const).map((metric) => {
                const reduction = comparable[metric];
                return (
                  <div
                    className="watershed-effect"
                    key={metric}
                    data-direction={
                      reduction < 0 ? 'increase' : reduction > 0 ? 'decrease' : 'equal'
                    }
                  >
                    <span>{metric === 'floodingM3' ? '관망 월류량' : '외부 방류량'}</span>
                    <strong>
                      {number(Math.abs(reduction))} m³{' '}
                      {reduction < 0 ? '증가' : reduction > 0 ? '감소' : '변화 없음'}
                    </strong>
                    <small>기준 − 설계: {number(reduction)} m³</small>
                    <small>
                      기준 {totalAmount(baseline!.totals![metric])} → 설계{' '}
                      {totalAmount(strategy!.totals![metric])} m³
                    </small>
                  </div>
                );
              })}
              <p>
                월류량은 지표 침수 깊이가 아닙니다. 방류량의 변화만으로 하류 침수 위험이나 첨두
                감소를 판단할 수 없습니다.
              </p>
              {baseline?.evaluationMetrics &&
              strategy?.evaluationMetrics &&
              result.signedPeakReductionM3s != null ? (
                <WatershedPeaks
                  baseline={baseline.evaluationMetrics}
                  strategy={strategy.evaluationMetrics}
                  reduction={result.signedPeakReductionM3s}
                />
              ) : (
                <p>이전 계산 기록에는 출구 첨두가 수집되지 않았습니다.</p>
              )}
            </>
          )}
          <details>
            <summary>계산 상태·시설 최종 상태</summary>
            {result.cases.map((c) => (
              <div key={c.id} className="watershed-case">
                <strong>
                  {c.id === 'baseline' ? '시설 없는 기준안' : '시설 설계안'} ·{' '}
                  {c.numericalStatus === 'PASSED' ? '수치 검사 통과' : '실패'}
                </strong>
                {c.convergence && (
                  <p>비수렴 {c.convergence.nonConvergedSteps.toLocaleString('ko-KR')}회</p>
                )}
                {c.totals && <p>관망 물수지 잔차 {number(c.totals.balanceResidualM3)} m³</p>}
                {c.calendarShortfallSeconds !== undefined && (
                  <p>입력 종료 시각보다 {number(c.calendarShortfallSeconds)}초 짧은 엔진 계산 창</p>
                )}
                {c.facilities?.map((f) => (
                  <div className="watershed-facility-state" key={f.swmmId}>
                    <strong>
                      {f.subcatchmentId} · {f.swmmId.replace(/^WL_/, '')} · {number(f.areaM2)} m²
                    </strong>
                    <p>
                      표면 수심 {number(f.surfaceDepthMm)} mm · 최종 저류 {number(f.finalStorageM3)}{' '}
                      m³
                    </p>
                    {f.soilMoisture != null && <p>토양수분 {number(f.soilMoisture * 100)}%</p>}
                    <p>
                      시설 수지 잔차 {number(f.balanceResidualM3)} m³ ·{' '}
                      {f.numericalStatus === 'PASSED' ? '통과' : '실패'}
                    </p>
                  </div>
                ))}
              </div>
            ))}
            <p>
              SWMM {result.engine.engineVersion} · {result.numericalProfile.id}
            </p>
          </details>
          <details>
            <summary>이 결과의 적용 범위·가정</summary>
            <ul>
              {result.limitations.map((text, i) => (
                <li key={i}>{text}</li>
              ))}
            </ul>
          </details>
          {job.state === 'SUCCEEDED' && (
            <a
              className="watershed-download"
              href={`/api/v1/watersheds/${encodeURIComponent(job.id)}/bundle`}
              download
            >
              입력·결과·재현 코드 ZIP 다운로드
            </a>
          )}
        </>
      )}
    </section>
  );
}
