import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import catalogRaw from '../view/fixtures/catalog.json';
import actual from '../view/fixtures/public-storage-job.json';
import { watershedCatalogDto, watershedJobDto } from '../dto/watershedDto';
import { validateCombinedDesign } from './storageDesign';
import type { StoragePlacement } from '../dto/storageDto';
import { WatershedResult } from '../view/WatershedResult';
import { WatershedLayout } from '../view/WatershedLayout';
const catalog = watershedCatalogDto.parse(catalogRaw);
const tank: StoragePlacement = {
  id: 'Tank1',
  connectionId: 'C1',
  areaM2: 100,
  invertM: 16,
  depthM: 5,
  initialDepthM: 0,
  inlet: { crestM: 18.5, diameterM: 0.2, dischargeCoefficient: 0.65, flapGate: false },
  drain: { crestM: 16.2, diameterM: 0.03, dischargeCoefficient: 0.65, flapGate: false },
  overflow: { crestM: 18.5, diameterM: 0.12, dischargeCoefficient: 0.65, flapGate: false },
};
it('공개 연결의 저류조 단독 설계와 개구부·공통 식별자 경계 검사', () => {
  expect(validateCombinedDesign(catalog, [], [tank])).toBe('');
  for (const invalid of [
    { ...tank, connectionId: 'Out1' },
    { ...tank, areaM2: 100.001 },
    { ...tank, initialDepthM: 6 },
    { ...tank, inlet: { ...tank.inlet, crestM: 17 } },
    { ...tank, overflow: { ...tank.overflow, crestM: 22 } },
  ])
    expect(validateCombinedDesign(catalog, [], [invalid])).not.toBe('');
  expect(
    validateCombinedDesign(
      catalog,
      [
        {
          id: 'tank1',
          facilityType: 'BIORETENTION',
          catchmentId: 'S1',
          areaM2: 100,
          treatedImperviousM2: 0,
        },
      ],
      [tank]
    )
  ).not.toBe('');
  expect(
    validateCombinedDesign(
      catalog,
      [],
      Array.from({ length: 21 }, (_, i) => ({ ...tank, id: `Tank${i}` }))
    )
  ).not.toBe('');
});
it('실제 저류조·생물저류 혼합 계산의 용량·유출·물수지와 악화 표시', () => {
  const job = watershedJobDto.parse(actual);
  const html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('저류조 물수지');
  expect(html).toContain('500 m³');
  expect(html).toContain('277.12');
  expect(html).toContain('20.3 m³ 증가');
  expect(html).toContain('증가');
  expect(html).toContain('공사비 미산정');
  expect(html).not.toContain('0원');
});
it('설계와 다른 용량·빠진 원장·수지 실패를 통과 결과로 표시하지 않음', () => {
  const changed = structuredClone(actual);
  changed.result.cases[1].connectedStorage!.wholeRunLedger.facilities[0].capacityM3 = 1000;
  expect(watershedJobDto.safeParse(changed).success).toBe(false);
  const missing = structuredClone(actual);
  delete missing.result.cases[1].connectedStorage;
  expect(watershedJobDto.safeParse(missing).success).toBe(false);
  const failed = structuredClone(actual);
  failed.result.cases[1].connectedStorage!.wholeRunLedger.facilities[0].balanceResidualM3 = 100;
  expect(watershedJobDto.safeParse(failed).success).toBe(false);
});
it('선택 가능한 공개 관로 23개의 키보드·클릭 대상과 연결점 표시', () => {
  const html = renderToStaticMarkup(
    <WatershedLayout
      layout={catalog.layout!}
      selectedId=""
      placements={[]}
      onSelect={() => {}}
      selectedLinkId="C1"
      selectableLinkIds={catalog.storageCatalog!.connections.map((c) => c.id)}
      onSelectLink={() => {}}
    />
  );
  expect(html.match(/관로 연결 선택/g)).toHaveLength(23);
  expect(html).toContain('C1 · J1 → J2');
  expect(html).not.toContain('class="watershed-catchment" data-selected="true"');
});
