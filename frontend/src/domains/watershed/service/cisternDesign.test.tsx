import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import catalogRaw from '../view/fixtures/catalog.json';
import { watershedCatalogDto } from '../dto/watershedDto';
import type { CisternPlacement } from '../dto/cisternDto';
import type { WatershedState } from '../controller/useWatershed';
import { cisternCatchments } from './cisternDesign';
import { validateCombinedDesign } from './storageDesign';
import { previewCisternCosts } from './cisternCosts';
import { CisternDesignForm } from '../view/CisternDesignForm';
const catalog = watershedCatalogDto.parse(catalogRaw);
const tank = {
  id: 'Cistern1',
  catchmentId: 'S9',
  captureAreaM2: 10,
  areaM2: 2.35,
  invertM: 12.75,
  depthM: 2,
  initialDepthM: 0,
  drain: { crestM: 12.8, diameterM: 0.04, dischargeCoefficient: 0.65, flapGate: true },
  overflow: { crestM: 14.3, diameterM: 0.2, dischargeCoefficient: 0.65, flapGate: true },
} satisfies CisternPlacement;
it('공개 적격 집수·면적·배수 높이·다른 시설 중복 제한', () => {
  expect(cisternCatchments(catalog)).toHaveLength(14);
  expect(validateCombinedDesign(catalog, [], [], [], [], tank)).toBe('');
  for (const changed of [
    { ...tank, catchmentId: 'S1' },
    { ...tank, captureAreaM2: 13729.38 },
    { ...tank, initialDepthM: 3 },
    { ...tank, drain: { ...tank.drain, crestM: 15 } },
    { ...tank, captureAreaM2: NaN },
  ])
    expect(validateCombinedDesign(catalog, [], [], [], [], changed)).not.toBe('');
  const lid = {
    id: 'Bio1',
    facilityType: 'BIORETENTION' as const,
    catchmentId: 'S9',
    areaM2: 20,
    treatedImperviousM2: 100,
  };
  expect(validateCombinedDesign(catalog, [lid], [], [], [], tank)).toBe('');
  expect(
    validateCombinedDesign(
      catalog,
      [{ ...lid, facilityType: 'RAINWATER_CISTERN' }],
      [],
      [],
      [],
      tank
    )
  ).toContain('덮개형 이용조');
  expect(
    validateCombinedDesign(catalog, [{ ...lid, treatedImperviousM2: 13700 }], [], [], [], tank)
  ).toContain('원 불투수 면적');
  expect(
    validateCombinedDesign(
      catalog,
      [{ ...lid, areaM2: 12727.03, treatedImperviousM2: 0 }],
      [],
      [],
      [],
      { ...tank, captureAreaM2: 1000 }
    )
  ).toContain('전면 배치');
  expect(
    validateCombinedDesign(
      catalog,
      [{ ...lid, id: 'Cistern1', catchmentId: 'S1' }],
      [],
      [],
      [],
      tank
    )
  ).toContain('식별자');
  expect(validateCombinedDesign(catalog, [{ ...lid, catchmentId: 'S1' }], [], [], [], tank)).toBe(
    ''
  );
  const mixed = {
    ...tank,
    catchmentId: 'S1',
    invertM: 16.48,
    drain: { ...tank.drain, crestM: 16.53 },
    overflow: { ...tank.overflow, crestM: 18.03 },
  };
  expect(validateCombinedDesign(catalog, [], [], [], [], mixed)).toBe('');
  expect(
    validateCombinedDesign(catalog, [], [], [], [], { ...mixed, captureAreaM2: 30000 })
  ).toContain('불투수 면적');
});
it('명시적 단면 용량과 기존 공개 견적 비교 및 공통 입력 표시', () => {
  const quotes = previewCisternCosts(catalog, [], tank);
  expect(quotes?.items[0].capacityM3).toBe(4.7);
  expect(quotes?.items[0].equivalentUnits).toBe(2);
  expect(previewCisternCosts(catalog, [], { ...tank, areaM2: 2 })?.items[0].status).toBe(
    'CAPACITY_NOT_MATCHED'
  );
  const state = {
    drafts: [],
    storageDrafts: [],
    conduitDrafts: [],
    pumpDrafts: [],
    cisternDraft: null,
    busy: false,
  } as unknown as WatershedState;
  const html = renderToStaticMarkup(<CisternDesignForm catalog={catalog} state={state} />);
  expect(html).toContain('집수 면적');
  expect(html).toContain('초기 수심');
  expect(html).toContain('관망 역압');
  expect(html).toContain('역류 방지 플랩');
  expect(html).toContain('보존할 투수');
  expect(html).not.toContain('value="12.75"');
  expect(html).toContain('일반 배출 중지 · 비상 배수만 허용');
});

it('배출 중지 명시와 배수구 동시 입력·누락을 구분', () => {
  expect(
    validateCombinedDesign(catalog, [], [], [], [], {
      ...tank,
      drainClosed: true,
      drain: null,
    })
  ).toBe('');
  for (const invalid of [
    { ...tank, drainClosed: true },
    { ...tank, drainClosed: false, drain: null },
    { ...tank, drain: null },
  ])
    expect(validateCombinedDesign(catalog, [], [], [], [], invalid)).toContain('배출 중지');
});

import actual from '../view/fixtures/public-hydraulic-cistern-job.json';
import { watershedJobDto } from '../dto/watershedDto';
import { WatershedResult } from '../view/WatershedResult';
it('실제 회원 계산의 이용조 원장·견적·악화 표시와 변조 거부', () => {
  const job = watershedJobDto.parse(actual);
  const html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('빗물이용조 물수지');
  expect(html).toContain('4.7 m³');
  expect(html).toContain('1.3607');
  expect(html).toContain('증가');
  expect(html).toContain('2.5962');
  for (const change of ['capacity', 'missing', 'failed', 'quote']) {
    const copy = structuredClone(actual);
    if (change === 'capacity')
      copy.result.cases[1].networkCistern!.wholeRunLedger.facilities[0].capacityM3 = 7;
    if (change === 'missing') delete copy.result.cases[1].networkCistern;
    if (change === 'failed')
      copy.result.cases[1].networkCistern!.wholeRunLedger.facilities[0].floodingM3 = 1;
    if (change === 'quote') copy.design.cistern!.footprintM2 = 3;
    expect(watershedJobDto.safeParse(copy).success).toBe(false);
  }
});

it('배출 중지 결과는 같은 배출 조건의 원장을 요구하며 자연배수 원장으로 대체 불가', () => {
  const value = structuredClone(actual) as unknown as {
    design: { cistern: { drain: unknown } };
    result: {
      cases: {
        networkCistern?: { wholeRunLedger: { facilities: { drainOperation?: string }[] } };
      }[];
    };
  };
  value.design.cistern.drain = { mode: 'CLOSED_NO_WITHDRAWAL' };
  expect(watershedJobDto.safeParse(value).success).toBe(false);
  value.result.cases[1].networkCistern!.wholeRunLedger.facilities[0].drainOperation =
    'CLOSED_NO_WITHDRAWAL';
  const parsed = watershedJobDto.parse(value);
  expect(renderToStaticMarkup(<WatershedResult job={parsed} />)).toContain(
    '일반 배출 중지 · 비상 배수만 허용'
  );
  value.design.cistern.drain = { ...tank.drain, mode: 'CLOSED_NO_WITHDRAWAL' };
  expect(watershedJobDto.safeParse(value).success).toBe(false);
});
