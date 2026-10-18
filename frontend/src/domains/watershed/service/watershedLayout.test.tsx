import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from '../view/fixtures/catalog.json';
import { watershedCatalogDto } from '../dto/watershedDto';
import { downstreamLayout, layoutExtent } from './watershedLayout';
import { WatershedLayout } from '../view/WatershedLayout';
const catalog = watershedCatalogDto.parse(fixture),
  layout = catalog.layout!;
it('원본 S1 출구부터 연결된 하류만 추적하고 상류 관로를 포함하지 않음', () => {
  const path = downstreamLayout(layout, 'S1');
  expect(path.start).toBe('J4');
  expect(path.outfalls).toEqual(['Out1']);
  expect(path.links.has('C6')).toBe(true);
  expect(path.links.has('C1')).toBe(false);
  expect(path.nodes.has('J1')).toBe(false);
  const cyclic = structuredClone(layout);
  cyclic.links.push({ ...cyclic.links[0], id: 'Cycle', fromNode: 'J3', toNode: 'J4' });
  expect(downstreamLayout(cyclic, 'S1').outfalls).toEqual(['Out1']);
});
it('다른 출구·원본 해시·중복 구역의 표시 자료 거부', () => {
  const wrong = structuredClone(fixture);
  wrong.layout.catchments[0].outletNodeId = 'J1';
  expect(watershedCatalogDto.safeParse(wrong).success).toBe(false);
  const foreign = structuredClone(fixture);
  foreign.layout.sourceOriginalSha256 = '0'.repeat(64);
  expect(watershedCatalogDto.safeParse(foreign).success).toBe(false);
  const duplicate = structuredClone(fixture);
  duplicate.layout.catchments.push(duplicate.layout.catchments[0]);
  expect(watershedCatalogDto.safeParse(duplicate).success).toBe(false);
});
it('선택 구역 하나와 구역별 설계 개수 표시, 연결 절점 좌표의 전체 화면 포함', () => {
  const html = renderToStaticMarkup(
    <WatershedLayout
      layout={layout}
      selectedId="S1"
      onSelect={() => {}}
      placements={[
        {
          id: 'F1',
          catchmentId: 'S1',
          facilityType: 'BIORETENTION',
          areaM2: 100,
          treatedImperviousM2: 0,
        },
      ]}
    />
  );
  expect(html.match(/<polygon/g)).toHaveLength(14);
  expect(html.match(/class="watershed-catchment" data-selected="true"/g)).toHaveLength(1);
  expect(html).toContain('<tspan>S1</tspan>');
  expect(html).toContain('1곳</tspan>');
  expect(html).toContain('실제 유량 방향이 아닙니다');
  const box = layoutExtent([
    ...layout.nodes.map((n) => n.coordinate),
    ...layout.catchments.flatMap((c) => c.points),
  ]);
  for (const n of layout.nodes) {
    expect(n.coordinate[0]).toBeGreaterThan(box.x);
    expect(n.coordinate[0]).toBeLessThan(box.x + box.width);
    expect(-n.coordinate[1]).toBeGreaterThan(box.y);
    expect(-n.coordinate[1]).toBeLessThan(box.y + box.height);
  }
});
