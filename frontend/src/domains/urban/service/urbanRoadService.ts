import type { CityTile } from '../../city/entity/city';
import type { NativeBridgeGroup } from '../dto/nativeBridgeDto';
import type { NativeTransport } from '../dto/nativeTransportDto';
import type { Street } from '../entity/urban';
import { railServices, type RailService } from './railLifeService';
import { streetPath } from './streetLifeService';
import { nativeStreets } from './nativeStreetService';
import { nativeRailStreets } from './nativeTransportService';
import { attachNativeTunnels, nativeTunnelStreets } from './nativeTunnelService';

export type UrbanRoadTile = Pick<CityTile, 'id' | 'nativeFeatures' | 'urban'>;
export class UrbanRoadBuilder {
  private readonly lanes: Map<string, number>;
  private readonly widths: Map<string, number>;
  private readonly railways: Street[];
  readonly railTraffic: Street[];
  readonly railServices: RailService[];
  private tiles?: UrbanRoadTile[];
  private selection = '';
  private roads: Street[] = [];

  constructor(
    private readonly bridges: NativeBridgeGroup[],
    private readonly transport: NativeTransport
  ) {
    this.lanes = new Map(transport.lanes.map(([id, count]) => [id, count]));
    this.widths = new Map(transport.lanes.filter((r) => r[2]).map(([id, , width]) => [id, width!]));
    this.railways = nativeRailStreets(transport, bridges);
    this.railTraffic = [
      ...this.railways,
      ...nativeStreets(
        [],
        bridges.filter((g) => g.lowerDeck?.rail)
      ).filter((r) => r.nativeRailKind),
    ];
    this.railServices = railServices(this.railTraffic.map(streetPath));
  }

  build(tiles: UrbanRoadTile[], center: [number, number], distance: number) {
    const radius = Math.max(750, distance * 0.85);
    const visible = this.bridges.filter(
      (g) =>
        g.bounds[0] <= center[0] + radius &&
        g.bounds[2] >= center[0] - radius &&
        g.bounds[1] <= center[1] + radius &&
        g.bounds[3] >= center[1] - radius
    );
    const nearRail = this.railways.filter((r) =>
      r.coordinates.some((p, i) => {
        const a = r.coordinates[Math.max(0, i - 1)];
        return (
          Math.min(a[0], p[0]) <= center[0] + radius &&
          Math.max(a[0], p[0]) >= center[0] - radius &&
          Math.min(a[1], p[1]) <= center[1] + radius &&
          Math.max(a[1], p[1]) >= center[1] - radius
        );
      })
    );
    const tunnels = this.transport.tunnels.filter((t) =>
      t.polygons.some((p) =>
        p[0].some((q) => Math.hypot(q[0] - center[0], q[1] - center[1]) < Math.max(2000, distance))
      )
    );
    const selection = JSON.stringify([
      visible.map((g) => g.id),
      nearRail.map((r) => r.id),
      tunnels.map((t) => t.id),
    ]);
    // 같은 표시 대상이면 연결 그래프와 이동체 경로의 객체를 그대로 유지한다.
    if (this.tiles === tiles && this.selection === selection) return this.roads;
    this.roads = [
      ...attachNativeTunnels(
        [...nativeStreets(tiles, visible, this.lanes, this.widths), ...nearRail],
        tunnels
      ),
      ...nativeTunnelStreets(tunnels),
    ];
    this.tiles = tiles;
    this.selection = selection;
    return this.roads;
  }
}
