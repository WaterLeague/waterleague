import { expect, it } from 'vitest';
import actual from '../view/fixtures/public-cistern-job.json';
import { WatershedResult } from '../view/WatershedResult';
import { renderToStaticMarkup } from 'react-dom/server';
import catalogRaw from '../view/fixtures/catalog.json';
import evidence from '../../../../../simulation/tests/fixtures/member-cistern-costs-v1.json';
import { watershedCatalogDto, watershedJobDto } from '../dto/watershedDto';
import { cisternCostSnapshotDto } from '../dto/cisternCostDto';
import { previewCisternCosts } from './cisternCosts';
import { CisternReferenceCosts } from '../view/CisternReferenceCosts';
const catalog = watershedCatalogDto.parse(catalogRaw);
const expected = cisternCostSnapshotDto.parse(evidence.cisternCosting);
it('실제 회원 계산의 견적과 결과 일치·중복 미산정 카드 제거', () => {
  const job = watershedJobDto.parse(actual);
  const html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('저장된 빗물이용조 견적');
  expect(html).toContain('8.4738 m³ 감소');
  expect(html).not.toContain('진주 사업계획');
  const changed = structuredClone(actual);
  changed.result.cisternCosting.items[0].quotes[0].quotedSubtotalKrw += 1;
  expect(watershedJobDto.safeParse(changed).success).toBe(false);
});
it('동일 용량의 3견적·미기재·연간 비용 가정을 서버 수량 계약과 일치', () => {
  const preview = previewCisternCosts(
    catalog,
    evidence.placements.map((p) => ({
      ...p,
      facilityType: 'RAINWATER_CISTERN',
      catchmentId: p.subcatchmentId,
    }))
  );
  expect(preview).toEqual(expected);
  expect(preview!.items[0].quotes.map((q) => q.quotedSubtotalKrw)).toEqual([
    10894000, 7024000, 5714000,
  ]);
  expect(preview!.items[0].quotes[2].components.LOG).toBeNull();
  expect(preview!.items[1].quotes).toEqual([]);
  const html = renderToStaticMarkup(<CisternReferenceCosts costing={expected} preview />);
  expect(html).toContain('10,894,000원');
  expect(html).toContain('용량 환산 없음');
  expect(html).toContain('물통 개수·단면·배관·펌프 규격 일치는 미확인');
  expect(html).toContain('게임 예산 차감 없음');
});
it('원가 소계·중복·물리 용량 불일치 거부와 이전 기록 보존', () => {
  for (const change of [
    (x: typeof evidence.cisternCosting) => {
      x.items[0].quotes[0].components.BARREL += 1;
    },
    (x: typeof evidence.cisternCosting) => {
      x.items[0].quotes[1] = x.items[0].quotes[0];
    },
    (x: typeof evidence.cisternCosting) => {
      x.items[0].equivalentUnits = 3;
    },
  ]) {
    const x = structuredClone(evidence.cisternCosting);
    change(x);
    expect(cisternCostSnapshotDto.safeParse(x).success).toBe(false);
  }
  const job = {
    id: '10000000-0000-4000-8000-000000000004',
    catalogHash: catalog.catalogHash,
    state: 'QUEUED',
    createdAt: '2026-10-18T00:00:00Z',
    message: '',
    design: structuredClone(evidence),
    result: null,
  };
  expect(watershedJobDto.safeParse(job).success).toBe(true);
  job.design.placements[0].areaM2 = 3;
  expect(watershedJobDto.safeParse(job).success).toBe(false);
  const old = { ...job, design: { placements: job.design.placements } };
  expect(watershedJobDto.safeParse(old).success).toBe(true);
});
