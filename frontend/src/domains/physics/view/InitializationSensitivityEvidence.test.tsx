import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/initializationSensitivity.json';
import { initializationSensitivityDto } from '../dto/initializationSensitivityDto';
import { InitializationSensitivityEvidence } from './InitializationSensitivityEvidence';

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
