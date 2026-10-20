import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/public-shared-cistern-job-v1.json';
import { watershedJobDto } from '../dto/watershedDto';
import { StorageLedger } from './StorageLedger';

const job = () => watershedJobDto.parse(fixture.job);
const ledger = (value: ReturnType<typeof job>) =>
  value.result!.cases.find((c) => c.id === 'strategy')!.networkCistern!.wholeRunLedger
    .facilities[0];

it('실제 소유자 API 결과의 원 집수·초기 저장량·현재 공간·재이용 미산정 표시', () => {
  const value = job();
  expect(fixture.evidence).toBe('ACTUAL_API_WORKER_DTO_PROJECTION_NOT_AUTHENTICATED_BROWSER');
  expect(value.design.cistern?.schemaVersion).toBe(3);
  expect(value.design.cistern?.subcatchmentId).toBe('S1');
  expect(value.design.placements[0].subcatchmentId).toBe('S1');
  const row = ledger(value);
  expect(row.initialStorageM3).toBeCloseTo(0.7049214988474577, 10);
  expect(row.nativeCapacityM3).toBeCloseTo((4.7 * 0.028316846592) / 0.02832, 10);
  expect(row.initialAvailableM3).toBeCloseTo(row.nativeCapacityM3! - row.initialStorageM3, 10);
  expect(row.finalAvailableM3).toBeCloseTo(row.nativeCapacityM3! - row.finalStorageM3, 10);
  expect(row.reuseM3).toBeNull();
  const summary = value.result!.cases.find((c) => c.id === 'strategy')!.networkCistern!;
  const html = renderToStaticMarkup(<StorageLedger title="빗물이용조 물수지" summary={summary} />);
  expect(html).toContain('설계 용량 4.7');
  expect(html).toContain('계산 용량 4.6995');
  expect(html).toContain('남은 저장 공간');
  expect(html).toContain('초기 0.70492');
  expect(html).toContain('사용 수요 미확보 · 재이용량 미산정');
});

it('설계 총용량을 현재 공간으로 표시하거나 수요 없는 재이용량을 0으로 치환한 결과 거부', () => {
  const invalid: Array<(row: Record<string, unknown>) => void> = [
    (r) => {
      r.finalAvailableM3 = r.capacityM3;
    },
    (r) => {
      r.nativeCapacityM3 = r.capacityM3;
    },
    (r) => {
      r.volumeBasis = 'DECLARED_CAPACITY';
    },
    (r) => {
      delete r.initialAvailableM3;
    },
    (r) => {
      r.reuseM3 = 0;
    },
    (r) => {
      delete r.reuseStatus;
    },
    (r) => {
      for (const key of [
        'nativeCapacityM3',
        'volumeBasis',
        'initialAvailableM3',
        'finalAvailableM3',
      ])
        delete r[key];
    },
  ];
  for (const mutate of invalid) {
    const changed = structuredClone(job());
    mutate(ledger(changed));
    expect(watershedJobDto.safeParse(changed).success).toBe(false);
  }
});
