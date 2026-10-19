import React from 'react';
import { createRoot } from 'react-dom/client';
import { GamePage } from '../src/domains/game/view/GamePage';
import { GameAudioEngine } from '../src/domains/audio/service/gameAudioEngine';
import { ContinuousSound, type AmbientKind } from '../src/domains/audio/service/soundSynthesis';
import '../src/shared/ui/base.css';
import '../src/shared/ui/game.css';
import '../src/domains/game/view/play.css';
import '../src/shared/ui/game-theme.css';
import '../src/shared/ui/gameplay-chrome.css';

// 실제 앱과 동일한 음향 그래프를 검증 화면에서만 계측한다.
const contexts: {
  context: AudioContext;
  probes: AnalyserNode[];
  sources: Set<AudioBufferSourceNode>;
}[] = [];
const NativeContext = window.AudioContext;
window.AudioContext = class extends NativeContext {
  private probes: AnalyserNode[] = [];
  private sources = new Set<AudioBufferSourceNode>();
  constructor(options?: AudioContextOptions) {
    super(options);
    contexts.push({ context: this, probes: this.probes, sources: this.sources });
  }
  createBufferSource() {
    const source = super.createBufferSource();
    this.sources.add(source);
    source.addEventListener('ended', () => this.sources.delete(source));
    return source;
  }
  createDynamicsCompressor() {
    const node = super.createDynamicsCompressor();
    const probe = super.createAnalyser();
    probe.fftSize = 2048;
    node.connect(probe);
    this.probes.push(probe);
    return node;
  }
};
const worklets = new Set<AudioWorkletNode>();
const processorErrors: string[] = [];
const NativeWorklet = window.AudioWorkletNode;
window.AudioWorkletNode = class extends NativeWorklet {
  constructor(context: BaseAudioContext, name: string, options?: AudioWorkletNodeOptions) {
    super(context, name, options);
    worklets.add(this);
    this.port.addEventListener('message', (event) => {
      if (event.data === 'ended') worklets.delete(this);
    });
    this.addEventListener('processorerror', () => processorErrors.push(name));
  }
};
let environment = { rain: 0, distance: 0, playing: false, speed: 1, flood: false };
let moving = { car: 0, walk: 0 };
let installationSounds = 0;
let peak = 0;
const originalEnvironment = GameAudioEngine.prototype.environment;
GameAudioEngine.prototype.environment = function (value) {
  environment = {
    rain: value.rain,
    distance: Math.round(value.distance),
    playing: value.playing,
    speed: value.speed,
    flood: !!value.flood,
  };
  originalEnvironment.call(this, value);
};
const originalActors = GameAudioEngine.prototype.actors;
GameAudioEngine.prototype.actors = function (actors) {
  moving = {
    car: actors.filter((a) => a.kind === 'car').length,
    walk: actors.filter((a) => a.kind === 'walk').length,
  };
  originalActors.call(this, actors);
};
const originalInstalled = GameAudioEngine.prototype.installed;
GameAudioEngine.prototype.installed = function (point) {
  installationSounds++;
  originalInstalled.call(this, point);
};

