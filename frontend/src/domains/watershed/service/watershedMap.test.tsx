import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import catalogRaw from '../view/fixtures/catalog.json';
import { watershedCatalogDto } from '../dto/watershedDto';
import { watershedMap } from './watershedMap';
import { WatershedMapPlan } from '../view/WatershedMapPlan';
import type { City } from '../../city/entity/city';
import profile from '../view/fixtures/seocho-georeference-v1.json';
const response = () => ({
  ...structuredClone(catalogRaw),
  georeference: structuredClone(profile),
  georeferenceHash: '36a477f877d0d0fc4518f5e7664497e6e36798299745880932d5b43148ac01ab',
});
const city = { coordinateSystem: 'EPSG:5186', originProjected: [198128, 551989] } as City;
it('위치 가정은 원본 절점·관로·집수 연결과 결속하고 지도 원점만 뺀다', () => {
  const catalog = watershedCatalogDto.parse(response());
  const map = watershedMap(catalog.georeference!, city);
  expect(map.nodes[0].coordinate[0]).toBeCloseTo(202601.168 - 198128, 7);
  expect(map.nodes[0].coordinate[1]).toBeCloseTo(542961.602 - 551989, 7);
  expect(map.catchments.map((c) => c.id)).toEqual(catalog.layout!.catchments.map((c) => c.id));
  const html = renderToStaticMarkup(
    <svg>
      <WatershedMapPlan map={map} selectedId="S2" disabled={false} onSelect={() => {}} />
    </svg>
  );
  expect(html.match(/role="button"/g)).toHaveLength(14);
  expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
  expect(html).toContain('도로 대조 위치 가정');
});
it('확정 좌표계 주장·도로 스냅·다른 원본·연결 누락을 거부한다', () => {
  for (const change of [
    (r: ReturnType<typeof response>) => {
      r.georeference.sourceCrsVerified = true;
    },
    (r: ReturnType<typeof response>) => {
      r.georeference.nodes[0].coordinate[0] += 1;
    },
    (r: ReturnType<typeof response>) => {
      r.georeference.sourceLayoutSha256 = '0'.repeat(64);
    },
    (r: ReturnType<typeof response>) => {
      r.georeference.links[0].toNode = 'J99';
    },
    (r: ReturnType<typeof response>) => {
      r.georeference.catchments.pop();
    },
    (r: ReturnType<typeof response>) => {
      r.georeference.links[0].points.pop();
    },
  ]) {
    const value = response();
    change(value);
    expect(watershedCatalogDto.safeParse(value).success).toBe(false);
  }
});
