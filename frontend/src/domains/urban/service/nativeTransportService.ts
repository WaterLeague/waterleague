import type { NativeTransport } from '../dto/nativeTransportDto';
import type { NativeBridgeGroup } from '../dto/nativeBridgeDto';
import type { Street } from '../entity/urban';
import { bridgeTransportBindings } from './nativeBridgeTransportService';
export function nativeRailStreets(
  data: NativeTransport | undefined,
  groups: NativeBridgeGroup[] | undefined
): Street[] {
  if (!data) return [];
  const bindings = bridgeTransportBindings(groups ?? []);
  return data.routes.map((route) => ({
    id: 'rail:' + route.id,
    class: 'railway',
    districtId: '',
    widthM: 0,
    widthSource: 'NOT_CONFIRMED',
    walk: false,
    motor: false,
    oneway: 0,
    sidewalk: '',
    bridge: false,
    coordinates: route.coordinates,
    nativeGroundCutPolygons: groups?.[0]?.displayWaterPolygons,
    nativeRailKind: route.kind,
    nativeRailName: route.name,
    nativeSourceRole: 'RAIL_DISPLAY_PATH',
    nativeBridgeProfiles: [...new Set(route.sourceFids.flatMap((fid) => bindings.get(fid) ?? []))],
  }));
}
