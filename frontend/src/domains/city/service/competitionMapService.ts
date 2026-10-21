import type { City, CityTile } from '../entity/city';
import {
  clipLine,
  clipPolygons,
  mapScope,
  scopeContains,
  scopeIntersects,
  type MapScope,
} from '../../../shared/service/mapScope';
import type { TopographyTile } from '../../topography/dto/topographyDto';
export function competitionCity(city: City, ids: string[]): City {
  const allowed = new Set(ids),
    districts = city.districts.filter((d) => allowed.has(d.id));
  if (!districts.length) throw new Error('대회 지도 범위 없음');
  if (districts.length === city.districts.length) return city;
  const scope = mapScope(districts);
  return {
    ...city,
    districts,
    boundary: scope.polygons,
    bounds: scope.bounds,
    tiles: city.tiles.filter((t) => scopeIntersects(t.bounds, scope)),
    overviewBuildings: city.overviewBuildings.filter((b) => allowed.has(b.districtId)),
    surfaces: city.surfaces.flatMap((s) => {
      const polygons = clipPolygons(s.polygons, scope);
      return polygons.length ? [{ ...s, polygons }] : [];
    }),
  };
}
export function scopeCityTile(tile: CityTile, scope?: MapScope): CityTile {
  if (!scope) return tile;
  const allowed = new Set(scope.ids);
  const feature = (f: CityTile['nativeFeatures'][number]): CityTile['nativeFeatures'] => {
    const g = f.geometry;
    if (g.type === 'Polygon' || g.type === 'MultiPolygon') {
      const coordinates = clipPolygons(
        g.type === 'Polygon' ? [g.coordinates] : g.coordinates,
        scope
      );
      return coordinates.length
        ? [{ ...f, geometry: { type: 'MultiPolygon' as const, coordinates } }]
        : [];
    }
    const coordinates = (g.type === 'LineString' ? [g.coordinates] : g.coordinates).flatMap(
      (line) => clipLine(line, scope)
    );
    return coordinates.length
      ? [{ ...f, geometry: { type: 'MultiLineString' as const, coordinates } }]
      : [];
  };
  return {
    ...tile,
    buildings: tile.buildings.filter((b) => allowed.has(b.districtId)),
    nativeFeatures: tile.nativeFeatures.filter((f) => allowed.has(f.districtId)).flatMap(feature),
    urban: tile.urban
      ? {
          ...tile.urban,
          crosswalks: tile.urban.crosswalks.filter((v) => allowed.has(v.districtId)),
          walkPaths: tile.urban.walkPaths.filter((v) => allowed.has(v.districtId)),
          parkingLots: tile.urban.parkingLots.filter((v) => allowed.has(v.districtId)),
        }
      : undefined,
  };
}
export function scopeTopography(tile: TopographyTile, scope?: MapScope): TopographyTile {
  if (!scope) return tile;
  return {
    ...tile,
    points: tile.points.flatMap(([layer, id, points, label]) => {
      const selected = points.filter((p) => scopeContains(p, scope));
      return selected.length ? [[layer, id, selected, label]] : [];
    }),
    lines: tile.lines.flatMap(([layer, id, lines, label]) => {
      const selected = lines.flatMap((line) => clipLine(line, scope));
      return selected.length ? [[layer, id, selected, label]] : [];
    }),
    areas: tile.areas.flatMap(([layer, id, polygons, label]) => {
      const selected = clipPolygons(polygons, scope);
      return selected.length ? [[layer, id, selected, label]] : [];
    }),
  };
}
export function competitionOverview(city: City) {
  const [x, y, right, top] = city.bounds;
  return {
    center: [(x + right) / 2, (y + top) / 2] as [number, number],
    distance: Math.max(4800, Math.max(right - x, top - y) * 1.4),
  };
}
