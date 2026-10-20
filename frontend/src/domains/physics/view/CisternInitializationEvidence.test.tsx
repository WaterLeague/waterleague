import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/cistern-initialization-v3.json';
import { initializationSensitivityDto } from '../dto/initializationSensitivityDto';
import { InitializationSensitivityEvidence } from './InitializationSensitivityEvidence';

it('관측 호우의 네 초기 저류 조건과 운전별 공급 결과 표시', () => {
  const value = initializationSensitivityDto.parse(fixture);
  expect(value.schemaVersion).toBe(3);
  if (value.schemaVersion !== 3) throw new Error('이용조 비교 버전 불일치');
  expect(value.cases.map((c) => c.status === 'SUCCEEDED' && c.nativeSeedStorageM3)).toEqual([
    0, 2.35, 0, 2.35,
  ]);
  const html = renderToStaticMarkup(<InitializationSensitivityEvidence value={value} />);
  expect(html).toContain('자연배수 운전');
  expect(html).toContain('문헌 수요에 따른 일정 인출');
  expect(html).toContain('선행 계산 시작의 저류');
  expect(html).toContain('7일 후 사건 시작 저류');
  expect(html).toContain('50.11');
  expect(html).toContain('하루 201L');
  expect(html).toContain('https://journal.cricit.kr/jkswe/XmlViewer/f253405');
  expect(html).toContain('물수지 잔차');
  expect(html).toContain('일반 점수에 더하지 않습니다');
  expect(html).not.toContain('비교 보류');
  expect(html).not.toContain('계산 실패');
});

it('초기 저류 미반영·조건 중복·수요 혼용·기간과 물수지 변조 거부', () => {
  const mutations: ((v: typeof fixture) => void)[] = [
    (v) => {
      v.cases[1].nativeSeedStorageM3 = 0;
    },
    (v) => {
      v.cases[1] = v.cases[0];
    },
    (v) => {
      v.cases[0].demand = v.cases[2].demand;
    },
    (v) => {
      v.cases[2].demand = null;
    },
    (v) => {
      v.cases[2].demand!.evaluationStart = '2022-08-08T09:02:17Z';
    },
    (v) => {
      v.cases[0].preparationStart = v.evaluationStart;
    },
    (v) => {
      v.cases[0].initialization.seed = 'FULL_CISTERN';
    },
    (v) => {
      v.cases[0].initialization.scoreExcludesWarmup = false;
    },
    (v) => {
      v.cases[0].tank.outflowM3 += 1;
    },
    (v) => {
      v.cases[0].metrics.initialLidStorageM3 = 0;
    },
    (v) => {
      v.comparisons[1] = v.comparisons[0];
    },
    (v) => {
      v.comparisons[0].comparison.seedDifferences[0].wetMinusDry.initialLidStorageM3 = 1;
    },
    (v) => {
      v.capacityM3 = 1;
    },
    (v) => {
      v.rankingEligible = true;
    },
  ];
  for (const mutate of mutations) {
    const changed = structuredClone(fixture);
    mutate(changed);
    expect(initializationSensitivityDto.safeParse(changed).success).toBe(false);
  }
});

it('한 조건 실패는 해당 운전만 보류하고 원시 오류를 숨김', () => {
  const failed = {
    ...fixture,
    status: 'INCOMPLETE',
    cases: [
      ...fixture.cases.slice(0, 3),
      {
        days: 7,
        seedSaturationPercent: 100,
        operation: 'LITERATURE_DEMAND',
        status: 'FAILED',
        errorCode: 'PRIVATE_TEST_FAILURE',
      },
    ],
    comparisons: [
      fixture.comparisons[0],
      {
        operation: 'LITERATURE_DEMAND',
        comparison: { status: 'INCOMPLETE', ranges: null, seedDifferences: null },
      },
    ],
  };
  const parsed = initializationSensitivityDto.parse(failed);
  const html = renderToStaticMarkup(<InitializationSensitivityEvidence value={parsed} />);
  expect(html).toContain('이 운전 조건의 초기 저류 차이는 비교 보류');
  expect(html).toContain('계산 실패');
  expect(html).not.toContain('PRIVATE_TEST_FAILURE');
  expect(html.match(/사건 시작 저류가 빈 상태보다/g)).toHaveLength(1);
  expect(initializationSensitivityDto.safeParse({ ...failed, status: 'SUCCEEDED' }).success).toBe(
    false
  );
  expect(
    initializationSensitivityDto.safeParse({ ...failed, comparisons: fixture.comparisons }).success
  ).toBe(false);
});
