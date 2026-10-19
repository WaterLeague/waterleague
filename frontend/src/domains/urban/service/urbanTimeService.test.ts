import { expect, it } from 'vitest';
import { urbanTime } from './urbanTimeService';
it('주간의 실제 시각과 재해의 배속·정지·탐색 시각 분리', () => {
  const clock = {
    current: { historical: false, at: 1000, playing: true, speed: 30, sampledAt: 100 },
  };
  expect(urbanTime(clock, 9000000, 600)).toBe(9000000);
  clock.current.historical = true;
  expect(urbanTime(clock, 9000000, 600)).toBe(16000);
  clock.current.playing = false;
  expect(urbanTime(clock, 9000000, 600)).toBe(1000);
  clock.current.at = 400000;
  expect(urbanTime(clock, 9000000, 600)).toBe(400000);
});
it('재해 시각 미확보를 현재 시각으로 대체하지 않음', () => {
  expect(
    urbanTime(
      { current: { historical: true, at: null, playing: true, speed: 1, sampledAt: 0 } },
      123,
      100
    )
  ).toBeNull();
});
