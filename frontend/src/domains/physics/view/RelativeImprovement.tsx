import type { ComparedMetric } from '../dto/metricComparisonDto';
import { physicalAmount } from '../service/physicalValueFormat';

export function RelativeImprovement({ metric }: { metric?: ComparedMetric }) {
  if (!metric) return null;
  return (
    <small>
      {metric.relativeStatus === 'COMPUTED'
        ? `보조 개선율 ${physicalAmount(metric.relativeImprovementPercent!)}%`
        : metric.relativeStatus === 'ZERO_BASELINE'
          ? '기준값 0 · 개선율 미산정'
          : metric.relativeStatus === 'NEGATIVE_BASELINE'
            ? '음수 기준값 · 개선율 미산정'
            : metric.relativeStatus === 'NUMERIC_RANGE_EXCEEDED'
              ? '개선율 표현 범위 초과 · 절대 차이 참조'
              : '개선율 비교 보류'}
    </small>
  );
}
