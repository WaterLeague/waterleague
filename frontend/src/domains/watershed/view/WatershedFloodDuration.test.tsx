import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/public-network-flood-duration-v1.json';
import { watershedMetricsDto } from '../dto/watershedMetricsDto';
import { comparedMetricDto, metricComparisonDto } from '../../physics/dto/metricComparisonDto';
import { WatershedFloodDuration } from './WatershedFloodDuration';

it('실제 관망 응답의 동시 월류 시간과 증가한 효과 보존', () => {
  const comparison = metricComparisonDto.parse(fixture.comparison);
  const metric = comparedMetricDto.parse(fixture.metric);
  const before = watershedMetricsDto.parse(fixture.baseline);
  const after = watershedMetricsDto.parse(fixture.strategy);
  expect(metric.baseline).toBe(before.floodingDuration!.floodingSeconds);
  expect(metric.strategy).toBe(after.floodingDuration!.floodingSeconds);
  expect(metric.signedImprovement).toBeCloseTo(-2.17, 8);
  const html = renderToStaticMarkup(
    <WatershedFloodDuration metric={metric} window={comparison.window} />
  );
  expect(html).toContain('2.17초 증가');
  expect(html).toContain('보조 개선율 -0.004978%');
  expect(html).toContain('번만 계산하며');
  expect(html).toContain('data-direction="increase"');
  const pending = renderToStaticMarkup(
    <WatershedFloodDuration metric={metric} window={comparison.window} canCompare={false} />
  );
  expect(pending).toContain('월류 시간 효과 비교 보류');
  expect(pending).not.toContain('2.17초 증가');
});

it('월류 시간의 평가 경계·기간·방법·수치·단계 수 변조 거부', () => {
  for (const change of [
    'start',
    'end',
    'coverage',
    'method',
    'nan',
    'negative',
    'over',
    'steps',
    'complete',
  ]) {
    const raw = structuredClone(fixture.strategy);
    const duration = raw.floodingDuration;
    if (change === 'start') duration.startSeconds = 1;
    if (change === 'end') duration.endSeconds += 1;
    if (change === 'coverage') duration.coveredSeconds -= 1;
    if (change === 'method') duration.method = 'SUM_NODE_SECONDS';
    if (change === 'nan') duration.floodingSeconds = Number.NaN;
    if (change === 'negative') duration.floodingSeconds = -1;
    if (change === 'over') duration.floodingSeconds = duration.coveredSeconds + 1;
    if (change === 'steps') duration.nativeSteps -= 1;
    if (change === 'complete') duration.complete = false;
    expect(watershedMetricsDto.safeParse(raw).success, change).toBe(false);
  }
});

it('실제 0초·과거 미수집·계산 실패를 서로 다른 상태로 표시', () => {
  const zero = comparedMetricDto.parse({
    ...fixture.metric,
    baseline: 0,
    strategy: 0,
    signedImprovement: 0,
    relativeImprovementPercent: null,
    relativeStatus: 'ZERO_BASELINE',
  });
  const html = renderToStaticMarkup(<WatershedFloodDuration metric={zero} />);
  expect(html).toContain('0초 변화 없음');
  expect(html).toContain('기준값 0 · 개선율 미산정');
  const old = renderToStaticMarkup(<WatershedFloodDuration />);
  expect(old).toContain('관망 전체 월류 시간 자료가 없습니다');
  expect(old).not.toContain('0초');
  for (const reason of [
    'NUMERICAL_FAILURE',
    'BOUNDARY_MISMATCH',
    'INCOMPLETE_RUN',
    'UNMODELED_COVER_RAIN',
  ]) {
    const withheld = comparedMetricDto.parse({
      ...fixture.metric,
      status: 'WITHHELD',
      reason,
      signedImprovement: null,
      relativeImprovementPercent: null,
      relativeStatus: 'NOT_COMPARABLE',
    });
    const failed = renderToStaticMarkup(<WatershedFloodDuration metric={withheld} />);
    expect(failed).toContain('월류 시간 효과 비교 보류');
    expect(failed).toContain('기준 43,592초');
    expect(failed).not.toContain('보조 개선율');
    expect(failed).not.toContain('2.17초 증가');
  }
});
