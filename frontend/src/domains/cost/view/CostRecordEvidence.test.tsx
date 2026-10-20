import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import record from './fixtures/costRecord.json';
import { costRecordDto } from '../dto/costDto';
import { CostRecordEvidence } from './CostRecordEvidence';
import { priceAdjustmentDto } from '../dto/priceAdjustmentDto';
import prices from '../../../../../backend/src/main/resources/facilities/game-prices-202608-v1.json';
import server from './fixtures/indexed-server-records-v1.json';
import { siteDto } from '../../installation/dto/installationDto';

it('서버의 실제 후보·저장 원가를 읽고 이전 단가와 새 단가의 설치비를 구분', () => {
  const site = siteDto.parse(server.currentSite);
  expect(site.unitCosts.PERMEABLE_PAVEMENT).toBe(123733);
  expect(site.costSourceSha256).toBe(prices.currentCostSourceSha256);
  for (const [record, expected] of [
    [server.oldCost, '1,100,000원'],
    [server.newCost, '1,237,330원'],
  ] as const) {
    const value = costRecordDto.parse(record);
    const html = renderToStaticMarkup(<CostRecordEvidence value={value} />);
    expect(html).toContain(expected);
    expect(html).toContain('10 m²');
    expect(html.includes('2026년 8월 가격 추정')).toBe(record === server.newCost);
  }
});

it('지수 환산 단가의 원가·가정·잠정치를 표시하고 산식·버전 위장을 거부', () => {
  const current = prices.versions[prices.currentCostSourceSha256 as keyof typeof prices.versions];
  const source = current.costModel.facilities.PERMEABLE_PAVEMENT;
  const unit = source.unitCost;
  const total = record.estimate.quantityM2 * unit;
  const updated = {
    ...record,
    estimate: {
      ...record.estimate,
      version: 'PUBLIC_REFERENCE_QUANTITY_V2',
      priceAdjustment: 'KICT_MONTHLY_INDEX_RATIO_ANNUAL_PROXY_V1',
      costSourceSha256: prices.currentCostSourceSha256,
      source,
      unitCostKrw: unit,
      budgetChargeKrw: total,
      referenceSubtotalKrw: total,
      lines: record.estimate.lines.map((line) => ({
        ...line,
        unitCostKrw: unit,
        amountKrw: total,
      })),
    },
  };
  expect(costRecordDto.safeParse(updated).success).toBe(true);
  const html = renderToStaticMarkup(<CostRecordEvidence value={updated} />);
  expect(html).toContain('123,733원');
  expect(html).toContain('2026년 8월 가격 추정');
  expect(html).toContain('잠정');
  expect(html).toContain('2022년 연평균');
  expect(html).toContain('110,000원');
  const parsed = costRecordDto.parse(updated);
  if (parsed.status !== 'RECORDED') throw new Error('원가 기록 누락');
  const adjustment = parsed.estimate.source.priceAdjustment!;
  for (const bad of [
    { ...adjustment, baseMonthlyIndices: [] },
    { ...adjustment, originalUnitCostKrw: 1.5 },
    { ...adjustment, targetIndex: { ...adjustment.targetIndex, value: 0 } },
    { ...adjustment, targetIndex: { ...adjustment.targetIndex, value: 1e308 } },
    {
      ...adjustment,
      baseMonthlyIndices: adjustment.baseMonthlyIndices.map((m) => ({ ...m, value: 1e308 })),
    },
    {
      ...adjustment,
      baseMonthlyIndices: adjustment.baseMonthlyIndices.map((m) => ({ ...m, value: 0 })),
    },
    { ...adjustment, adjustedUnitCostKrw: adjustment.adjustedUnitCostKrw + 1 },
  ])
    expect(priceAdjustmentDto.safeParse(bad).success).toBe(false);
  for (const mutate of [
    (v: typeof updated) => {
      v.estimate.version = 'PUBLIC_REFERENCE_QUANTITY_V1';
    },
    (v: typeof updated) => {
      v.estimate.priceAdjustment = 'NONE';
    },
    (v: typeof updated) => {
      Reflect.deleteProperty(v.estimate.source, 'priceAdjustment');
    },
    (v: typeof updated) => {
      v.estimate.source.unitCost += 1;
    },
  ]) {
    const changed = structuredClone(updated);
    mutate(changed);
    expect(costRecordDto.safeParse(changed).success).toBe(false);
  }
});

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
