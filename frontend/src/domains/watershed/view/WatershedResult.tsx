import { StorageLedger } from './StorageLedger';
import { WatershedSurfaceResult } from './WatershedSurfaceResult';
import { PumpOperation } from './PumpOperation';
import { WatershedPlayback } from './WatershedPlayback';
import { CisternReferenceCosts } from './CisternReferenceCosts';
import { conduitDimensions } from '../service/conduitDesign';
import type { WatershedJob } from '../dto/watershedDto';
import { WatershedCosts } from './WatershedCosts';
import { WatershedPeaks } from './WatershedPeaks';
import { WatershedFloodMap } from './WatershedFloodMap';
import { WatershedFloodDuration } from './WatershedFloodDuration';
import { networkNames } from '../service/watershedDesign';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';
import { RelativeImprovement } from '../../physics/view/RelativeImprovement';
import type { ReactNode } from 'react';
function NetworkReference({ coupled, children }: { coupled: boolean; children: ReactNode }) {
  if (!coupled) return <>{children}</>;
  return (
    <details className="watershed-network-reference">
      <summary>지표를 연결하지 않은 관망만의 참고 비교</summary>
      <p>
        위의 결합 계산과 경계 조건이 다릅니다. 아래 유량·월류·재생은 이 별도 계산의 결과입니다.
        지표에서 관망으로 되돌아오는 물은 포함하지 않습니다.
      </p>
      {children}
    </details>
  );
}
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
  const unmodeledCover = job.design.placements.some((p) => p.facilityType === 'RAINWATER_CISTERN');
  const comparable =
    !unmodeledCover &&
    job.state === 'SUCCEEDED' &&
    result?.numericalStatus === 'PASSED' &&
    result.signedReductionM3;
  return (
    <section className="watershed-result" aria-label="관망 계산 결과">
      <header>
        <h3>내 관망 설계 결과</h3>
        <span className="watershed-status">{jobLabels[job.state]}</span>
      </header>
      <time dateTime={job.createdAt}>{new Date(job.createdAt).toLocaleString('ko-KR')}</time>
      {job.design.surfaceConnection && !result && (
        <p>
          관망·지표의 기준안과 설계안을 함께 계산합니다. 작업이 끝나면 수심·출구 유량 비교가
          표시됩니다.
        </p>
      )}
      {result?.surfaceComparison && <WatershedSurfaceResult result={result.surfaceComparison} />}
      {job.design.locationReference && (
        <p>
          지도 위치 가정 {job.design.locationReference.assumedSourceCrs} · 제출 당시 원본 고정 · 원
          좌표계 미확인
        </p>
      )}
      <ul>
        {job.design.placements.map((p) => (
          <li key={p.id}>
            {p.subcatchmentId} · {networkNames[p.facilityType]} {number(p.areaM2)} m² · 처리{' '}
            {number(p.treatedImperviousM2)} m²
          </li>
        ))}
      </ul>
      {job.design.cistern && (
        <p>
          {job.design.cistern.subcatchmentId} · 빗물이용조 · 집수{' '}
          {number(job.design.cistern.captureAreaM2)} m² · 용량{' '}
          {number(job.design.cistern.footprintM2 * job.design.cistern.depthAreaCurve[1].depthM)} m³
          {' · '}
          {'mode' in job.design.cistern.drain
            ? '일반 배출 중지 · 비상 배수만 허용'
            : '관망 수두 기반 배수·역류'}
        </p>
      )}
      {job.design.cistern?.inletPipe && (
        <p>
          집수 연결관 · 길이 {number(job.design.cistern.inletPipe.lengthM)} m · 직경{' '}
          {number(job.design.cistern.inletPipe.diameterM)} m · Manning 조도{' '}
          {number(job.design.cistern.inletPipe.roughness)} · 관 바닥{' '}
          {number(job.design.cistern.inletPipe.upstreamInvertM)} →{' '}
          {number(job.design.cistern.inletPipe.downstreamInvertM)} m · 입구 월류 깊이{' '}
          {number(job.design.cistern.inletPipe.upstreamMaxDepthM)} m
        </p>
      )}
      {(['drain', 'overflow'] as const).map((kind) => {
        const pipe = job.design.cistern?.[kind === 'drain' ? 'drainPipe' : 'overflowPipe'];
        return (
          pipe && (
            <p key={kind}>
              {kind === 'drain' ? '일반 배수' : '비상 배수'} 연결관 · 길이 {number(pipe.lengthM)} m
              · 직경 {number(pipe.diameterM)} m · Manning 조도 {number(pipe.roughness)} · 관 바닥{' '}
              {number(pipe.upstreamInvertM)} → {number(pipe.downstreamInvertM)} m · 접속부 월류 깊이{' '}
              {number(pipe.upstreamMaxDepthM)} m
            </p>
          )
        );
      })}
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
      {job.design.pumps && (
        <p className="watershed-warning">펌프·압력관 공사비 미산정 · 참고 부분합 제외</p>
      )}
      {job.design.pumps?.placements.map((p) => (
        <p key={p.id}>
          {p.id} · 빗물펌프장 · {p.fromNode} → {p.toNode} · 기동/정지 {p.startDepthM}/{p.stopDepthM}{' '}
          m
        </p>
      ))}
      {job.design.storage && (
        <p className="watershed-warning">
          지하 저류조 공사비 미산정 · 참고 공사비 부분합에 포함되지 않습니다.
        </p>
      )}
      {job.design.cisternCosting && (
        <CisternReferenceCosts
          costing={job.design.cisternCosting}
          lifeCycleCosts={job.result?.cisternLifeCycleCosts}
        />
      )}
      {job.design.costing && (
        <WatershedCosts
          costing={job.design.costing}
          cisternQuoteIds={job.design.cisternCosting?.items.map((i) => i.placementId)}
          additionalUnpriced={[
            ...(job.design.storage?.placements ?? []).map((p) => ({
              id: p.id,
              name: '지하 저류조',
            })),
            ...(job.design.pumps?.placements ?? []).map((p) => ({
              id: p.id,
              name: '빗물펌프장·압력관',
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
          <NetworkReference coupled={Boolean(result.surfaceComparison)}>
            <p
              className={
                result.numericalStatus === 'PASSED' ? 'watershed-pass' : 'watershed-warning'
              }
            >
              {result.numericalStatus === 'PASSED'
                ? '수치 검사 통과 · 현장 정확도 검증과 구분'
                : '수치 검사 실패 · 효과 비교 보류'}
            </p>
            <PumpOperation job={job} />
            {unmodeledCover && (
              <p role="status">
                덮개 강우의 별도 배수 경로가 없는 구형 이용조 설계입니다. 원 계산값은 보관하며 효과
                비교를 보류합니다.
              </p>
            )}
            {job.state === 'SUCCEEDED' &&
              result.networkLayout &&
              result.cases.every((c) => c.complete) && (
                <WatershedPlayback
                  key={job.id}
                  jobId={job.id}
                  layout={result.networkLayout.layout}
                />
              )}
            {strategy?.connectedStorage && (
              <StorageLedger title="저류조 물수지" summary={strategy.connectedStorage} />
            )}
            {strategy?.networkCistern && (
              <StorageLedger title="빗물이용조 물수지" summary={strategy.networkCistern} />
            )}
            <WatershedFloodDuration
              metric={result.metricComparison?.metrics.find(
                (m) => m.id === 'networkFloodingSeconds'
              )}
              window={result.metricComparison?.window}
              canCompare={Boolean(comparable)}
            />
            {comparable && (
              <>
                {result.networkLayout && baseline?.nodeFlooding && strategy?.nodeFlooding && (
                  <WatershedFloodMap
                    key={job.id}
                    layout={result.networkLayout.layout}
                    baseline={baseline.nodeFlooding}
                    strategy={strategy.nodeFlooding}
                  />
                )}
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
                      <RelativeImprovement
                        metric={result.metricComparison?.metrics.find(
                          (m) =>
                            m.id ===
                            (metric === 'floodingM3' ? 'networkFloodingM3' : 'networkOutflowM3')
                        )}
                      />
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
                    metric={result.metricComparison?.metrics.find((m) => m.id === 'networkPeakM3s')}
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
                  {c.execution && (
                    <p>
                      {c.execution.mode === 'REUSED'
                        ? '동일 조건의 검증된 계산 결과 재사용'
                        : '이번 요청에서 새로 계산'}
                    </p>
                  )}
                  {c.convergence && (
                    <p>비수렴 {c.convergence.nonConvergedSteps.toLocaleString('ko-KR')}회</p>
                  )}
                  {c.totals && <p>관망 물수지 잔차 {number(c.totals.balanceResidualM3)} m³</p>}
                  {c.calendarShortfallSeconds !== undefined && (
                    <p>
                      입력 종료 시각보다 {number(c.calendarShortfallSeconds)}초 짧은 엔진 계산 창
                    </p>
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
                        표면 수심 {number(f.surfaceDepthMm)} mm · 최종 저류{' '}
                        {number(f.finalStorageM3)} m³
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
          </NetworkReference>
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
