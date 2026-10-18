import type { PlaybackCatalog, PlaybackFrame } from '../dto/playbackDto';
export function requirePlaybackBinding(
  catalog: PlaybackCatalog,
  frame: PlaybackFrame,
  requested: number
) {
  if (
    frame.jobId !== catalog.jobId ||
    frame.inputHash !== catalog.inputHash ||
    frame.requestedTimeSeconds !== requested ||
    requested > catalog.timesSeconds[catalog.timesSeconds.length - 1] ||
    frame.cases.some((c) => {
      const source = catalog.sources.find((s) => s.id === c.id);
      return (
        !source ||
        source.framesSha256 !== c.framesSha256 ||
        source.resultSha256 !== c.resultSha256 ||
        source.numericalStatus !== c.numericalStatus
      );
    })
  )
    throw new Error('관망 재생 입력·시각 불일치');
  return frame;
}
export const recordedFlowPoints = (points: number[][], flow: number) =>
  flow < 0 ? [...points].reverse() : points;
export const playbackDepthColor = (depth: number, scale: number) =>
  depth <= 0
    ? '#cbd5e1'
    : `hsl(208 64% ${87 - 53 * Math.min(1, Math.max(0, depth / (scale || 1)))}%)`;
