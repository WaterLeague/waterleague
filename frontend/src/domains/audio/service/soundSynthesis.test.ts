import { expect, test } from 'vitest';
import {
  ContinuousSound,
  distanceGain,
  installationSound,
  type AmbientKind,
} from './soundSynthesis';

const kinds: AmbientKind[] = ['rain', 'water', 'car', 'walk'];
const rms = (values: Float32Array) =>
  Math.sqrt(values.reduce((sum, v) => sum + v * v, 0) / values.length);
function rendered(kind: AmbientKind, seconds: number, rate = 1, sampleRate = 8000, seed = 17) {
  const data = new Float32Array(sampleRate * seconds);
  new ContinuousSound(kind, sampleRate, seed).render(data, rate);
  return data;
}

test('가까울수록 크고 유효 범위 밖에서는 무음', () => {
  const values = [0, 15, 45, 100, 179, 180, 1000].map((d) => distanceGain(d, 12, 180));
  expect(values[0]).toBe(1);
  expect(values.at(-2)).toBe(0);
  expect(values.at(-1)).toBe(0);
  expect(values.every((v, i) => i === 0 || v <= values[i - 1])).toBe(true);
  expect(distanceGain(NaN, 12, 180)).toBe(0);
  expect(distanceGain(Infinity, 12, 180)).toBe(0);
});

test.each(kinds)(
  '%s 연속 12초 출력은 오디오 블록 크기와 무관하며 4초마다 반복하지 않음',
  (kind) => {
    const expected = rendered(kind, 12);
    const actual = new Float32Array(expected.length);
    const synth = new ContinuousSound(kind, 8000);
    let at = 0;
    for (let block = 0; at < actual.length; block++) {
      const end = Math.min(actual.length, at + [128, 61, 256, 117][block % 4]);
      synth.render(actual.subarray(at, end));
      at = end;
    }
    expect(actual).toEqual(expected);
    expect(rms(actual)).toBeGreaterThan(0.001);
    expect(actual.every((v) => Number.isFinite(v) && Math.abs(v) < 1)).toBe(true);
    expect(actual.slice(32000, 64000)).not.toEqual(actual.slice(0, 32000));
  }
);

test.each(kinds)('%s 배속 변경·무음 블록 후에도 필터 상태와 위상 유지', (kind) => {
  const synth = new ContinuousSound(kind, 48000);
  const reference = new ContinuousSound(kind, 48000);
  for (const speed of [1, 2, 3, 5, 10, 60, 3600, 1]) {
    const silence = new Float32Array(511).fill(1);
    synth.render(silence, 0);
    expect(silence.every((v) => v === 0)).toBe(true);
    const chunk = new Float32Array(4096),
      expected = new Float32Array(4096);
    synth.render(chunk, speed);
    reference.render(expected, speed);
    expect(chunk).toEqual(expected);
    expect(chunk.every((v) => Number.isFinite(v) && Math.abs(v) < 1)).toBe(true);
  }
});

test.each<AmbientKind>(['rain', 'water'])('%s 과거 4초 경계 전후 음량·고역 비율 유지', (kind) => {
  const data = rendered(kind, 25, 1, 48000);
  const windows = [];
  for (let second = 1; second < 24; second++) {
    const chunk = data.slice(second * 48000, (second + 1) * 48000);
    const differences = chunk.slice(1).map((value, i) => value - chunk[i]);
    windows.push({ volume: rms(chunk), texture: rms(differences) / rms(chunk) });
  }
  for (const key of ['volume', 'texture'] as const) {
    const values = windows.map((w) => w[key]);
    expect(Math.max(...values) / Math.min(...values)).toBeLessThan(1.25);
  }
});

test('발걸음 간격은 1초 경계와 무관하며 5배속에서 5배 빨라짐', () => {
  for (const rate of [1, 5]) {
    const data = rendered('walk', 3, rate, 48000);
    const peaks: number[] = [];
    let active = false;
    for (let at = 0; at < data.length; at += 240) {
      const next = rms(data.subarray(at, at + 240)) > 0.055;
      if (next && !active && (!peaks.length || at - peaks.at(-1)! > 4800 / rate)) peaks.push(at);
      active = next;
    }
    expect(peaks.length).toBeGreaterThanOrEqual(5 * rate);
    for (let i = 1; i < peaks.length; i++)
      expect(Math.abs((peaks[i] - peaks[i - 1]) / 48000 - 0.5 / rate)).toBeLessThan(0.015);
  }
});

test('다른 음원 시드는 서로 같은 파형을 반복하지 않으며 설치 확인음은 한 번만 생성', () => {
  expect(rendered('rain', 1, 1, 8000, 17)).not.toEqual(rendered('rain', 1, 1, 8000, 719));
  const effect = installationSound(48000);
  expect(effect.length).toBe(28800);
  expect(effect.every((v) => Number.isFinite(v) && Math.abs(v) < 1)).toBe(true);
  expect(Math.abs(effect[0]) + Math.abs(effect.at(-1)!)).toBe(0);
});
