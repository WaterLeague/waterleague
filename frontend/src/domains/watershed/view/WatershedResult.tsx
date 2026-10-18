import { CisternReferenceCosts } from './CisternReferenceCosts';
import { conduitDimensions } from '../service/conduitDesign';
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
      {job.design.conduits?.placements.map((p) => (
        <div key={p.id} className="watershed-facility-state">
          <strong>{p.conduitId} · 배수관·암거 개량</strong>
          <p>원본: {conduitDimensions(p.original)}</p>
          <p>설계: {conduitDimensions(p)}</p>
          <p>개량 공사비 미산정 · 참고 부분합 제외</p>
        </div>
      ))}
      {job.design.storage?.placements.map((p) => (
        <p key={p.id}>
          {p.id} · 지하 저류조 · {p.inlet.nodeId} → {p.drain.nodeId} · 설계 용량{' '}
          {number(p.depthAreaCurve[1].depthM * p.depthAreaCurve[1].areaM2)} m³
        </p>
      ))}
      {job.design.storage && (
        <p className="watershed-warning">
          지하 저류조 공사비 미산정 · 참고 공사비 부분합에 포함되지 않습니다.
        </p>
      )}
      {job.design.cisternCosting && <CisternReferenceCosts costing={job.design.cisternCosting} />}
      {job.design.costing && (
        <WatershedCosts
          costing={job.design.costing}
          cisternQuoteIds={job.design.cisternCosting?.items.map((i) => i.placementId)}
          additionalUnpriced={[
            ...(job.design.storage?.placements ?? []).map((p) => ({
              id: p.id,
              name: '지하 저류조',
            })),
            ...(job.design.conduits?.placements ?? []).map((p) => ({
              id: p.id,
              name: '배수관·암거 개량',
            })),
          ]}
        />
      )}
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
          {strategy?.connectedStorage && (
            <div aria-label="저류조 물수지">
              <h3>저류조 물수지</h3>
              {strategy.connectedStorage.wholeRunLedger.facilities.map((f) => (
                <div key={f.id} className="watershed-facility-state">
                  <strong>
                    {f.id} · 설계 용량 {number(f.capacityM3)} m³
                  </strong>
                  <p>
                    초기 {number(f.initialStorageM3)} → 최종 저류 {number(f.finalStorageM3)} m³
                  </p>
                  <p>
                    유입 {number(f.inflowM3)} m³ · 유출·월류 {number(f.outflowIncludingFloodingM3)}{' '}
                    m³
                  </p>
                  <p>미연결 지표 월류 {number(f.floodingM3)} m³</p>
                  <p>
                    물수지 잔차 {number(f.balanceResidualM3)} m³ · 허용{' '}
                    {number(f.allowedResidualM3)} m³ ·{' '}
                    {f.numericalStatus === 'PASSED' ? '통과' : '실패'}
                  </p>
                </div>
              ))}
              <p>
                이 체적은 관망 전체 물수지에 포함됩니다. 수지 실패나 지표로 넘친 물의 미연결이
                있으면 효과 비교를 보류합니다.
              </p>
            </div>
          )}
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
                {c.conduits?.map((p) => (
                  <p key={p.id}>
                    {p.conduitId} · 계산 종료 유량 {number(p.flowM3s)} m³/s · 내부 수심{' '}
                    {number(p.depthM)} m · 시작 후 {number(c.conduitStateTimeSeconds!)}초. 양수는
                    관로 정의 방향이며 첨두 유량이 아닙니다.
                  </p>
                ))}
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
