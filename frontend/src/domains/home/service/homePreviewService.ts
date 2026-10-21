import { daylight, solarPosition } from '../../urban/service/solarService';

export type PreviewTimeline = { epoch: number; elapsed: number; startedAt: number | null };

export function previewElapsed(timeline: PreviewTimeline, now: number) {
  return (
    timeline.elapsed +
    (timeline.startedAt === null ? 0 : Math.max(0, now - timeline.startedAt) / 1000)
  );
}

export function previewTime(timeline: PreviewTimeline, elapsed: number) {
  return timeline.epoch + elapsed * 3_600_000;
}

export function previewTimeLabel(at: number) {
  const koreanTime = new Date(at + 9 * 3_600_000);
  return `${String(koreanTime.getUTCHours()).padStart(2, '0')}:${String(koreanTime.getUTCMinutes()).padStart(2, '0')}`;
}

export function previewWeather(mode: 'weekly' | 'disaster', epoch: number, elapsed: number) {
  if (mode === 'disaster') return { day: 0.75, rain: 1, solar: null };
  const solar = solarPosition(epoch + elapsed * 3_600_000);
  // 소개용 24초 하루·14초 날씨 순환이며 관측·물리 입력으로 사용하지 않는다.
  const wet = Math.max(
    0,
    Math.min(1, (Math.sin((elapsed / 14) * Math.PI * 2 - Math.PI / 2) + 0.25) * 1.4)
  );
  return {
    day: daylight(solar.elevation),
    rain: wet * wet * (3 - 2 * wet),
    solar,
  };
}
