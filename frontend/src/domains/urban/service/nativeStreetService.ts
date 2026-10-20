import type { CityTile } from '../../city/entity/city';
import type { Street } from '../entity/urban';
export function nativeSurfaceColor(role: string) {
  return role === 'SIDEWALK_AREA'
    ? '#b3ae9f'
    : role === 'CULTIVATION_LANDSCAPE_AREA'
      ? '#98aa8b'
      : role === 'BRIDGE_AREA' || role === 'TUNNEL_AREA'
        ? '#99a7a6'
        : role === 'RAILWAY_AREA'
          ? '#8b9292'
          : '#667071';
}
export function nativeStreets(tiles: CityTile[]): Street[] {
  const result: Street[] = [];
  for (const tile of tiles)
    for (const feature of tile.nativeFeatures) {
      if (['RIVER_WATER_AREA', 'LAKE_RESERVOIR_AREA', 'RAIL_CENTERLINE'].includes(feature.role))
        continue;
      const base = {
        id: feature.id,
        class: feature.roadClass ?? feature.role,
        districtId: feature.districtId,
        widthM: 0,
        widthSource: 'NOT_CONFIRMED' as const,
        walk: false,
        motor: false,
        oneway: 0,
        sidewalk: '',
        bridge: false,
        nativeSourceRole: feature.role,
      };
      const geometry = feature.geometry;
      if (geometry.type === 'Polygon' || geometry.type === 'MultiPolygon') {
        const polygons =
          geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
        result.push({ ...base, coordinates: polygons[0][0], nativePolygons: polygons });
      } else if (feature.role === 'ROAD_CENTERLINE') {
        const parts =
          geometry.type === 'LineString' ? [geometry.coordinates] : geometry.coordinates;
        for (let index = 0; index < parts.length; index++)
          result.push({
            ...base,
            id: feature.id + ':part:' + index,
            coordinates: parts[index],
            motor:
              feature.trafficDirection === 'BIDIRECTIONAL' &&
              feature.geometryEligibility === 'GEOMETRY_ONLY',
            nativeTrafficDirection: feature.trafficDirection ?? 'UNKNOWN',
          });
      }
    }
  return result;
}
