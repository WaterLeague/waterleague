import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import raw from '../view/fixtures/catalog.json';
import { watershedCatalogDto, watershedJobDto } from '../dto/watershedDto';
import result from '../view/fixtures/public-network-result.json';
import { watershedCostSnapshotDto } from '../dto/watershedCostDto';
import { previewWatershedCosts } from './watershedCosts';
import { WatershedCosts } from '../view/WatershedCosts';
import { designFingerprint } from './watershedDesign';
const catalog = watershedCatalogDto.parse(raw);
it('면적 참고 금액과 규격 불일치 시설을 구분하고 미산정을 무료로 표시하지 않음', () => {
  const cost = previewWatershedCosts(catalog, [
    {
      id: 'B',
      facilityType: 'BIORETENTION',
      catchmentId: 'S1',
      areaM2: 100.01,
      treatedImperviousM2: 0,
    },
    {
      id: 'S',
      facilityType: 'VEGETATIVE_SWALE',
      catchmentId: 'S1',
      areaM2: 100,
      treatedImperviousM2: 0,
    },
  ])!;
  expect(watershedCostSnapshotDto.parse(cost).knownReferenceSubtotalKrw).toBe(56005600);
  expect(cost.items[1].referenceAmountKrw).toBe(null);
  expect(cost.unpricedPlacementIds).toEqual(['S']);
  const html = renderToStaticMarkup(<WatershedCosts costing={cost} preview />);
  expect(html).toContain('56,005,600원');
  expect(html).toContain('미산정 시설 1곳');
  expect(html).toContain('현재 서울 견적 아님');
  expect(html).not.toContain('<strong>0원');
  expect(html).toContain('<strong>미산정</strong>');
  expect(
    watershedCostSnapshotDto.safeParse({ ...cost, knownReferenceSubtotalKrw: 56000000 }).success
  ).toBe(false);
});
it('전부 미산정인 설계의 합계를 0원으로 바꾸지 않고 단가 버전을 멱등 키에 포함', () => {
  const placements = [
    {
      id: 'C',
      facilityType: 'RAINWATER_CISTERN' as const,
      catchmentId: 'S1',
      areaM2: 1.18,
      treatedImperviousM2: 0,
    },
  ];
  const cost = previewWatershedCosts(catalog, placements)!;
  expect(cost.knownReferenceSubtotalKrw).toBe(null);
  expect(renderToStaticMarkup(<WatershedCosts costing={cost} />)).toContain(
    '산정 가능한 참고 금액 없음'
  );
  expect(designFingerprint(catalog.catalogHash, placements, catalog.costCatalogHash)).not.toBe(
    designFingerprint(catalog.catalogHash, placements)
  );
});
it('저장 결과의 비용과 설계 수량이 다르면 화면에서 거부', () => {
  const placements = [
    {
      id: 'Bio1',
      facilityType: 'BIORETENTION' as const,
      catchmentId: 'S1',
      areaM2: 100,
      treatedImperviousM2: 1000,
    },
  ];
  const costing = previewWatershedCosts(catalog, placements)!;
  const job = {
    id: '10000000-0000-4000-8000-000000000001',
    catalogHash: catalog.catalogHash,
    state: 'SUCCEEDED',
    createdAt: '2026-10-18T00:00:00Z',
    message: '',
    design: {
      placements: placements.map((p) => ({ ...p, subcatchmentId: p.catchmentId })),
      costing,
    },
    result: { ...result, costing },
  };
  expect(watershedJobDto.safeParse(job).success).toBe(true);
  expect(watershedJobDto.safeParse({ ...job, result }).success).toBe(false);
  expect(
    watershedJobDto.safeParse({
      ...job,
      design: { ...job.design, placements: [{ ...job.design.placements[0], areaM2: 101 }] },
    }).success
  ).toBe(false);
});
