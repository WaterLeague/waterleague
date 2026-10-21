import { readNativeTransport } from '../../urban/repository/nativeTransportDataSource';
import { NativeGroundCuts } from '../../urban/service/nativeGroundCutService';
import { readPublicData } from '../../../shared/repository/publicDataCache';
import { topographyTileDto } from '../dto/topographyDto';
import { topographyGeometry } from './topographyGeometryService';
import type { TopographyIndex, TopographyEntry } from '../dto/topographyDto';
import type { Terrain } from '../../terrain/entity/terrain';
import { readNativeBridges } from '../../urban/repository/nativeBridgeDataSource';
import {
  bridgeTransportBindings,
  type NativeBridgeTransport,
} from '../../urban/service/nativeBridgeTransportService';
let transport: Promise<NativeBridgeTransport> | undefined;
function loadTransport() {
  // 교통 결속 자료는 작업 간 공유하고 개별 타일 취소로 다른 작업을 끊지 않는다.
  return (transport ??= Promise.all([
    readNativeBridges(new AbortController().signal),
    readNativeTransport(new AbortController().signal),
  ])
    .then(([groups, data]) => {
      const bindings = bridgeTransportBindings(groups);
      bindings.tunnelCuts = new NativeGroundCuts(
        [],
        data.tunnels.filter((t) => t.profiles.length).flatMap((t) => t.polygons)
      );
      return bindings;
    })
    .catch((error: unknown) => {
      transport = undefined;
      throw error;
    }));
}
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
    const bindings = plan ? undefined : await loadTransport();
    request.signal.throwIfAborted();
    const data = topographyGeometry(tile, layers, terrains.get(terrainKey)!, plan, true, bindings);
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
