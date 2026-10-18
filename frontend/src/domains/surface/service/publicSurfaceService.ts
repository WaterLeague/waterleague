import type { PublicSurfaceCurrent } from '../dto/publicSurfaceDto';
import type { SurfaceFrame } from '../entity/surface';
import { assertSurfaceBinding, liveSurfaceFrameIndex } from './surfaceService';
export type PublicFrame = { id: string; basinId: string; name: string; frame: SurfaceFrame };
export function bindPublicFrame(
  run: PublicSurfaceCurrent['runs'][number],
  frame: SurfaceFrame,
  now: number
) {
  const index = liveSurfaceFrameIndex(run.catalog, now);
  if (index === null) throw new Error('최근 5분 이내 공개 계산 결과가 없습니다.');
  return {
    id: run.id,
    basinId: run.basinId,
    name: run.name,
    frame: assertSurfaceBinding(run.catalog, frame, index),
  };
}
export function currentPublicFrames(
  current: PublicSurfaceCurrent | null,
  frames: PublicFrame[],
  now: number
) {
  if (!current) return [];
  const sources = new Map(current.runs.map((run) => [run.id, run]));
  return frames.filter((value) => {
    const source = sources.get(value.id);
    return (
      !!source &&
      source.basinId === value.basinId &&
      source.catalog.catalogSha256 === value.frame.catalogSha256 &&
      liveSurfaceFrameIndex(source.catalog, now) === value.frame.index
    );
  });
}
