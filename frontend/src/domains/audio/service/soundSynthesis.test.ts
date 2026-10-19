import { expect, test } from 'vitest';
import { distanceGain, synthesizeSound, type SoundKind } from './soundSynthesis';

test('가까울수록 크고 유효 범위 밖에서는 무음', () => {
  const values = [0, 15, 45, 100, 179, 180, 1000].map((d) => distanceGain(d, 12, 180));
  expect(values[0]).toBe(1);
  expect(values.at(-2)).toBe(0);
  expect(values.at(-1)).toBe(0);
  expect(values.every((v, i) => i === 0 || v <= values[i - 1])).toBe(true);
  expect(distanceGain(NaN, 12, 180)).toBe(0);
  expect(distanceGain(Infinity, 12, 180)).toBe(0);
});

test.each<SoundKind>(['rain', 'water', 'car', 'walk', 'install'])(
  '%s 음원의 유한 진폭·재현성·무클리핑',
  (kind) => {
    const pcm = synthesizeSound(kind, 24000);
    expect(pcm).toEqual(synthesizeSound(kind, 24000));
    expect(pcm.every((v) => Number.isFinite(v) && Math.abs(v) < 1)).toBe(true);
    expect(pcm.reduce((sum, v) => sum + v * v, 0) / pcm.length).toBeGreaterThan(0.00001);
    if (kind === 'walk' || kind === 'install') {
      expect(Math.abs(pcm[0])).toBe(0);
      expect(Math.abs(pcm.at(-1)!)).toBe(0);
    }
  }
);

test('좌우 빗소리 시드가 달라 공간감 유지', () => {
  expect(synthesizeSound('rain', 8000, 17)).not.toEqual(synthesizeSound('rain', 8000, 719));
});

test.each<SoundKind>(['rain', 'water'])('%s 반복 경계에 무음이나 비정상 음량 변화 없음', (kind) => {
  const pcm = synthesizeSound(kind, 48000);
  const rms = (values: Float32Array) =>
    Math.sqrt(values.reduce((sum, v) => sum + v * v, 0) / values.length);
  const seam = new Float32Array([...pcm.slice(-480), ...pcm.slice(0, 480)]);
  const reference = rms(pcm);
  expect(rms(seam)).toBeGreaterThan(reference * 0.6);
  expect(rms(seam)).toBeLessThan(reference * 1.7);
  expect(pcm.slice(-10).some((v) => Math.abs(v) > 0.01)).toBe(true);
});
