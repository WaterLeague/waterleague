import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/rawMetricCases.json';
import { comparedMetricDto } from '../dto/metricComparisonDto';
import { runoffComparisonDto } from '../dto/runoffComparisonDto';
import native from './fixtures/nativeDesignContract.json';
import { RelativeImprovement } from './RelativeImprovement';

it('Python 수치 진단의 0·음수·100% 초과·미소 악화·결측 상태 교차 대조', () => {
  expect(fixture.classification).toBe('NUMERICAL_TEST_ONLY_NOT_OBSERVATIONS');
  for (const row of fixture.cases)
    expect(comparedMetricDto.safeParse(row.metric).success).toBe(true);
  const byId = (id: string) =>
    comparedMetricDto.parse(fixture.cases.find((r) => r.id === id)!.metric);
  expect(byId('over-100').relativeImprovementPercent).toBe(150);
  expect(byId('tiny-negative').signedImprovement).toBe(-1e-18);
  expect(byId('zero-baseline').relativeImprovementPercent).toBeNull();
  expect(byId('not-measured').baseline).toBeNull();
});

it('미소 악화 0 치환·다른 단위·비율 절단·보류 효과 위조 거부', () => {
  const tiny = fixture.cases.find((r) => r.id === 'tiny-negative')!.metric;
  const over = fixture.cases.find((r) => r.id === 'over-100')!.metric;
  const missing = fixture.cases.find((r) => r.id === 'not-measured')!.metric;
  for (const value of [
    { ...tiny, signedImprovement: 0 },
    { ...tiny, relativeImprovementPercent: 0 },
    { ...over, relativeImprovementPercent: 100 },
    { ...tiny, unit: 'kg' },
    { ...missing, baseline: 0 },
    { ...missing, signedImprovement: 0 },
  ])
    expect(comparedMetricDto.safeParse(value).success).toBe(false);
});

it('0 기준은 비율 미산정, 음의 개선율과 100% 초과 원값 표시', () => {
  const html = (id: string) =>
    renderToStaticMarkup(
      <RelativeImprovement
        metric={comparedMetricDto.parse(fixture.cases.find((r) => r.id === id)!.metric)}
      />
    );
  expect(html('zero-baseline')).toContain('기준값 0 · 개선율 미산정');
  expect(html('over-100')).toContain('150%');
  expect(html('tiny-negative')).toContain('-100%');
});

it('현재 스키마에서 원 지표 비교 계약 전체 누락 거부', () => {
  expect(runoffComparisonDto.safeParse(native.comparison).success).toBe(true);
  expect(runoffComparisonDto.safeParse({ ...native.comparison, schemaVersion: 2 }).success).toBe(
    false
  );
});
