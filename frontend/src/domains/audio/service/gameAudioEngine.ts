import type { AmbientSound, SoundPoint, StreetSound } from '../entity/audio';
import { distanceGain, synthesizeSound, type SoundKind } from './soundSynthesis';

type Voice = {
  source: AudioBufferSourceNode;
  gain: GainNode;
  pan: PannerNode | null;
  rate: number;
};
export class GameAudioEngine {
  private readonly master: GainNode;
  private readonly ambient: GainNode;
  private readonly compressor: DynamicsCompressorNode;
  private readonly buffers = new Map<SoundKind, AudioBuffer>();
  private readonly voices = new Map<string, Voice>();
  private readonly effects = new Set<Voice>();
  private readonly retiring = new Set<Voice>();
  private position: SoundPoint = [0, 30000, 22000];
  private muted = false;
  private disposed = false;
  private playing = true;
  private speed = 1;
  private lastActorsAt = -Infinity;
  private lastEffectAt = -Infinity;

  constructor(readonly context: BaseAudioContext) {
    this.master = context.createGain();
    this.master.gain.value = 0.65;
    this.ambient = context.createGain();
    this.compressor = context.createDynamicsCompressor();
    this.compressor.threshold.value = -12;
    this.compressor.knee.value = 12;
    this.compressor.ratio.value = 6;
    this.compressor.attack.value = 0.004;
    this.compressor.release.value = 0.2;
    this.ambient.connect(this.master);
    this.master.connect(this.compressor).connect(context.destination);
    this.loop('rain', 'rain', false);
    this.loop('flood', 'water', true);
  }

  get active() {
    return !this.disposed && !this.muted;
  }

  private buffer(kind: SoundKind) {
    const cached = this.buffers.get(kind);
    if (cached) return cached;
    const channels = kind === 'rain' || kind === 'water' ? 2 : 1;
    const pcm = synthesizeSound(kind, this.context.sampleRate);
    const buffer = this.context.createBuffer(channels, pcm.length, this.context.sampleRate);
    buffer.copyToChannel(pcm, 0);
    if (channels === 2)
      buffer.copyToChannel(synthesizeSound(kind, this.context.sampleRate, 719), 1);
    this.buffers.set(kind, buffer);
    return buffer;
  }

  private voice(kind: SoundKind, spatial: boolean, destination: AudioNode): Voice {
    const source = this.context.createBufferSource(),
      gain = this.context.createGain();
    source.buffer = this.buffer(kind);
    gain.gain.value = 0;
    source.connect(gain);
    const pan = spatial ? this.context.createPanner() : null;
    if (pan) {
      pan.panningModel = 'HRTF';
      // 지도 축척의 감쇠를 직접 계산하며 방향은 실제 3D 청취점으로 처리한다.
      pan.rolloffFactor = 0;
      gain.connect(pan).connect(destination);
    } else gain.connect(destination);
    return { source, gain, pan, rate: 1 };
  }

  private loop(id: string, kind: SoundKind, spatial: boolean) {
    const voice = this.voice(kind, spatial, this.ambient);
    voice.source.loop = true;
    voice.source.start(0, (this.voices.size * 0.137) % voice.source.buffer!.duration);
    this.voices.set(id, voice);
    return voice;
  }

  private smooth(param: AudioParam, value: number) {
    param.setTargetAtTime(value, this.context.currentTime, 0.08);
  }

  private fade(param: AudioParam, value: number, duration = 0.12) {
    param.cancelAndHoldAtTime(this.context.currentTime);
    param.linearRampToValueAtTime(value, this.context.currentTime + duration);
  }

  private locate(voice: Voice, point: SoundPoint) {
    if (!voice.pan) return;
    this.smooth(voice.pan.positionX, point[0]);
    this.smooth(voice.pan.positionY, point[1]);
    this.smooth(voice.pan.positionZ, point[2]);
  }

  private distance(point: SoundPoint) {
    return Math.hypot(...point.map((value, i) => value - this.position[i]));
  }

  listener(position: SoundPoint, forward: SoundPoint, up: SoundPoint) {
    if (this.disposed) return;
    this.position = position;
    const l = this.context.listener;
    [
      l.positionX,
      l.positionY,
      l.positionZ,
      l.forwardX,
      l.forwardY,
      l.forwardZ,
      l.upX,
      l.upY,
      l.upZ,
    ].forEach((param, i) => this.smooth(param, [...position, ...forward, ...up][i]));
  }

