import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import raw from '../../../../../backend/src/main/resources/infrastructure/equipment-history-20261018-v1.json';
import { equipmentHistoryDto } from '../dto/equipmentHistoryDto';
import { EquipmentHistoryPanel } from './EquipmentHistoryPanel';

it('미설치 설비와 연도 불확실성을 숨기지 않고 제원 단위를 보존', () => {
  const rows = raw.records.filter((r) => r.assetId === 'OA-21179:6827');
  const catalog = equipmentHistoryDto.parse({
    ...raw,
    sha256: 'a'.repeat(64),
    eventId: 'seoul-20110727',
    eventDate: '2011-07-27',
    records: rows.map((record) => ({
      record,
      temporalStatus:
        record.installedYear === 2012 ? 'NOT_INSTALLED_YET' : 'INSTALLATION_PRECEDES_EVENT',
      sourcePrecedesEvent: false,
      simulationIncluded: false,
    })),
  });
  const html = renderToStaticMarkup(
    <EquipmentHistoryPanel catalog={catalog} assetId="OA-21179:6827" />
  );
  expect(html).toContain('사건 이후 설치 · 당시 설비에서 제외');
  expect(html).toContain('설치연도상 선행 · 당시 존속·운전 미확인');
  expect(html).toContain('680 kW(HP)');
  expect(html).toContain('모터 3대');
  expect(html).toContain('물리 계산에 포함하지 않습니다');
  expect(html).not.toContain('m³/min');
  expect(renderToStaticMarkup(<EquipmentHistoryPanel catalog={catalog} assetId="missing" />)).toBe(
    ''
  );
  expect(
    equipmentHistoryDto.safeParse({
      ...catalog,
      records: [{ ...catalog.records[0], simulationIncluded: true }],
    }).success
  ).toBe(false);
});
