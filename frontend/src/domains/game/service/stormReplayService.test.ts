import { expect, it } from 'vitest';
import original from '../../../../public/data/kma-event.json';
import model from '../../../../../data/models/seongsu-lab.json';
import type { Job, Lab, Metrics, Version } from '../entity/game';
import { createStormReplay, replayIndexAtTime } from './stormReplayService';
import { GameDataError } from '../exception/GameDataError';

// 자정 경계와 구간 정렬을 검사하는 축소 입력이며 제품 자료와 분리.
const lab: Lab = {
  modelHash: 'model',
  model: {
    ...model,
    validationLevel: 'EXPLORATORY',
    officialEvaluationAvailable: false,
    currency: 'KRW',
    costModel: { ...model.costModel, currency: 'KRW' },
    cells: [],
    rainfall: {
      ...original,
      start: '2024-07-18T14:59:00Z',
      end: '2024-07-18T15:02:00Z',
      intervalSeconds: 60,
      depthsMm: [0, 2, 0.5],
      totalDepthMm: 2.5,
    },
  },
};
const version: Version = {
  id: 'version',
  strategyId: 'strategy',
  revision: 1,
  modelHash: 'model',
  inputHash: 'input',
  placements: [],
  designNote: '',
  cost: 0,
  currency: 'KRW',
  createdAt: '',
  events: { kind: 'CREATE', before: [], after: [] },
};
const metric = (seriesM3s: number[]): Metrics => ({
  seriesM3s,
  runoffM3: 0,
  surfaceRunoffM3: 0,
  lidDrainageM3: 0,
  finalStorageM3: 0,
  initialStorageM3: 0,
  accountedDischargeM3: 0,
  infiltrationM3: 0,
  evaporationM3: 0,
  precipitationM3: 0,
  runoffContinuityPercent: 0,
  peakM3s: Math.max(...seriesM3s),
});
const job: Job = {
  id: 'job',
  versionId: 'version',
  modelHash: 'model',
  inputHash: 'input',
  state: 'SUCCEEDED',
  errorCode: null,
  createdAt: '',
  result: {
    baseline: metric([0, 0.02, 0.1]),
    strategy: metric([0, 0.03, 0.05]),
    score: 10,
    official: false,
    validationLevel: 'EXPLORATORY',
    assumptions: [],
    sensitivity: [],
    engine: { version: '5.2.4', binarySha256: '', generatorSha256: '', platform: '' },
  },
};

it('직전 1분 강우와 구간 종료 보고시각의 유량을 같은 인덱스로 연결', () => {
  const before = JSON.stringify({ lab, job, version });
  const replay = createStormReplay(job, lab, version);
  expect(new Date(replay.frames[0].time).toISOString()).toBe('2024-07-18T15:00:00.000Z');
  expect(replay.frames.at(-1)!.time).toBe(Date.parse(lab.model.rainfall.end));
  expect(replay.frames.map((f) => f.cumulativeRainMm)).toEqual([0, 2, 2.5]);
  expect(replay.frames[1]).toMatchObject({ rainMm: 2, baselineM3s: 0.02, designM3s: 0.03 });
  expect(replay).toMatchObject({
    firstWetIndex: 1,
    rainPeakIndex: 1,
    flowPeakIndex: 2,
    maxFlowM3s: 0.1,
  });
  expect(JSON.stringify({ lab, job, version })).toBe(before);
});

it('다른 계산 버전·시간축·비유한 수치를 재생하지 않음', () => {
  for (const altered of [
    { ...job, inputHash: 'other' },
    { ...job, modelHash: 'other' },
    { ...job, versionId: 'other' },
  ])
    expect(() => createStormReplay(altered, lab, version)).toThrow(GameDataError);
  expect(() => createStormReplay(job, lab, null)).toThrow(GameDataError);
  for (const values of [[0], [0, NaN, 0.1], [0, -1, 0.1]])
    expect(() =>
      createStormReplay(
        { ...job, result: { ...job.result!, strategy: metric(values) } },
        lab,
        version
      )
    ).toThrow(GameDataError);
  for (const change of [
    { intervalSeconds: 600 },
    { end: '2024-07-18T15:03:00Z' },
    { totalDepthMm: 3 },
  ])
    expect(() =>
      createStormReplay(
        job,
        { ...lab, model: { ...lab.model, rainfall: { ...lab.model.rainfall, ...change } } },
        version
      )
    ).toThrow(GameDataError);
});

it('재생 시간에 따라 실제 보고 인덱스만 선택하고 마지막 프레임을 넘지 않음', () => {
  expect(replayIndexAtTime(3, 500, 60, 1439)).toBe(33);
  expect(replayIndexAtTime(33, 10, 30, 1439)).toBe(33);
  expect(replayIndexAtTime(100, 50000, 120, 1439)).toBe(1438);
  expect(replayIndexAtTime(0, -1, 60, 1439)).toBe(0);
});
