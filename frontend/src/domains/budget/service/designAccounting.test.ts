import { expect, test } from 'vitest';
import { designAccounting } from './designAccounting';
import type { BudgetAccounting } from '../dto/budgetDto';
const policy: BudgetAccounting = {
  version: 'TEST',
  programs: [
    {
      id: 'SHARED',
      name: '시험',
      limitKrw: 100,
      allocatedKrw: 99,
      remainingKrw: 1,
      sourceSha256: 'a'.repeat(64),
    },
  ],
  facilities: [
    {
      facilityType: 'RAIN_GARDEN',
      programId: 'SHARED',
      limitKrw: 80,
      allocatedKrw: 99,
      availableKrw: 1,
    },
    {
      facilityType: 'GREEN_ROOF',
      programId: 'SHARED',
      limitKrw: null,
      allocatedKrw: 0,
      availableKrw: 1,
    },
  ],
};
test('연구 배치는 주간 사용액과 독립하며 시설이 같은 사업 잔액 공유', () => {
  const frozen = JSON.stringify(policy);
  const view = designAccounting(policy, [
    { facilityType: 'RAIN_GARDEN', cost: 70 },
    { facilityType: 'GREEN_ROOF', cost: 20 },
  ]);
  expect(view.programs[0].allocatedKrw).toBe(90);
  expect(view.facilities.map((f) => f.availableKrw)).toEqual([10, 10]);
  expect(JSON.stringify(policy)).toBe(frozen);
  expect(designAccounting(policy, []).programs[0].remainingKrw).toBe(100);
});
test('서로 다른 시설의 한도 중복 사용과 유효하지 않은 비용 방지', () => {
  expect(
    designAccounting(policy, [{ facilityType: 'RAIN_GARDEN', cost: 79.99 }]).facilities[0]
      .availableKrw
  ).toBeCloseTo(0.01);
  expect(
    designAccounting(policy, [
      { facilityType: 'RAIN_GARDEN', cost: 70 },
      { facilityType: 'GREEN_ROOF', cost: 31 },
    ]).facilities.map((f) => f.availableKrw)
  ).toEqual([0, 0]);
  expect(() => designAccounting(policy, [{ facilityType: 'GREEN_ROOF', cost: NaN }])).toThrow();
  expect(() =>
    designAccounting(policy, [{ facilityType: 'PERMEABLE_PAVEMENT', cost: 1 }])
  ).toThrow();
});