async function rendered(
  kind: 'rain' | 'water' | 'car' | 'walk' | 'install',
  distance: number,
  mode = 'playing'
) {
  const context = new OfflineAudioContext(2, 48000, 24000);
  const engine = await GameAudioEngine.create(context);
  engine.listener([0, distance, 0], [0, -1, 0], [0, 0, -1]);
  engine.environment({
    playing: mode !== 'paused',
    speed: 1,
    rain: kind === 'rain' ? 2 : 0,
    distance,
    flood: kind === 'water' ? { point: [0, 0, 0], depth: 0.3, speed: 1 } : null,
  });
  if (mode === 'muted') engine.mute(true);
  if (kind === 'car' || kind === 'walk')
    engine.actors([{ id: 'test', kind, point: [0, 0, 0], speed: kind === 'walk' ? 1.3 : 8 }]);
  if (kind === 'install') engine.installed([0, 0, 0]);
  const buffer = await context.startRendering();
  let square = 0,
    count = 0,
    maximum = 0;
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const samples = buffer.getChannelData(c);
    for (let i = kind === 'install' ? 0 : 12000; i < samples.length; i++) {
      square += samples[i] ** 2;
      maximum = Math.max(maximum, Math.abs(samples[i]));
      count++;
    }
  }
  engine.dispose();
  return { rms: Math.sqrt(square / count), maximum };
}
async function continuousOutput(kind: AmbientKind) {
  const context = new OfflineAudioContext(1, 24000 * 24, 24000);
  const engine = await GameAudioEngine.create(context);
  const source = new AudioWorkletNode(context, 'waterleague-continuous-sound', {
    numberOfInputs: 0,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: { kind, seed: 17, channels: 1 },
  });
  source.connect(context.destination);
  const result = (await context.startRendering()).getChannelData(0);
  const expected = new Float32Array(result.length);
  new ContinuousSound(kind, 24000).render(expected);
  const difference = result.reduce(
    (maximum, value, i) => Math.max(maximum, Math.abs(value - expected[i])),
    0
  );
  source.port.postMessage({ stopAt: 0 });
  source.disconnect();
  source.port.close();
  engine.dispose();
  return `${kind}: ${difference < 1e-6 ? 'PASS' : 'FAIL'} 24초 연속 출력 · 블록 경계 오차 ${difference}`;
}
function AudioCheck() {
  const [state, setState] = React.useState('');
  const [results, setResults] = React.useState('미실행');
  React.useEffect(() => {
    const samples = new Float32Array(2048);
    const timer = setInterval(() => {
      for (const { context, probes } of contexts)
        if (context.state === 'running')
          for (const probe of probes) {
            probe.getFloatTimeDomainData(samples);
            for (const value of samples) peak = Math.max(peak, Math.abs(value));
          }
      setState(
        JSON.stringify({
          contexts: contexts.map((v) => v.context.state),
          rates: contexts
            .filter((v) => v.context.state === 'running')
            .flatMap((v) => [...v.sources].map((s) => Number(s.playbackRate.value.toFixed(2)))),
          streamRates: [...worklets]
            .filter((w) => w.context.state === 'running')
            .map((w) => Number(w.parameters.get('rate')!.value.toFixed(2))),
          processorErrors,
          environment,
          moving,
          installationSounds,
          peak: Number(peak.toFixed(6)),
        })
      );
    }, 200);
    return () => clearInterval(timer);
  }, []);
  async function run() {
    setResults('검증 중');
    const rows = [];
    for (const kind of ['rain', 'water', 'car', 'walk', 'install'] as const) {
      const near = await rendered(kind, 25),
        far = await rendered(kind, 500);
      const muted = await rendered(kind, 25, 'muted');
      const paused = kind !== 'install' ? await rendered(kind, 25, 'paused') : null;
      const pass =
        near.rms > 0.00001 &&
        near.rms > far.rms &&
        muted.rms < 0.00001 &&
        (!paused || paused.rms < 0.00001) &&
        near.maximum < 1;
      rows.push(
        `${kind}: ${pass ? 'PASS' : 'FAIL'} near=${near.rms.toFixed(6)} far=${far.rms.toFixed(6)} mute=${muted.rms.toFixed(7)} pause=${paused?.rms.toFixed(7) ?? '설치음 유지'}`
      );
    }
    for (const kind of ['rain', 'water', 'car', 'walk'] as const)
      rows.push(await continuousOutput(kind));
    setResults(rows.join('\n'));
  }
  return (
    <aside
      style={{
        position: 'fixed',
        bottom: 100,
        left: 12,
        zIndex: 1000,
        maxWidth: 460,
        background: '#fffef5',
        borderRadius: 16,
        padding: 12,
        boxShadow: '0 4px 30px #0003',
        fontSize: 11,
      }}
    >
      <details>
        <summary>음향 검증 계측</summary>
        <button onClick={() => void run()}>음향 출력 검사</button>
        <button
          onClick={() => {
            peak = 0;
          }}
        >
          최대 음량 초기화
        </button>
        <pre role="status" aria-label="음향 출력 검사 결과" style={{ whiteSpace: 'pre-wrap' }}>
          {results}
        </pre>
        <output aria-label="실시간 음향 계측" style={{ overflowWrap: 'anywhere' }}>
          {state}
        </output>
      </details>
    </aside>
  );
}
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <GamePage />
    <AudioCheck />
  </React.StrictMode>
);
