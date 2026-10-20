import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import network from './fixtures/rawMetrics-network-v1.json';
import withheld from './fixtures/rawMetrics-withheld-v1.json';
import native from './fixtures/rawMetrics-native-v1.json';
import { runoffComparisonDto } from '../dto/runoffComparisonDto';
import { RunoffComparison } from './RunoffComparison';
import { watershedJobDto, watershedResultDto } from '../../watershed/dto/watershedDto';
import { WatershedResult } from '../../watershed/view/WatershedResult';

it('실제 원형 워커의 평가체적 원값·선행 제외·서버 미산정 사유와 보조 비율 표시', () => {
  const value = runoffComparisonDto.parse(native.comparison);
  expect(value.schemaVersion).toBe(2);
  const primary = value.metricComparison!.metrics.find((m) => m.id === 'surfaceAccountedVolumeM3')!;
  expect(primary.signedImprovement).toBe(value.accountedReductionM3);
  expect(value.metricComparison!.metrics.find((m) => m.id === 'networkFloodingM3')!.reason).toBe(
    'NO_CONVEYANCE_NETWORK'
  );
  const html = renderToStaticMarkup(<RunoffComparison value={value} contract={native.contract} />);
  expect(html).toContain('평가체적 차이');
  expect(html).toContain('보조 개선율');
  expect(html).toContain('선행 기간 제외');
  expect(html).not.toContain('근거를 확인하지 못했습니다');
});

it('실제 소유자 HTTP 응답의 원 방류 악화·보조 비율과 종합점수 없음 유지', () => {
  expect(network.evidence).toBe('ACTUAL_AUTHENTICATED_HTTP_WORKER_DTO_PROJECTION');
  const job = watershedJobDto.parse(network.value);
  const assessment = job.result!.metricComparison!;
  expect(assessment.primaryMetricId).toBeNull();
  expect(assessment.compositeScore).toBeNull();
  expect(assessment.relativeUsedForRanking).toBe(false);
  expect(
    assessment.metrics.find((m) => m.id === 'networkOutflowM3')!.signedImprovement
  ).toBeLessThan(0);
  const html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('보조 개선율');
  expect(html).toContain('증가');
  expect(html).not.toContain('덮개 강우의 별도 배수 경로가 없는 구형 이용조');
});

it('실제 구형 RB 원 지표·비용 기록 보존과 수치 통과/효과 보류 분리', () => {
  const value = watershedResultDto.parse(withheld.value);
  expect(value.numericalStatus).toBe('PASSED');
  expect(value.signedReductionM3).toBeNull();
  expect(value.signedPeakReductionM3s).toBeNull();
  const metrics = value.metricComparison!.metrics.filter((m) => m.status === 'WITHHELD');
  expect(metrics).toHaveLength(3);
  expect(
    metrics.every(
      (m) => m.reason === 'UNMODELED_COVER_RAIN' && m.baseline !== null && m.strategy !== null
    )
  ).toBe(true);
  expect(value.cisternCosting).toBeDefined();
});

it('현재 결과의 전체 비교 계약 삭제·다른 평가 창·원값 변조·보류 개선량 주입 거부', () => {
  const job = watershedJobDto.parse(network.value);
  const missing = structuredClone(job);
  delete missing.result!.metricComparison;
  expect(watershedJobDto.safeParse(missing).success).toBe(false);
  const raw = structuredClone(job);
  raw.result!.metricComparison!.metrics.find((m) => m.id === 'networkOutflowM3')!.baseline! += 1;
  expect(watershedJobDto.safeParse(raw).success).toBe(false);
  const other = structuredClone(job);
  const window = other.result!.metricComparison!.window!;
  if (window.kind === 'ELAPSED_SECONDS') window.end -= 1;
  expect(watershedJobDto.safeParse(other).success).toBe(false);
  expect(
    watershedResultDto.safeParse({
      ...withheld.value,
      signedReductionM3: { floodingM3: 0, outflowM3: 0 },
    }).success
  ).toBe(false);
});
