import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import raw from '../../../../../backend/src/main/resources/infrastructure/seoul-public-20261018-v1.json';
import { infrastructureDto } from '../dto/infrastructureDto';
import { visibleInfrastructure } from './infrastructureService';
import { InfrastructureEvidence } from '../view/InfrastructurePanel';
const catalog = infrastructureDto.parse({
  ...raw,
  sha256: 'a'.repeat(64),
  usage: 'REFERENCE_ONLY',
  statusCounts: {},
  assets: raw.assets.filter((a) => a.displayStatus === 'REFERENCE'),
});

it('전체 도시에서는 펌프, 상세에서는 주변 공개 위치만 표시하며 선택 위치 보존', () => {
  const overview = visibleInfrastructure(catalog.assets, [0, 0], 35000, '');
  expect(overview.length).toBe(125);
  expect(overview.every((a) => a.kind === 'STORM_PUMP')).toBe(true);
  const selected = catalog.assets.find((a) => a.kind === 'RAINWATER_REUSE')!;
  expect(
    visibleInfrastructure(catalog.assets, selected.center, 1000, '').map((a) => a.id)
  ).toContain(selected.id);
  expect(visibleInfrastructure(catalog.assets, [50000, 50000], 200, selected.id)).toEqual([
    selected,
  ]);
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
