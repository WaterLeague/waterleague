import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/public-surface-comparison-v1.json';
import httpFixture from './fixtures/public-surface-job-v1.json';
import failedFixture from './fixtures/public-surface-failed-job-v1.json';
import refinedFixture from './fixtures/public-surface-job-v2.json';
import { watershedSurfaceComparisonDto } from '../dto/watershedSurfaceDto';
import { watershedJobDto } from '../dto/watershedDto';
import { WatershedSurfaceResult } from './WatershedSurfaceResult';
import { WatershedResult } from './WatershedResult';

it('1초 수문 간격의 실제 세 시설 회원 결과와 저장된 v2 설계를 함께 표시', () => {
  const job = watershedJobDto.parse(refinedFixture);
  const comparison = job.result?.surfaceComparison;
  expect(job.design.surfaceConnection?.id).toBe('seocho-surface-design-v2');
  expect(job.design.placements).toHaveLength(3);
  expect(comparison?.numericalStatus).toBe('PASSED');
  expect(comparison?.cases.map((c) => c.durationSeconds)).toEqual([86339, 86339]);
  expect(Object.keys(comparison?.signedReduction ?? {})).toHaveLength(6);
  const html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('유출 계산 간격 1초');
  expect(html).not.toContain('수치 검증 실패');
});

it('실제 식생수로 수지 실패 응답은 원 지표를 보존하고 여섯 개선량을 모두 보류', () => {
  const job = watershedJobDto.parse(failedFixture);
  expect(job.result?.surfaceComparison?.numericalStatus).toBe('FAILED');
  expect(job.result?.surfaceComparison?.signedReduction).toBeNull();
  const html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('수치 검증 실패');
  expect(html.match(/<td>보류<\/td>/g)).toHaveLength(6);
  expect(html).toContain('유출 계산 간격 300초');
  const changed = structuredClone(failedFixture);
  changed.design.surfaceConnection.id = 'seocho-surface-design-v2';
  expect(watershedJobDto.safeParse(changed).success).toBe(false);
});

it('공개 지형의 전체 기간 실제 계산에서 여섯 지표와 작은 효과를 원 단위로 표시', () => {
  const result = watershedSurfaceComparisonDto.parse(fixture);
  expect(result.cases.map((c) => c.complete)).toEqual([true, true]);
  expect(result.signedReduction?.outwardVolumeM3).toBe(15.988374673295766);
  expect(result.signedReduction?.maximumWetAreaM2).toBe(0);
  expect(result.totalScore).toBeNull();
  const html = renderToStaticMarkup(<WatershedSurfaceResult result={result} />);
  for (const label of [
    '두 출구의 총 방류량',
    '동시 출구 유량',
    '구역 내 최대 수심',
    '최대 침수 면적',
    '가장 오래 젖은 격자의 시간',
    '수심·면적·시간 누적량',
    '실제 침수지도·피해 감소로 해석할 수',
    '86,339',
  ])
    expect(html).toContain(label);
  expect(html).not.toContain('100점');
  expect(html).toContain('전체 물수지 잔차');
  expect(html).toContain('작은 개선량의 유의성이 입증되지는 않습니다');
  expect(html).toContain('2,989,828.546675');
  expect(html).toContain('2,989,812.558301');
});

it('실제 회원 응답의 결합 결과를 관망 단독 참고 결과와 구별하고 설계 결속 검사', () => {
  const job = watershedJobDto.parse(httpFixture);
  const html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('지표를 연결하지 않은 관망만의 참고 비교');
  expect(html).toContain('위의 결합 계산과 경계 조건이 다릅니다');
  expect(html).toContain('/bundle');
  const invalid = structuredClone(httpFixture);
  invalid.design.surfaceConnection.profileSha256 = 'f'.repeat(64);
  expect(watershedJobDto.safeParse(invalid).success).toBe(false);
  expect(
    watershedJobDto.safeParse({
      ...httpFixture,
      result: { ...httpFixture.result, surfaceComparison: undefined },
    }).success
  ).toBe(false);
});

it('원 계산의 조건·평가 길이·수치 실패를 성공으로 바꾼 응답 거부', () => {
  const changes = [
    (v: typeof fixture) => {
      v.cases[1].context.forcingSha256 = 'f'.repeat(64);
    },
    (v: typeof fixture) => {
      v.cases[1].context.engineSha256 = 'f'.repeat(64);
    },
    (v: typeof fixture) => {
      v.cases[1].id = 'baseline';
    },
    (v: typeof fixture) => {
      v.cases[1].complete = false;
    },
    (v: typeof fixture) => {
      v.cases[1].durationSeconds -= 1;
    },
    (v: typeof fixture) => {
      v.cases[1].calendarShortfallSeconds = 0;
    },
    (v: typeof fixture) => {
      v.cases[1].networkRoutingContinuityPercent = 1.01;
    },
    (v: typeof fixture) => {
      v.cases[1].surfaceNumericalStatus = 'FAILED';
    },
    (v: typeof fixture) => {
      v.cases[1].networkConvergence.nonConvergedSteps = 1;
    },
    (v: typeof fixture) => {
      v.cases[1].raw.maximumWetDurationSeconds = 86340;
    },
    (v: typeof fixture) => {
      v.signedReduction.maximumWetAreaM2 = 1;
    },
  ];
  for (const change of changes) {
    const value = structuredClone(fixture);
    change(value);
    expect(watershedSurfaceComparisonDto.safeParse(value).success).toBe(false);
  }
});

it('실패 원 지표는 남기되 개선량 보류, 악화된 음의 효과 보존', () => {
  const failed = {
    ...structuredClone(fixture),
    numericalStatus: 'FAILED',
    signedReduction: null,
  };
  failed.cases[1].numericalStatus = 'FAILED';
  failed.cases[1].surfaceNumericalStatus = 'FAILED';
  const result = watershedSurfaceComparisonDto.parse(failed);
  const html = renderToStaticMarkup(<WatershedSurfaceResult result={result} />);
  expect(html).toContain('수치 검증 실패');
  expect(html.match(/<td>보류<\/td>/g)).toHaveLength(6);
  expect(
    watershedSurfaceComparisonDto.safeParse({ ...failed, signedReduction: fixture.signedReduction })
      .success
  ).toBe(false);
  const worse = structuredClone(fixture);
  worse.cases[1].raw.maximumDepthM = worse.cases[0].raw.maximumDepthM + 0.5;
  worse.signedReduction.maximumDepthM = -0.5;
  expect(
    renderToStaticMarkup(
      <WatershedSurfaceResult result={watershedSurfaceComparisonDto.parse(worse)} />
    )
  ).toContain('-0.5');
});
