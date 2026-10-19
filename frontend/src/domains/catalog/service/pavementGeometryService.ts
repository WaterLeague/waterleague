import { BufferGeometry, Float32BufferAttribute } from 'three';
import type { Terrain } from '../../terrain/entity/terrain';
import {
  drapeSegment,
  drapeTriangle,
  terrainMeshHeight,
} from '../../terrain/service/terrainDrapeService';
import type { FacilityFootprint } from '../entity/facilityFootprint';

export function pavementGeometry(
  footprint: FacilityFootprint,
  terrain: Terrain | null,
  lift = 0.014
) {
  const positions: number[] = [],
    uv: number[] = [],
    lines: number[] = [];
  for (const polygon of footprint.polygons) {
    for (let i = 1; i + 1 < polygon.length; i++) {
      drapeTriangle([polygon[0], polygon[i], polygon[i + 1]], terrain, (triangle) => {
        for (const point of triangle) {
          positions.push(point[0], terrainMeshHeight(terrain, point) + lift, -point[1]);
          uv.push(point[0] / 2, point[1] / 2);
        }
      });
    }
  }
  for (const [a, b] of footprint.boundary)
    for (const segment of drapeSegment(a, b, terrain))
      for (const point of segment)
        lines.push(point[0], terrainMeshHeight(terrain, point) + lift + 0.0005, -point[1]);
  const surface = new BufferGeometry();
  surface.setAttribute('position', new Float32BufferAttribute(positions, 3));
  surface.setAttribute('uv', new Float32BufferAttribute(uv, 2));
  surface.computeVertexNormals();
  const outline = new BufferGeometry();
  outline.setAttribute('position', new Float32BufferAttribute(lines, 3));
  return { surface, outline, sides: new BufferGeometry() };
}
