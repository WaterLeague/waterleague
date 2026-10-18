import { expect, it } from 'vitest';
import { representativeInstallations } from './memberSitesService';
import type { SharedInstallation } from '../entity/installation';
it('같은 위치의 표시 대표는 입력 순서와 무관하게 내 시설 우선', () => {
  const values = ['other-b', 'me', 'other-a'].map(
    (ownerId, n) =>
      ({ id: String(n), districtId: 'D', cellId: 'R1', ownerId }) as SharedInstallation
  );
  for (const input of [values, [...values].reverse()]) {
    expect(representativeInstallations(input, 'me').get('D:R1')?.ownerId).toBe('me');
    expect(representativeInstallations(input, null).get('D:R1')?.id).toBe('0');
  }
  expect(values).toHaveLength(3);
});
