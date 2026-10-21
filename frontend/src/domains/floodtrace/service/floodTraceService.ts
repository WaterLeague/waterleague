import { ShapeUtils, Vector2 } from 'three';
import {
  boundaryEdges,
  clipPolygons,
  polygonBounds,
  scopeContains,
  type MapScope,
  type Polygons,
} from '../../../shared/service/mapScope';
import type { TraceTile } from '../entity/floodTrace';
import type { TraceEvent } from '../entity/floodTrace';
import type { PlanView } from '../../city/service/planNavigationService';

export function visibleTraceTiles(event: TraceEvent | undefined, camera: PlanView) {
  const [x, y] = camera.center,
    radius = camera.distance * 1.5;
  return (
    event?.tiles.filter(
      ({ bounds: [x0, y0, x1, y1] }) =>
        x0 <= x + radius && x1 >= x - radius && y0 <= y + radius && y1 >= y - radius
    ) ?? []
  );
}
export const traceColor = '#9354c5';

export function scopeTraceTile(tile: TraceTile, scope?: MapScope): TraceTile {
  if (!scope) return tile;
  const triangleVertices: number[] = [],
    path: string[] = [];
  for (let i = 0; i < tile.triangleVertices.length; i += 6) {
    const v = tile.triangleVertices.slice(i, i + 6);
    const polygon: Polygons = [
      [
        [
          [v[0], v[1]],
          [v[2], v[3]],
          [v[4], v[5]],
          [v[0], v[1]],
        ],
      ],
    ];
    const bounds = polygonBounds(polygon);
    const pieces = boundaryEdges(bounds, scope).length
      ? clipPolygons(polygon, scope)
      : scopeContains(polygon[0][0][0], scope)
        ? polygon
        : [];
    for (const piece of pieces) {
      const rings = piece.map((r) => r.slice(0, -1).map((p) => new Vector2(...p)));
      const vertices = rings.flat();
      for (const face of ShapeUtils.triangulateShape(rings[0], rings.slice(1)))
        for (const index of face) triangleVertices.push(vertices[index].x, vertices[index].y);
      for (const ring of piece) path.push('M' + ring.map(([x, y]) => x + ',' + -y).join('L') + 'Z');
    }
  }
  return { ...tile, triangleVertices, path: path.join('') };
}
