import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import record from './fixtures/costRecord.json';
import { costRecordDto } from '../dto/costDto';
import { CostRecordEvidence } from './CostRecordEvidence';

it('저장된 수량·단가와 미산정 비용을 구분하고 전체 공사비로 표시하지 않음', () => {
  const value = costRecordDto.parse(record);
  const html = renderToStaticMarkup(<CostRecordEvidence value={value} />);
  expect(html).toContain('2,227,500원');
  expect(html).toContain('20.25 m²');
  expect(html).toContain('110,000원');
  expect(html).toContain('전체 현장 공사비');
  expect(html).toContain('미확정');
  expect(html).toContain('2022년 공개자료');
  expect(html).not.toContain('>0원<');
  expect(
    costRecordDto.safeParse({ ...record, estimate: { ...record.estimate, budgetChargeKrw: 1 } })
      .success
  ).toBe(false);
  expect(
    costRecordDto.safeParse({
      ...record,
      estimate: { ...record.estimate, completeInstalledCostKrw: 2227500 },
    }).success
  ).toBe(false);
});

it('기존 미기록 비용은 현재 단가로 대체하지 않음', () => {
  const html = renderToStaticMarkup(
    <CostRecordEvidence value={{ status: 'NOT_RECORDED', sha256: null, estimate: null }} />
  );
  expect(html).toContain('설치 당시 상세 원가 미기록');
  expect(html).not.toContain('원</');
  expect(costRecordDto.safeParse({ ...record, status: 'NOT_RECORDED' }).success).toBe(false);
});
