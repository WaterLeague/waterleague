import { describe, expect, it } from 'vitest';
import { playbackSecond, rainfallFrame } from './playbackService';
describe('실제 경과 시간 기반 재해 재생', () => {
  it('1초를 1초로 진행하며 분 관측 경계에서만 강우 프레임 변경', () => {
    expect(playbackSecond(0, 1000, 1, 120)).toBe(1);
    expect(rainfallFrame(playbackSecond(0, 59999, 1, 120), 2)).toBe(0);
    expect(rainfallFrame(playbackSecond(0, 60000, 1, 120), 2)).toBe(1);
  });
  it('늦은 콜백에서도 실제 경과 시간 반영 및 종료 범위 제한', () => {
    expect(playbackSecond(5, 3200, 1, 120)).toBe(8);
    expect(playbackSecond(60, 2000, 60, 120)).toBe(120);
    expect(rainfallFrame(120, 2)).toBe(1);
  });
});
