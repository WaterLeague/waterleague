import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/initializationSensitivity.json';
import { initializationSensitivityDto } from '../dto/initializationSensitivityDto';
import { InitializationSensitivityEvidence } from './InitializationSensitivityEvidence';

it('식생수로는 단일 빈 표면 상태로 표시하고 가짜 건습 차이를 거부', () => {
  const raw = {
    ...fixture,
    schemaVersion: 2,
    method: 'OBSERVED_SPINUP_FACILITY_STATE_COMPARISON_V2',
    facilityType: 'VEGETATIVE_SWALE',
    seedPolicy: 'NOT_APPLICABLE_FIXED_EMPTY_SURFACE',
    cases: [fixture.cases[0]],
    comparison: { ...fixture.comparison, seedDifferences: [] },
    limitations: [],
  };
  const value = initializationSensitivityDto.parse(raw);
  const html = renderToStaticMarkup(<InitializationSensitivityEvidence value={value} />);
  expect(html).toContain('빈 표면 시작');
  expect(html).toContain('건습 비교는 해당 없으며');
  expect(html).not.toContain('포화 시작');
  expect(html).not.toContain('포화 시작의 평가체적 감소량이');
  for (const invalid of [
    { ...raw, cases: fixture.cases },
    { ...raw, cases: [fixture.cases[1]] },
    { ...raw, comparison: fixture.comparison },
    { ...raw, seedPolicy: 'LID_SATURATION_BOUNDARIES' },
    { ...fixture, facilityType: 'VEGETATIVE_SWALE' },
  ])
    expect(initializationSensitivityDto.safeParse(invalid).success).toBe(false);
  const failed = initializationSensitivityDto.parse({
    ...raw,
    cases: [{ days: 7, seedSaturationPercent: 0, status: 'FAILED', errorCode: 'PRIVATE_FAILURE' }],
    comparison: { status: 'INCOMPLETE', ranges: null, seedDifferences: null },
  });
  expect(renderToStaticMarkup(<InitializationSensitivityEvidence value={failed} />)).not.toContain(
    'PRIVATE_FAILURE'
  );
});

it('실제 2022년 강우 계산의 두 초기 조건과 음의 효과를 보존한 표시', () => {
  const value = initializationSensitivityDto.parse(fixture);
  const html = renderToStaticMarkup(<InitializationSensitivityEvidence value={value} />);
  expect(html).toContain('100 m²');
  expect(html).toContain('46.805');
  expect(html).toContain('-0.0023217');
  expect(html).toContain('7.11e-15');
  expect(html).toContain('확률 신뢰구간이나 초기 상태의 수렴 판정이 아닙니다');
  expect(html).not.toContain('비교 미완료');
});

it('실패 조건의 0값 대체와 원시 오류 노출을 차단한 표시', () => {
  const value = initializationSensitivityDto.parse({
    ...fixture,
    cases: [
      fixture.cases[0],
      { days: 7, seedSaturationPercent: 100, status: 'FAILED', errorCode: 'SWMM_ERROR_TEST' },
    ],
    comparison: { status: 'INCOMPLETE', ranges: null, seedDifferences: null },
  });
  const html = renderToStaticMarkup(<InitializationSensitivityEvidence value={value} />);
  expect(html).toContain('비교 미완료');
  expect(html).toContain('계산 실패');
  expect(html).not.toContain('SWMM_ERROR_TEST');
  expect(html).not.toContain('포화 시작의 평가체적 감소량이');
  expect(
    initializationSensitivityDto.safeParse({ ...value, comparison: fixture.comparison }).success
  ).toBe(false);
  expect(
    initializationSensitivityDto.safeParse({
      ...fixture,
      cases: [fixture.cases[0], fixture.cases[0]],
    }).success
  ).toBe(false);
});
