import { readPublicData } from '../../../shared/repository/publicDataCache';
import { topographyTileDto } from '../dto/topographyDto';
import { topographyGeometry } from './topographyGeometryService';
import type { TopographyIndex, TopographyEntry } from '../dto/topographyDto';
import type { Terrain } from '../../terrain/entity/terrain';
const requests = new Map<number, AbortController>(),
  terrains = new Map<number, Terrain | null>();
self.onmessage = async (
  event: MessageEvent<{
    id: number;
    cancel?: boolean;
    entry: TopographyEntry;
    layers: TopographyIndex['layers'];
    terrainKey: number;
    terrain?: Terrain | null;
    plan: boolean;
  }>
) => {
  const { id, cancel, entry, layers, terrainKey, terrain, plan } = event.data;
  if (cancel) {
    requests.get(id)?.abort();
    return;
  }
  const request = new AbortController();
  requests.set(id, request);
  try {
    if (terrain !== undefined) {
      terrains.clear();
      terrains.set(terrainKey, terrain);
    }
    if (!terrains.has(terrainKey)) throw new Error('지형 연결 누락');
    const raw = await readPublicData(
      '/data/seoul-features-v1/' + entry.file,
      entry.sha256,
      entry.bytes,
      request.signal,
      'topography'
    );
    const tile = topographyTileDto.parse(raw);
    if (
      tile.id !== entry.id ||
      tile.points.length !== entry.counts.points ||
      tile.lines.length !== entry.counts.lines ||
      tile.areas.length !== entry.counts.areas
    )
      throw new Error('지형지물 타일 대응 오류');
    request.signal.throwIfAborted();
    const data = topographyGeometry(tile, layers, terrains.get(terrainKey)!, plan, true);
    request.signal.throwIfAborted();
    const transfer = Object.values(data)
      .filter((value): value is Float32Array => value instanceof Float32Array)
      .map((value) => value.buffer);
    transfer.push(...data.models.map((model) => model.matrices.buffer));
    self.postMessage({ id, data }, { transfer });
  } catch {
    self.postMessage({ id, failed: true });
  } finally {
    requests.delete(id);
  }
};
