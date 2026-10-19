import type { UrbanTime } from '../entity/urban';
export function urbanTime(clock: UrbanTime, now = Date.now(), monotonic = performance.now()) {
  const value = clock.current;
  if (!value.historical) return now;
  if (value.at == null) return null;
  return (
    value.at +
    (value.playing ? Math.max(0, Math.min(1000, monotonic - value.sampledAt)) * value.speed : 0)
  );
}

export function urbanAnimationTime(
  clock: UrbanTime,
  previous: number,
  animate: boolean,
  now = Date.now(),
  monotonic = performance.now()
) {
  const at = urbanTime(clock, now, monotonic);
  if (at == null || (!animate && (!clock.current.historical || clock.current.playing)))
    return previous;
  // 사건 시작 기준 초를 사용하여 재탐색을 재현하고 셰이더의 큰 타임스탬프 정밀도 손실을 막는다.
  const origin = clock.current.origin ?? Math.floor(at / 86400000) * 86400000;
  return (at - origin) / 1000;
}
