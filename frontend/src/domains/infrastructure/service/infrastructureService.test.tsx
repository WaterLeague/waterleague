import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import raw from '../../../../../backend/src/main/resources/infrastructure/native-v1/catalog.json';
import { infrastructureDto } from '../dto/infrastructureDto';
import {
  publicInfrastructureBuildingIds,
  unreservedRoofIds,
  visibleInfrastructure,
  infrastructureMarkers,
} from './infrastructureService';
import { InfrastructureEvidence } from '../view/InfrastructurePanel';
import { InfrastructureFootprintsPlan } from '../view/InfrastructureFootprints';
const catalog = infrastructureDto.parse({
  ...raw,
  sha256: 'a'.repeat(64),
  usage: 'REFERENCE_ONLY',
  statusCounts: {},
  assets: raw.assets.filter((a) => a.displayStatus === 'REFERENCE'),
});

it('전체 도시부터 모든 공개 시설 표시와 상세 선택 보존', () => {
  const overview = visibleInfrastructure(catalog.assets, [0, 0], 35000, '');
  expect(overview.length).toBe(catalog.assets.length);
  const markers = infrastructureMarkers(overview, 35000, '');
  expect(markers.length).toBeLessThan(overview.length);
  expect(markers.reduce((sum, a) => sum + (a.clusterCount ?? 1), 0)).toBe(overview.length);
  expect(infrastructureMarkers(overview, 1000, '')).toEqual(overview);
  const selected = catalog.assets.find((a) => a.kind === 'RAINWATER_REUSE')!;
  expect(
    visibleInfrastructure(catalog.assets, selected.center, 1000, '').map((a) => a.id)
  ).toContain(selected.id);
  expect(visibleInfrastructure(catalog.assets, [50000, 50000], 200, selected.id)).toEqual([
    selected,
  ]);
});

it('현재 공개 자료는 위치점으로 제공하며 시설 부지 경계를 생성하지 않음', () => {
  expect(catalog.assets.every((asset) => asset.geometryEvidence === 'LOCATION_POINT')).toBe(true);
  expect(catalog.assets.every((asset) => asset.footprint == null)).toBe(true);
  const layer = renderToStaticMarkup(
    <svg>
      <InfrastructureFootprintsPlan assets={catalog.assets} selectedId="" />
    </svg>
  );
  expect(layer).not.toContain('<path');
});

it('자료 기준일·분당 양수량과 당시 재현 미확인을 함께 표시', () => {
  const asset = catalog.assets.find((a) => a.id === '15148889:가양')!;
  const source = catalog.sources.find((s) => s.id === asset.sourceId)!;
  const html = renderToStaticMarkup(
    <InfrastructureEvidence asset={asset} source={source} historical />
  );
  expect(html).toContain('2025-09-08');
  expect(html).toContain('90,000 m³');
  expect(html).toContain('양수량 (m³/min)');
  expect(html).toContain('재해 당시 시설로 확인되지 않음');
  expect(html).toContain('부지 경계가 아닙니다');
  expect(html).not.toContain('1,350,000');
  expect(infrastructureDto.safeParse({ ...catalog, usage: 'CALIBRATED' }).success).toBe(false);
});

it('공개 위치점으로 지붕 후보를 예약하거나 높이·시설 경계를 추정하지 않음', () => {
  expect(publicInfrastructureBuildingIds(catalog.assets).size).toBe(0);
  const roofs = new Set(['ngii:N1A_B0010000:' + '1'.repeat(64)]);
  expect([...unreservedRoofIds(roofs, catalog.assets)]).toEqual([...roofs]);
  expect(roofs.size).toBe(1);
});
