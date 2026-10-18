import { api } from '../../../shared/repository/apiClient';
import { publicSurfaceDto } from '../dto/publicSurfaceDto';
import { surfaceFrameDto } from '../dto/surfaceDto';
function query(bounds: number[], index = 0) {
  return new URLSearchParams({
    index: String(index),
    minX: String(bounds[0]),
    minY: String(bounds[1]),
    maxX: String(bounds[2]),
    maxY: String(bounds[3]),
  });
}
export async function loadPublicSurfaces(bounds: number[], signal: AbortSignal) {
  return publicSurfaceDto.parse(
    await api('/surface/current?' + query(bounds), 'GET', undefined, signal)
  );
}
export async function loadPublicSurfaceFrame(
  id: string,
  index: number,
  bounds: number[],
  signal: AbortSignal
) {
  if (!/^[a-f0-9-]{36}$/.test(id)) throw new Error('공개 계산 기록을 확인해 주세요.');
  return surfaceFrameDto.parse(
    await api(`/surface/current/${id}/frame?` + query(bounds, index), 'GET', undefined, signal)
  );
}
