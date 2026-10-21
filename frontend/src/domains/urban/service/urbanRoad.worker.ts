import type { MapScope } from '../../../shared/service/mapScope';
import { competitionStreets } from './competitionStreetService';
import { railServices } from './railLifeService';
import { streetPath } from './streetLifeService';
import type { Street } from '../entity/urban';
import { readNativeBridges } from '../repository/nativeBridgeDataSource';
import { readNativeTransport } from '../repository/nativeTransportDataSource';
import { UrbanRoadBuilder, type UrbanRoadTile } from './urbanRoadService';

let loading: Promise<UrbanRoadBuilder> | undefined;
const tileCache = new Map<string, UrbanRoadTile>();
let tiles: UrbanRoadTile[] = [],
  latest = 0,
  sentRoads: Street[] | undefined,
  sentRail = false;
self.onmessage = async (
  event: MessageEvent<{
    id: number;
    tiles?: UrbanRoadTile[];
    tileIds?: string[];
    center: [number, number];
    distance: number;
    scope?: MapScope;
  }>
) => {
  const { id, center, distance, scope } = event.data;
  latest = id;
  try {
    if (event.data.tileIds) {
      for (const tile of event.data.tiles ?? []) tileCache.set(tile.id, tile);
      tiles = event.data.tileIds.map((id) => {
        const tile = tileCache.get(id);
        if (!tile) throw new Error('도로 타일 연결 누락');
        return tile;
      });
      const wanted = new Set(event.data.tileIds);
      for (const id of tileCache.keys()) if (!wanted.has(id)) tileCache.delete(id);
    }
    const builder = await (loading ??= Promise.all([
      readNativeBridges(new AbortController().signal),
      readNativeTransport(new AbortController().signal),
    ])
      .then(([groups, transport]) => new UrbanRoadBuilder(groups, transport))
      .catch((error: unknown) => {
        loading = undefined;
        throw error;
      }));
    if (latest !== id) return;
    const roads = builder.build(tiles, center, distance);
    self.postMessage({
      id,
      ...(roads !== sentRoads ? { roads: competitionStreets(roads, scope) } : {}),
      ...(!sentRail
        ? {
            railTraffic: competitionStreets(builder.railTraffic, scope),
            railServices: scope
              ? railServices(competitionStreets(builder.railTraffic, scope).map(streetPath))
              : builder.railServices,
          }
        : {}),
    });
    sentRoads = roads;
    sentRail = true;
  } catch {
    if (latest === id) self.postMessage({ id, failed: true });
  }
};
