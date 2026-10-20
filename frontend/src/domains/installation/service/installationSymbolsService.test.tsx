import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { installationSymbols } from './installationSymbolsService';
import {
  facilitySymbolGeometry,
  facilitySymbolPaths,
} from '../../catalog/service/facilitySymbolService';
import { InstallationSymbolsPlan } from '../view/InstallationSymbolsPlan';
import type { SharedInstallation, SharedSite } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';

const types = Object.keys(facilitySymbolPaths) as FacilityType[];
const installed = types.map((facilityType, n) => ({
  id: String(n),
  ownerId: 'other',
  ownerName: '시험 회원',
  districtId: 'A',
  cellId: `G${n}`,
  center: [n * 10, 0],
  heightM: 0,
  facilityType,
  areaM2: 10,
  cost: 1,
  installedAt: '2026-10-19T00:00:00Z',
})) as SharedInstallation[];

test('일곱 유형의 유한 입체 형상과 서로 다른 형태, 원 입력 보존', () => {
  const shapes = types.map((type) => {
    const geometry = facilitySymbolGeometry(type);
    const positions = geometry.getAttribute('position');
    expect(Array.from(positions.array).every(Number.isFinite)).toBe(true);
    expect(geometry.getAttribute('normal').count).toBe(positions.count);
    expect(geometry.getAttribute('color').count).toBe(positions.count);
    geometry.computeBoundingBox();
    expect(geometry.boundingBox!.min.y).toBeGreaterThanOrEqual(-1e-7);
    expect(geometry.boundingBox!.max.y).toBeGreaterThan(0.1);
    const hash = Array.from(positions.array).join(',');
    geometry.dispose();
    return hash;
  });
  expect(new Set(shapes).size).toBe(types.length);
});

test('상세 도형의 중복 표식 제거·미로딩 위치 유지·지도 주변 시설 유지', () => {
  const sites = [{ districtId: 'A', cellId: 'G0' }] as SharedSite[];
  const before = JSON.stringify(installed);
  expect(installationSymbols(installed, sites, null, 2400)).toHaveLength(types.length);
  expect(installationSymbols(installed, sites, null, 2399).map((i) => i.cellId)).not.toContain(
    'G0'
  );
  expect(installationSymbols(installed, [], null, 50)).toHaveLength(types.length);
  expect(JSON.stringify(installed)).toBe(before);
});

test('같은 위치의 회원 중 본인 우선·한 표식과 전체 원 기록 유지', () => {
  const values = [
    ...installed,
    { ...installed[0], id: 'mine', ownerId: 'me', facilityType: 'GREEN_ROOF' as const },
  ];
  const rows = installationSymbols(values, [], 'me', 5000);
  expect(rows).toHaveLength(types.length);
  expect(rows.find((i) => i.cellId === 'G0')?.id).toBe('mine');
  expect(
    installationSymbols([...values].reverse(), [], 'me', 5000).find((i) => i.cellId === 'G0')?.id
  ).toBe('mine');
  expect(values).toHaveLength(types.length + 1);
});

test('2D 기호의 유형·위치·선택과 접근 가능한 위치 조회', () => {
  const html = renderToStaticMarkup(
    <svg>
      <InstallationSymbolsPlan
        installations={installed}
        selectedKey="A:G0"
        ownDistrictId="B"
        scale={10}
        onSelect={() => {}}
      />
    </svg>
  );
  expect(html.match(/role="button"/g)).toHaveLength(types.length);
  expect(html.match(/실제 치수 아님/g)).toHaveLength(types.length);
  expect(html).toContain('lucide-container');
  expect(html).toContain('lucide-route');
  expect(html).toContain('lucide-droplets');
  expect(html).toContain('translate(50 0) scale(10)');
  expect(html).toContain('#ffd15b');
  expect(html).toContain('opacity="0.16"');
});

test('시설 필터에서 다른 시설 기호도 투명도만 낮춰 유지', () => {
  const html = renderToStaticMarkup(
    <svg>
      <InstallationSymbolsPlan
        installations={installed}
        selectedKey=""
        ownDistrictId={null}
        facilityType="GREEN_ROOF"
        scale={10}
        onSelect={() => {}}
      />
    </svg>
  );
  expect(html.match(/role="button"/g)).toHaveLength(types.length);
  expect(html.match(/opacity="1"/g)).toHaveLength(1);
  expect(html.match(/opacity="0.2"/g)).toHaveLength(types.length - 1);
});
