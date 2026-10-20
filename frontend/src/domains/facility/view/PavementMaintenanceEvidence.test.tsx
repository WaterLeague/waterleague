import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/pavementMaintenance-public-v1.json';
import { pavementMaintenanceDto } from '../dto/pavementMaintenanceDto';
import { PavementMaintenanceEvidence } from './PavementMaintenanceEvidence';

test('실제 회원 HTTP 결과의 세 조건과 미산정 청소 상태 표시', () => {
  const report = pavementMaintenanceDto.parse(fixture.value);
  const markup = renderToStaticMarkup(<PavementMaintenanceEvidence value={report} />);
  expect(markup).toContain('협잡물 96g');
  expect(markup).toContain('협잡물 192g');
  expect(markup).toContain('12,564');
  expect(markup).toContain('청소 후 회복은 근거 미확보로 미산정');
  expect(markup).toContain('이 Type-A 블록의');
  expect(markup).toContain('청소 전후 현장 측정 사례');
  expect(markup).toContain('선택한 서울 위치나 Type-A 블록의 청소 효과를 예측하는 값은 아닙니다');
  expect(markup).toContain('현재 설치 설계의 비용·효과·순위에는 합산하지 않습니다');
  expect(markup).toContain(report.source.sha256);
  expect(report.cases.map((c) => c.status === 'SUCCEEDED' && c.metrics.contributionM3)).toEqual(
    Array(3).fill(0.01973221915550316)
  );
});

test('다른 재료·막힘 조건·시간창·차이값·가짜 청소값 거부', () => {
  const mutations = [
    (v: typeof fixture.value) => {
      v.cases[1].scenario.conductivityMmH = 711.2;
    },
    (v: typeof fixture.value) => {
      v.cases[2].scenario.id = 'DUST_96_G';
    },
    (v: typeof fixture.value) => {
      v.cases[1].scenario.cloggingFactor = 1;
    },
    (v: typeof fixture.value) => {
      v.cases[1].scenario.pavementPorosity = 0.1;
    },
    (v: typeof fixture.value) => {
      v.cases[1].initialization.evaluationStart = '2022-08-09T00:00:00Z';
    },
    (v: typeof fixture.value) => {
      v.differencesFromFresh[0].minusFresh.contributionM3 = 1;
    },
    (v: typeof fixture.value) => {
      v.rankingEligible = true;
    },
  ];
  for (const mutate of mutations) {
    const changed = structuredClone(fixture.value);
    mutate(changed);
    expect(pavementMaintenanceDto.safeParse(changed).success).toBe(false);
  }
  expect(
    pavementMaintenanceDto.safeParse({
      ...fixture.value,
      cleaningRecovery: { ...fixture.value.cleaningRecovery, value: 0 },
    }).success
  ).toBe(false);
});

test('일부 수치 실패는 0으로 채우지 않고 비교 미완료로 표시', () => {
  const value = structuredClone(fixture.value);
  const cases = value.cases.map((c, i) =>
    i === 1
      ? {
          status: 'FAILED',
          scenario: c.scenario,
          phase: 'SCENARIO',
          errorCode: 'LIVE_NUMERICAL_QUALITY_FAILED',
        }
      : c
  );
  const report = pavementMaintenanceDto.parse({
    ...value,
    cases,
    status: 'INCOMPLETE',
    differencesFromFresh: null,
  });
  const markup = renderToStaticMarkup(<PavementMaintenanceEvidence value={report} />);
  expect(markup).toContain('비교 미완료');
  expect(markup).toContain('계산 실패');
  expect(markup).not.toContain('LIVE_NUMERICAL_QUALITY_FAILED');
  expect(pavementMaintenanceDto.safeParse({ ...report, status: 'SUCCEEDED' }).success).toBe(false);
});
