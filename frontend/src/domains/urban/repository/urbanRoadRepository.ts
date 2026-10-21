import type { MapScope } from '../../../shared/service/mapScope';
import type { CityTile } from '../../city/entity/city';
import type { Street } from '../entity/urban';
import type { RailService } from '../service/railLifeService';
export type UrbanRoads = { roads: Street[]; railTraffic: Street[]; railServices: RailService[] };

export class UrbanRoadSession {
  private worker: Worker | null = null;
  private sequence = 0;
  private tiles?: CityTile[];
  private tileCache = new Map<string, CityTile>();
  private data: UrbanRoads = { roads: [], railTraffic: [], railServices: [] };
  private disposed = false;

  constructor(
    private readonly receive: (data: UrbanRoads) => void,
    private readonly failed: () => void
  ) {}

  update(tiles: CityTile[], center: [number, number], distance: number, scope?: MapScope) {
    if (this.disposed) return;
    try {
      if (!this.worker) {
        const worker = new Worker(new URL('../service/urbanRoad.worker.ts', import.meta.url), {
          type: 'module',
        });
        this.worker = worker;
        worker.onmessage = (
          event: MessageEvent<Partial<UrbanRoads> & { id: number; failed?: boolean }>
        ) => {
          if (this.worker !== worker) return;
          const value = event.data;
          // 이전 응답의 공유 자료도 보관하되 화면에는 최신 시야만 적용한다.
          if (value.roads || value.railTraffic || value.railServices)
            this.data = {
              roads: value.roads ?? this.data.roads,
              railTraffic: value.railTraffic ?? this.data.railTraffic,
              railServices: value.railServices ?? this.data.railServices,
            };
          if (value.id !== this.sequence) return;
          if (value.failed) this.failed();
          else this.receive(this.data);
        };
        worker.onerror = worker.onmessageerror = () => {
          if (this.worker !== worker) return;
          this.stop();
          this.failed();
        };
      }
      this.worker.postMessage({
        id: ++this.sequence,
        center,
        distance,
        scope,
        ...(tiles !== this.tiles
          ? {
              tileIds: tiles.map((tile) => tile.id),
              tiles: tiles
                .filter((tile) => this.tileCache.get(tile.id) !== tile)
                .map(({ id, nativeFeatures, urban }) => ({ id, nativeFeatures, urban })),
            }
          : {}),
      });
      this.tiles = tiles;
      this.tileCache = new Map(tiles.map((tile) => [tile.id, tile]));
    } catch {
      this.stop();
      this.failed();
    }
  }

  private stop() {
    this.worker?.terminate();
    this.worker = null;
    this.tiles = undefined;
    this.tileCache.clear();
  }
  dispose() {
    this.disposed = true;
    this.stop();
  }
}
