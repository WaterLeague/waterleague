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
