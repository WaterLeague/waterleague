import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { budgetRecordEvidenceDto } from '../dto/budgetDto';
import { BudgetRecordEvidence } from './BudgetRecordEvidence';

const id = '10000000-0000-4000-8000-000000000001';
const base = {
  schemaVersion: 1,
  calculationId: id,
  installationId: id,
  capturedAt: '2026-10-18T08:00:00Z',
  evaluatedThrough: '2026-10-18T07:00:00Z',
  status: 'AVAILABLE',
  timeBasis: 'EFFECTIVE_EVENT_TIME',
  installationCostKrw: 5600000,
  allocatedAtEvaluationKrw: 5600000,
  allocatedAtCaptureKrw: 0,
  removedAt: '2026-10-18T07:30:00Z',
  entries: [
    {
      id: '1',
      installationId: id,
      programId: 'SEOUL_RAINWATER',
      facilityType: 'RAIN_GARDEN',
      eventType: 'ALLOCATE',
      amountKrw: 5600000,
      effectiveAt: '2026-10-18T06:00:00Z',
      recordedAt: '2026-10-18T06:00:00Z',
      provenance: 'LEGACY_IMPORT',
      accountingVersion: 'PREVIOUS_RULE',
      sourceBudgetPolicy: { ruleVersion: 'PREVIOUS_RULE', limitKrw: 80000000 },
    },
    {
      id: '2',
      installationId: id,
      programId: 'SEOUL_RAINWATER',
      facilityType: 'RAIN_GARDEN',
      eventType: 'RELEASE',
      amountKrw: 5600000,
      effectiveAt: '2026-10-18T07:30:00Z',
      recordedAt: '2026-10-18T07:30:00Z',
      provenance: 'LIVE_TRANSACTION',
      accountingVersion: 'PREVIOUS_RULE',
      sourceBudgetPolicy: { ruleVersion: 'PREVIOUS_RULE', limitKrw: 80000000 },
    },
  ],
};

it('계산 당시 배정·이후 취소와 최초 정책을 분리하여 표시', () => {
  const value = budgetRecordEvidenceDto.parse(base);
  const html = renderToStaticMarkup(<BudgetRecordEvidence value={value} />);
  expect(html).toContain('계산 종료 당시 배정액');
  expect(html).toContain('5,600,000원');
  expect(html).toContain('원장 조회 시점 배정액');
  expect(html).toContain('0원');
  expect(html).toContain('계산 종료 이후');
  expect(html).toContain('PREVIOUS_RULE');
  expect(html).toContain('이전 설치 기록에서 이관');
  expect(html).not.toContain('2000000000');
});

it('원장 미확보는 0원·무료로 표시하지 않고 상태 모순 거부', () => {
  const absent = budgetRecordEvidenceDto.parse({
    ...base,
    status: 'NOT_RECORDED',
    entries: [],
    allocatedAtEvaluationKrw: null,
    allocatedAtCaptureKrw: null,
  });
  const html = renderToStaticMarkup(<BudgetRecordEvidence value={absent} />);
  expect(html).toContain('원장 미확보');
  expect(html).not.toContain('<dd>0원');
  expect(budgetRecordEvidenceDto.safeParse({ ...base, status: 'NOT_RECORDED' }).success).toBe(
    false
  );
  expect(budgetRecordEvidenceDto.safeParse({ ...base, allocatedAtCaptureKrw: -1 }).success).toBe(
    false
  );
});
