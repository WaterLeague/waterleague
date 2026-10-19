import { partBounds } from '../../../shared/repository/meshBounds';
import { ShapeUtils, Vector2, BufferGeometry, BufferAttribute } from 'three';
import { drapeTriangle, terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import type { GroundCandidate } from './candidateTilesService';
import type { Terrain } from '../../terrain/entity/terrain';
self.onmessage = ({ data }: { data: { rows: GroundCandidate[]; terrain: Terrain | null } }) => {
  try {
    const positions: number[] = [],
      masks: number[] = [],
      ends: number[] = [];
    for (const row of data.rows) {
      const rings = [row[3], ...(row[4] ?? [])].map((r) => {
        const p: Vector2[] = [];
        for (let i = 0; i < r.length - 2; i += 2) p.push(new Vector2(r[i], r[i + 1]));
        return p;
      });
      const points = rings.flat();
      for (const indices of ShapeUtils.triangulateShape(rings[0], rings.slice(1))) {
        const triangle = indices.map((i) => [points[i].x, points[i].y] as [number, number]) as [
          [number, number],
          [number, number],
          [number, number],
        ];
        drapeTriangle(triangle, data.terrain, (t) => {
          for (const p of t) {
            positions.push(p[0], terrainMeshHeight(data.terrain, p) + 0.014, -p[1]);
            masks.push(row[2]);
          }
        });
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
    self.postMessage(
      { positions: p, masks: m, ends, bounds, sphere },
      { transfer: [p.buffer, m.buffer, bounds.buffer] }
    );
  } catch {
    self.postMessage({ failed: true });
  }
};
