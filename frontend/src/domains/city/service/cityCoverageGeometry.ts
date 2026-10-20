import { BufferGeometry, Float32BufferAttribute, ShapeGeometry } from 'three';
import type { CityCoverageArea } from '../repository/cityCoverageRepository';
import { polygonShapes } from '../../catalog/service/mapGeometryService';
import type { Terrain } from '../../terrain/entity/terrain';
import { drapeTriangle, terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
export function cityCoverageGeometry(areas: CityCoverageArea[], terrain: Terrain | null) {
  const positions: number[] = [];
  for (const area of areas) {
    const flat = new ShapeGeometry(polygonShapes(area.polygons));
    const vertices = flat.getAttribute('position'),
      indices = flat.getIndex();
    if (indices)
      for (let i = 0; i < indices.count; i += 3) {
        const triangle = [0, 1, 2].map((j) => {
          const k = indices.getX(i + j);
          return [vertices.getX(k), vertices.getY(k)] as [number, number];
        }) as [[number, number], [number, number], [number, number]];
        drapeTriangle(triangle, terrain, (piece) => {
          for (const p of piece) positions.push(p[0], terrainMeshHeight(terrain, p) + 0.6, -p[1]);
        });
      }
    flat.dispose();
  }
  const result = new BufferGeometry();
  result.setAttribute('position', new Float32BufferAttribute(positions, 3));
  result.computeBoundingSphere();
  return result;
}
