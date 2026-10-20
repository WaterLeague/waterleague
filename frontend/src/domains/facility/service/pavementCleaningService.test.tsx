import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import catalog from '../../../../../data/derived/pavement-cleaning-v1.json';
import catalogRaw from '../../../../../data/derived/pavement-cleaning-v1.json?raw';
import { pavementCleaningDto } from '../dto/pavementCleaningDto';
import { cleaningComparison, cleaningObservations } from './pavementCleaningService';
import {
  CleaningObservationTable,
  PavementCleaningEvidence,
} from '../view/PavementCleaningEvidence';

const report = pavementCleaningDto.parse(catalog);

test('공개 표 3의 위치·연도별 전후 수치와 원문·파생 해시 보존', async () => {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(catalogRaw));
  const hash = [...new Uint8Array(digest)].map((v) => v.toString(16).padStart(2, '0')).join('');
  expect(hash).toBe('69a7449d84cbdc970f056923bbc4c1b223d896098e88de3298b6aaeab157def3');
  expect(report.source.sha256).toBe(
    '9a9c9a4874d604b60c18f578edb28f02f00ee849f0dbcfba3ae53d1c61a9ce08'
  );
  expect(cleaningObservations).toEqual(report);
  const numeric = (s: (typeof report.pairs)[number]['before']) => [
    s.testCount,
    s.min,
    s.max,
    s.median,
    s.mean,
    s.standardDeviation,
  ];
  expect(report.pairs.map((p) => [numeric(p.before), numeric(p.after), p.pValue])).toEqual([
    [[6, 1.3, 10.8, 1.76, 3.43, 3.69], [6, 9.4, 165, 154, 111, 75.4], 0.0167],
    [[6, 135, 315, 231, 229, 77.7], [6, 103, 193, 143, 146, 36.7], 0.0975],
    [[16, 1.54, 361, 64.4, 100, 108], [16, 33.9, 381, 173, 173, 114], 0.0148],
    [[16, 0.81, 190, 4.39, 36.4, 63.7], [16, 8.52, 699, 148, 202, 192], 0.002],
  ]);
});

test('모든 시험 쌍의 단위 환산은 속도 통계만 변경하고 횟수·증감률·원본 보존', () => {
  const before = structuredClone(report);
  for (const pair of report.pairs) {
    const minute = cleaningComparison(pair, 'mm/min');
    const hour = cleaningComparison(pair, 'mm/h');
    for (const side of ['before', 'after'] as const) {
      expect(hour[side].testCount).toBe(minute[side].testCount);
      for (const key of ['min', 'max', 'median', 'mean', 'standardDeviation'] as const)
        expect(hour[side][key]).toBeCloseTo(minute[side][key] * 60, 10);
    }
    expect(hour.medianDifference).toBeCloseTo(minute.medianDifference * 60, 10);
    expect(hour.medianChangePercent).toBe(minute.medianChangePercent);
  }
  expect(report).toEqual(before);
});

test('음수·100% 초과 변화 보존과 기준값 0의 미산정', () => {
  const lower = cleaningComparison(report.pairs[1], 'mm/min');
  expect(lower.medianDifference).toBe(-88);
  expect(lower.medianChangePercent).toBeCloseTo(-38.095238095238095);
  expect(cleaningComparison(report.pairs[0], 'mm/min').medianChangePercent).toBeGreaterThan(100);
  const zero = structuredClone(report.pairs[0]);
  zero.before = { testCount: 6, min: 0, max: 0, median: 0, mean: 0, standardDeviation: 0 };
  expect(cleaningComparison(zero, 'mm/min').medianChangePercent).toBeNull();
});

test('전후 범위·횟수·중복 구역·새 상태/비용의 임의 생성 거부', () => {
  const mutations = [
    (v: typeof catalog) => {
      v.pairs[0].before.median = 11;
    },
    (v: typeof catalog) => {
      v.pairs[0].after.testCount = 3;
    },
    (v: typeof catalog) => {
      v.pairs[1].id = v.pairs[0].id;
    },
    (v: typeof catalog) => {
      v.pairs[0].pValue = 2;
    },
    (v: typeof catalog) => {
      v.simulationEligible = true;
    },
    (v: typeof catalog) => {
      v.rankingEligible = true;
    },
  ];
  for (const mutate of mutations) {
    const changed = structuredClone(catalog);
    mutate(changed);
    expect(pavementCleaningDto.safeParse(changed).success).toBe(false);
  }
  for (const key of ['newConditionValue', 'maintenanceCostKrw'])
    expect(
      pavementCleaningDto.safeParse({
        ...catalog,
        pairs: catalog.pairs.map((p, i) => (i === 0 ? { ...p, [key]: 0 } : p)),
      }).success
    ).toBe(false);
});

test('선택 구역의 전후 통계·부호·원문 검정 표시와 신설 회복률 구분', () => {
  for (const pair of report.pairs) {
    const markup = renderToStaticMarkup(<CleaningObservationTable pair={pair} unit="mm/min" />);
    expect(markup).toContain(pair.campaign);
    expect(markup).toContain(pair.location);
    expect(markup).toContain('표준편차');
    expect(markup).toContain('최소–최대');
    expect(markup).toContain('시험 횟수');
  }
  const lower = renderToStaticMarkup(
    <CleaningObservationTable pair={report.pairs[1]} unit="mm/h" />
  );
  expect(lower).toContain('-5,280');
  expect(lower).toContain('-38.0952%');
  expect(lower).toContain('통계적으로 뚜렷한 차이가 없었던 사례');
  const markup = renderToStaticMarkup(<PavementCleaningEvidence />);
  expect(markup).toContain('role="combobox"');
  expect(markup).toContain('청소 전후 시험 구역');
  expect(markup).toContain('침투속도 표시 단위');
  expect(markup).toContain('신설 대비 회복률·비용효율은 미산정');
  expect(markup).toContain(report.source.url);
  expect(markup).not.toContain('data/private');
});
