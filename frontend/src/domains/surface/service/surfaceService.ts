import type { SurfaceCatalog, SurfaceFrame, SurfaceMetric } from '../entity/surface';
import type { PlanView } from '../../city/service/planNavigationService';
export function surfaceFrameIndex(catalog: SurfaceCatalog, at: string | null) {
  if (at === null) return catalog.timesSeconds.length - 1;
  const seconds = (Date.parse(at) - Date.parse(catalog.startUtc)) / 1000;
  const times = catalog.timesSeconds,
    last = times[times.length - 1];
  const tolerance = 8 * Number.EPSILON * Math.max(1, Math.abs(last));
  if (!Number.isFinite(seconds) || seconds < -tolerance || seconds > last + tolerance) return null;
  let low = 0,
    high = times.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (times[mid] <= seconds + 8 * Number.EPSILON * Math.max(1, Math.abs(times[mid])))
      low = mid + 1;
    else high = mid;
  }
  return Math.max(0, low - 1);
}
export function liveSurfaceFrameIndex(catalog: SurfaceCatalog, now: number) {
  const start = Date.parse(catalog.startUtc);
  if (!Number.isFinite(now) || !Number.isFinite(start)) return null;
  for (let i = catalog.timesSeconds.length - 1; i >= 0; i--) {
    const age = now - (start + catalog.timesSeconds[i] * 1000);
    if (age >= 0) return age <= 300000 ? i : null;
  }
  return null;
}
export function surfaceBounds(camera: PlanView) {
  const radius = Math.ceil((camera.distance * 3) / 250) * 250;
  return [
    Math.max(-60000, Math.floor(camera.center[0] / 250) * 250 - radius),
    Math.max(-60000, Math.floor(camera.center[1] / 250) * 250 - radius),
    Math.min(60000, Math.ceil(camera.center[0] / 250) * 250 + radius),
    Math.min(60000, Math.ceil(camera.center[1] / 250) * 250 + radius),
  ];
}
export function assertSurfaceBinding(catalog: SurfaceCatalog, frame: SurfaceFrame, index: number) {
  if (
    frame.catalogSha256 !== catalog.catalogSha256 ||
    frame.index !== index ||
    frame.timeSeconds !== catalog.timesSeconds[index] ||
    frame.cells.some(
      (c) =>
        c.triangleId >= catalog.triangleCount ||
        (catalog.schemaVersion === 2 ? c.flowDirection === undefined : !!c.flowDirection)
    )
  )
    throw new Error('계산 결과가 변경되었습니다. 다시 불러와 주세요.');
  return frame;
}
export const depthSteps = [0.1, 0.3, 0.5, 1, 2];
export const speedSteps = [0.1, 0.3, 0.5, 1, 2];
export const surfacePalette = ['#bfdbfe', '#7dd3fc', '#38bdf8', '#0284c7', '#075985', '#172554'];
export function surfaceColor(cell: SurfaceFrame['cells'][number], metric: SurfaceMetric) {
  const value = metric === 'depth' ? cell.depthM : cell.speedMps;
  const index = (metric === 'depth' ? depthSteps : speedSteps).findIndex(
    (threshold) => value < threshold
  );
  return surfacePalette[index < 0 ? surfacePalette.length - 1 : index];
}
