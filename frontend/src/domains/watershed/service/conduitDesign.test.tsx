import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import source from '../view/fixtures/catalog.json';
import actual from '../view/fixtures/public-conduit-job.json';
import { watershedCatalogDto, watershedJobDto } from '../dto/watershedDto';
import type { ConduitPlacement } from '../dto/conduitDto';
import { validateCombinedDesign } from './storageDesign';
import { WatershedResult } from '../view/WatershedResult';
const catalog = watershedCatalogDto.parse(source);
const pipe: ConduitPlacement = {
  id: 'Pipe1',
  conduitId: 'C2',
  shape: 'RECT_CLOSED',
  fullDepthM: 2.2,
  widthM: 3,
  barrels: 1,
  roughness: 0.0147,
};
it('관로 단독 설계와 같은 관로 중복·단면·수량·마찰 경계 검사', () => {
  expect(validateCombinedDesign(catalog, [], [], [pipe])).toBe('');
  for (const invalid of [
    { ...pipe, conduitId: 'NEW' },
    { ...pipe, widthM: null },
    { ...pipe, shape: 'CIRCULAR' as const },
    { ...pipe, barrels: 1.5 },
    { ...pipe, roughness: 0 },
    { ...pipe, fullDepthM: 3.201 },
  ])
    expect(validateCombinedDesign(catalog, [], [], [invalid])).not.toBe('');
  expect(validateCombinedDesign(catalog, [], [], [pipe, { ...pipe, id: 'Pipe2' }])).not.toBe('');
  expect(
    validateCombinedDesign(
      catalog,
      [
        {
          id: 'pipe1',
          facilityType: 'BIORETENTION',
          catchmentId: 'S1',
          areaM2: 100,
          treatedImperviousM2: 0,
        },
      ],
      [],
      [pipe]
    )
  ).not.toBe('');
  expect(
    validateCombinedDesign(catalog, [], [], [{ ...pipe, shape: 'CIRCULAR', widthM: null }])
  ).toBe('');
});
it('실제 혼합 계산의 공개 원 단면·설계 단면과 최종 관로 상태 표시', () => {
  const job = watershedJobDto.parse(actual),
    html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('C2 · 배수관·암거 개량');
  expect(html).toContain('높이 2.2 × 폭 2.2 m');
  expect(html).toContain('높이 2.2 × 폭 3 m');
  expect(html).toContain('241.72 m³ 감소');
  expect(html).toContain('3.3068 m³ 감소');
  expect(html).toContain('첨두 유량이 아닙니다');
  expect(html).toContain('개량 공사비 미산정');
});
it('관로 상태 누락·중복·다른 관로 결과를 정상 계산으로 표시하지 않음', () => {
  const missing = structuredClone(actual);
  delete (missing.result.cases[1] as { conduits?: unknown }).conduits;
  expect(watershedJobDto.safeParse(missing).success).toBe(false);
  const changed = structuredClone(actual);
  changed.result.cases[1].conduits[0].conduitId = 'C3';
  expect(watershedJobDto.safeParse(changed).success).toBe(false);
  const duplicate = structuredClone(actual);
  duplicate.design.conduits.placements.push({
    ...duplicate.design.conduits.placements[0],
    id: 'Pipe2',
    conduitId: 'C3',
  });
  for (const c of duplicate.result.cases) c.conduits.push({ ...c.conduits[0] });
  expect(watershedJobDto.safeParse(duplicate).success).toBe(false);
});
