import { Box3, Matrix4, Mesh, Ray } from 'three';
import type { BuildingMeshData } from './buildingGeometryService';

export function buildingRaycast(data: Pick<BuildingMeshData, 'bounds' | 'ends'>): Mesh['raycast'] {
  const inverse = new Matrix4(),
    ray = new Ray(),
    box = new Box3();
  return function (this: Mesh, raycaster, intersections) {
    const geometry = this.geometry;
    const originalStart = geometry.drawRange.start,
      originalCount = geometry.drawRange.count;
    const originalEnd = originalStart + originalCount;
    inverse.copy(this.matrixWorld).invert();
    ray.copy(raycaster.ray).applyMatrix4(inverse);
    try {
      // 원 건물 경계 상자와 교차한 면만 검사하며 면 번호·구멍·높이 판정은 Three.js에 유지한다.
      for (let i = 0; i < data.ends.length; i++) {
        const start = Math.max(originalStart, i ? data.ends[i - 1] * 3 : 0);
        const end = Math.min(originalEnd, data.ends[i] * 3);
        if (start >= end) continue;
        box.min.fromArray(data.bounds, i * 6);
        box.max.fromArray(data.bounds, i * 6 + 3);
        if (!ray.intersectsBox(box)) continue;
        geometry.setDrawRange(start, end - start);
        Mesh.prototype.raycast.call(this, raycaster, intersections);
      }
    } finally {
      geometry.setDrawRange(originalStart, originalCount);
    }
  };
}
