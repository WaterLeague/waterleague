import { partBounds } from '../../../shared/repository/meshBounds';
import { ShapeUtils, Vector2, BufferGeometry, BufferAttribute } from 'three';
import { drapeTriangle, terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import type { GroundCandidate } from './candidateTilesService';
import { candidateSurfaceLift } from './candidateTilesService';
import type { Terrain } from '../../terrain/entity/terrain';
export function candidateGeometry(rows: GroundCandidate[], terrain: Terrain | null) {
  const positions: number[] = [],
    masks: number[] = [],
    ends: number[] = [];
  for (const row of rows) {
    for (const component of row[3]) {
      const rings = component.map((ring) => ring.slice(0, -1).map(([x, y]) => new Vector2(x, y)));
      const points = rings.flat();
      for (const indices of ShapeUtils.triangulateShape(rings[0], rings.slice(1))) {
        const triangle = indices.map((i) => [points[i].x, points[i].y] as [number, number]) as [
          [number, number],
          [number, number],
          [number, number],
        ];
        drapeTriangle(triangle, terrain, (t) => {
          for (const p of t) {
            positions.push(p[0], terrainMeshHeight(terrain, p) + candidateSurfaceLift, -p[1]);
            masks.push(row[2]);
          }
        });
      }
    }
    ends.push(positions.length / 9);
  }
  const p = new Float32Array(positions),
    m = new Float32Array(masks);
  const bounds = partBounds(p, ends),
    geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(p, 3));
  geometry.computeBoundingSphere();
  const sphere = [...geometry.boundingSphere!.center.toArray(), geometry.boundingSphere!.radius];
  geometry.dispose();
  return { positions: p, masks: m, ends, bounds, sphere };
}
