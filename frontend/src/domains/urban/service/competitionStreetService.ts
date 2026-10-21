import {
  clipLine,
  clipPolygons,
  type MapScope,
  type Point,
} from '../../../shared/service/mapScope';
import type { Street } from '../entity/urban';
function distanceAlong(point: Point, coordinates: Point[]) {
  let nearest = Infinity,
    walked = 0,
    along = 0;
  for (let i = 1; i < coordinates.length; i++) {
    const a = coordinates[i - 1],
      b = coordinates[i],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      length = Math.hypot(dx, dy);
    const t = Math.max(
      0,
      Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (length * length || 1))
    );
    const distance = Math.hypot(point[0] - a[0] - dx * t, point[1] - a[1] - dy * t);
    if (distance < nearest) {
      nearest = distance;
      along = walked + t * length;
    }
    walked += length;
  }
  return along;
}
function clipPath<T extends { coordinates: Point[]; span: [number, number] }>(
  path: T,
  scope: MapScope
): T[] {
  return clipLine(path.coordinates, scope).flatMap((coordinates) => {
    const start = distanceAlong(coordinates[0], path.coordinates),
      end = distanceAlong(coordinates.at(-1)!, path.coordinates);
    const span: [number, number] = [
      Math.max(0, path.span[0] - start),
      Math.min(end - start, path.span[1] - start),
    ];
    return span[1] > span[0] ? [{ ...path, coordinates, span }] : [];
  });
}
function elevationAt(point: Point, road: Street) {
  const along = distanceAlong(point, road.coordinates);
  let walked = 0;
  for (let i = 1; i < road.coordinates.length; i++) {
    const a = road.coordinates[i - 1],
      b = road.coordinates[i],
      length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (walked + length >= along)
      return (
        road.elevationsM![i - 1] +
        (road.elevationsM![i] - road.elevationsM![i - 1]) *
          Math.max(0, Math.min(1, (along - walked) / (length || 1)))
      );
    walked += length;
  }
  return road.elevationsM!.at(-1)!;
}
// 경계에서 자른 표시 경로에도 원 높이 프로필을 보존한다.
export function competitionStreets(roads: Street[], scope?: MapScope): Street[] {
  if (!scope) return roads;
  return roads.flatMap((road) => {
    const segments = clipLine(road.coordinates, scope);
    if (!segments.length) return [];
    const surface = { ...road };
    for (const key of [
      'nativePolygons',
      'nativeMarkingPolygons',
      'nativeLaneClipPolygons',
      'nativeGroundCutPolygons',
      'nativeUnderpassPolygons',
      'nativeBridgeGroupPolygons',
      'nativeJunctionPolygons',
      'walkPolygons',
    ] as const) {
      if (road[key]) surface[key] = clipPolygons(road[key], scope);
    }
    surface.nativeRailPaths = road.nativeRailPaths?.flatMap((line) => clipLine(line, scope));
    surface.nativeWaterDecks = road.nativeWaterDecks?.map((d) => ({
      ...d,
      polygons: clipPolygons(d.polygons, scope),
      waterPolygons: clipPolygons(d.waterPolygons, scope),
      deckPolygons: clipPolygons(d.deckPolygons, scope),
    }));
    surface.nativeWalkingDecks = road.nativeWalkingDecks?.map((d) => ({
      ...d,
      polygons: clipPolygons(d.polygons, scope),
      deckPolygons: clipPolygons(d.deckPolygons, scope),
    }));
    surface.nativeTunnels = road.nativeTunnels?.map((t) => ({
      ...t,
      polygons: clipPolygons(t.polygons, scope),
    }));
    surface.nativeLanePaths = road.nativeLanePaths?.flatMap((p) => clipPath(p, scope));
    surface.nativeStructurePath = road.nativeStructurePath
      ? clipPath(road.nativeStructurePath, scope)[0]
      : undefined;
    return segments.map((coordinates, i) => ({
      ...surface,
      id: road.id + ':scope:' + i,
      coordinates,
      elevationsM: road.elevationsM ? coordinates.map((p) => elevationAt(p, road)) : undefined,
    }));
  });
}
