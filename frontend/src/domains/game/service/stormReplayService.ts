import type { Job, Lab, Version } from '../entity/game';
import type { StormReplayData } from '../entity/stormReplay';
import { GameDataError } from '../exception/GameDataError';
import { matchesEvaluatedDesign } from './roundService';

export function createStormReplay(job: Job, lab: Lab, evaluated: Version | null): StormReplayData {
  if (
    job.state !== 'SUCCEEDED' ||
    !job.result ||
    !evaluated ||
    !matchesEvaluatedDesign(job, evaluated, lab.modelHash, evaluated.placements)
  )
    throw new GameDataError();
  const rain = lab.model.rainfall;
  const { baseline, strategy } = job.result;
  const count = rain.depthsMm.length;
  const start = Date.parse(rain.start),
    end = Date.parse(rain.end);
  if (
    !Array.isArray(baseline?.seriesM3s) ||
    !Array.isArray(strategy?.seriesM3s) ||
    rain.intervalSeconds !== 60 ||
    count < 2 ||
    count > 10080 ||
    !Number.isFinite(start) ||
    !Number.isFinite(end) ||
    end - start !== count * 60000 ||
    baseline.seriesM3s.length !== count ||
    strategy.seriesM3s.length !== count ||
    [rain.depthsMm, baseline.seriesM3s, strategy.seriesM3s].some((series) =>
      series.some((v) => !Number.isFinite(v) || v < 0)
    )
  )
    throw new GameDataError();
  let cumulativeRainMm = 0,
    maxRainMm = 0,
    maxFlowM3s = 0,
    rainPeakIndex = 0,
    flowPeakIndex = 0;
  const frames = rain.depthsMm.map((rainMm, index) => {
    cumulativeRainMm += rainMm;
    if (rainMm > maxRainMm) {
      maxRainMm = rainMm;
      rainPeakIndex = index;
    }
    if (baseline.seriesM3s[index] > baseline.seriesM3s[flowPeakIndex]) flowPeakIndex = index;
    maxFlowM3s = Math.max(maxFlowM3s, baseline.seriesM3s[index], strategy.seriesM3s[index]);
    // 구간 강우는 종료 시각에 표시하고 유량은 같은 SWMM 보고시각 값을 사용.
    return {
      index,
      time: start + (index + 1) * 60000,
      rainMm,
      cumulativeRainMm,
      baselineM3s: baseline.seriesM3s[index],
      designM3s: strategy.seriesM3s[index],
    };
  });
  if (!Number.isFinite(rain.totalDepthMm) || Math.abs(cumulativeRainMm - rain.totalDepthMm) > 0.001)
    throw new GameDataError();
  return {
    frames,
    firstWetIndex: Math.max(
      0,
      rain.depthsMm.findIndex((v) => v > 0)
    ),
    rainPeakIndex,
    flowPeakIndex,
    maxRainMm,
    maxFlowM3s,
  };
}

export function replayIndexAtTime(
  startIndex: number,
  elapsedMs: number,
  minutesPerSecond: number,
  count: number
) {
  return Math.min(
    count - 1,
    Math.max(0, startIndex + Math.floor((Math.max(0, elapsedMs) * minutesPerSecond) / 1000))
  );
}
