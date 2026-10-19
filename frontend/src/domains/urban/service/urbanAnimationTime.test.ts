import { expect, it } from 'vitest';
import { urbanAnimationTime } from './urbanTimeService';
it('주간 실제 시간 흐름과 모션 축소 정지', () => {
  const clock = {
    current: { historical: false, at: null, playing: false, speed: 1, sampledAt: 0 },
  };
  const time = Date.parse('2026-10-19T09:00:00Z');
  expect(
    urbanAnimationTime(clock, 0, true, time + 1000, 0) - urbanAnimationTime(clock, 0, true, time, 0)
  ).toBe(1);
  expect(urbanAnimationTime(clock, 123, false, time, 0)).toBe(123);
});
it('재해 배속·정지·역탐색의 수면 위상 재현과 시각 결측 보존', () => {
  const clock = {
    current: {
      historical: true,
      at: Date.parse('2022-08-08T09:00:00Z') as number | null,
      playing: true,
      speed: 30,
      sampledAt: 0,
      origin: Date.parse('2022-08-08T00:00:00Z'),
    },
  };
  const initial = urbanAnimationTime(clock, 0, true, 0, 0);
  expect(urbanAnimationTime(clock, 0, true, 0, 500) - initial).toBe(15);
  clock.current.playing = false;
  expect(urbanAnimationTime(clock, 0, false, 0, 500)).toBe(initial);
  clock.current.at! += 3600000;
  expect(urbanAnimationTime(clock, 0, false, 0, 500) - initial).toBe(3600);
  clock.current.at! -= 3600000;
  expect(urbanAnimationTime(clock, 0, false, 0, 999)).toBe(initial);
  clock.current.at = null;
  expect(urbanAnimationTime(clock, 42, true, 0, 999)).toBe(42);
});
