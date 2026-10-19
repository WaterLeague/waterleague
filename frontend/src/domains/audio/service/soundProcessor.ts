import { ContinuousSound, type AmbientKind } from './soundSynthesis';

declare const sampleRate: number;
declare const currentTime: number;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
}
declare function registerProcessor(name: string, processor: typeof CitySoundProcessor): void;

class CitySoundProcessor extends AudioWorkletProcessor {
  private readonly channels: ContinuousSound[];
  private stopAt = Infinity;
  static get parameterDescriptors() {
    return [
      { name: 'rate', defaultValue: 1, minValue: 0, maxValue: 10000, automationRate: 'k-rate' },
    ];
  }
  constructor(options: {
    processorOptions: { kind: AmbientKind; seed: number; channels: number };
  }) {
    super();
    const { kind, seed, channels } = options.processorOptions;
    this.channels = Array.from(
      { length: channels },
      (_, i) => new ContinuousSound(kind, sampleRate, seed + i * 719)
    );
    this.port.onmessage = (event: MessageEvent<{ stopAt: number }>) => {
      if (Number.isFinite(event.data.stopAt)) this.stopAt = event.data.stopAt;
    };
  }
  process(
    _inputs: Float32Array[][],
    outputs: Float32Array[][],
    parameters: Record<string, Float32Array>
  ) {
    if (currentTime >= this.stopAt) {
      this.port.postMessage('ended');
      this.port.close();
      return false;
    }
    const output = outputs[0];
    for (let i = 0; i < output.length; i++) this.channels[i].render(output[i], parameters.rate[0]);
    return true;
  }
}

registerProcessor('waterleague-continuous-sound', CitySoundProcessor);
