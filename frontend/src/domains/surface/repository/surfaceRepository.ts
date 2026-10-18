import { api } from '../../../shared/repository/apiClient';
import { surfaceCatalogDto, surfaceFrameDto } from '../dto/surfaceDto';
import type { SurfaceSource } from '../entity/surface';
const prefixes = {
  historical: '/historical/',
  installation: '/installations/',
  'own-record': '/installations/records/',
  'research-record': '/research/installations/',
};
function path(source: SurfaceSource) {
  if (!/^[a-f0-9-]{36}$/.test(source.id)) throw new Error('계산 기록을 확인해 주세요.');
  return prefixes[source.kind] + source.id + '/surface/';
}
export async function loadSurfaceCatalog(source: SurfaceSource, signal: AbortSignal) {
  return surfaceCatalogDto.parse(await api(path(source) + 'catalog', 'GET', undefined, signal));
}
export async function loadSurfaceFrame(
  source: SurfaceSource,
  index: number,
  bounds: number[],
  signal: AbortSignal
) {
  const query = new URLSearchParams({
    index: String(index),
    minX: String(bounds[0]),
    minY: String(bounds[1]),
    maxX: String(bounds[2]),
    maxY: String(bounds[3]),
  });
  return surfaceFrameDto.parse(
    await api(path(source) + 'frame?' + query, 'GET', undefined, signal)
  );
}
