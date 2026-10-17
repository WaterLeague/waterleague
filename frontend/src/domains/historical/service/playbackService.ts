export function playbackSecond(start: number, elapsedMs: number, speed: number, duration: number) {
  return Math.min(
    duration,
    Math.max(0, start + Math.floor((Math.max(0, elapsedMs) * speed) / 1000))
  );
}
export function rainfallFrame(second: number, count: number) {
  return Math.max(0, Math.min(count - 1, Math.floor(second / 60)));
}
