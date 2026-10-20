import { expect, it } from 'vitest';
import { lifeCycleMoney } from './lifeCycleMoney';

it('큰 금액과 음수 잔존가치의 소수를 부동소수 변환 없이 표시한다', () => {
  expect(lifeCycleMoney('9007199254740993.05', 'KRW')).toBe('9,007,199,254,740,993.05원');
  expect(lifeCycleMoney('-0.04', 'KRW')).toBe('-0.04원');
  expect(lifeCycleMoney('3295.40', 'USD')).toBe('3,295.4 USD');
  expect(lifeCycleMoney('0.00', 'KRW')).toBe('0원');
});
