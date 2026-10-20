import type { ComparedMetric, MetricComparison } from '../../physics/dto/metricComparisonDto';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';
import { RelativeImprovement } from '../../physics/view/RelativeImprovement';

export function WatershedFloodDuration({
  metric,
  window,
  canCompare = true,
}: {
  metric?: ComparedMetric;
  window?: MetricComparison['window'];
  canCompare?: boolean;
}) {
  const difference = metric?.signedImprovement;
  const comparable = canCompare && metric?.status === 'COMPARABLE' && difference != null;
  return (
    <section aria-label="관망 전체 월류 발생 시간">
      <h3>관망 전체 월류 발생 시간</h3>
      {!metric || metric.status === 'UNAVAILABLE' ? (
        <p>이 기록에는 관망 전체 월류 시간 자료가 없습니다.</p>
      ) : (
        <div
          className="watershed-effect"
          data-direction={
            comparable
              ? difference < 0
                ? 'increase'
                : difference > 0
                  ? 'decrease'
                  : 'equal'
              : undefined
          }
        >
          {comparable ? (
            <strong>
              {number(Math.abs(difference))}초{' '}
              {difference < 0 ? '증가' : difference > 0 ? '감소' : '변화 없음'}
            </strong>
          ) : (
            <strong>월류 시간 효과 비교 보류</strong>
          )}
          <small>
            기준 {metric.baseline === null ? '자료 없음' : `${number(metric.baseline)}초`} → 설계{' '}
            {metric.strategy === null ? '자료 없음' : `${number(metric.strategy)}초`}
          </small>
          {comparable && <RelativeImprovement metric={metric} />}
        </div>
      )}
      {window?.kind === 'ELAPSED_SECONDS' && (
        <small>
          계산 시작 후 {number(window.start)}~{number(window.end)}초 구간
        </small>
      )}
      <p>
        한 곳 이상에서 관망 밖으로 물이 넘친 시간입니다. 여러 지점에서 동시에 넘친 시간은 한 번만
        계산하며, 지표에 물이 고인 시간은 포함하지 않습니다.
      </p>
    </section>
  );
}