  mute(muted: boolean) {
    this.muted = muted;
    if (!this.disposed) this.fade(this.master.gain, muted ? 0 : 0.65);
    if (muted) this.actors([]);
  }

  environment(value: AmbientSound) {
    if (this.disposed) return;
    this.playing = value.playing;
    this.speed = Number.isFinite(value.speed) && value.speed > 0 ? value.speed : 1;
    this.fade(this.ambient.gain, value.playing ? 1 : 0, value.playing ? 0.12 : 0.025);
    for (const voice of this.voices.values())
      this.smooth(voice.source.playbackRate, voice.rate * this.speed);
    const rain = this.voices.get('rain')!;
    const intensity = Math.min(1, Math.sqrt(Math.max(0, value.rain) / 2));
    this.smooth(rain.gain.gain, intensity * distanceGain(value.distance, 220, 18000) * 0.7);
    const flood = this.voices.get('flood')!;
    if (value.flood) {
      this.locate(flood, value.flood.point);
      const strength =
        0.3 + Math.min(0.45, (value.flood.speed ?? 0) * 0.12 + (value.flood.depth ?? 0) * 0.15);
      this.smooth(
        flood.gain.gain,
        strength * distanceGain(this.distance(value.flood.point), 40, 650)
      );
    } else this.smooth(flood.gain.gain, 0);
    if (!value.playing || this.context.currentTime - this.lastActorsAt > 0.5) this.actors([]);
  }

  actors(actors: StreetSound[]) {
    if (this.disposed) return;
    this.lastActorsAt = this.context.currentTime;
    const audible =
      this.playing && !this.muted
        ? actors
            .map((actor) => ({
              ...actor,
              gain: distanceGain(
                this.distance(actor.point),
                actor.kind === 'walk' ? 12 : 35,
                actor.kind === 'walk' ? 180 : 650
              ),
            }))
            .filter((a) => a.speed > 0 && a.gain > 0.001)
            .sort((a, b) => b.gain - a.gain)
        : [];
    const counts = { walk: 0, car: 0 };
    const selected = audible.filter((a) => ++counts[a.kind] <= 4);
    const ids = new Set(selected.map((a) => a.id));
    for (const [id, voice] of this.voices) {
      if (id === 'rain' || id === 'flood' || ids.has(id)) continue;
      this.smooth(voice.gain.gain, 0);
      voice.source.stop(this.context.currentTime + 0.3);
      this.retiring.add(voice);
      voice.source.onended = () => {
        this.disconnect(voice);
        this.retiring.delete(voice);
      };
      this.voices.delete(id);
    }
    for (const actor of selected) {
      const voice = this.voices.get(actor.id) ?? this.loop(actor.id, actor.kind, true);
      this.locate(voice, actor.point);
      this.smooth(voice.gain.gain, actor.gain * (actor.kind === 'walk' ? 0.65 : 0.45));
      voice.rate =
        actor.kind === 'walk'
          ? Math.min(1.6, Math.max(0.65, actor.speed / 1.35))
          : Math.min(1.7, 0.65 + actor.speed / 22);
      this.smooth(voice.source.playbackRate, voice.rate * this.speed);
    }
  }

  installed(point: SoundPoint) {
    if (!this.active || this.context.currentTime - this.lastEffectAt < 0.12) return;
    this.lastEffectAt = this.context.currentTime;
    const voice = this.voice('install', true, this.master);
    this.locate(voice, point);
    voice.gain.gain.value = distanceGain(this.distance(point), 100, 6000) * 0.8;
    this.effects.add(voice);
    voice.source.onended = () => {
      this.disconnect(voice);
      this.effects.delete(voice);
    };
    voice.source.start();
  }

  private disconnect(voice: Voice) {
    voice.source.disconnect();
    voice.gain.disconnect();
    voice.pan?.disconnect();
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    for (const voice of [...this.voices.values(), ...this.effects, ...this.retiring]) {
      voice.source.stop();
      this.disconnect(voice);
    }
    this.voices.clear();
    this.effects.clear();
    this.retiring.clear();
    this.buffers.clear();
    this.ambient.disconnect();
    this.master.disconnect();
    this.compressor.disconnect();
  }
}
