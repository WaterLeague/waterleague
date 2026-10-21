import { BufferAttribute, BufferGeometry } from 'three';
import type { Terrain } from '../entity/terrain';

type MeshData = { positions: Float32Array; normals: Float32Array; indices: Uint32Array };
const cache = new WeakMap<Terrain, MeshData>();

export function terrainMeshData(terrain: Terrain): MeshData {
  const found = cache.get(terrain);
  if (found) return found;
  const count = terrain.width * terrain.height;
  const positions = new Float32Array(count * 3),
    indices: number[] = [];
  for (let i = 0; i < count; i++) {
    positions.set(
      [
        terrain.origin[0] + (i % terrain.width) * terrain.spacing[0],
        terrain.heights[i],
        -(terrain.origin[1] + Math.floor(i / terrain.width) * terrain.spacing[1]),
      ],
      i * 3
    );
    if (
      i % terrain.width < terrain.width - 1 &&
      Math.floor(i / terrain.width) < terrain.height - 1
    ) {
      const b = i + 1,
        c = i + terrain.width,
        d = c + 1;
      if (
        terrain.districts[i] ||
        terrain.districts[b] ||
        terrain.districts[c] ||
        terrain.districts[d]
      )
        indices.push(i, c, b, b, c, d);
    }
  }
  const geometry = new BufferGeometry();
  const index = new Uint32Array(indices);
  geometry.setAttribute('position', new BufferAttribute(positions, 3));
  geometry.setIndex(new BufferAttribute(index, 1));
  geometry.computeVertexNormals();
  const value = {
    positions,
    normals: geometry.getAttribute('normal').array as Float32Array,
    indices: index,
  };
  geometry.dispose();
  cache.set(terrain, value);
  return value;
}

export function createTerrainGeometry(terrain: Terrain, districtIds?: string[]): BufferGeometry {
  const data = terrainMeshData(terrain);
  const geometry = new BufferGeometry();
  // 불변 좌표·법선만 재사용하고 색상·GPU 속성은 장면마다 소유하여 해제 충돌을 막는다.
  geometry.setAttribute('position', new BufferAttribute(data.positions, 3));
  geometry.setAttribute('normal', new BufferAttribute(data.normals, 3));
  let indices = data.indices;
  if (districtIds && districtIds.length < terrain.districtIds.length) {
    const allowed = new Set(
      districtIds.map((id) => terrain.districtIds.indexOf(id) + 1).filter((i) => i > 0)
    );
    const selected: number[] = [];
    for (let i = 0; i < indices.length; i += 3) {
      const triangle = [indices[i], indices[i + 1], indices[i + 2]];
      if (triangle.every((v) => allowed.has(terrain.districts[v]))) selected.push(...triangle);
    }
    indices = new Uint32Array(selected);
  }
  geometry.setIndex(new BufferAttribute(indices, 1));
  geometry.setAttribute(
    'color',
    new BufferAttribute(new Float32Array(terrain.width * terrain.height * 4), 4)
  );
  geometry.computeBoundingSphere();
  return geometry;
}
