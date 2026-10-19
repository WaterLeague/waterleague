import { expect, test } from 'vitest';
import type { SharedInstallation, InstallationLayout } from '../entity/installation';
import { installationLayoutKey } from './installationLayoutService';
import { representativeInstallations } from './memberSitesService';

const original = {
  id: 'a',
  districtId: 'D',
  cellId: 'RW123',
  ownerId: 'me',
  ownerName: '회원',
  facilityType: 'GREEN_ROOF',
  areaM2: 20,
  center: [0, 0],
  heightM: 10,
  cost: 20000,
  installedAt: '2022-08-08T09:00:00Z',
  scoreM3: null,
} as SharedInstallation;

test('재해 점수·평가 시각 갱신과 응답 순서 변경은 지도 형상 입력 유지', () => {
  const other = { ...original, id: 'b', ownerId: 'other', areaM2: 30 };
  const key = installationLayoutKey([original, other]);
  const updated = { ...original, scoreM3: 12.3, evaluatedThrough: '2022-08-08T10:00:00Z' };
  expect(installationLayoutKey([other, updated])).toBe(key);
  const layout = JSON.parse(key) as InstallationLayout[];
  expect(layout[0]).not.toHaveProperty('scoreM3');
  expect(representativeInstallations([updated, other], 'me').get('D:RW123')?.scoreM3).toBe(12.3);
  expect(representativeInstallations(layout, 'me').get('D:RW123')?.areaM2).toBe(20);
  expect(original.scoreM3).toBeNull();
});

test('설치 시각 통과·되감기·철거와 위치·시설·면적·소유 변경은 형상 갱신', () => {
  const key = installationLayoutKey([original]);
  expect(installationLayoutKey([])).not.toBe(key);
  expect(installationLayoutKey([original, { ...original, id: 'b' }])).not.toBe(key);
  for (const change of [
    { districtId: 'D2' },
    { cellId: 'RW124' },
    { ownerId: 'other' },
    { facilityType: 'PERMEABLE_PAVEMENT' as const },
    { areaM2: 25 },
  ])
    expect(installationLayoutKey([{ ...original, ...change }])).not.toBe(key);
  const layout = JSON.parse(key) as InstallationLayout[];
  const other = { ...layout[0], id: 'b', ownerId: 'other' };
  expect(representativeInstallations([...layout, other], 'other').get('D:RW123')).toBe(other);
});
