import { expect, test } from 'vitest';
import {
  previewElapsed,
  previewTime,
  previewTimeLabel,
  previewWeather,
  type PreviewTimeline,
} from './homePreviewService';

test('한국 시각에서 시작해 24초에 하루가 지나고 자정을 넘긴다', () => {
  const timeline: PreviewTimeline = {
    epoch: Date.parse('2026-10-21T14:30:00Z'),
    elapsed: 0,
    startedAt: 1000,
  };
  expect(previewTimeLabel(timeline.epoch)).toBe('23:30');
  expect(previewTimeLabel(previewTime(timeline, previewElapsed(timeline, 2000)))).toBe('00:30');
  expect(previewTime(timeline, 24) - timeline.epoch).toBe(24 * 3_600_000);
});

test('중단된 시간은 경과에서 제외하고 재개 시 이어서 흐른다', () => {
  const timeline: PreviewTimeline = { epoch: 0, elapsed: 2, startedAt: null };
  expect(previewElapsed(timeline, 90_000)).toBe(2);
  timeline.startedAt = 90_000;
  expect(previewElapsed(timeline, 91_500)).toBe(3.5);
});

test('주간 미리보기는 낮밤과 강수·비강수를 순환하고 재해는 비를 유지한다', () => {
  const noon = Date.parse('2026-10-21T03:00:00Z');
  expect(previewWeather('weekly', noon, 0)).toMatchObject({ day: 1, rain: 0 });
  expect(previewWeather('weekly', noon, 12).day).toBe(0);
  expect(previewWeather('weekly', noon, 7).rain).toBe(1);
  expect(previewWeather('weekly', noon, 14).rain).toBe(0);
  expect(previewWeather('disaster', noon, 0)).toEqual(previewWeather('disaster', noon, 14));
  expect(previewWeather('disaster', noon, 14).rain).toBe(1);
});

test('소개 시계의 시각으로 서울의 해 방향을 계산하고 오전·오후 방향을 바꾼다', () => {
  const morning = Date.parse('2026-10-21T00:00:00Z');
  const am = previewWeather('weekly', morning, 0).solar!;
  const pm = previewWeather('weekly', morning, 6).solar!;
  expect(am.direction[0]).toBeGreaterThan(0);
  expect(pm.direction[0]).toBeLessThan(0);
  expect(am.elevation).toBeGreaterThan(0);
  expect(previewWeather('weekly', morning, 12).solar!.elevation).toBeLessThan(0);
});
