export interface StormFrame {
  index: number;
  time: number;
  rainMm: number;
  cumulativeRainMm: number;
  baselineM3s: number;
  designM3s: number;
}
export interface StormReplayData {
  frames: StormFrame[];
  firstWetIndex: number;
  rainPeakIndex: number;
  flowPeakIndex: number;
  maxRainMm: number;
  maxFlowM3s: number;
}
