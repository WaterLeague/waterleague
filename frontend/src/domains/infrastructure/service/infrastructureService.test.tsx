import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import raw from '../../../../../backend/src/main/resources/infrastructure/seoul-public-20261018-v2.json';
import { infrastructureDto } from '../dto/infrastructureDto';
import { visibleInfrastructure } from './infrastructureService';
import { InfrastructureEvidence } from '../view/InfrastructurePanel';
import { InfrastructureFootprintsPlan } from '../view/InfrastructureFootprints';
const catalog = infrastructureDto.parse({
  ...raw,
  sha256: 'a'.repeat(64),
  usage: 'REFERENCE_ONLY',
  statusCounts: {},
  assets: raw.assets.filter((a) => a.displayStatus === 'REFERENCE'),
});

it('전체 도시에서는 펌프와 저류 경계, 상세에서는 주변 공개 위치 표시와 선택 보존', () => {
  const overview = visibleInfrastructure(catalog.assets, [0, 0], 35000, '');
  expect(overview.length).toBe(128);
  expect(overview.every((a) => a.kind === 'STORM_PUMP' || a.footprint)).toBe(true);
  const selected = catalog.assets.find((a) => a.kind === 'RAINWATER_REUSE')!;
  expect(
    visibleInfrastructure(catalog.assets, selected.center, 1000, '').map((a) => a.id)
  ).toContain(selected.id);
  expect(visibleInfrastructure(catalog.assets, [50000, 50000], 200, selected.id)).toEqual([
    selected,
  ]);
});

it('지도 도형과 위치점을 구분하고 설치 제외·용량 미확인·ODbL 출처 표시', () => {
  const asset = catalog.assets.find((a) => a.name === '잠실유수지')!;
  const source = catalog.sources.find((s) => s.id === asset.sourceId)!;
  const html = renderToStaticMarkup(
    <InfrastructureEvidence asset={asset} source={source} historical />
  );
  expect(html).toContain('OpenStreetMap 도형 원문');
  expect(html).toContain('ODbL 1.0');
  expect(html).toContain('새 게임 시설을 설치할 수 없습니다');
  expect(html).toContain('용량·현재 운영·과거 존속은 미확인');
  expect(html).not.toContain('점 표시는 부지 경계가 아닙니다');
  const layer = renderToStaticMarkup(
    <svg>
      <InfrastructureFootprintsPlan assets={catalog.assets} selectedId={asset.id} />
    </svg>
  );
  expect(layer.match(/<path/g)).toHaveLength(3);
  expect(layer).toContain('fill-rule="evenodd"');
  expect(layer).toContain('pointer-events="none"');
  expect(layer.match(/fill="#dda62e"/g)).toHaveLength(1);
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
