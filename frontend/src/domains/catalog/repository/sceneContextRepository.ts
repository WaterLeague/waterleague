import { sceneContextDto } from '../dto/sceneContextDto';
import type { CandidateMap } from '../entity/catalog';
import type { SceneContext } from '../entity/sceneContext';
import { CatalogError } from '../exception/CatalogError';

const cache = new Map<string, SceneContext>();
function requireMap(context: SceneContext, map: CandidateMap) {
  const source = map.contextSource;
  if (
    !source ||
    context.mapId !== map.snapshot.id ||
    context.baseMapSha256 !== source.baseMapSha256 ||
    context.sourceSha256 !== map.snapshot.sourceHash ||
    context.widthM !== map.snapshot.widthM ||
    context.depthM !== map.snapshot.depthM ||
    !map.snapshot.originProjected ||
    context.originProjected.some((v, i) => v !== map.snapshot.originProjected![i])
  )
    throw new CatalogError('INVALID_DATA');
  return context;
}
export async function loadSceneContext(
  map: CandidateMap,
  signal: AbortSignal
): Promise<SceneContext | null> {
  const source = map.contextSource;
  if (!source) return null;
  const cached = cache.get(source.sha256);
  if (cached) {
    requireMap(cached, map);
    cache.delete(source.sha256);
    cache.set(source.sha256, cached);
    return cached;
  }
  try {
    const response = await fetch('/data/' + source.file, { signal, credentials: 'same-origin' });
    if (!response.ok) throw new CatalogError('NETWORK');
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength !== source.bytes || bytes.byteLength > 2 * 1024 * 1024)
      throw new CatalogError('INVALID_DATA');
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
    if (hash !== source.sha256) throw new CatalogError('INVALID_DATA');
    const context = requireMap(
      sceneContextDto.parse(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes))),
      map
    );
    if (!signal.aborted) {
      cache.set(source.sha256, context);
      while (cache.size > 10) cache.delete(cache.keys().next().value!);
    }
    return context;
  } catch (error) {
    if (signal.aborted || error instanceof CatalogError) throw error;
    throw new CatalogError('INVALID_DATA');
  }
}
