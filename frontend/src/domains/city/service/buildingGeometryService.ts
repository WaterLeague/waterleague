import { ExtrudeGeometry } from 'three';
import type { CityBuilding } from '../entity/city';
import { polygonShapes } from '../../catalog/service/mapGeometryService';

export type BuildingMeshData = {
  positions: Float32Array;
  normals: Float32Array;
  bounds: Float32Array;
  ends: number[];
};
export function buildBuildingMesh(buildings: CityBuilding[]): BuildingMeshData {
  const parts: { positions: Float32Array; normals: Float32Array }[] = [];
  const ends: number[] = [];
  const bounds = new Float32Array(buildings.length * 6);
  let length = 0;
  for (const b of buildings) {
    const geometry = new ExtrudeGeometry(polygonShapes(b.polygons), {
      depth: b.heightM,
      bevelEnabled: false,
      steps: 1,
    });
    const positions = geometry.getAttribute('position').array as Float32Array;
    if (b.baseElevationM)
      for (let i = 2; i < positions.length; i += 3) positions[i] += b.baseElevationM;
    geometry.computeBoundingBox();
    const box = geometry.boundingBox!;
    bounds.set([...box.min.toArray(), ...box.max.toArray()], ends.length * 6);
    const normals = geometry.getAttribute('normal').array as Float32Array;
    parts.push({ positions, normals });
    length += positions.length;
    ends.push(length / 9);
    geometry.dispose();
  }
  const positions = new Float32Array(length),
    normals = new Float32Array(length);
  let offset = 0;
  for (const part of parts) {
    positions.set(part.positions, offset);
    normals.set(part.normals, offset);
    offset += part.positions.length;
  }
  return { positions, normals, bounds, ends };
}
