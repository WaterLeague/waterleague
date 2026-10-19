export type AmbientKind = 'rain' | 'water' | 'car' | 'walk';
export type SoundKind = AmbientKind | 'install';

// 관측 음원이 아닌 게임 효과음이다. 블록 사이에 난수·필터·위상을 유지한다.
export class ContinuousSound {
  private random: number;
  private low = 0;
  private mid = 0;
  private drift = 0;
  private phase = 0;

  constructor(
    private readonly kind: AmbientKind,
    private readonly sampleRate: number,
    seed = 17
  ) {
    this.random = seed >>> 0 || 17;
    this.phase = (this.random % 997) / 997;
  }

  render(output: Float32Array, rate = 1) {
    if (!(rate > 0) || !Number.isFinite(rate)) {
      output.fill(0);
      return;
    }
    const lowAlpha = 1 - Math.exp((-870 * rate) / this.sampleRate);
    const midAlpha = 1 - Math.exp((-8370 * rate) / this.sampleRate);
    const driftAlpha = 1 - Math.exp((-2 * rate) / this.sampleRate);
    const motorStep = Math.min(0.22, (58 * rate) / this.sampleRate);
    const stepAdvance = (2 * rate) / this.sampleRate;
    for (let i = 0; i < output.length; i++) {
      this.random ^= this.random << 13;
      this.random ^= this.random >>> 17;
      this.random ^= this.random << 5;
      const noise = (this.random >>> 0) / 2147483648 - 1;
      this.low += lowAlpha * (noise - this.low);
      this.mid += midAlpha * (noise - this.mid);
      this.drift += driftAlpha * (noise - this.drift);
      let value: number;
      if (this.kind === 'rain') {
        const swell = 0.88 + 0.06 * Math.tanh(this.drift * 30);
        value = ((noise - this.mid) * 0.24 + this.mid * 0.9) * swell;
      } else if (this.kind === 'water') {
        const ripple = 0.75 + 0.12 * Math.tanh(this.drift * 30);
        value = (this.low * 3.5 + this.mid * 0.48) * ripple;
      } else if (this.kind === 'car') {
        const angle = this.phase * Math.PI * 2;
        value =
          Math.sin(angle) * 0.11 + Math.sin(angle * 2) * 0.05 + this.low * 1.5 + this.mid * 0.25;
        this.phase = (this.phase + motorStep) % 1;
      } else {
        const age = this.phase * 0.5;
        const envelope = (1 - Math.exp(-age * 500)) * Math.exp(-age * 38);
        value = (this.mid * 1.1 + Math.sin(2 * Math.PI * 92 * age) * 0.4) * envelope;
        this.phase = (this.phase + stepAdvance) % 1;
      }
      output[i] = Math.max(-0.95, Math.min(0.95, value));
    }
  }
}

export function installationSound(sampleRate: number) {
  const samples = new Float32Array(Math.round(sampleRate * 0.6));
  let random = 17,
    mid = 0;
  for (let i = 0; i < samples.length; i++) {
    random ^= random << 13;
    random ^= random >>> 17;
    random ^= random << 5;
    mid += 0.16 * ((random >>> 0) / 2147483648 - 1 - mid);
    const t = i / sampleRate;
    const tap = t < 0.3 ? mid * Math.exp(-(t % 0.15) * 65) * 0.8 : 0;
    const chime = Math.sin(2 * Math.PI * (t < 0.15 ? 660 : 880) * t);
    samples[i] = tap + chime * 0.15 * Math.min(1, t / 0.008) * Math.exp(-t * 6);
  }
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
