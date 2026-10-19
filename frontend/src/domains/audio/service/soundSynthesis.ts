export type SoundKind = 'rain' | 'water' | 'car' | 'walk' | 'install';

// 관측 음원이 아닌 게임 효과음이다. 고정 시드로 재생성하며 외부 음원 요청이 없다.
export function synthesizeSound(kind: SoundKind, sampleRate: number, seed = 17) {
  const duration = kind === 'install' ? 0.6 : kind === 'walk' ? 1 : 4;
  const loop = kind === 'rain' || kind === 'water' || kind === 'car';
  const length = Math.round(sampleRate * duration);
  const overlap = loop ? Math.round(sampleRate * 0.35) : 0;
  const samples = new Float32Array(length + overlap);
  let random = seed >>> 0 || 17,
    low = 0,
    mid = 0;
  for (let i = 0; i < samples.length; i++) {
    random ^= random << 13;
    random ^= random >>> 17;
    random ^= random << 5;
    const noise = (random >>> 0) / 2147483648 - 1;
    low += 0.018 * (noise - low);
    mid += 0.16 * (noise - mid);
    const t = i / sampleRate;
    let value: number;
    if (kind === 'rain') {
      const swell = 0.82 + 0.1 * Math.sin((t * Math.PI) / 2) + 0.08 * Math.sin(t * Math.PI * 2);
      value = ((noise - mid) * 0.24 + mid * 0.9) * swell;
    } else if (kind === 'water') {
      const ripple = 0.65 + 0.2 * Math.sin(t * Math.PI * 1.5) + 0.15 * Math.sin(t * Math.PI * 4);
      value = (low * 3.5 + mid * 0.48) * ripple;
    } else if (kind === 'car') {
      const motor = Math.sin(2 * Math.PI * 58 * t) * 0.11 + Math.sin(2 * Math.PI * 116 * t) * 0.05;
      value = motor * (0.85 + 0.15 * Math.sin(t * Math.PI * 4)) + low * 1.5 + mid * 0.25;
    } else if (kind === 'walk') {
      const step = t % 0.5;
      const envelope = Math.min(1, step / 0.004) * Math.exp(-step * 38);
      value = (mid * 1.1 + Math.sin(2 * Math.PI * 92 * step) * 0.4) * envelope;
    } else {
      const strike = t % 0.15;
      const tap = t < 0.3 ? mid * Math.exp(-strike * 65) * 0.8 : 0;
      const chime = Math.sin(2 * Math.PI * (t < 0.15 ? 660 : 880) * t);
      value = tap + chime * 0.15 * Math.min(1, t / 0.008) * Math.exp(-t * 6);
    }
    samples[i] = Math.max(-0.95, Math.min(0.95, value));
  }
  if (loop) {
    // 끝 이후의 연속 파형을 처음과 겹쳐 루프 경계에 무음 구간을 만들지 않는다.
    for (let i = 0; i < overlap; i++) {
      const mix = i / overlap;
      const incoming = kind === 'car' ? mix : Math.sin((mix * Math.PI) / 2);
      const outgoing = kind === 'car' ? 1 - mix : Math.cos((mix * Math.PI) / 2);
      samples[i] = samples[i] * incoming + samples[length + i] * outgoing;
    }
    return samples.slice(0, length);
  }
  // 설치 충격음·발걸음의 개별 타격에만 짧은 시작·종료 완화를 적용한다.
  const fade = Math.floor(sampleRate * 0.008);
  for (let i = 0; i < fade; i++) {
    samples[i] *= i / fade;
    samples[samples.length - 1 - i] *= i / fade;
  }
  return samples;
}

export function distanceGain(distance: number, reference: number, limit: number) {
  if (!Number.isFinite(distance) || distance >= limit) return 0;
  const d = Math.max(0, distance);
  return Math.pow(reference / (reference + d), 1.2) * Math.pow(1 - d / limit, 2);
}
